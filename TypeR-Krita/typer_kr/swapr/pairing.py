"""Typeset-Dateien den passenden Clean-Bildern zuordnen.

Die Dateinamen stimmen in der Praxis nicht ueberein ('page 1-Recuperado.jpg'
neben 'page 1.JPG'), deshalb wird ueber die Seitenzahl gepaart und erst als
Rueckfall ueber die sortierte Reihenfolge.
"""

import os
import re

from .kra import page_number

_CHUNK = re.compile(r"(\d+)")


def natural_key(path):
    """Sortierschluessel, bei dem 'page 2' vor 'page 10' kommt."""
    name = os.path.basename(path).lower()
    return [int(p) if p.isdigit() else p for p in _CHUNK.split(name)]


class Pair:
    __slots__ = ("ts", "clean", "note")

    def __init__(self, ts, clean=None, note=""):
        self.ts = ts
        self.clean = clean
        self.note = note

    @property
    def ts_name(self):
        return os.path.basename(self.ts)

    @property
    def clean_name(self):
        return os.path.basename(self.clean) if self.clean else ""


def make_pairs(ts_files, clean_files):
    """Liefert (pairs, uebrige_clean_dateien).

    Bevorzugt die Zuordnung ueber die Seitenzahl. Sind die Seitenzahlen nicht
    eindeutig oder nicht vorhanden, wird nach Reihenfolge gepaart und das in
    der Notiz vermerkt, damit man es im UI sieht.
    """
    ts_files = sorted(ts_files, key=natural_key)
    clean_files = sorted(clean_files, key=natural_key)

    ts_nums = [page_number(os.path.basename(f)) for f in ts_files]
    cl_nums = [page_number(os.path.basename(f)) for f in clean_files]

    usable = (
        all(n is not None for n in ts_nums)
        and all(n is not None for n in cl_nums)
        and len(set(ts_nums)) == len(ts_nums)
        and len(set(cl_nums)) == len(cl_nums)
    )

    pairs = []
    if usable:
        by_num = dict(zip(cl_nums, clean_files))
        used = set()
        for path, num in zip(ts_files, ts_nums):
            match = by_num.get(num)
            if match is None:
                pairs.append(Pair(path, None, f"keine Clean-Seite {num}"))
            else:
                used.add(match)
                pairs.append(Pair(path, match))
        rest = [c for c in clean_files if c not in used]
    else:
        note = "nach Reihenfolge zugeordnet - bitte pruefen"
        for i, path in enumerate(ts_files):
            match = clean_files[i] if i < len(clean_files) else None
            pairs.append(Pair(path, match, note if match else "keine Clean-Seite uebrig"))
        rest = clean_files[len(ts_files):]

    return pairs, rest
