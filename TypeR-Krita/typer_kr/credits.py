# -*- coding: utf-8 -*-
"""Who thought of what, and who built it.

Three columns, one row per feature: the feature, where the **idea** came
from, and who **wrote** it. Separate because they are separate: most of
what this plugin does was somebody else's idea first, and saying so is the
only honest way to ship a tool that openly rebuilds features from another
one.

Kept as plain data, Qt-free, so the panel that shows it has nothing to
decide and a new feature is one line here. The names are as the author gave
them, in the order the credit is read: idea first.

`IDEA_NOTES` says a word about the people, once, under the table - a name
on its own tells a reader nothing.
"""

#: Who the names are. Keyed by the exact string used in CREDITS.
IDEA_NOTES = (
    ("Sakushi", "typer_credit_sakushi"),
    ("Giongo", "typer_credit_giongo"),
    ("KSR", "typer_credit_ksr"),
)

#: (feature, idea by, written by). The feature name is a translation key;
#: the two names are shown as they stand, because a person's name is not
#: translated.
CREDITS = (
    ("cr_textshapr", "Sakushi", "Claude"),
    ("cr_outline", "Sakushi", "Claude"),
    ("cr_batch", "Sakushi", "Claude"),
    ("cr_giongo", "Giongo", "Claude"),
    ("cr_script_edit", "KSR", "Claude"),
    ("cr_fonts", "Valle", "Claude"),
    ("cr_font_search", "Valle", "Claude"),
    ("cr_keys_list", "Valle", "Claude"),
    ("cr_credits", "Valle", "Claude"),
    ("cr_sfx", "Valle", "Claude"),
    ("cr_presets", "Valle", "Claude"),
    ("cr_scripts", "Valle", "Claude"),
    ("cr_colour", "Valle", "Claude"),
    ("cr_patterns", "Valle", "Claude"),
    ("cr_bubblr", "Valle", "Claude"),
    ("cr_swap", "Valle", "Claude"),
    ("cr_vertical", "Claude", "Claude"),
    ("cr_balloons", "Claude", "Claude"),
    ("cr_texttypes", "Claude", "Claude"),
    ("cr_lab", "Claude", "Claude"),
)


def rows(tr=None):
    """[(feature, idea, code)] with the feature name translated."""
    out = []
    for key, idea, code in CREDITS:
        name = tr(key) if tr else key
        out.append((name, idea, code))
    return out


def people(tr=None):
    """[(name, what they are)] for the note under the table."""
    out = []
    for name, key in IDEA_NOTES:
        out.append((name, tr(key) if tr else key))
    return out


def by_idea(name):
    """Which features came from this person's head."""
    return [k for (k, idea, _c) in CREDITS if idea == name]
