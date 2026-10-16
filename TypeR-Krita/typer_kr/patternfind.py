# -*- coding: utf-8 -*-
"""Find the repeating tile in a crop of a pattern.

Give it any piece of a repeating pattern - a screenshot, a scan, a corner of a
page - and it works out how far the pattern repeats across and down, so the
crop can be cut to one tile that lines up with itself.

Qt-free and standard library only: Krita's Python has no numpy, so the whole
search runs in plain Python and the cost has to be budgeted rather than
assumed.

**How a shift is scored.** For a candidate period p, the image is compared
with itself moved by p pixels: the mean absolute difference over the overlap,
divided by the mean absolute deviation of the image itself. Below 1 means
"more alike than the image is varied"; measured on real crops, a true period
lands at 0.2-0.4 and anything else sits above 0.8, which is a gap wide enough
to decide on.

**Why not projection profiles.** Summing columns into a 1D signal and looking
for its period is far cheaper, and it was the first thing tried - but measured
against the 2D score on real patterns it picks the wrong answer: on a
polka-dot crop its best period scored 0.20 in the profile and 1.87 in 2D
(nothing of the sort), while the period that really tiles scored 0.61 in the
profile, well outside any sensible cutoff. A profile throws away which *row* a
dark pixel was in, and that is exactly what tells a lattice from a
coincidence. So every candidate is scored in 2D, and the cost is kept down
instead by searching on a scaled-down copy and subsampling the comparison.
"""

#: a tile smaller than this is noise, not a pattern
MIN_PERIOD = 3
#: a period is only believable if the crop holds at least this many repeats
MIN_REPEATS = 2.0
#: a shift scoring below this counts as a period (see the module docstring)
GOOD = 0.5
#: ...and below this it is beyond doubt
STRONG = 0.3
#: a smaller period is preferred only while it is nearly as good as the best
SLACK = 1.5
#: ...or at most this much worse in absolute terms, so that noise cannot rule
#: the real period out by handing a large one a slightly better score
MARGIN = 0.15
#: how many periods get the careful treatment
MAX_CANDIDATES = 24
#: a period must be this much better than the half-shift between its repeats
CONTRAST = 2.0
#: how many pixel comparisons one score may cost (keeps the sweep ~1s)
BUDGET = 2500
#: ...and how many the final, careful re-scoring of the survivors may cost
FINE_BUDGET = 60000
#: tiles larger than this are not searched for - no screentone is that big,
#: and the sweep costs one score per candidate
MAX_TILE = 300


def to_gray(pixels, bpp):
    """Interleaved pixel bytes -> one byte per pixel.

    bpp 1 is already grey; 3 and 4 are B,G,R(,A) the way Qt hands them over.
    The green channel alone would do for a quick job, but a pattern drawn in
    pure red on black would then be invisible.
    """
    if bpp == 1:
        return bytes(pixels)
    out = bytearray(len(pixels) // bpp)
    for i in range(len(out)):
        j = i * bpp
        out[i] = (pixels[j] + pixels[j + 1] + pixels[j + 2]) // 3
    return bytes(out)


def _mean_dev(gray, w, h, step):
    """(mean, mean absolute deviation) of the sampled pixels."""
    total = 0
    n = 0
    for y in range(0, h, step):
        r = y * w
        for x in range(0, w, step):
            total += gray[r + x]
            n += 1
    if not n:
        return 0.0, 0.0
    mean = total / float(n)
    dev = 0.0
    for y in range(0, h, step):
        r = y * w
        for x in range(0, w, step):
            v = gray[r + x]
            dev += v - mean if v >= mean else mean - v
    return mean, dev / float(n)


def step_for(w, h, budget=BUDGET):
    """Sampling step that keeps one score inside the budget."""
    cells = w * h
    if cells <= budget:
        return 1
    s = int((cells / float(budget)) ** 0.5)
    return max(1, s)


def shift_score(gray, w, h, dx, dy, step=None, dev=None):
    """How alike the image is to itself moved by (dx, dy). Lower is better.

    None when the shift leaves too little overlap to judge, or when the image
    is so flat that nothing can be told apart.
    """
    if dx >= w or dy >= h:
        return None
    if step is None:
        step = step_for(w, h)
    if dev is None:
        _m, dev = _mean_dev(gray, w, h, step)
    if dev <= 1e-6:
        return None
    total = 0.0
    count = 0
    for y in range(0, h - dy, step):
        r1 = y * w
        r2 = (y + dy) * w + dx
        for x in range(0, w - dx, step):
            a = gray[r1 + x]
            b = gray[r2 + x]
            total += a - b if a >= b else b - a
            count += 1
    if count < 16:                      # too little overlap to mean anything
        return None
    return (total / float(count)) / dev


def sweep(gray, w, h, axis, max_p=None):
    """[(period, score), ...] for every candidate period along one axis.

    Scored at full resolution: a period is an integer number of pixels in the
    image the user loaded, and scaling that image first would turn it into a
    fraction (measured: a 12 px period in a 240 px crop came back as 59 after
    a 1.25x shrink, because no small integer fits any more). The cost stays
    bounded through the sampling step and MAX_TILE instead.
    """
    n = w if axis == 0 else h
    if max_p is None:
        max_p = min(int(n / MIN_REPEATS), MAX_TILE)
    step = step_for(w, h)
    _m, dev = _mean_dev(gray, w, h, step)
    out = []
    for p in range(MIN_PERIOD, max_p + 1):
        s = (shift_score(gray, w, h, p, 0, step, dev) if axis == 0
             else shift_score(gray, w, h, 0, p, step, dev))
        if s is not None:
            out.append((p, s))
    return out


def _score_at(scored, p):
    """The swept score for period `p`, or None when it was not swept."""
    for q, s in scored:
        if q == p:
            return s
    return None


def has_contrast(scored, p, s):
    """Does the image actually come apart between two repeats?

    A smooth gradient is nearly identical to itself under any small shift and
    would otherwise be reported as a pattern with a tiny tile (measured: a
    plain left-to-right gradient scored 0.047 at a shift of 3). On a real
    pattern the half-shift puts dots between dots and scores far worse; on a
    gradient it scores just as well. One ratio tells them apart.
    """
    half = _score_at(scored, max(MIN_PERIOD, p // 2))
    if half is None:
        return True                     # nothing to compare against: allow it
    if s <= 1e-6:
        return half > 1e-6              # exact repeat, and the half is not
    return (half / s) >= CONTRAST


def divisors(p, lowest=MIN_PERIOD):
    """Every divisor of p down to `lowest`, smallest first.

    If a pattern repeats every p pixels and its real period is shorter, that
    period divides p - so the divisors are where to look for it.
    """
    out = []
    for d in range(lowest, p // 2 + 1):
        if p % d == 0:
            out.append(d)
    return out


def candidates(scored):
    """Periods worth a closer look: the sweep's local minima and the divisors
    of each, smallest first.

    The divisors matter when the sweep is noisy: its scores jitter, so the
    fundamental may not be a local minimum while one of its multiples is
    (measured: dots 12 px apart under heavy noise came out as 108).
    """
    if not scored:
        return []
    best = min(s for _p, s in scored)
    if best >= GOOD:
        return []
    found = []
    for i, (p, s) in enumerate(scored):
        if s >= GOOD:
            continue
        prev_s = scored[i - 1][1] if i > 0 else float("inf")
        next_s = scored[i + 1][1] if i + 1 < len(scored) else float("inf")
        if s <= prev_s and s <= next_s:
            found.append((p, s))
    found.sort(key=lambda ps: ps[1])            # best-scoring first
    out = []
    for p, _s in found:
        for q in divisors(p) + [p - 1, p, p + 1]:
            if q >= MIN_PERIOD and q not in out:
                out.append(q)
        if len(out) >= MAX_CANDIDATES:
            break
    out.sort()
    return out[:MAX_CANDIDATES]


def pick_period(scored, gray=None, w=0, h=0, axis=0):
    """The fundamental period out of a sweep, or None.

    Multiples of a period score just as well as the period itself, so the
    smallest believable one wins - but only while it is nearly as good as the
    best score around (SLACK). Without that, a half-period that merely looks
    plausible would beat the real one.

    The sweep's scores are subsampled and can tie two neighbouring periods
    that are not actually equal, so when the image is passed in, every
    survivor is re-scored pixel by pixel first.
    """
    cands = candidates(scored)
    if not cands:
        return None
    fine = {}
    if gray is not None:
        step = step_for(w, h, FINE_BUDGET)
        _m, dev = _mean_dev(gray, w, h, step)
        for p in cands + [max(MIN_PERIOD, c // 2) for c in cands]:
            if p in fine:
                continue
            fine[p] = (shift_score(gray, w, h, p, 0, step, dev) if axis == 0
                       else shift_score(gray, w, h, 0, p, step, dev))
    def score_of(p):
        s = fine.get(p)
        return s if s is not None else _score_at(scored, p)

    graded = [(p, score_of(p)) for p in cands]
    graded = [(p, s) for p, s in graded if s is not None]
    graded = _collapse(graded)
    if not graded:
        return None
    best = min(s for _p, s in graded)
    if best >= GOOD:
        return None
    limit = min(GOOD, max(best * SLACK, best + MARGIN))
    for p, s in graded:
        if s > limit:
            continue
        half = score_of(max(MIN_PERIOD, p // 2))
        if half is None or _contrast_ok(s, half):
            return p, s
    return None


def _collapse(graded):
    """Keep only the bottom of each run of adjacent periods.

    p-1, p and p+1 are the same dip sampled at three offsets; without this the
    rule "prefer the smaller period" would take the shoulder of a dip over its
    bottom (measured: 30 at 0.11 chosen over 31 at 0.00).
    """
    out = []
    run = []
    for p, s in sorted(graded):
        if run and p == run[-1][0] + 1:
            run.append((p, s))
            continue
        if run:
            out.append(min(run, key=lambda ps: ps[1]))
        run = [(p, s)]
    if run:
        out.append(min(run, key=lambda ps: ps[1]))
    return out


def _contrast_ok(s, half):
    """Does the half-shift score far worse than the period? (see has_contrast)"""
    if s <= 1e-6:
        return half > 1e-6
    return (half / s) >= CONTRAST


def find_tile(pixels, w, h, bpp=1):
    """Work out the repeating tile of a crop.

    Returns a dict:
        tile_w, tile_h   the repeat (None on an axis with no repeat)
        score_x, score_y how alike the crop is at that shift (0 = identical)
        confidence       0..1, from the weaker of the two axes
        repeats_x/y      how often the tile fits in the crop
    or None when the crop shows no repeat at all.

    An axis without a repeat is a real answer, not a failure: a halftone
    gradient repeats across but never down, and saying so is more use than
    inventing a height.
    """
    if w < 2 * MIN_PERIOD or h < 2 * MIN_PERIOD:
        return None
    gray = to_gray(pixels, bpp)
    px = pick_period(sweep(gray, w, h, 0), gray, w, h, 0)
    py = pick_period(sweep(gray, w, h, 1), gray, w, h, 1)
    if px is None and py is None:
        return None
    tw, sx = px if px else (None, None)
    th, sy = py if py else (None, None)
    scores = [s for s in (sx, sy) if s is not None]
    worst = max(scores) if scores else 1.0
    return {
        "tile_w": tw, "tile_h": th,
        "score_x": sx, "score_y": sy,
        "confidence": max(0.0, min(1.0, 1.0 - worst / GOOD)),
        "strong": all(s < STRONG for s in scores),
        "repeats_x": (w / float(tw)) if tw else 0.0,
        "repeats_y": (h / float(th)) if th else 0.0,
    }


def average_tile(pixels, w, h, tile_w, tile_h, bpp=1, x0=0, y0=0):
    """One tile, averaged over every repeat the crop holds.

    A single crop carries the source's noise, JPEG ringing and anti-aliasing;
    averaging the repeats cancels most of it, and a crop holding twenty
    repeats gives a far cleaner tile than any one of them. Returns the pixel
    bytes of the tile, same bpp as the input.
    """
    tile_w = tile_w or w
    tile_h = tile_h or h
    sums = [0] * (tile_w * tile_h * bpp)
    counts = [0] * (tile_w * tile_h)
    for y in range(y0, h):
        ty = (y - y0) % tile_h
        for x in range(x0, w):
            tx = (x - x0) % tile_w
            src = (y * w + x) * bpp
            cell = ty * tile_w + tx
            counts[cell] += 1
            dst = cell * bpp
            for c in range(bpp):
                sums[dst + c] += pixels[src + c]
    out = bytearray(tile_w * tile_h * bpp)
    for i in range(tile_w * tile_h):
        n = counts[i] or 1
        for c in range(bpp):
            out[i * bpp + c] = sums[i * bpp + c] // n
    return bytes(out)


def is_binary(gray, threshold=0.9):
    """Is this two-tone (screentone, hatching) rather than shaded?

    Averaging repeats leaves grey edges on a black-and-white pattern; knowing
    it was two-tone to begin with is what lets the caller put the crispness
    back instead of shipping a blurred tile.
    """
    if not gray:
        return False
    dark = sum(1 for v in gray if v < 64)
    light = sum(1 for v in gray if v > 191)
    return (dark + light) / float(len(gray)) >= threshold


def threshold_tile(tile, bpp=1, level=128):
    """Push an averaged tile back to black and white."""
    out = bytearray(tile)
    n = len(tile) // bpp
    for i in range(n):
        j = i * bpp
        v = tile[j] if bpp == 1 else (tile[j] + tile[j + 1] + tile[j + 2]) // 3
        hit = 0 if v < level else 255
        for c in range(min(3, bpp)):
            out[j + c] = hit
    return bytes(out)

def crop_tile(pixels, w, h, tile_w, tile_h, bpp=1, x0=0, y0=0):
    """One repeat cut straight out of the crop, no averaging."""
    out = bytearray(tile_w * tile_h * bpp)
    for ty in range(tile_h):
        sy = (y0 + ty) % h
        for tx in range(tile_w):
            sx = (x0 + tx) % w
            src = (sy * w + sx) * bpp
            dst = (ty * tile_w + tx) * bpp
            out[dst:dst + bpp] = pixels[src:src + bpp]
    return bytes(out)


def seam_ratio(tile, tile_w, tile_h):
    """How much the wrap-around edges stand out, 1.0 being not at all.

    The step across the seam is compared with the average step inside the
    tile: a tile cut at the right period continues into itself no more
    abruptly than it changes anywhere else, whatever the pattern looks like.
    """
    if tile_w < 2 or tile_h < 2:
        return 1.0
    inner_x = seam_x = 0.0
    for y in range(tile_h):
        row = y * tile_w
        for x in range(1, tile_w):
            a, b = tile[row + x], tile[row + x - 1]
            inner_x += a - b if a >= b else b - a
        a, b = tile[row], tile[row + tile_w - 1]
        seam_x += a - b if a >= b else b - a
    inner_x /= float(tile_h * (tile_w - 1))
    seam_x /= float(tile_h)

    inner_y = seam_y = 0.0
    for x in range(tile_w):
        for y in range(1, tile_h):
            a, b = tile[y * tile_w + x], tile[(y - 1) * tile_w + x]
            inner_y += a - b if a >= b else b - a
        a, b = tile[x], tile[(tile_h - 1) * tile_w + x]
        seam_y += a - b if a >= b else b - a
    inner_y /= float(tile_w * (tile_h - 1))
    seam_y /= float(tile_w)

    rx = seam_x / inner_x if inner_x > 1e-6 else 1.0
    ry = seam_y / inner_y if inner_y > 1e-6 else 1.0
    return max(rx, ry)


def tile_score(tile_gray, tile_w, tile_h, src_dev):
    """(score, seam, detail) for a finished tile - lower score is better.

    `detail` is the tile's own contrast against the crop's, and it carries the
    decision: the candidates differ in whether they kept the pattern or
    averaged it into grey, not in where their edges fall. Averaging repeats of
    a pattern whose period is not a whole number of pixels flattens it - on a
    real crop that produced detail 0.14 against 1.03 for a single repeat.

    `seam` only breaks ties. Taken on its own it punishes a tile that is
    exactly right but happens to cut through a dot (measured: 2.5 on a tile
    whose period scores were both 0.000), because a screentone is mostly flat
    white and any edge looks dramatic against that average. How the two edges
    meet is already measured, properly, by the period's own score.
    """
    seam = seam_ratio(tile_gray, tile_w, tile_h)
    _m, dev = _mean_dev(tile_gray, tile_w, tile_h, 1)
    detail = (dev / src_dev) if src_dev > 1e-6 else 0.0
    return 4.0 * max(0.0, 1.0 - detail) + 0.1 * seam, seam, detail


def best_tile(pixels, w, h, tile_w, tile_h, bpp=1, gray=None):
    """The tile to actually hand over, chosen by how well it tiles.

    Tries a repeat cut from a few places in the crop and the average of all
    of them, and keeps whichever tiles best - see tile_score. Returns
    (tile bytes, tile_w, tile_h, score, how, seam, detail), where `how` is
    "single" or "averaged".
    """
    tile_w = max(1, tile_w or w)
    tile_h = max(1, tile_h or h)
    if gray is None:
        gray = to_gray(pixels, bpp)
    offsets = [(0, 0)]
    if w > 2 * tile_w and h > 2 * tile_h:       # the middle of the crop too
        offsets.append(((w - tile_w) // 2, (h - tile_h) // 2))
    _m, src_dev = _mean_dev(gray, w, h, step_for(w, h, FINE_BUDGET))
    best = None
    tries = [(crop_tile(pixels, w, h, tile_w, tile_h, bpp, x0, y0), "single")
             for (x0, y0) in offsets]
    tries.append((average_tile(pixels, w, h, tile_w, tile_h, bpp), "averaged"))
    for tile, how in tries:
        gt = tile if bpp == 1 else to_gray(tile, bpp)
        score, seam, detail = tile_score(gt, tile_w, tile_h, src_dev)
        if best is None or score < best[3]:
            best = (tile, tile_w, tile_h, score, how, seam, detail)
    return best
