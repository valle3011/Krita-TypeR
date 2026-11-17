# -*- coding: utf-8 -*-
"""Does the shaper pick what the letterer picked?

For every finished block: take the words, the font and the size the
person actually used, hand the shaper a box the block would sit in, and
ask where the person's own line breaking comes out in the ranking.

**What this can and cannot say.** The bubble is not in the .kra - only
the block is - so the box has to be the block with the padding added
back. The person's shape therefore starts with the box's own
proportions, which flatters it: a pass proves little. A *miss* proves a
lot, because it means that among arrangements of the same words at the
same size in a box the person's own block fits, the scorer preferred
something else. This is a finder of failures and a guard against
regressions, not a certificate.

The line height is taken from the page (the gap between the tspans), so
the measurer matches what was really set.
"""
import io
import json
import os
import sys
import types

ROOT = r"G:\Other computers\Mein Computer\ClaudeProgram\TypeR-Krita"
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
pkg = types.ModuleType("typer_kr")
pkg.__path__ = [os.path.join(ROOT, "typer_kr")]
sys.modules.setdefault("typer_kr", pkg)

from typer_kr._qt import (QApplication, QFont,          # noqa: E402
                          QFontMetricsF, font_families)
import importlib.util as _ilu                            # noqa: E402
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
PAD = 0.12
LIMIT = 12


def measurer_for(fam, px_line_h):
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

        return (width_of, fm.horizontalAdvance(" "), px * px_line_h,
                fm.ascent(), fm.descent())
    return measurer


have = set(font_families())
ranks = []
skipped = {"font": 0, "short": 0, "oneline": 0, "nocand": 0}
misses = []

for b in BLOCKS:
    lines = [ln.strip() for ln in b["lines"]]
    if len(lines) < 2:
        skipped["oneline"] += 1
        continue
    text = " ".join(lines)
    if len(text.split()) < 3:
        skipped["short"] += 1
        continue
    if b["font"] not in have:
        skipped["font"] += 1
        continue
    px = int(round(b["px"]))
    ys = b["y"]
    gap = (ys[1] - ys[0]) if len(ys) > 1 else px * 1.0
    line_h_ratio = max(0.5, min(2.5, gap / float(px)))

    m = measurer_for(b["font"], line_h_ratio)
    width_of, space_w, line_h, _a, _d = m(px)
    block_w = max(width_of(ln) for ln in lines)
    block_h = line_h * len(lines)
    box_w = block_w / (1.0 - PAD)
    box_h = block_h / (1.0 - PAD)

    try:
        cands = L.shape_candidates(text, m, box_w, box_h, px, 8, PAD,
                                   mode="balanced", limit=LIMIT)
    except Exception:                   # noqa: BLE001
        cands = []
    if not cands:
        skipped["nocand"] += 1
        continue
    want = tuple(lines)
    rank = None
    for i, c in enumerate(cands):
        if tuple(L.runs_text(r).strip() for r in c["lines"]) == want:
            rank = i + 1
            break
    ranks.append(rank)
    if rank is None or rank > 3:
        misses.append((b, rank, cands[0]))

n = len(ranks)
hit1 = sum(1 for r in ranks if r == 1)
hit3 = sum(1 for r in ranks if r and r <= 3)
found = sum(1 for r in ranks if r)
print("blocks judged: %d   (skipped: %s)" % (n, skipped))
print()
print("the letterer's own line breaking came out ...")
print("   first            : %4d  (%.1f %%)" % (hit1, 100.0 * hit1 / n))
print("   in the top three : %4d  (%.1f %%)" % (hit3, 100.0 * hit3 / n))
print("   offered at all   : %4d  (%.1f %%)" % (found, 100.0 * found / n))
print("   not even offered : %4d  (%.1f %%)" % (n - found,
                                                100.0 * (n - found) / n))
import collections                                      # noqa: E402
print()
print("rank histogram:", dict(sorted(collections.Counter(
    r if r else 0 for r in ranks).items())))
print()
print("--- what it picked instead, where the person's shape was offered "
      "but ranked 4th or worse, or not at all (first 12) ---")
for b, rank, top in misses[:12]:
    print("%s %s  %s %dpx  rank=%s" % (b["chapter"], b["page"], b["font"],
                                       b["px"], rank))
    print("    person: %s" % " | ".join(ln.strip() for ln in b["lines"]))
    print("    shaper: %s" % " | ".join(L.runs_text(r).strip()
                                        for r in top["lines"]))
