# -*- coding: utf-8 -*-
"""What changed in each version, and which of it a user has not seen yet.

A Krita plugin updates by having its files overwritten, so there is no moment
at which anything could announce itself. The docker therefore compares the
version it ships with against the last one it recorded having shown, and the
first time Krita is started after an update it says what is new.

Kept Qt-free and apart from the docker so the list is easy to extend and the
"which entries are new" rule can be tested on its own. Entries are newest
first, and each carries both interface languages, like the rest of the plugin.
"""

#: [(version, {lang: [line, ...]}), ...] - newest first.
CHANGELOG = [
    ("1.12", {
        "en": [
            "Preset keybinds: give a style a key and press it when the "
            "speaker changes, instead of walking the character and preset "
            "dropdowns. The field sits under the preset list.",
            "A keybind can combine keys the way Ctrl+C does — and ordinary "
            "letters count, so A+B means hold A and press B. The order "
            "matters, so B+A is a different keybind.",
            "A for Akarie and A+B for Akarie bold can both be bound: holding "
            "A applies Akarie at once, adding B switches to the bold one.",
            "Keybinds belong to the manga, so the same few keys are free "
            "again in the next series.",
            "Google Docs scripts load again. Drive stopped letting any "
            "program read a .gdoc, so TypeR now looks the document up in the "
            "Drive client's own index, and asks for the link if that comes up "
            "empty.",
        ],
        "de": [
            "Tastenkürzel für Presets: gib einem Stil eine Taste und drück "
            "sie, wenn die sprechende Figur wechselt, statt durch die "
            "Auswahllisten zu klicken. Das Feld steht unter der Preset-Liste.",
            "Ein Kürzel kann Tasten kombinieren wie Strg+C — und normale "
            "Buchstaben zählen mit: A+B heißt A halten und B drücken. Die "
            "Reihenfolge zählt, B+A ist ein anderes Kürzel.",
            "A für Akarie und A+B für Akarie fett lassen sich beide belegen: "
            "A halten wendet sofort Akarie an, B dazu schaltet auf fett.",
            "Kürzel gehören zum Manga — in der nächsten Serie sind dieselben "
            "Tasten wieder frei.",
            "Google-Docs-Skripte laden wieder. Drive lässt eine .gdoc von "
            "keinem Programm mehr lesen, also schlägt TypeR das Dokument im "
            "lokalen Drive-Index nach — und fragt nach dem Link, wenn das "
            "nichts findet.",
        ],
    }),
]


def parse_version(text):
    """A version as a tuple of numbers, for comparing: "1.11" -> (1, 11).

    Compared as numbers on purpose, because the scheme counts past nine:
    as text "1.9" would sort after "1.11". Anything unparsable is (), which
    compares lower than every real version.
    """
    out = []
    for part in str(text or "").strip().split("."):
        part = part.strip()
        if not part.isdigit():
            return tuple(out)
        out.append(int(part))
    return tuple(out)


def entries_since(seen, current, changelog=None):
    """The changelog entries between `seen` and `current`, newest first.

    An update that skips a version or two still gets told about all of them.
    Nothing is returned when `seen` is already at or past `current`, so the
    announcement happens exactly once per version - and `seen` being empty is
    the caller's decision to make, not this function's (see
    _whatsnew_baseline): here it simply means "has seen nothing", which shows
    everything.
    """
    lo = parse_version(seen)
    hi = parse_version(current)
    if not hi or lo >= hi:
        return []
    out = []
    for version, langs in (changelog if changelog is not None else CHANGELOG):
        v = parse_version(version)
        if lo < v <= hi:
            out.append((version, langs))
    out.sort(key=lambda e: parse_version(e[0]), reverse=True)
    return out


def lines_for(entries, lang):
    """[(version, [line, ...]), ...] in one language, falling back to English.

    A language that has not been translated yet must not turn the dialog into
    a blank box, which is the same rule the rest of the interface follows.
    """
    out = []
    for version, langs in entries:
        lines = langs.get(lang) or langs.get("en") or []
        if lines:
            out.append((version, [str(x) for x in lines]))
    return out
