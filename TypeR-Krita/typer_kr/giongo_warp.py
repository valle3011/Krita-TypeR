# -*- coding: utf-8 -*-
"""Liquify: pushing the letters about with a brush.

Qt-free on purpose. A warp is a list of *dabs* - one per step of the
drag - and a dab is plain numbers, so the whole thing can be stored in
the parameters, shared, undone, and tested without a window.

Coordinates are the letter's own, before it is placed: the em box of the
glyph as `giongo_render.glyph()` builds it, x to the right, y down, the
middle of the box at the origin, `REF` tall. A warp therefore turns,
leans and scales with the letter it belongs to, and survives everything
the layout does to it afterwards.

A dab is ``[mode, cx, cy, r, p, q, hard]``:

===========  ====================================================
``push``     p, q are how far the brush dragged
``inflate``  p is how hard it swells (fraction of the radius)
``pinch``    p is how hard it draws in
``twirl``    p is how far it turns, in degrees
===========  ====================================================
"""
import json
import math

#: the four tools, in the order the panel offers them
MODES = ("push", "inflate", "pinch", "twirl")

#: the glyph em the coordinates are in - the same number as
#: `giongo_render._REF`, kept here too so this module needs nothing from
#: the renderer. A test holds the two together.
REF = 200.0

#: no letter may collect more than this; a drag adds one per step
MAX_DABS = 400

RANGES = {
    "liquify_size": (5, 200),       # % of the letter
    "liquify_force": (1, 100),      # %
    "liquify_hard": (0, 95),        # %
}


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def falloff(t, hard):
    """How much of the brush reaches a point `t` of the way to its rim.

    1 in the middle, 0 at the rim and outside it. `hard` holds the full
    strength out to that share of the radius and the rest eases off, so
    a hard brush dents and a soft one swells.
    """
    if t <= 0.0:
        return 1.0
    if t >= 1.0:
        return 0.0
    h = _clamp(float(hard), 0.0, 0.95)
    if t <= h:
        return 1.0
    u = (t - h) / (1.0 - h)
    return (1.0 - u * u) ** 2


def dab(mode, cx, cy, r, p=0.0, q=0.0, hard=0.0):
    """One touch of the brush, as it is stored."""
    if mode not in MODES:
        mode = "push"
    return [mode, float(cx), float(cy), max(1.0, float(r)), float(p),
            float(q), _clamp(float(hard), 0.0, 0.95)]


def invert(d):
    """The same dab the other way round - what Alt does while dragging."""
    mode, cx, cy, r, p, q, hard = d
    if mode == "inflate":
        mode = "pinch"
    elif mode == "pinch":
        mode = "inflate"
    else:
        p, q = -p, -q
    return [mode, cx, cy, r, p, q, hard]


def sanitize(dabs):
    """Whatever came out of a settings file, as dabs this module trusts."""
    out = []
    for d in (dabs or []):
        try:
            mode, cx, cy, r, p, q, hard = (list(d) + [0.0] * 7)[:7]
        except TypeError:
            continue
        if mode not in MODES:
            continue
        try:
            out.append(dab(mode, cx, cy, r, p, q, hard))
        except (TypeError, ValueError):
            continue
    return out[-MAX_DABS:]


#: how far one dab may move a point, as a share of its radius. Past
#: this the outline folds over itself instead of bending.
MAX_PULL = 0.55


def displace(x, y, dabs):
    """Where (x, y) ends up: the point plus every dab that reaches it."""
    ox = oy = 0.0
    for mode, cx, cy, r, p, q, hard in dabs:
        dx, dy = x - cx, y - cy
        if dx > r or dx < -r or dy > r or dy < -r:
            continue                    # the cheap test first: most miss
        dist = math.hypot(dx, dy)
        if dist >= r:
            continue
        f = falloff(dist / r, hard)
        if f <= 0.0:
            continue
        if mode == "push":
            ax, ay = _bounded(p * f, q * f, r * MAX_PULL)
            ox += ax
            oy += ay
        elif mode in ("inflate", "pinch"):
            if dist < 1e-6:
                continue                # the very middle has no direction
            s = p * r * f * (1.0 if mode == "inflate" else -1.0)
            # pulling in can never pull a point past the middle
            if mode == "pinch":
                s = max(s, -dist)
            ax, ay = _bounded(dx / dist * s, dy / dist * s, r * MAX_PULL)
            ox += ax
            oy += ay
        elif mode == "twirl":
            a = math.radians(p) * f
            ca, sa = math.cos(a), math.sin(a)
            ox += dx * ca - dy * sa - dx
            oy += dx * sa + dy * ca - dy
    return ox, oy


def _bounded(ox, oy, limit):
    """`(ox, oy)` no longer than `limit`, pointing the same way."""
    d = math.hypot(ox, oy)
    if d <= limit or d <= 0.0:
        return ox, oy
    k = limit / d
    return ox * k, oy * k


def warp_points(points, dabs):
    """A whole contour moved at once: [(x, y)] -> [(x, y)]."""
    if not dabs:
        return list(points)
    out = []
    for x, y in points:
        ox, oy = displace(x, y, dabs)
        out.append((x + ox, y + oy))
    return out


def reach(dabs):
    """How far outside the em box the warp can push a point.

    The renderer needs this to know whether a letter may now stick out
    beyond where its glyph was.
    """
    far = 0.0
    for mode, _cx, _cy, r, p, q, _h in dabs:
        if mode == "push":
            far = max(far, math.hypot(p, q))
        elif mode in ("inflate", "pinch"):
            far = max(far, abs(p) * r)
        elif mode == "twirl":
            far = max(far, r)
    return far


#: what one step of a drag does at full force, per tool
STEP_INFLATE = 0.035        # of the radius
STEP_TWIRL = 4.5            # degrees


def radius_for(size_pct):
    """The brush radius in the letter's own units."""
    return max(10.0, float(size_pct) / 100.0 * REF / 2.0)


def dab_for(mode, cx, cy, size_pct, force_pct, hard_pct, dx=0.0, dy=0.0):
    """The dab one step of a drag makes, from the three sliders.

    `dx, dy` is how far the pointer moved since the last step, in the
    letter's units. Push follows the hand (at full force exactly, below
    that the material lags behind, which is what the force slider is
    for); the others work on the spot.
    """
    r = radius_for(size_pct)
    f = _clamp(float(force_pct), 1.0, 100.0) / 100.0
    hard = _clamp(float(hard_pct), 0.0, 95.0) / 100.0
    if mode == "push":
        return dab("push", cx, cy, r, dx * f, dy * f, hard)
    if mode in ("inflate", "pinch"):
        return dab(mode, cx, cy, r, STEP_INFLATE * f, 0.0, hard)
    return dab("twirl", cx, cy, r, STEP_TWIRL * f, 0.0, hard)


#: how far apart dabs are laid along a drag, as a share of the radius
SPACING = 1.0 / 3.0

#: a jump right across the canvas is one gesture, not two hundred dabs
MAX_STEPS = 24


def dabs_for(mode, x0, y0, x1, y1, size_pct, force_pct, hard_pct):
    """Every dab one step of a drag leaves, in the order it leaves them."""
    r = radius_for(size_pct)
    dx, dy = float(x1) - float(x0), float(y1) - float(y0)
    dist = math.hypot(dx, dy)
    n = 1 if dist <= r * SPACING else min(
        MAX_STEPS, int(math.ceil(dist / max(1.0, r * SPACING))))
    out = []
    for i in range(1, n + 1):
        t = i / float(n)
        out.append(dab_for(mode, x0 + dx * t, y0 + dy * t, size_pct,
                           force_pct, hard_pct, dx / n, dy / n))
    return out


# --- the warps of a whole effect ------------------------------------------

def key_of(group, index):
    """The letter's name in the table, as `giongo.letter_key` makes it."""
    return "%d:%d" % (int(group), int(index))


def warp_of(params, group, index):
    """The dabs on one letter, [] if it was never touched."""
    table = params.get("warps") or {}
    return sanitize(table.get(key_of(group, index)))


def add_dab(params, group, index, d):
    """Put one more dab on a letter. Returns the dabs it now has."""
    table = dict(params.get("warps") or {})
    k = key_of(group, index)
    dabs = sanitize(table.get(k)) + [list(d)]
    table[k] = dabs[-MAX_DABS:]
    params["warps"] = table
    return table[k]


def clear_warp(params, group=None, index=None):
    """Forget the warp on one letter, or on all of them."""
    if group is None or index is None:
        params["warps"] = {}
        return
    table = dict(params.get("warps") or {})
    table.pop(key_of(group, index), None)
    params["warps"] = table


def has_warp(params, group=None, index=None):
    if group is None or index is None:
        return any(params.get("warps") or {})
    return bool(warp_of(params, group, index))


def sanitize_table(table):
    """The whole `warps` table, cleaned; empty letters dropped."""
    out = {}
    for k, v in (table or {}).items():
        if not isinstance(k, str) or ":" not in k:
            continue
        a, _s, b = k.partition(":")
        if not (a.lstrip("-").isdigit() and b.lstrip("-").isdigit()):
            continue
        dabs = sanitize(v)
        if dabs:
            out[k] = dabs
    return out


def fingerprint(dabs):
    """A short, stable string for a warp, to key a cache with."""
    if not dabs:
        return ""
    return json.dumps([[m, round(a, 2), round(b, 2), round(r, 2),
                        round(p, 3), round(q, 3), round(h, 3)]
                       for m, a, b, r, p, q, h in dabs],
                      separators=(",", ":"))
