# for some reason, these imports take a long time. Figure out why.
import plover.dictionary.base
import plover.translation
import plover.formatting
import plover.steno_dictionary

from plover.exception import InvalidConfigurationError, DictionaryLoaderException
from plover.steno import Stroke, normalize_steno

import re

class Steno:
    def __init__(self, files):
        try:
            dicts = map(plover.dictionary.base.load_dictionary, files)
        except DictionaryLoaderException as e:
            raise InvalidConfigurationError(unicode(e))

        self.translator = plover.translation.Translator()
        self.translator.get_dictionary().set_dicts(dicts)
        self.translator.set_min_undo_length(10)
        self.formatter = plover.formatting.Formatter()
        self.output = StringOutput()
        self.formatter.set_output(self.output)
        self.translator.add_listener(self.formatter.format)

    def reverse_translate(self,val):
        return self.translator.get_dictionary().reverse_lookup(val)

    def translate(self, strokes):
        self.output.reset()
        self.translator.clear_state()
        for s in strokes:
            self.translator.translate(s)
        return self.output.get()

# you could make this more efficient but whatever
class StringOutput():
    def __init__(self):
        self.buffer = ""
    def send_backspaces(self, n):
        self.buffer = self.buffer[:-n]
    def send_string(self, s):
        self.buffer += s
    def reset(self):
        self.buffer = ""
    def get(self):
        if len(self.buffer) == 0:
            return ""
        elif self.buffer[0] == " ":
            return self.buffer[1:]
        else:
            return self.buffer

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
