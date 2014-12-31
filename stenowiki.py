import os
import sys
import re
import bleach
import markdown
import markdown.extensions
from markdown.util import etree

_root_dir = os.path.dirname(__file__)
sys.path.insert(0, _root_dir)
sys.path.insert(0, os.path.join(_root_dir, "plover"))

import flask
from flask import Flask, render_template, redirect, url_for, request

from jinja2 import Markup

import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.ext.declarative

from wtforms import Form, TextField, TextAreaField, validators, ValidationError

from stenowiki import steno, sound
# NB: versioned doesn't work with flask-sqlalchemy
# see https://github.com/mitsuhiko/flask-sqlalchemy/issues/182
# so we do it manually
from stenowiki.history_meta import Versioned, versioned_session

engine = sqlalchemy.create_engine('sqlite:////tmp/test.db', convert_unicode=True)
db_session = sqlalchemy.orm.scoped_session(sqlalchemy.orm.sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
versioned_session(db_session)
Base = sqlalchemy.ext.declarative.declarative_base()
Base.query = db_session.query_property()
db = sqlalchemy

app = Flask(__name__)

class Entry(Versioned, Base):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    stroke = db.Column(db.String(25), unique=True)
    sound = db.Column(db.String(100))
    word = db.Column(db.String(50))
    content = db.Column(db.Text())
    content_html = db.Column(db.Text())

    def __init__(self, stroke, word):
        self.stroke = stroke
        self.word = word
        self.sound = ""
        self.content = ""
        self.content_html = ""

    def __repr__(self):
        return '<Entry %s %s %s _>' % (self.stroke, self.sound, self.word)

@app.route("/")
def hello():
    return "Hello"

class StrokeForm(Form):
    sound = TextField('Phonetic sounding')
    content = TextAreaField('Description')
    def validate_sound(self, field):
        s = sound.parse(field.data).stroke()
        if s != self.stroke:
            raise ValidationError("Your phonetic sounding is for stroke %s, but the stroke you are editing is %s" % (s, self.stroke))

@app.template_filter('sound')
def filter_sound(arg):
    return Markup(etree.tostring(sound.parse(arg).html()))

ALLOWED_TAGS = ('b','i','strong','em','p','div','span','a','ul','ol','li','br','code','del','pre','s','strike','sub','sup','table')

ALLOWED_ATTRIBUTES = { '*': ['class'], 'a': ['href'] }

class WikiLinkPattern(markdown.inlinepatterns.Pattern):
    def handleMatch(self, m):
        val = m.group(2)
        strokes = steno.normalize(val)
        if strokes:
            stroke_text = '/'.join(map(lambda s: s.rtfcre, strokes))
            el = etree.Element('a', {'href': url_for('stroke', value=stroke_text)})
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
        e = Entry(stroke_text, steno.translate(strokes))
        is_default = True
    form = StrokeForm(request.form, obj=e)
    form.stroke = stroke_text # HACK
    if request.method == 'POST' and form.validate():
        if is_default: db_session.add(e)
        e.sound = form.sound.data
        e.content = form.content.data
        e.content_html = flask.escape(e.content) # TODO
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
    return render_template('word.html', word=value, es=es)

@app.route("/install")
def install():
    Base.metadata.create_all(bind=engine)
    return "OK"

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

if __name__ == "__main__":
    app.run(debug=True)
    pass
