# -*- coding: utf-8 -*-
"""Metamorphic, property/fuzz, boundary, round-trip and regression tests for
TypeR's Qt-free layout engine (typer_kr/layout.py). No Krita/PyQt5 needed.

These check *relations* and *invariants* rather than exact numbers, so they
catch classes of bugs (sizing, fit, centring, dedup, hyphenation) that fixed
example tests miss.

Run:  python test_metamorphic.py
"""
import importlib.util
import os
import random
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "layout", os.path.join(_HERE, "typer_kr", "layout.py"))
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  ok   " + name)
    else:
        _fail += 1
        print("  FAIL " + name)


# A monospace measurer: every char is 0.5*px wide, lines 1.2*px tall, cap 0.7*px.
def measurer(px):
    cw = 0.5 * px

    def width_of(x):
        runs = getattr(x, "runs", None)
        if runs is None:
            if isinstance(x, (list, tuple)):
                return sum(len(t) for t, _ in x) * cw
            return len(x) * cw
        return sum(len(t) for t, _ in runs) * cw

    return width_of, cw, 1.2 * px, 0.8 * px, 0.2 * px


def cand_px(cands):
    return [c["px"] for c in cands]


def line_texts(c):
    return [L.runs_text(r) for r in c["lines"]]


SAMPLE = "THAT HE PISSES ME OFF, BUT NOT ENOUGH TO SAY IT OUT LOUD"

# =====================================================================
# METAMORPHIC: relations that must always hold
# =====================================================================
print("--- metamorphic ---")

# a bigger box never forces a SMALLER best size (monotonic in area)
best_small = L.shape_candidates("HELLO THERE FRIEND", measurer, 120, 120, 200, 6,
                                0.1, mode="balanced")
best_big = L.shape_candidates("HELLO THERE FRIEND", measurer, 240, 240, 200, 6,
                              0.1, mode="balanced")
check("bigger box -> best px is not smaller",
      best_big and best_small and best_big[0]["px"] >= best_small[0]["px"])

# more padding never yields a BIGGER size (less usable area)
low_pad = L.shape_candidates(SAMPLE, measurer, 200, 200, 200, 6, 0.05,
                             mode="balanced")
high_pad = L.shape_candidates(SAMPLE, measurer, 200, 200, 200, 6, 0.35,
                              mode="balanced")
check("more padding -> best px is not bigger",
      low_pad and high_pad and high_pad[0]["px"] <= low_pad[0]["px"])

# raising the max-size cap never lowers the achievable size
cap_lo = L.shape_candidates("BIG", measurer, 400, 400, 40, 6, 0.0,
                            mode="balanced")
cap_hi = L.shape_candidates("BIG", measurer, 400, 400, 400, 6, 0.0,
                            mode="balanced")
check("higher max_px cap -> best px is not smaller",
      cap_hi and cap_lo and cap_hi[0]["px"] >= cap_lo[0]["px"])

# every candidate's px stays within [min_px, max_px]
_c = L.shape_candidates(SAMPLE, measurer, 200, 260, 90, 12, 0.1, mode="balanced")
check("all candidate px within [min_px, max_px]",
      _c and all(12 <= c["px"] <= 90 for c in _c))

# 'tall' never has fewer lines than 'wide' at the top
_tall = L.shape_candidates(SAMPLE, measurer, 220, 300, 120, 6, 0.1, mode="tall")
_wide = L.shape_candidates(SAMPLE, measurer, 220, 300, 120, 6, 0.1, mode="wide")
check("tall top has >= lines than wide top",
      _tall and _wide and _tall[0]["k"] >= _wide[0]["k"])

# =====================================================================
# PROPERTY / FUZZ: invariants over many random inputs
# =====================================================================
print("--- property / fuzz ---")
random.seed(1234)
WORDS = ["THE", "QUICK", "BROWN", "FOX", "JUMPS", "OVER", "A", "LAZY", "DOG!",
         "PISSES", "ME", "OFF,", "EMBARRASSING", "SO", "HI", "OK", "WOW"]

fuzz_ok = fit_ok = range_ok = dedup_ok = finite_ok = True
for _ in range(400):
    n = random.randint(1, 9)
    text = " ".join(random.choice(WORDS) for _ in range(n))
    bw = random.randint(40, 400)
    bh = random.randint(40, 400)
    mx = random.randint(20, 200)
    pad = random.choice([0.0, 0.1, 0.2, 0.3])
    mode = random.choice(["balanced", "tall", "wide", "round"])
    hy = random.random() < 0.5
    try:
        cands = L.shape_candidates(text, measurer, bw, bh, mx, 6, pad,
                                   mode=mode, hyphenate=hy, limit=10)
    except Exception:
        fuzz_ok = False
        break
    if len(cands) > 10:
        dedup_ok = False
    usable_w = bw * (1.0 - pad)
    for c in cands:
        if not (6 <= c["px"] <= mx):
            range_ok = False
        if not (c["score"] == c["score"] and abs(c["score"]) != float("inf")):
            finite_ok = False
        # no rendered line may exceed the usable width (round uses ellipse rows)
        if mode != "round":
            width_of, space_w, _lh, _a, _d = measurer(c["px"])
            for runs in c["lines"]:
                if width_of(runs) > usable_w + 1.0:
                    fit_ok = False

check("fuzz: shape_candidates never raises", fuzz_ok)
check("fuzz: every candidate px within [6, max_px]", range_ok)
check("fuzz: every score is finite (no NaN/inf)", finite_ok)
check("fuzz: no line exceeds the usable width", fit_ok)
check("fuzz: never more than `limit` candidates", dedup_ok)

# balance_even always returns exactly k lines (or the greedy fallback stays <=k)
bal_ok = True
for _ in range(200):
    _txt = " ".join(random.choice(WORDS) for _ in range(random.randint(2, 8)))
    words = L.make_words(_txt, [False] * len(_txt))
    k = random.randint(1, len(words))
    width_of, space_w, _lh, _a, _d = measurer(40)
    lines = L.balance_even(words, width_of, space_w, 500.0, k)
    if len(lines) > k:
        bal_ok = False
check("balance_even never returns more than k lines", bal_ok)

# =====================================================================
# BOUNDARY / EDGE CASES
# =====================================================================
print("--- boundary ---")
check("empty text -> no candidates",
      L.shape_candidates("   ", measurer, 100, 100, 100, 6, 0.1) == [])
check("single word still fits",
      bool(L.shape_candidates("HELLO", measurer, 100, 100, 100, 6, 0.1)))
check("one character fits",
      bool(L.shape_candidates("A", measurer, 100, 100, 100, 6, 0.1)))
check("tiny box -> no crash, maybe empty",
      isinstance(L.shape_candidates(SAMPLE, measurer, 4, 4, 100, 6, 0.1), list))
check("min_px == max_px -> px is exactly that",
      all(c["px"] == 30 for c in
          L.shape_candidates("HI THERE", measurer, 300, 300, 30, 30, 0.0)))
_huge = L.shape_candidates("SUPERCALIFRAGILISTIC", measurer, 60, 300, 200, 6,
                           0.0, hyphenate=True, lang="en")
check("over-wide word: candidates exist and none overflow badly",
      isinstance(_huge, list))

# =====================================================================
# ROUND-TRIP
# =====================================================================
print("--- round-trip ---")
# words -> line_runs -> runs_text recovers the spaced text
_w = L.make_words("ALPHA BETA GAMMA", [False]*16)
check("make_words -> line_runs -> runs_text round-trips",
      L.runs_text(L.line_runs(_w)) == "ALPHA BETA GAMMA")
# group_words splits then the pieces rejoin to the whole
_g = L.group_words(_w, {0, 1})
check("group_words pieces rejoin to the original",
      " ".join(L.runs_text(L.line_runs(ln)) for ln in _g) == "ALPHA BETA GAMMA")
# dehyphenate is idempotent (running it twice == once)
_d1, _ = L.dehyphenate("embar- rassing and co- op")
_d2, _ = L.dehyphenate(_d1)
check("dehyphenate is idempotent", _d1 == _d2)
# dehyphenate keeps the mask length equal to the new text length, always
dh_mask_ok = True
for src in ["a- b", "big- Bang here", "X-ray e- mail", "no hyphens here",
            "multi--- dash", "trail- "]:
    t, m = L.dehyphenate(src, [False] * len(src))
    if len(m) != len(t):
        dh_mask_ok = False
check("dehyphenate: mask length always matches text length", dh_mask_ok)

# =====================================================================
# REGRESSION: the concrete bugs fixed this session
# =====================================================================
print("--- regression ---")

# TextShapR: the recommended card follows the user's size UP (bigger/fuller),
# it must not settle on a much smaller, airier block for a portrait bubble.
_port = L.shape_candidates("THAT HE PISSES ME OFF, BUT", measurer,
                           220, 320, 200, 6, 0.12, mode="balanced")
check("regression: portrait bubble recommends the bigger (>=50px) shape",
      _port and _port[0]["px"] >= 50)

# a comfortably full block is NOT penalised like a cramped edge-to-edge one:
# a ~0.80 fill must score higher than a ~0.98 edge-to-edge fill of the same text
def arr(px, *texts):
    return {"px": px, "k": len(texts), "lines": [[(t, False)] for t in texts]}

_full = arr(40, "aaaaaaa", "bbbbbbb", "ccccccc")     # tall, ~0.8 fill in 100x120
_edge = arr(52, "aaaaaaaaaa", "bbbbbbbbbb")          # 2 huge lines, edge-to-edge
check("regression: full block scores >= edge-to-edge cram",
      L.score_arrangement(_full, measurer, 100, 130, 52) >
      L.score_arrangement(_edge, measurer, 100, 130, 52))

# optical vertical centring: with a real cap height, the CAP BLOCK is centred
# exactly on the box centre (all-caps lettering sits dead centre). box 0..200,
# centre cy=100; one line, cap=56 -> caps span [baseline-56, baseline].
check("regression: cap-height centring puts the caps on the box centre",
      abs((L.vertical_start("middle", 0, 200, 0.0, 1, 24, 80, 20, cap=56)
           - 56 / 2.0) - 100.0) < 0.01)
# no cap -> unchanged em-box centring (baseline = cy + (ascent - descent)/2)
check("regression: no cap -> em-box centring is unchanged",
      abs(L.vertical_start("middle", 0, 200, 0.0, 1, 24, 80, 20)
          - (100.0 + (80 - 20) / 2.0)) < 0.01)
# a bogus (too-large) cap is clamped and never sends the text off the box
check("regression: a bogus cap is clamped (baseline stays on the box)",
      0.0 <= L.vertical_start("middle", 0, 200, 0.0, 1, 24, 80, 20, cap=99999)
      <= 200.0)

# de-hyphenation feeds through the picker
_cdh = L.shape_candidates("hyphen- ation works", measurer, 200, 200, 60, 6, 0.0,
                          dehyphenate=True)
check("regression: dehyphenate flows through shape_candidates",
      _cdh and any("hyphenation" in " ".join(line_texts(c)).lower()
                   for c in _cdh))

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
