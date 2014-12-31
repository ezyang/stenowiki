# for some reason, these imports take a long time. Figure out why.
import plover.dictionary.base
import plover.translation
import plover.formatting
import plover.steno_dictionary

from plover.exception import InvalidConfigurationError, DictionaryLoaderException
from plover.steno import Stroke, normalize_steno

import re

try:
    dicts = [plover.dictionary.base.load_dictionary("/home/ezyang/.local/share/plover/dict.json")]
except DictionaryLoaderException as e:
    raise InvalidConfigurationError(unicode(e))

# you could make this more efficient but whatever
class StringOutput():
    def __init__(self):
        self.buffer = ""
    def send_backspaces(self, n):
        self.buffer = self.buffer[:-n]
    def send_string(self, s):
        self.buffer += s
    def get(self):
        x = self.buffer
        self.buffer = ""
        if x[0] == " ":
            return x[1:]
        else:
            return x

the_dict = plover.steno_dictionary.StenoDictionaryCollection()
the_dict.set_dicts(dicts)

def new_translator():
    translator = plover.translation.Translator()
    # TODO: hmm, this might be a bit inefficient, looks like dicts gets copied
    translator.get_dictionary().set_dicts(dicts)
    translator.set_min_undo_length(10)
    formatter = plover.formatting.Formatter()
    output = StringOutput()
    formatter.set_output(output)
    translator.add_listener(formatter.format)
    return translator, output

def reverse_lookup(val):
    return the_dict.reverse_lookup(val)

# this is actually a trick to make sure the hyphen is in
# the right place: otherwise Plover accepts H-AT and produces
# a stroke with "-A" rather than "A-"
STROKE_RE = re.compile(r"^(S?T?K?P?W?H?R?(A?O?\*?-?E?U?|-)F?R?P?B?L?G?T?S?D?Z?)(/S?T?K?P?W?H?R?(A?O?\*?-?E?U?|-)F?R?P?B?L?G?T?S?D?Z?)*$")

def normalize(value):
    if STROKE_RE.match(value) is None:
        return None
    return map(stroke, value.split('/'))

def stroke(s):
    keys = []
    on_left = True
    vowels = False
    for k in s:
        if k in 'EU*-':
            on_left = False
        if k in 'AO':
            vowels = True
        elif vowels:
            on_left = False
        if k == '-': 
            continue
        elif k == '*': 
            keys.append(k)
        elif on_left: 
            keys.append(k + '-')
        else:
            keys.append('-' + k)
    return Stroke(keys)

def translate(strokes):
    translator, output = new_translator()
    for s in strokes:
        translator.translate(s)
    return output.get()
