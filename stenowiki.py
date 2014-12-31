import os
import sys
import re
import bleach
import xml.etree.ElementTree as ET

_root_dir = os.path.dirname(__file__)
sys.path.insert(0, _root_dir)
sys.path.insert(0, os.path.join(_root_dir, "plover"))

import flask
from flask import Flask, render_template, redirect, url_for, request
import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.ext.declarative

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
        if request.method == 'POST':
            db_session.add(e)
        is_default = True
    if request.method == 'POST':
        e.sound = request.form['sound']
        e.content = request.form['content']
        e.content_html = flask.escape(e.content) # TODO
        db_session.commit()
        return redirect(url_for("stroke", value=stroke_text))
    sound_html = ET.tostring(sound.parse(e.sound).html())
    action = request.args.get('action')
    return render_template('stroke.html', e=e,
            sound_html=sound_html, is_default=is_default, action=action,
            phonemes=sound.phonemes.items())

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
