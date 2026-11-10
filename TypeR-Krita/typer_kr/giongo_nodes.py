# -*- coding: utf-8 -*-
"""The outline of a letter as points you can take hold of.

Qt-free, like the rest of the Giongo core. A letter that has been opened
for point editing keeps its outline here instead of taking it from the
font: a list of contours, each a closed ring of nodes, in the glyph's own
em - the same coordinates a liquify warp uses, so both follow the letter
wherever the layout puts it.

A node is ``[x, y, ix, iy, ox, oy, smooth]``:

=========  ==================================================
x, y       where the point sits
ix, iy     the handle the curve arrives on, as an offset
ox, oy     the handle it leaves on, as an offset
smooth     1 = the two handles are kept in line, 0 = a corner
=========  ==================================================

Segments are always cubic: a straight line is simply a segment whose two
handles are zero, which is what the renderer writes out and what every
font does anyway.
"""
import json
import math

#: a node with no handles at all is a corner with straight sides
ZERO = (0.0, 0.0, 0.0, 0.0)


def node(x, y, ix=0.0, iy=0.0, ox=0.0, oy=0.0, smooth=0):
    return [float(x), float(y), float(ix), float(iy), float(ox), float(oy),
            1 if smooth else 0]


def sanitize_contours(contours):
    """Whatever came back from a file, as contours this module trusts."""
    out = []
    for c in (contours or []):
        ring = []
        for n in (c or []):
            try:
                x, y, ix, iy, ox, oy, sm = (list(n) + [0] * 7)[:7]
                ring.append(node(x, y, ix, iy, ox, oy, sm))
            except (TypeError, ValueError):
                continue
        if len(ring) >= 2:
            out.append(ring)
    return out


def sanitize_table(table):
    """The whole `nodes` table; letters with nothing usable are dropped."""
    out = {}
    for k, v in (table or {}).items():
        if not isinstance(k, str) or ":" not in k:
            continue
        a, _s, b = k.partition(":")
        if not (a.lstrip("-").isdigit() and b.lstrip("-").isdigit()):
            continue
        cs = sanitize_contours(v)
        if cs:
            out[k] = cs
    return out


def key_of(group, index):
    return "%d:%d" % (int(group), int(index))


def nodes_of(params, group, index):
    """The stored outline of one letter, [] if it has none."""
    table = params.get("nodes") or {}
    return sanitize_contours(table.get(key_of(group, index)))


def set_nodes(params, group, index, contours):
    table = dict(params.get("nodes") or {})
    cs = sanitize_contours(contours)
    if cs:
        table[key_of(group, index)] = cs
    else:
        table.pop(key_of(group, index), None)
    params["nodes"] = table
    return cs


def clear_nodes(params, group=None, index=None):
    if group is None or index is None:
        params["nodes"] = {}
        return
    table = dict(params.get("nodes") or {})
    table.pop(key_of(group, index), None)
    params["nodes"] = table


def has_nodes(params, group=None, index=None):
    if group is None or index is None:
        return bool(params.get("nodes"))
    return bool(nodes_of(params, group, index))


def fingerprint(contours):
    """A short, stable string for an outline, to key a cache with."""
    if not contours:
        return ""
    return json.dumps([[[round(v, 2) for v in n] for n in c]
                       for c in contours], separators=(",", ":"))


def signed_area(ring):
    """Twice the area of the ring's points; negative = the other way."""
    total = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        total += x1 * y2 - x2 * y1
    return total


def holds(ring, x, y):
    """Is (x, y) inside this ring? Ray casting over its points."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            t = (y - y1) / (y2 - y1) if y2 != y1 else 0.0
            if x < x1 + t * (x2 - x1):
                inside = not inside
    return inside


def reverse(ring):
    """The same ring walked the other way, handles swapped with it."""
    out = []
    for n in reversed(ring):
        out.append(node(n[0], n[1], n[4], n[5], n[2], n[3], n[6]))
    return out


def centre(ring):
    """A point to ask `holds` about: the average of the ring's points."""
    n = max(1, len(ring))
    return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)


def rewind(contours):
    """Orient the contours so a non-zero fill shows the holes as holes.

    A ring sitting inside an odd number of bigger ones is a hole and has
    to run against them; every other ring runs with the outside.

    What is asked is whether a *point of* the ring lies inside another,
    not whether its middle does: a box and the hole cut in its middle
    share a middle, and asking about that turned both of them round,
    which changes nothing between them.
    """
    sizes = [abs(signed_area(r)) for r in contours]
    out = []
    for i, ring in enumerate(contours):
        px, py = ring[0][0], ring[0][1]
        depth = sum(1 for j, other in enumerate(contours)
                    if j != i and sizes[j] > sizes[i]
                    and holds(other, px, py))
        want_negative = depth % 2 == 1
        if (signed_area(ring) < 0) != want_negative:
            ring = reverse(ring)
        out.append(ring)
    return out


# --- taking hold of it ----------------------------------------------------

def nearest_node(contours, x, y, within=None):
    """(contour, node) nearest to (x, y), or None."""
    best = None
    bd = None
    for ci, ring in enumerate(contours):
        for ni, n in enumerate(ring):
            d = math.hypot(n[0] - x, n[1] - y)
            if bd is None or d < bd:
                bd, best = d, (ci, ni)
    if best is None or (within is not None and bd > within):
        return None
    return best


def handle_points(contours, ci, ni):
    """((in x, in y), (out x, out y)) of one node, in em coordinates."""
    n = contours[ci][ni]
    return (n[0] + n[2], n[1] + n[3]), (n[0] + n[4], n[1] + n[5])


def nearest_handle(contours, x, y, within=None):
    """(contour, node, "in"|"out") nearest to (x, y), or None."""
    best = None
    bd = None
    for ci, ring in enumerate(contours):
        for ni, n in enumerate(ring):
            for which, (hx, hy) in zip(("in", "out"),
                                       handle_points(contours, ci, ni)):
                if (n[2], n[3]) == (0.0, 0.0) and which == "in":
                    continue            # a handle at the point is not one
                if (n[4], n[5]) == (0.0, 0.0) and which == "out":
                    continue
                d = math.hypot(hx - x, hy - y)
                if bd is None or d < bd:
                    bd, best = d, (ci, ni, which)
    if best is None or (within is not None and bd > within):
        return None
    return best


def move_node(contours, ci, ni, dx, dy):
    """Move a point. Its handles are offsets, so they come along."""
    n = contours[ci][ni]
    n[0] += float(dx)
    n[1] += float(dy)
    return contours


def _mirror(n, which):
    """Keep a smooth node's two handles in line, the far one's length kept."""
    if not n[6]:
        return
    if which == "out":
        hx, hy = n[4], n[5]
        other = (n[2], n[3])
    else:
        hx, hy = n[2], n[3]
        other = (n[4], n[5])
    d = math.hypot(hx, hy)
    if d < 1e-9:
        return
    ol = math.hypot(*other) or d
    ux, uy = -hx / d * ol, -hy / d * ol
    if which == "out":
        n[2], n[3] = ux, uy
    else:
        n[4], n[5] = ux, uy


def move_handle(contours, ci, ni, which, x, y):
    """Put one handle at (x, y). A smooth node turns the other to match."""
    n = contours[ci][ni]
    if which == "out":
        n[4], n[5] = float(x) - n[0], float(y) - n[1]
    else:
        n[2], n[3] = float(x) - n[0], float(y) - n[1]
    _mirror(n, which)
    return contours


def set_smooth(contours, ci, ni, smooth):
    """Corner or smooth. Becoming smooth lines the handles up at once."""
    n = contours[ci][ni]
    n[6] = 1 if smooth else 0
    if n[6]:
        # the direction through the point, so a corner eases into a curve
        hx, hy = n[4] - n[2], n[5] - n[3]
        d = math.hypot(hx, hy)
        if d < 1e-9:
            prev = contours[ci][(ni - 1) % len(contours[ci])]
            nxt = contours[ci][(ni + 1) % len(contours[ci])]
            hx, hy = nxt[0] - prev[0], nxt[1] - prev[1]
            d = math.hypot(hx, hy) or 1.0
            k = min(d / 3.0, 120.0)
            n[2], n[3] = -hx / d * k, -hy / d * k
            n[4], n[5] = hx / d * k, hy / d * k
        else:
            li = math.hypot(n[2], n[3]) or d / 3.0
            lo = math.hypot(n[4], n[5]) or d / 3.0
            n[2], n[3] = -hx / d * li, -hy / d * li
            n[4], n[5] = hx / d * lo, hy / d * lo
    return contours


def toggle_smooth(contours, ci, ni):
    return set_smooth(contours, ci, ni, not contours[ci][ni][6])


def _bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    return (u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0]
            + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1]
            + t * t * t * p3[1])


def segment(contours, ci, ni):
    """The four control points of the segment that leaves node `ni`."""
    ring = contours[ci]
    a = ring[ni]
    b = ring[(ni + 1) % len(ring)]
    return ((a[0], a[1]), (a[0] + a[4], a[1] + a[5]),
            (b[0] + b[2], b[1] + b[3]), (b[0], b[1]))


def point_on(contours, ci, ni, t):
    """Where the segment leaving `ni` is, `t` of the way along."""
    p0, p1, p2, p3 = segment(contours, ci, ni)
    return _bezier(p0, p1, p2, p3, t)


def nearest_segment(contours, x, y, steps=12):
    """(contour, node, t, distance) of the outline nearest to (x, y)."""
    best = None
    for ci, ring in enumerate(contours):
        for ni in range(len(ring)):
            p0, p1, p2, p3 = segment(contours, ci, ni)
            for s in range(steps + 1):
                t = s / float(steps)
                px, py = _bezier(p0, p1, p2, p3, t)
                d = math.hypot(px - x, py - y)
                if best is None or d < best[3]:
                    best = (ci, ni, t, d)
    return best


def insert_node(contours, ci, ni, t=0.5):
    """Split the segment leaving `ni` at `t`, exactly where it ran.

    De Casteljau: the two halves together are the same curve, so adding a
    point never changes the shape - it only gives something to take hold
    of.
    """
    ring = contours[ci]
    a = ring[ni]
    b = ring[(ni + 1) % len(ring)]
    p0, p1, p2, p3 = segment(contours, ci, ni)
    t = min(max(float(t), 0.001), 0.999)

    def lerp(u, v):
        return (u[0] + (v[0] - u[0]) * t, u[1] + (v[1] - u[1]) * t)

    q0, q1, q2 = lerp(p0, p1), lerp(p1, p2), lerp(p2, p3)
    r0, r1 = lerp(q0, q1), lerp(q1, q2)
    mid = lerp(r0, r1)
    a[4], a[5] = q0[0] - a[0], q0[1] - a[1]
    b[2], b[3] = q2[0] - b[0], q2[1] - b[1]
    fresh = node(mid[0], mid[1], r0[0] - mid[0], r0[1] - mid[1],
                 r1[0] - mid[0], r1[1] - mid[1], 1)
    ring.insert(ni + 1, fresh)
    return contours


def delete_node(contours, ci, ni):
    """Take a point out. A ring of fewer than three goes with it."""
    ring = contours[ci]
    if len(ring) <= 3:
        contours.pop(ci)
        return contours
    ring.pop(ni)
    return contours


def bounds(contours):
    """(x0, y0, x1, y1) of the points and their handles, or None."""
    xs = []
    ys = []
    for ring in contours:
        for n in ring:
            xs += [n[0], n[0] + n[2], n[0] + n[4]]
            ys += [n[1], n[1] + n[3], n[1] + n[5]]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def count(contours):
    return sum(len(ring) for ring in contours)
