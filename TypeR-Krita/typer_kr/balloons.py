# -*- coding: utf-8 -*-
"""Speech-balloon shape library.

Every balloon shape is a signal the reader decodes instantly: an oval is a
normal voice, a cloud is a thought, a spiky burst is a shout, an evenly jagged
outline is a radio or a phone. A typesetter needs to draw all of them, so this
module generates each one as an SVG path that fills a given box.

The shapes are generated rather than hand-drawn: a closed ring of points around
the box's center whose radius is modulated per angle, then either joined with
straight lines (the angular shapes) or smoothed into bezier curves (the round
ones). One `mod` function per shape is the whole difference between a cloud and
a shout — see SHAPES.

Qt-free on purpose: the geometry is testable without Krita, and typer_kr only
has to hand the path to addShapesFromSvg. The conventions follow the same
sources as texttypes.py (Blambot, Nekyou, Insidescanlation).
"""
import math

# --- the ring generator ----------------------------------------------------


def _catmull_rom(points):
    """A closed smooth path through `points` (Catmull-Rom as cubic beziers).

    Each segment's control points come from the neighbours' difference, which
    is what turns a modulated ring into round cloud lobes instead of a polygon.
    """
    n = len(points)
    d = "M{:.2f},{:.2f}".format(points[0][0], points[0][1])
    for i in range(n):
        p0 = points[(i - 1) % n]
        p1 = points[i]
        p2 = points[(i + 1) % n]
        p3 = points[(i + 2) % n]
        c1x = p1[0] + (p2[0] - p0[0]) / 6.0
        c1y = p1[1] + (p2[1] - p0[1]) / 6.0
        c2x = p2[0] - (p3[0] - p1[0]) / 6.0
        c2y = p2[1] - (p3[1] - p1[1]) / 6.0
        d += "C{:.2f},{:.2f} {:.2f},{:.2f} {:.2f},{:.2f}".format(
            c1x, c1y, c2x, c2y, p2[0], p2[1])
    return d + "Z"


def _polygon(points):
    d = "M{:.2f},{:.2f}".format(points[0][0], points[0][1])
    for (px, py) in points[1:]:
        d += "L{:.2f},{:.2f}".format(px, py)
    return d + "Z"


def _lcg(seed):
    """The small deterministic generator the shapes use for jitter. Seeded, so
    a 'rough' balloon looks the same every time it is inserted — a balloon that
    reshuffled itself on every redraw would be unusable."""
    state = [seed]

    def rnd():
        state[0] = (state[0] * 9301 + 49297) % 233280
        return state[0] / 233280.0
    return rnd


def _ring(mod, steps):
    """Points of a closed ring on the unit circle, radius modulated by
    `mod(angle, index)`."""
    pts = []
    for i in range(steps):
        a = i / float(steps) * math.pi * 2.0
        r = mod(a, i)
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def _fit(points, x, y, w, h):
    """Map the generated points onto the target box exactly.

    The shapes modulate past r=1 (a burst's spikes) or stay well inside it, so
    fitting the actual bounding box — rather than assuming a unit circle — is
    what makes every shape fill the same box the caller asked for.
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    sx = w / (x1 - x0) if x1 > x0 else 1.0
    sy = h / (y1 - y0) if y1 > y0 else 1.0
    return [(x + (px - x0) * sx, y + (py - y0) * sy) for (px, py) in points]


# --- the shapes ------------------------------------------------------------
# Each entry: the radius modulation, how many points to sample it at, and
# whether the ring is smoothed (round) or joined straight (angular).

def _mod_oval(a, i):
    return 1.0


def _mod_cloud(a, i):
    # 4.5 lobes around the ring: the classic thought-bubble scallop
    return 0.86 + 0.14 * abs(math.cos(a * 4.5))


def _mod_burst(a, i):
    # long spikes alternating with a deep inset = an explosion
    return 0.6 if i % 2 else 1.02


def _mod_radio(a, i):
    # the same idea as burst but shallow and even: an electronic voice
    return 0.82 if i % 2 else 1.0


def _mod_wavy(a, i):
    # a slow 7-per-turn wobble: the deflated, weak voice
    return 0.94 + 0.07 * math.sin(a * 7)


SHAPES = {
    "oval":   {"mod": _mod_oval,  "steps": 48, "smooth": True},
    "dashed": {"mod": _mod_oval,  "steps": 48, "smooth": True, "dash": True},
    "cloud":  {"mod": _mod_cloud, "steps": 44, "smooth": True},
    "burst":  {"mod": _mod_burst, "steps": 22, "smooth": False},
    "radio":  {"mod": _mod_radio, "steps": 32, "smooth": False},
    "wavy":   {"mod": _mod_wavy,  "steps": 60, "smooth": True},
    "rough":  {"mod": None,       "steps": 26, "smooth": False, "seed": 7},
    "robot":  {"mod": None,       "steps": 0,  "smooth": False},
}

# stable order for the UI: the everyday shapes first
SHAPE_ORDER = ["oval", "cloud", "burst", "radio", "dashed", "robot", "wavy",
               "rough"]

# which text type each shape belongs to (texttypes.py ids), for the UI hint
SHAPE_FOR_TYPE = {
    "oval": "dialogue", "cloud": "thought", "burst": "shout",
    "radio": "radio", "dashed": "whisper", "robot": "robot",
    "wavy": "weak", "rough": "monster",
}


def shape_points(shape, x, y, w, h):
    """The fitted outline points of `shape`, or None. The tail needs these too
    — it has to start ON the outline, not at a guessed offset inside it."""
    spec = SHAPES.get(shape)
    if spec is None or w <= 0 or h <= 0:
        return None
    if shape == "robot":
        # a rectangle with its corners cut off — the synthetic-voice balloon.
        # Not a ring: the cut is a fixed fraction of the box, so it stays a
        # crisp chamfer instead of scaling into a curve.
        c = min(w, h) * 0.18
        return [(x + c, y), (x + w - c, y), (x + w, y + c), (x + w, y + h - c),
                (x + w - c, y + h), (x + c, y + h), (x, y + h - c), (x, y + c)]
    if spec.get("seed") is not None:
        rnd = _lcg(spec["seed"])
        pts = _ring(lambda a, i: 0.8 + rnd() * 0.3, spec["steps"])
    else:
        pts = _ring(spec["mod"], spec["steps"])
    return _fit(pts, x, y, w, h)


def balloon_path(shape, x, y, w, h):
    """The SVG path data for `shape` filling the box (x, y, w, h)."""
    pts = shape_points(shape, x, y, w, h)
    if pts is None:
        return None
    return (_catmull_rom(pts) if SHAPES[shape]["smooth"] else _polygon(pts))


def _bottom_crossing(pts, xt):
    """Where the outline crosses the vertical line x=xt on its BOTTOM side, as
    ((x, y), segment_index). Interpolated onto the outline rather than snapped
    to the nearest vertex, so it lands exactly on the edge for every shape —
    including the robot, whose bottom is one long segment with no vertex near
    the tail at all."""
    n = len(pts)
    best = None
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        if a[0] == b[0] or (a[0] - xt) * (b[0] - xt) > 0:
            continue
        t = (xt - a[0]) / (b[0] - a[0])
        py = a[1] + t * (b[1] - a[1])
        if best is None or py > best[0][1]:
            best = ((xt, py), i)
    return best


def _walk(pts, i_from, i_to, forward):
    """The outline vertices from segment `i_from` to segment `i_to`, going one
    way round the ring."""
    n = len(pts)
    out = []
    i = (i_from + 1) % n if forward else i_from
    stop = i_to if forward else (i_to + 1) % n
    while len(out) <= n:
        out.append(pts[i])
        if i == stop:
            break
        i = (i + 1) % n if forward else (i - 1) % n
    return out


def _base_arc(pts, i_l, i_r):
    """The stretch of outline between the two tail-base crossings that runs
    along the BOTTOM of the balloon (of the ring's two possible ways round,
    the one whose vertices sit lower)."""
    if i_l == i_r:
        return []                      # both crossings on one straight edge
    fwd = _walk(pts, i_l, i_r, True)
    bwd = _walk(pts, i_l, i_r, False)
    mean = lambda a: sum(p[1] for p in a) / float(len(a)) if a else 0.0
    return fwd if mean(fwd) >= mean(bwd) else bwd


def tail_path(shape, x, y, w, h):
    """The tail that points at the speaker, hanging off the bottom-left of the
    balloon (the common default; a real tail follows the mouth, which is the
    typesetter's call once the shape is on the page).

    Returns a list of path/shape dicts. The tail's base is not a chord across
    the balloon but the balloon's own outline between the two base points, so
    the tail can never draw a line through the balloon's interior — which a
    straight base does, and which no amount of stacking hides (Krita does not
    stack addShapesFromSvg shapes in document order).
    """
    pts = shape_points(shape, x, y, w, h)
    if pts is None:
        return []
    tip_x = x + w * 0.16
    tip_y = y + h * 1.30       # below the box: the tail hangs out
    if shape == "cloud":
        # a thought trail: shrinking circles instead of a spike
        return [
            {"kind": "circle", "cx": x + w * 0.30, "cy": y + h * 1.06,
             "r": min(w, h) * 0.085},
            {"kind": "circle", "cx": tip_x, "cy": y + h * 1.24,
             "r": min(w, h) * 0.05},
        ]
    cl = _bottom_crossing(pts, x + w * 0.26)
    cr = _bottom_crossing(pts, x + w * 0.50)
    if cl is None or cr is None:
        return []
    (p_l, i_l), (p_r, i_r) = cl, cr
    base = [p_l] + _base_arc(pts, i_l, i_r) + [p_r]
    if shape in ("radio", "robot"):
        # a lightning bolt: the voice arrives through a wire
        mid_y = (p_r[1] + tip_y) / 2.0
        return [{"kind": "path", "d": _polygon(
            base + [(x + w * 0.44, mid_y), (x + w * 0.30, mid_y),
                    (tip_x, tip_y), (x + w * 0.26, mid_y + h * 0.04),
                    (x + w * 0.20, mid_y)])}]
    return [{"kind": "path", "d": _polygon(base + [(tip_x, tip_y)])}]


def balloon_svg(shape, x, y, w, h, img_w, img_h, fill="#ffffff",
                stroke="#000000", stroke_w=3.0, tail=True):
    """A complete SVG document with the balloon, ready for addShapesFromSvg.

    Filled white and stroked black by default: a balloon is opaque — it covers
    the artwork underneath, which is the whole point of putting text in one.
    """
    d = balloon_path(shape, x, y, w, h)
    if d is None:
        return None
    dash = ""
    if SHAPES[shape].get("dash"):
        # a whisper's outline is broken, not solid
        dash = ' stroke-dasharray="{:.1f} {:.1f}"'.format(
            stroke_w * 2.5, stroke_w * 2.0)
    common = ('fill="{f}" stroke="{s}" stroke-width="{w:.2f}" '
              'stroke-linejoin="round"').format(f=fill, s=stroke, w=stroke_w)
    body = '<path d="{d}" {c}{dash}/>'.format(d=d, c=common, dash=dash)
    if tail:
        for t in tail_path(shape, x, y, w, h):
            if t["kind"] == "circle":
                body += '<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" {c}/>'.format(
                    cx=t["cx"], cy=t["cy"], r=t["r"], c=common)
            else:
                body += '<path d="{d}" {c}/>'.format(d=t["d"], c=common)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="{w}" height="{h}">{body}</svg>'
    ).format(w=img_w, h=img_h, body=body)
