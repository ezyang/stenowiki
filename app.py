import os
import sys
import re
import datetime

import bleach
import markdown
import markdown.extensions
from markdown.util import etree

import flask
from flask import Flask, render_template, redirect, url_for, request
import flask_wtf
import flask_wtf.csrf
import wtforms
import flask_login
from werkzeug.security import generate_password_hash, check_password_hash

from jinja2 import Markup

import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.ext.declarative

_root_dir = os.path.dirname(__file__)
sys.path.insert(0, _root_dir)
sys.path.insert(0, os.path.join(_root_dir, "plover"))

from stenowiki import steno, sound
# NB: versioned doesn't work with flask-sqlalchemy
# see https://github.com/mitsuhiko/flask-sqlalchemy/issues/182
# so we do it manually
from stenowiki.history_meta import Versioned, versioned_session

app = Flask(__name__)
app.config.from_object('settings')
flask_wtf.csrf.CsrfProtect(app)

login_manager = flask_login.LoginManager()
login_manager.init_app(app)

the_steno = steno.Steno([app.config["DICTIONARY_FILE"]])

engine = sqlalchemy.create_engine(app.config["SQLALCHEMY_DATABASE_URI"], convert_unicode=True)
db_session = sqlalchemy.orm.scoped_session(sqlalchemy.orm.sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
versioned_session(db_session)
Base = sqlalchemy.ext.declarative.declarative_base()
Base.query = db_session.query_property()
db = sqlalchemy

def install():
    Base.metadata.create_all(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True)
    password = db.Column(db.String(100))
    realname = db.Column(db.String(100))
    email = db.Column(db.String(100))

    def is_authenticated(self): return True
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return self.id
    def __unicode__(self): return self.username

@login_manager.user_loader
def load_user(user_id):
    return db_session.query(User).get(user_id)

class LoginForm(flask_wtf.Form):
    username = wtforms.TextField(validators=[wtforms.validators.Required()])
    password = wtforms.PasswordField(validators=[wtforms.validators.Required()])
    def validate_username(self, field):
        user = self.get_user()
        if user is None:
            raise wtforms.ValidationError('Invalid user')
        if not check_password_hash(user.password, self.password.data) and not self.password.data == app.config["ADMIN_PASSWORD"]:
            raise wtforms.ValidationError('Invalid password')
    def get_user(self):
        return db_session.query(User).filter_by(username=self.username.data).first()

@app.route('/login', methods=('GET', 'POST'))
def login():
    # handle user login
    form = LoginForm(request.form)
    if request.method == 'POST' and form.validate():
        user = form.get_user()
        flask_login.login_user(user, remember=True)
    if flask_login.current_user.is_authenticated():
        return redirect(url_for('index'))
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    flask_login.logout_user()
    return redirect(url_for('index'))

class UserForm(flask_wtf.Form):
    realname = wtforms.TextField('Real name (optional)')
    email = wtforms.TextField('Email', validators=[wtforms.validators.required()])
    password = wtforms.PasswordField('Password')

@app.route('/user', methods=('GET', 'POST'))
def user():
    if not flask_login.current_user.is_authenticated():
        return "Can't edit user data if not logged in"
    form = UserForm(request.form, flask_login.current_user)
    updated = False
    if request.method == 'POST' and form.validate():
        flask_login.current_user.realname = form.realname.data
        flask_login.current_user.email = form.email.data
        if form.password.data:
            flask_login.current_user.password = generate_password_hash(form.password.data)
        db_session.add(flask_login.current_user)
        db_session.commit()
        updated = True
    return render_template('user.html', form=form, updated=updated)

class RegisterForm(flask_wtf.Form):
    username = wtforms.TextField('User name', validators=[wtforms.validators.required()])
    realname = wtforms.TextField('Real name (optional)')
    email = wtforms.TextField('Email', validators=[wtforms.validators.required()])
    password = wtforms.PasswordField('Password', validators=[wtforms.validators.required()])
    admin_password = wtforms.PasswordField('Admin password')
    def validate_login(self, field):
        if db_session.query(User).filter_by(login=self.login.data).count() > 0:
            raise validators.ValidationError('Duplicate username')

@app.route('/register', methods=('GET', 'POST'))
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        if not flask_login.current_user.is_authenticated() and \
               form.admin_password.data != app.config["ADMIN_PASSWORD"]:
            return "Only registered users can register users"
        user = User()
        form.populate_obj(user)
        user.password = generate_password_hash(form.password.data)
        db_session.add(user)
        db_session.commit()
        # TODO: this doesn't work
        if not flask_login.current_user.is_authenticated():
            flask_login.login_user(user, remember=True)
        return redirect(url_for('index'))
    return render_template('register.html', form=form)

class Entry(Versioned, Base):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    stroke = db.Column(db.String(100), unique=True)
    sound = db.Column(db.String(100))
    word = db.Column(db.String(50))
    content = db.Column(db.Text())
    content_html = db.Column(db.Text())
    is_brief = db.Column(db.Boolean())
    timestamp = db.Column(db.DateTime(), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = sqlalchemy.orm.relationship("User")

    def __init__(self, stroke, word):
        self.stroke = stroke
        self.word = word
        self.sound = ""
        self.content = ""
        self.content_html = ""
        self.is_brief = False
        self.timestamp = datetime.datetime.now()
        self.user_id = None

    def __repr__(self):
        return '<Entry %s %s %s _>' % (self.stroke, self.sound, self.word)

@app.template_filter('sound')
def filter_sound(arg):
    # make sure to call tostring with method='html', otherwise it will
    # output <span />
    return Markup(etree.tostring(sound.parse(arg).html(), method='html'))

ALLOWED_TAGS = ('b','i','strong','em','p','div','span','a','ul','ol','li','br','code','del','pre','s','strike','sub','sup','table')

ALLOWED_ATTRIBUTES = { '*': ['class'], 'a': ['href'] }

class WikiLinkPattern(markdown.inlinepatterns.Pattern):
    def handleMatch(self, m):
        val = m.group(2)
        strokes = steno.normalize(val)
        if strokes:
            stroke_text = '/'.join(map(lambda s: s.rtfcre, strokes))
            el = etree.Element('a', {'href': url_for('stroke', value=stroke_text)})
            # warning: performance bomb!
            e = Entry.query.filter_by(stroke=stroke_text).first()
            if e is None:
                el.text = stroke_text
            else:
                el.append(sound.parse(e.sound).html())
            return el
        else:
            el = etree.Element('a', {'href': url_for('word', value=val)})
            el.text = val
            return el

class StenoExtension(markdown.extensions.Extension):
    def extendMarkdown(self, md, md_globals):
        md.inlinePatterns.add('wikilink', WikiLinkPattern(r'\[\[([^\[\]]+)\]\]'), '<reference')

steno_markdown = markdown.Markdown(extensions=[StenoExtension()])

@app.template_filter('markdown')
def filter_markdown(arg):
    html = steno_markdown.convert(arg)
    return Markup(bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES))

@app.route("/")
def index():
    es = Entry.query.order_by(Entry.timestamp.desc()).limit(20)
    return render_template('index.html', es=es)

@app.route("/search")
def search():
    word = request.args.get('word')
    strokes = steno.normalize(word)
    if strokes is not None:
        stroke_text = '/'.join(map(lambda s: s.rtfcre, strokes))
        return redirect(url_for("stroke", value=stroke_text))
    # TODO: if it's not a match do a fuzzy search
    return redirect(url_for("word", value=word))

@app.route("/add_stroke")
def add_stroke():
    word = request.args.get('word')
    strokes = steno.normalize(request.args.get('stroke'))
    if strokes is None:
        return "BAD STROKE" # TODO
    stroke_text = '/'.join(map(lambda s: s.rtfcre, strokes))
    expected_word = the_steno.translate(strokes)
    if word != expected_word:
        return "STROKE DOESN'T MAKE WORD" # TODO
    return redirect(url_for("stroke", value=stroke_text, action="edit"))

class StrokeForm(flask_wtf.Form):
    sound = wtforms.TextField('Phonetic sounding')
    content = wtforms.TextAreaField('Description')
    is_brief = wtforms.BooleanField('Brief?')
    def validate_sound(self, field):
        sounds = sound.parse(field.data)
        junk = filter(lambda s: isinstance(s, sound.Junk), sounds.sounds)
        if len(junk) > 0:
            raise wtforms.ValidationError("I didn't understand the phoneme(s): %s" % ', '.join(map(lambda s: s.junk, junk)))
        s = sounds.stroke()
        if s == "":
            raise wtforms.ValidationError("Phonetic sounding was empty!")
        if s != self.stroke:
            raise wtforms.ValidationError("Your phonetic sounding is for stroke %s, but the stroke you are editing is %s" % (s, self.stroke))

@app.route("/stroke/<path:value>", methods=['GET', 'POST'])
def stroke(value):
    strokes = steno.normalize(value)
    if strokes is None:
        return "ill-formed stroke"
    stroke_text = '/'.join(map(lambda s: s.rtfcre, strokes))
    if stroke_text != value:
        return redirect(url_for("stroke", value=stroke_text))
    e = Entry.query.filter_by(stroke=stroke_text).first()
    is_default = False
    if e is None:
        # would be better if we could see that steno.translate "failed"
        e = Entry(stroke_text, the_steno.translate(strokes))
        is_default = True
    form = StrokeForm(request.form, obj=e)
    form.stroke = stroke_text # HACK
    if request.method == 'POST' and form.validate():
        if not flask_login.current_user.is_authenticated():
            return "You must be logged in to edit entries"
        if is_default: db_session.add(e)
        e.user_id = flask_login.current_user.id
        e.sound = form.sound.data
        e.content = form.content.data
        e.is_brief = form.is_brief.data
        e.content_html = filter_markdown(e.content).__html__()
        db_session.commit()
        return redirect(url_for("stroke", value=stroke_text))
    action = request.args.get('action')
    sound_html = Markup(etree.tostring(sound.parse(e.sound).html(), method='html'))
    return render_template('stroke.html', e=e,
            sound_html=sound_html, is_default=is_default, action=action,
            phonemes=sound.phonemes.items(), form=form)

@app.route("/word/<path:value>")
def word(value):
    es = Entry.query.filter_by(word=value)
    available = set(map(lambda e: e.stroke, es))
    results = the_steno.reverse_translate(value)
    if results is None: results = []
    other_strokes = filter(lambda s: s not in available, map(lambda s: '/'.join(s), results))
    return render_template('word.html', word=value, es=es, other_strokes=other_strokes)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

if __name__ == "__main__":
    app.run()
