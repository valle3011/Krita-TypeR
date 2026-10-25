# -*- coding: utf-8 -*-
"""Draw a stroke along a centre line, the way a pen or a brush would.

A letter arrives here as the centre lines of its strokes (see
`strokefont.py`); this turns one such line into the outline of a drawn
stroke, which the scene then fills like any other shape.

The shape of a stroke is one function of one variable: how wide it is at each
point along its length. A marker is the same width throughout and ends round;
a brush starts heavy and runs out to a point; a board is wider still and ends
cut at a slant. Everything else here is in service of that - resampling so
the width can change smoothly, smoothing the direction so a kink in the
centre line does not become a dent in the outline, and offsetting to both
sides.

Qt-free and standard library only: it computes points, it does not draw them.
Randomness always comes from a seed the caller gives, so the same sound with
the same settings produces the same lettering twice.
"""
import math
import random

#: the pens, in the order the interface offers them
PENS = ("pen", "marker", "brush", "board", "lightning", "rough")

#: per pen: how wide (as a share of the letter size), and how the width runs
#: from the start of a stroke to its end. The profile is sampled, so a few
#: points describe a curve.
PEN_STYLE = {
    # quiet, small sounds: thin and even, barely tapered
    "pen": dict(width=0.085, profile=((0.0, 0.75), (0.15, 1.0),
                                      (0.85, 1.0), (1.0, 0.7)),
                cap="round", wobble=0.0),
    # cute sounds: one even weight, round ends
    "marker": dict(width=0.17, profile=((0.0, 1.0), (1.0, 1.0)),
                   cap="round", wobble=0.0),
    # slashes and water: lands heavy, runs out to a point
    "brush": dict(width=0.22, profile=((0.0, 0.55), (0.12, 1.0),
                                       (0.55, 0.72), (0.88, 0.3),
                                       (1.0, 0.02)),
                  cap="taper", wobble=0.02),
    # impact and rumble: heaviest, ends cut off at a slant
    "board": dict(width=0.235, profile=((0.0, 0.95), (0.5, 1.0),
                                       (1.0, 0.9)),
                  cap="angle", angle=28.0, wobble=0.0),
    # explosions: a bolt, in few long runs with sharp turns
    "lightning": dict(width=0.19, profile=((0.0, 1.0), (0.45, 0.6),
                                           (0.5, 1.0), (1.0, 0.45)),
                      cap="angle", angle=52.0, wobble=0.0,
                      zigzag=0.032, segments=4, steps=14, smooth_rounds=0),
    # dry, scratchy: a wobbling line that thins at both ends, comes apart
    # towards the end and throws specks
    "rough": dict(width=0.17, profile=((0.0, 0.2), (0.2, 1.0),
                                       (0.8, 1.0), (1.0, 0.18)),
                  cap="round", wobble=0.07, gaps=3, gap_from=0.4,
                  specks=3),
}

#: how finely a stroke is cut up. More steps means a smoother edge and more
#: points in the finished path; 48 is where a 200 px letter stops improving.
STEPS = 48


def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def polyline_length(points):
    return sum(_dist(points[i], points[i + 1])
               for i in range(len(points) - 1))


def resample(points, count):
    """`count` points spread evenly along the line, ends included.

    A stroke arrives with its points wherever the source put them - close
    together through a curve, far apart along a straight - and a width that
    changes along the stroke needs them evenly spaced, or it changes in
    steps instead of running.
    """
    pts = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
    if len(pts) < 2:
        return [pts[0], pts[0]] if pts else []
    total = polyline_length(pts)
    if total <= 1e-9:
        return [pts[0]] * count
    out = [pts[0]]
    step = total / float(count - 1)
    target = step
    walked = 0.0
    i = 0
    while i < len(pts) - 1 and len(out) < count - 1:
        seg = _dist(pts[i], pts[i + 1])
        if seg <= 1e-12:
            i += 1
            continue
        while walked + seg >= target - 1e-12 and len(out) < count - 1:
            t = (target - walked) / seg
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t,
                        pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t))
            target += step
        walked += seg
        i += 1
    out.append(pts[-1])
    return out


def smooth(points, rounds=2):
    """Average each point with its neighbours, ends held in place.

    A simplified line turns a corner at each kept point, and every corner
    would show up in the outline as a notch.
    """
    pts = list(points)
    for _ in range(rounds):
        if len(pts) < 3:
            break
        out = [pts[0]]
        for i in range(1, len(pts) - 1):
            out.append(((pts[i - 1][0] + 2 * pts[i][0] + pts[i + 1][0]) / 4.0,
                        (pts[i - 1][1] + 2 * pts[i][1] + pts[i + 1][1]) / 4.0))
        out.append(pts[-1])
        pts = out
    return pts


def tangents(points):
    """A unit direction at every point, from its neighbours."""
    n = len(points)
    out = []
    for i in range(n):
        a = points[max(0, i - 1)]
        b = points[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        if d < 1e-9:
            out.append(out[-1] if out else (1.0, 0.0))
        else:
            out.append((dx / d, dy / d))
    return out


def profile_at(profile, t):
    """The width factor at `t` along the stroke, straight-line between the
    points that describe the profile."""
    if t <= profile[0][0]:
        return profile[0][1]
    for i in range(len(profile) - 1):
        t0, v0 = profile[i]
        t1, v1 = profile[i + 1]
        if t0 <= t <= t1:
            if t1 - t0 < 1e-9:
                return v1
            k = (t - t0) / (t1 - t0)
            return v0 + (v1 - v0) * k
    return profile[-1][1]


def _arc(centre, radius, a0, a1, steps=8):
    out = []
    for i in range(steps + 1):
        a = a0 + (a1 - a0) * i / float(steps)
        out.append((centre[0] + math.cos(a) * radius,
                    centre[1] + math.sin(a) * radius))
    return out


def zigzag(points, amount, segments, rnd):
    """Bend a line into a few long straight runs that jump sideways.

    What makes a splinter read as a splinter is the length of the straight
    parts between the turns; jitter spread over every sample only frays the
    edge.
    """
    if amount <= 0 or len(points) < 3 or segments < 2:
        return points
    n = len(points)
    out = []
    side = 1.0 if rnd.random() < 0.5 else -1.0
    for i, p in enumerate(points):
        t = i / float(n - 1)
        seg = min(segments - 1, int(t * segments))
        # position across this run, 0 at its start, 1 at its end
        local = t * segments - seg
        k = 1.0 - abs(local * 2.0 - 1.0)        # peak in the middle of a run
        j = max(0, min(n - 1, i))
        a = points[max(0, j - 1)]
        b = points[min(n - 1, j + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / d, dx / d
        off = amount * k * side * (1.0 if seg % 2 == 0 else -1.0)
        out.append((p[0] + nx * off, p[1] + ny * off))
    return out


def stroke_shapes(points, size, pen="brush", seed=0, width_scale=1.0,
                  style=None):
    """One drawn stroke as a list of closed outlines.

    Usually one, but a dry brush comes apart into several and throws specks,
    so a stroke is not always a single shape.
    """
    st = dict(PEN_STYLE.get(pen, PEN_STYLE["brush"]))
    if style:
        st.update(style)
    rnd = random.Random(seed)
    base = size * st["width"] * width_scale

    if st.get("gaps"):
        pieces = _dry_pieces(points, st, rnd)
    else:
        pieces = [(points, 0.0, 1.0)]

    out = []
    for (part, t0, t1) in pieces:
        poly = stroke_outline(part, size, pen=pen, seed=rnd.randrange(1 << 30),
                              width_scale=width_scale, style=st,
                              span=(t0, t1))
        if len(poly) >= 3:
            out.append(poly)
    for _ in range(st.get("specks", 0)):
        poly = _speck(points, base, rnd)
        if poly:
            out.append(poly)
    return out


def _dry_pieces(points, st, rnd):
    """Split a stroke where the bristles would lift, towards its end."""
    pts = resample(points, STEPS)
    n = len(pts)
    if n < 4:
        # a dot, or a stroke of no length: there is nothing to break up,
        # and asking for a cut inside it would ask for an empty range
        return [(points, 0.0, 1.0)]
    start = max(1, min(n - 2, int(n * st.get("gap_from", 0.5))))
    cuts = []
    for _ in range(st.get("gaps", 0)):
        i = rnd.randrange(start, n - 1)
        cuts.append((i, max(1, int(rnd.random() * 2) + 1)))
    blocked = set()
    for (i, width) in cuts:
        for k in range(i, min(n - 1, i + width)):
            blocked.add(k)
    pieces = []
    run = []
    for i in range(n):
        if i in blocked:
            if len(run) >= 2:
                pieces.append((run, run[0][2], run[-1][2]))
            run = []
            continue
        run.append((pts[i][0], pts[i][1], i / float(n - 1)))
    if len(run) >= 2:
        pieces.append((run, run[0][2], run[-1][2]))
    return [([(x, y) for (x, y, _t) in part], t0, t1)
            for (part, t0, t1) in pieces] or [(points, 0.0, 1.0)]


def _speck(points, base, rnd):
    """A fleck of ink beside the stroke, where a bristle flicked."""
    if len(points) < 2:
        return None
    i = rnd.randrange(len(points))
    p = points[i]
    j = min(len(points) - 1, i + 1)
    dx, dy = points[j][0] - p[0], points[j][1] - p[1]
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d, dx / d
    side = 1.0 if rnd.random() < 0.5 else -1.0
    off = base * (0.45 + rnd.random() * 0.5) * side
    r = base * (0.035 + rnd.random() * 0.055)
    return _arc((p[0] + nx * off, p[1] + ny * off), r, 0.0, math.tau, 7)


def stroke_outline(points, size, pen="brush", seed=0, width_scale=1.0,
                   style=None, span=(0.0, 1.0)):
    """The outline of one drawn stroke as a closed list of (x, y).

    `points` is the centre line, `size` the letter size in the same units -
    a pen's width is a share of it, so a stroke stays in proportion when the
    lettering is scaled. `span` says which part of the whole stroke this
    piece covers, so a broken-up dry stroke keeps one continuous taper.
    """
    st = dict(PEN_STYLE.get(pen, PEN_STYLE["brush"]))
    if style:
        st.update(style)
    rnd = random.Random(seed)

    base = size * st["width"] * width_scale
    if len(points) < 2 or polyline_length(points) < 1e-9:
        # a dot: the stroke has no length, so it is just a blob
        cx, cy = points[0] if points else (0.0, 0.0)
        return _arc((cx, cy), base * 0.5, 0.0, math.tau, 16)

    steps = int(st.get("steps", STEPS))
    pts = resample(points, steps)
    if st.get("zigzag"):
        # measured against the stroke, not only against the letter: a short
        # dakuten tick would otherwise be thrown about as far as a long
        # downstroke and stop being a tick at all
        reach = min(size * st["zigzag"], polyline_length(pts) * 0.16)
        pts = zigzag(pts, reach, int(st.get("segments", 4)), rnd)
    pts = smooth(pts, rounds=int(st.get("smooth_rounds", 2)))
    tans = tangents(pts)
    n = len(pts)

    t0, t1 = span
    half = []
    for i, p in enumerate(pts):
        # where this point sits in the WHOLE stroke, not just in this piece
        t = t0 + (t1 - t0) * (i / float(n - 1))
        w = base * profile_at(st["profile"], t) * 0.5
        if st.get("wobble"):
            w *= 1.0 + st["wobble"] * (rnd.random() - 0.5) * 2.0
        half.append(max(w, base * 0.012))

    left, right = [], []
    for i, (p, tg) in enumerate(zip(pts, tans)):
        nx, ny = -tg[1], tg[0]
        left.append((p[0] + nx * half[i], p[1] + ny * half[i]))
        right.append((p[0] - nx * half[i], p[1] - ny * half[i]))

    cap = st.get("cap", "round")
    out = list(left)
    out.extend(_end_cap(pts[-1], tans[-1], half[-1], cap, st, at_start=False))
    out.extend(reversed(right))
    out.extend(_end_cap(pts[0], tans[0], half[0], cap, st, at_start=True))
    return out


def _end_cap(p, tangent, half, cap, st, at_start):
    """The few points that close one end of a stroke.

    The outline arrives here having walked up one side; these points carry it
    across the end and leave it on the other side, so they must start at
    +normal and finish at -normal (mirrored at the start of the stroke).
    """
    tx, ty = tangent
    nx, ny = -ty, tx
    if at_start:
        tx, ty, nx, ny = -tx, -ty, -nx, -ny
    if half <= 1e-9 or cap == "taper":
        return [(p[0] + tx * half * 0.6, p[1] + ty * half * 0.6)]
    if cap == "angle":
        # a straight chord across the stroke, tilted - both ends stay on the
        # stroke's own width, which is what a flat edge leaves behind
        a = math.radians(st.get("angle", 30.0))
        ox, oy = math.cos(a), math.sin(a)
        ax, ay = nx * ox + tx * oy, ny * ox + ty * oy
        return [(p[0] + ax * half, p[1] + ay * half),
                (p[0] - ax * half, p[1] - ay * half)]
    start = math.atan2(ny, nx)
    return _arc(p, half, start, start - math.pi, 8)


def style_from(params, pen):
    """Turn the user's four numbers into changes to the pen's own shape.

    Each is a percentage of what the pen already does, so 100 leaves it
    exactly as it was made and the four sliders mean the same thing
    whichever pen is chosen.
    """
    base = PEN_STYLE.get(pen)
    if not base:
        return None
    taper = max(0.0, float(params.get("pen_taper", 100))) / 100.0
    wobble = max(0.0, float(params.get("pen_wobble", 100))) / 100.0
    angle = max(0.0, float(params.get("pen_angle", 100))) / 100.0
    dry = max(0.0, float(params.get("pen_dry", 100))) / 100.0
    out = {}
    if abs(taper - 1.0) > 1e-6:
        # the profile keeps its shape; only how far it falls away changes,
        # so a brush with a short taper is still a brush
        prof = base["profile"]
        top = max(v for (_t, v) in prof)
        out["profile"] = tuple((t, top - (top - v) * taper) for (t, v) in prof)
    if abs(wobble - 1.0) > 1e-6:
        out["wobble"] = base.get("wobble", 0.0) * wobble
        if base.get("zigzag"):
            out["zigzag"] = base["zigzag"] * wobble
    if abs(angle - 1.0) > 1e-6 and base.get("angle"):
        out["angle"] = max(0.0, min(80.0, base["angle"] * angle))
    if abs(dry - 1.0) > 1e-6 and base.get("gaps"):
        out["gaps"] = max(0, int(round(base["gaps"] * dry)))
        out["specks"] = max(0, int(round(base.get("specks", 0) * dry)))
    return out or None


def letter_outlines(lines, size, pen="brush", seed=0, width_scale=1.0,
                    style=None):
    """Every shape of one letter: usually one per stroke, more for a dry pen."""
    out = []
    # the lines arrive in the order and the direction they are written in -
    # that is the whole point of the data, and guessing at it here would
    # only undo it
    for i, line in enumerate(lines):
        out.extend(stroke_shapes(line, size, pen=pen, seed=seed + i * 7919,
                                 width_scale=width_scale, style=style))
    return out
