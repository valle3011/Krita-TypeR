# -*- coding: utf-8 -*-
"""Agreement with the shaper, chapter by chapter.

Not every chapter is lettered with the same care, and tuning a scorer
against a corpus that quietly contains weaker work tunes it towards the
weaker work. This says whether any chapter stands out - and, by
re-running with the weakest ones dropped, whether the number that was
tuned on the corpus survives without them.

    python bench/by_chapter.py blocks.json [drop_worst]

Reads only.
"""
import collections
import io
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
pkg = types.ModuleType("typer_kr")
pkg.__path__ = [os.path.join(ROOT, "typer_kr")]
sys.modules.setdefault("typer_kr", pkg)

from typer_kr._qt import (QApplication, QFont,          # noqa: E402
                          QFontMetricsF, font_families)

import importlib.util as _ilu                           # noqa: E402
_alt = os.environ.get("LAYOUT_MODULE")
if _alt:
    _sp = _ilu.spec_from_file_location("typer_kr.layout_alt", _alt)
    L = _ilu.module_from_spec(_sp)
    sys.modules["typer_kr.layout_alt"] = L
    _sp.loader.exec_module(L)
else:
    from typer_kr import layout as L

app = QApplication.instance() or QApplication([])
BLOCKS = json.loads(io.open(sys.argv[1], encoding="utf-8").read())
DROP = int(sys.argv[2]) if len(sys.argv) > 2 else 0
PAD = 0.12


def measurer_for(fam, ratio):
    def measurer(px):
        px = max(1, int(round(px)))
        fn = QFont(fam)
        fn.setPixelSize(px)
        fm = QFontMetricsF(fn)

        def width_of(x):
            runs = getattr(x, "runs", None)
            if runs is None:
                if isinstance(x, (list, tuple)):
                    runs = x
                else:
                    return fm.horizontalAdvance(x)
            return sum(fm.horizontalAdvance(r[0]) for r in runs)

        return (width_of, fm.horizontalAdvance(" "), px * ratio,
                fm.ascent(), fm.descent())
    return measurer


def rank_of(b, have):
    lines = [ln.strip() for ln in b["lines"]]
    if len(lines) < 2 or len(" ".join(lines).split()) < 3:
        return None
    if b["font"] not in have:
        return None
    px = int(round(b["px"]))
    ys = b["y"]
    gap = (ys[1] - ys[0]) if len(ys) > 1 else px
    m = measurer_for(b["font"], max(0.5, min(2.5, gap / float(px))))
    width_of, _sw, line_h, _a, _d = m(px)
    bw = max(width_of(ln) for ln in lines)
    bh = line_h * len(lines)
    try:
        cands = L.shape_candidates(" ".join(lines), m, bw / (1 - PAD),
                                   bh / (1 - PAD), px, 8, PAD,
                                   mode="balanced", limit=12)
    except Exception:                   # noqa: BLE001
        return None
    if not cands:
        return None
    want = tuple(lines)
    for i, c in enumerate(cands):
        if tuple(L.runs_text(r).strip() for r in c["lines"]) == want:
            return i + 1
    return 0                            # offered nothing like it


have = set(font_families())
per = collections.defaultdict(list)
for b in BLOCKS:
    r = rank_of(b, have)
    if r is not None:
        per[b["chapter"]].append(r)

rows = []
for ch, ranks in per.items():
    n = len(ranks)
    rows.append((100.0 * sum(1 for r in ranks if r == 1) / n,
                 100.0 * sum(1 for r in ranks if 1 <= r <= 3) / n, n, ch))
rows.sort()

print("%-26s %6s %8s %9s" % ("chapter", "blocks", "first", "top three"))
for first, top3, n, ch in rows:
    print("%-26s %6d %7.1f %% %7.1f %%" % (ch, n, first, top3))

alln = sum(r[2] for r in rows)
allfirst = sum(r[0] * r[2] for r in rows) / alln
alltop = sum(r[1] * r[2] for r in rows) / alln
print("%-26s %6d %7.1f %% %7.1f %%" % ("ALL", alln, allfirst, alltop))

if DROP:
    kept = rows[DROP:]
    n = sum(r[2] for r in kept)
    f = sum(r[0] * r[2] for r in kept) / n
    t = sum(r[1] * r[2] for r in kept) / n
    print()
    print("without the %d weakest chapters (%s):"
          % (DROP, ", ".join(r[3] for r in rows[:DROP])))
    print("%-26s %6d %7.1f %% %7.1f %%" % ("KEPT", n, f, t))
