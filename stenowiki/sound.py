import json
import re
from markdown.util import etree
import collections

phonemes = collections.OrderedDict([
        # basic phonemes
        ("s", "S"),
        ("t", "T"),
        ("k", "K"),
        ("p", "P"),
        ("w", "W"),
        ("wv", "W"),
        ("h", "H"),
        ("r", "R"),
        ("*", "*"),
        ("-f", "-F"),
        ("-fs", "-F"),
        ("-v", "-F"),
        ("-r", "-R"),
        ("-p", "-P"),
        ("-b", "-B"),
        ("-l", "-L"),
        ("-g", "-G"),
        ("-t", "-T"),
        ("-s", "-S"),
        ("-d", "-D"),
        ("-z", "-Z"),
        # vowels
        ("a", "A"),
        ("o", "O"),
        ("e", "E"),
        ("u", "U"),
        ("i", "EU"),
        ("ay", "AEU"),
        ("ee", "AOE"),
        ("eye", "AOEU"),
        ("oh", "OE"),
        ("ew", "AOU"),
        ("aw", "AU"),
        ("ow", "OU"),
        ("ou", "OU"),
        ("oi", "OEU"),
        ("ea", "AE"),
        ("ae", "AE"),
        ("oo", "AO"),
        ("oa", "AO"),
        # asterisked vowels
        ("a*", "A*"),
        ("o*", "O*"),
        ("e*", "*E"),
        ("u*", "*U"),
        ("i*", "*EU"),
        ("ay*", "A*EU"),
        ("ee*", "AO*E"),
        ("eye*", "AO*EU"),
        ("oh*", "O*E"),
        ("ew*", "A*OU"),
        ("aw*", "A*U"),
        ("ow*", "O*U"),
        ("oi*", "O*EU"),
        ("ea*", "A*E"),
        ("ae*", "A*E"),
        ("oo*", "AO*"),
        ("oa*", "AO*"),
        # missing keys
        ("d", "TK"),
        ("f", "TP"),
        ("l", "HR"),
        ("g", "TKPW"),
        ("b", "PW"),
        ("z", "S"), # asterisk1
        ("v", "SR"),
        ("-k", "BG"),
        # more letters
        ("n", "TPH"),
        ("m", "PH"),
        ("j", "SKWR"),
        ("y", "KWR"),
        ("-n", "-PB"),
        ("-m", "-PL"),
        ("-lm", "-PL"),
        ("-j", "-PBLG"),
        # fingerspelled variants
        ("c", "KR"),
        ("q", "KW"),
        ("x", "KP"),
        ("zz", "STKPW"),
        # digraphs
        ("th", "TH"),
        ("ch", "KH"),
        ("sh", "SH"),
        ("-th", "T"), # asterisk
        ("-ch", "-FP"),
        ("-sh", "-RB"),
        ("-ng", "-PBG"),
        ("-nj", "-PBG"),
        # compound clusters
        ("-mp", "PL"), # asterisk
        ("-rv", "-FRB"),
        ("-lch", "-LG"),
        ("-lj", "-LG"),
        ("-lk", "LG"), # asterisk
        ("-nk", "PBG"), # asterisk
        ("-shun", "-GS"),
        ("-kshun", "-BGS"),
        ("-rch", "-FRPB"),
        ("-nch", "-FRPB"),
        # suffix keys (s is a repeat)
        ("-ed", "-D"),
        ("-ing", "-G"),
        ])

"""
These should work as pages!
        # related sounds (arguably should render as original though)
        "s@f": "-F",
        "v@w": "W",
        # briefing extras (this should be user editable)
        "com-": "K",
        "ex-": "KP",
        "-ly": "-L",
        "-xt": "-GT",
"""

# atom :=
#   phoneme             # ordinary phoneme
#   -                   # disambiguating hyphen
#   [
#   ]                   # brackets for inversion
#   phoneme:STROKE      # custom stroke
#   !STROKE             # added key misstroke
#   !phoneme:STROKE     # custom misstroke
#
# Hyphen can be omitted as per steno order rules.
#
# Not doing a *proper* grammar so the parser is more robust.

def parse(val):
    tokens = re.split(r'([ \[\]])', val)
    sounds = []
    in_right = False
    for t in tokens:
        if t == "":
            pass
        elif t.isspace():
            pass
        elif t == "[":
            sounds.append(BeginInversion())
        elif t == "]":
            sounds.append(EndInversion())
        elif t == "-":
            in_right = True
            sounds.append(Phoneme("", "-", "hyphen"))
        elif t == "*":
            in_right = True
            sounds.append(Phoneme("", "*", "asterisk"))
        elif t == "/":
            in_right = False
            sounds.append(Phoneme("", "/", "slash"))
        else:
            match = re.match(r'^!([A-Z*\-]+)', t)
            if match:
                stroke = match.group(1)
                attr = 'misstroke'
                sounds.append(Phoneme("", stroke, attr))
                continue
            match = re.match(r'^(!?)(-?[a-z]+\*?)(?::([A-Z*\-]+))?', t)
            if match:
                phoneme = match.group(2)
                # UGHHHH
                if in_right and phoneme.find('-') != 0:
                    phoneme = '-' + phoneme
                if phoneme.find('-') == 0:
                    in_right = True
                stroke = match.group(3)
                if stroke is None:
                    if phoneme not in phonemes and phoneme.find('-') == 0:
                        phoneme = phoneme[1:]
                    if phoneme not in phonemes:
                        sounds.append(Junk(t))
                        continue
                    stroke = phonemes[phoneme]
                    attr = 'phoneme'
                else:
                    if match.group(1) == '!':
                        attr = 'misstroke'
                    else:
                        attr = 'custom'
                if re.match(r'[AOEU*]', stroke):
                    in_right = True
                sounds.append(Phoneme(phoneme, stroke, attr))
            else:
                sounds.append(Junk(t))
    return Sounds(sounds)

class Sounds:
    def __init__(self, sounds):
        self.sounds = sounds
    def is_misstroke(self):
        return any(map(lambda s: s.attr == "misstroke", self.sounds))
    def stroke(self):
        stroke = ""
        for sound in self.sounds:
            if isinstance(sound, Phoneme):
                if sound.stroke.find("-") == 0 and sound.stroke != "-":
                    stroke += sound.stroke[1:]
                else:
                    stroke += sound.stroke
        return stroke
    def __str__(self):
        return ' '.join(map(lambda s: str(s), self.sounds))
    def html(self):
        table = etree.Element('span', { "class": "sounds" })
        stroke_row = etree.SubElement(table, 'span', { "class": "strokes" })
        for sound in self.sounds:
            td = etree.SubElement(stroke_row, 'span', { "class": sound.attr + " cell" })
            if isinstance(sound, Phoneme):
                if sound.stroke.find("-") == 0 and sound.stroke != "-":
                    td.text = sound.stroke[1:]
                else:
                    td.text = sound.stroke
            if td.text and len(td.text) > 1:
                td.set("class", sound.attr + " cell multi")
        phon_row = etree.SubElement(table, 'span', { "class": "phonemes" })
        for sound in self.sounds:
            td = etree.SubElement(phon_row, 'span', { "class": sound.attr + " cell" })
            if isinstance(sound, Phoneme):
                out = sound.phoneme.replace("*", "")
                # special case
                if out == "fs" or out == "-fs":
                    td.text = "s"
                elif out == "wv":
                    td.text = "v"
                elif out.find("-") == 0:
                    td.text = out[1:]
                else:
                    td.text = out
            elif isinstance(sound, BeginInversion):
                td.text = "["
            elif isinstance(sound, EndInversion):
                td.text = "]"
            elif isinstance(sound, Junk):
                td.text = sound.junk
        return table

class Sound:
    pass

class Phoneme(Sound):
    def __init__(self, phoneme, stroke, attr):
        self.phoneme = phoneme
        self.stroke = stroke
        self.attr = attr
    def __str__(self):
        if self.attr == "phoneme":
            return self.phoneme
        elif self.attr == "misstroke":
            if not self.phoneme:
                return "!" + self.stroke
            else:
                return "!" + self.phoneme + ":" + self.stroke
        elif self.attr == "custom":
            return self.phoneme + ":" + self.stroke
        else:
            return self.stroke

class BeginInversion(Sound):
    def __init__(self): self.attr = "begin-inversion"
    def __str__(self): return '['

class EndInversion(Sound):
    def __init__(self): self.attr = "end-inversion"
    def __str__(self): return ']'

class Junk(Sound):
    def __init__(self, junk):
        self.junk = junk
        self.attr = "junk"
    def __str__(self): return self.junk

# layout
#
# STROKE <-- color
# ------
# phonem <-- color
#
# Design constraint: The letters in STROKE must be in steno order.
#
# Writing model: You write down phonemes, and they translate into strokes
# *in the order you write them down in*.
#
# Consequences: For the majority of strokes, these two rules will let
# you annotate strokes as you want.  However, there are a few cases
# where you might run into a little trouble:
#
#   1. Inversion.  Solution: just put the sounds in stroke order!
#      You can also add brackets to indicate that an inversion has
#      occurred, to make it easier for someone studying the stroke.
#
#   2. Asterisk modifying a letter sound.  Solution: manually put in
#      the asterisk and use the other sound.  (I considered
#      automatically inserting the asterisk, but this was more
#      complication for not much benefit.)
#
#   3. Asterisk in the middle of a vowel chord.  Solution: all vowel
#      chords have asterisked versions
#
#   4. Everything else (overlap, misstroke dropping/adding keys).
#      Solution: make a larger custom phoneme/stroke pair which does the
#      stroke correctly.  In general, you can work around *any* problem
#      this way, but you lose precision (since the annotation applies
#      for the entire stroke), so we have added workarounds for some
#      specific problems.
#
# The asterisk handling is a sort of "worse is better" approach, but
# I don't think we lose any semantic meaning by doing it this way.

# cribbed from https://plover.goeswhere.com/
meanings = [
    { "from": "STKPW", "to": "z" },
    { "from": "SKWR", "to": "j" },
    { "from": "TKPW", "to": "g" },
    { "from": "PBLG", "to": "j" },
    { "from": "KWR", "to": "y" },
    { "from": "TPH", "to": "n" },
    { "from": "KHR", "to": ["k", "l"] }, # not ch-r
    { "from": "PHR", "to": ["p", "l"] }, # not m-r
    { "from": "FPL", "to": ["-fs", "-m"] }, # not ch-l
    { "from": "BGS", "to": "kshun" },
    { "from": "SR", "to": "v" },
    { "from": "TK", "to": "d" },
    { "from": "TP", "to": "f" },
    { "from": "PH", "to": "m" },
    { "from": "PW", "to": "b" },
    { "from": "KW", "to": "q" },
    { "from": "HR", "to": "l" },
    { "from": "KP", "to": "x" },
    { "from": "FP", "to": "ch" },
    { "from": "RB", "to": "sh" },
    { "from": "PB", "to": "n" },
    { "from": "PL", "to": "m" },
    { "from": "BG", "to": "k" },
    { "from": "GS", "to": "shun" },
    { "from": "TH", "to": "th" },
    { "from": "KH", "to": "ch" },
    { "from": "SH", "to": "sh" },
    { "from": "AO*EU", "to": "eye*" },
    { "from": "A*EU", "to": "ay*" },
    { "from": "AO*E", "to": "ee*" },
    { "from": "AO*U", "to": "ew*" },
    { "from": "O*EU", "to": "oi*" },
    { "from": "A*U", "to": "aw*" },
    { "from": "A*E", "to": "ae*" },
    { "from": "O*U", "to": "ow*" },
    { "from": "O*E", "to": "oh*" },
    { "from": "AOEU", "to": "eye" },
    { "from": "AEU", "to": "ay" },
    { "from": "AOE", "to": "ee" },
    { "from": "AOU", "to": "ew" },
    { "from": "OEU", "to": "oi" },
    { "from": "AU", "to": "aw" },
    { "from": "EA", "to": "ea" },
    { "from": "OU", "to": "ow" },
    { "from": "EU", "to": "i" },
    { "from": "OE", "to": "oh" },
    { "from": "AO", "to": "oo" },
  ]

def guess_sound(stroke):
    sounds = []
    i = 0
    while i < len(stroke):
        done = False
        for m in meanings:
            if stroke.startswith(m["from"], i):
                if not isinstance(m["to"], str):
                    for to in m["to"]:
                        sounds.append(Phoneme(to, phonemes[to], "phoneme"))
                else:
                    sounds.append(Phoneme(m["to"], m["from"], "phoneme"))
                i += len(m["from"])
                done = True
                break
        if done: continue
        if stroke[i] == "*":
            sounds.append(Phoneme("", "*", "asterisk"))
        elif stroke[i] == "-":
            sounds.append(Phoneme("", "-", "hyphen"))
        elif stroke[i] == "/":
            sounds.append(Phoneme("", "/", "slash"))
        else:
            # missing dashes
            sounds.append(Phoneme(stroke[i].lower(), stroke[i], "phoneme"))
        i += 1
    return Sounds(sounds)
