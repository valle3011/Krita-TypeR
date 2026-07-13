# -*- coding: utf-8 -*-
"""Pure speech-bubble detection and reading-order logic (Qt-free).

Input is a grayscale grid as ``bytes``/``bytearray`` plus its width/height —
the docker converts Krita's pixel data to that; nothing in this module touches
Qt or Krita, so everything is testable with plain ``python``.

Pipeline (see ``detect_bubbles``):

1. downscale by integer stride so the working grid is small enough for pure
   Python (slicing keeps this at C speed),
2. threshold to a white mask (``bytes.translate`` with a 256-entry table),
3. connected components on the white mask (iterative BFS, 4-neighborhood),
4. filter the components down to plausible bubbles (area, aspect, fill
   ratio, border contact, optional dark-outline check on the pixels directly
   around the component),
5. merge overlapping/nested boxes (e.g. a bubble split by its tail),
6. map the boxes back to full-resolution coordinates and suggest a shape
   ("round" for ellipse-like components, else "rect").

All thresholds are keyword arguments with named defaults so a UI can expose
them later without touching the algorithm.
"""

from collections import deque

# --- named default thresholds ----------------------------------------------

BRIGHT_THRESH = 215      # luminance >= this counts as "white-ish"
MIN_AREA_FRAC = 0.0005   # component area >= 0.05 % of the page
MAX_AREA_FRAC = 0.20     # ... and <= 20 % of the page
MIN_ASPECT = 0.2         # bbox width / height between these two
MAX_ASPECT = 5.0
MIN_FILL_RATIO = 0.55    # component px / bbox px (bubbles are convex-ish)
RECT_FILL_RATIO = 0.92   # >= this fills its bbox like a rectangle; below it
                         # the bubble is treated as round (an ellipse fills
                         # ~pi/4 = 0.785 of its bbox)
MAX_BORDER_FRAC = 0.05   # reject when the component covers more than this
                         # fraction of the image border (background/margins)
DARK_THRESH = 80         # grayscale value <= this counts as "dark" (outline)
MIN_OUTLINE_FRAC = 0.55  # dark fraction required just outside the component
                         # (checked at full resolution, so real bubbles score
                         # near 1.0; fuzzy white glow regions fail)
MIN_BOX_PX = 28          # bbox must be at least this wide AND high (full-res
                         # pixels) — kills tiny slivers on huge pages
MAX_GRID_W = 600         # downscale target width for the working grid

# "bubbles must contain text": fraction of dark pixels in the core region of
# the bbox (raw pages always have the JP text inside the bubble)
CORE_FRAC = 0.55         # central part of the bbox that is sampled
MIN_TEXT_FRAC = 0.01     # below: empty highlight/sparkle -> rejected
MAX_TEXT_FRAC = 0.45     # above: heavy art lines / stripe pattern -> rejected

# neck splitting (joined double bubbles)
NECK_RATIO = 0.5         # waist must be thinner than this x the smaller lobe
MIN_LOBE_FRAC = 0.25     # both lobes cover at least this of the bbox extent

# free text / SFX detection (dark character-sized blobs clustered together)
SFX_DARK_THRESH = 100    # grid value <= this is "ink" for the sfx pass
SFX_MIN_AREA = 6         # character component size window (grid cells)
SFX_MAX_AREA = 800
SFX_MIN_EXT = 3          # ... and bbox extent window (grid cells)
SFX_MAX_EXT = 60
SFX_GAP_FACTOR = 1.2     # cluster when the bbox gap < this x larger extent
SFX_MIN_MEMBERS = 2      # a lone blob is usually art, not text
SFX_PAD_FRAC = 0.20      # padding added around the cluster bbox
SFX_MAX_COMPONENTS = 600 # more char-sized blobs than this = page too busy,
                         # skip the sfx pass instead of guessing


# --- grid helpers ------------------------------------------------------------

def downscale(gray, width, height, max_w=MAX_GRID_W):
    """Sample `gray` (len == width*height) with an integer stride so the
    result is at most `max_w` wide. Returns (grid, gw, gh, stride).

    Row slicing (`gray[base:base + width:stride]`) keeps the copy at C speed;
    no per-pixel Python loop is involved.
    """
    if width <= 0 or height <= 0:
        return b"", 0, 0, 1
    stride = max(1, (width + max_w - 1) // max_w)
    if stride == 1:
        return bytes(gray), width, height, 1
    gw = (width + stride - 1) // stride
    rows = []
    for y in range(0, height, stride):
        base = y * width
        rows.append(bytes(gray[base:base + width:stride]))
    grid = b"".join(rows)
    gh = len(rows)
    return grid, gw, gh, stride


def threshold_mask(grid, thresh=BRIGHT_THRESH):
    """0/1 mask (as bytes) of the pixels whose value is >= thresh."""
    table = bytes(1 if v >= thresh else 0 for v in range(256))
    return grid.translate(table)


# --- connected components ----------------------------------------------------

def find_components(mask, width, height):
    """Connected components of the 1-pixels in `mask` (4-neighborhood).

    Iterative BFS with a deque — pages contain huge regions, recursion is not
    an option. Returns a list of dicts:
        {"area": int, "bbox": (x0, y0, x1, y1),   # inclusive
         "border": int}                            # px on the image border
    """
    n = width * height
    visited = bytearray(n)
    comps = []
    last_row = height - 1
    last_col = width - 1
    for start in range(n):
        if not mask[start] or visited[start]:
            continue
        visited[start] = 1
        queue = deque((start,))
        area = 0
        border = 0
        x0 = x1 = start % width
        y0 = y1 = start // width
        while queue:
            i = queue.popleft()
            x = i % width
            y = i // width
            area += 1
            if x < x0:
                x0 = x
            elif x > x1:
                x1 = x
            if y < y0:
                y0 = y
            elif y > y1:
                y1 = y
            if x == 0 or x == last_col or y == 0 or y == last_row:
                border += 1
            if x > 0:
                j = i - 1
                if mask[j] and not visited[j]:
                    visited[j] = 1
                    queue.append(j)
            if x < last_col:
                j = i + 1
                if mask[j] and not visited[j]:
                    visited[j] = 1
                    queue.append(j)
            if y > 0:
                j = i - width
                if mask[j] and not visited[j]:
                    visited[j] = 1
                    queue.append(j)
            if y < last_row:
                j = i + width
                if mask[j] and not visited[j]:
                    visited[j] = 1
                    queue.append(j)
        comps.append({"area": area, "bbox": (x0, y0, x1, y1), "border": border})
    return comps


# --- filtering ----------------------------------------------------------------

def _outline_dark_frac(mask, width, height, bbox,
                       gray, full_w, full_h, stride,
                       dark_thresh=DARK_THRESH):
    """Fraction of DARK cells among the non-white cells directly adjacent to
    the white cells inside `bbox` (i.e. the component's contour neighborhood
    — shape-independent, works for ellipses too, where the bbox corners are
    artwork).

    Whether a contour cell is "dark" is decided on the FULL-resolution page:
    a grid cell covers a stride x stride pixel block, and thin bubble
    outlines (2-3 px) can fall between the sampling points of the downscaled
    grid — so the block is scanned for any pixel <= dark_thresh. Bubbles have
    a near-black outline (and dark text inside), so the fraction is high for
    them; a borderless white-ish blob on gray artwork scores low. Cost is
    proportional to the candidate's contour length, not the page.
    """
    x0, y0, x1, y1 = bbox
    dark = 0
    total = 0
    cache = {}

    def block_dark(gx, gy):
        i = gy * width + gx
        hit = cache.get(i)
        if hit is None:
            bx0 = gx * stride
            by0 = gy * stride
            bx1 = min(bx0 + stride, full_w)
            by1 = min(by0 + stride, full_h)
            hit = False
            for yy in range(by0, by1):
                base = yy * full_w
                for xx in range(bx0, bx1):
                    if gray[base + xx] <= dark_thresh:
                        hit = True
                        break
                if hit:
                    break
            cache[i] = hit
        return hit

    for y in range(y0, y1 + 1):
        base = y * width
        for x in range(x0, x1 + 1):
            i = base + x
            if not mask[i]:
                continue
            # 4 neighbors; the ones outside the mask form the contour ring
            if x > 0 and not mask[i - 1]:
                total += 1
                dark += 1 if block_dark(x - 1, y) else 0
            if x < width - 1 and not mask[i + 1]:
                total += 1
                dark += 1 if block_dark(x + 1, y) else 0
            if y > 0 and not mask[i - width]:
                total += 1
                dark += 1 if block_dark(x, y - 1) else 0
            if y < height - 1 and not mask[i + width]:
                total += 1
                dark += 1 if block_dark(x, y + 1) else 0
    if total == 0:
        return 0.0
    return dark / float(total)


def _core_text_frac(gray, full_w, full_h, bbox, stride,
                    dark_thresh=DARK_THRESH, core_frac=CORE_FRAC,
                    max_samples=20000):
    """Fraction of dark pixels in the central `core_frac` region of `bbox`
    (grid coords), sampled at FULL resolution so thin glyph strokes survive
    the downscale. Large cores are subsampled with an integer step so at most
    ~`max_samples` pixels are read."""
    x0, y0, x1, y1 = bbox
    fx0 = x0 * stride
    fy0 = y0 * stride
    fx1 = min(full_w, (x1 + 1) * stride)
    fy1 = min(full_h, (y1 + 1) * stride)
    bw = fx1 - fx0
    bh = fy1 - fy0
    cw = max(1, int(bw * core_frac))
    ch = max(1, int(bh * core_frac))
    cx0 = fx0 + (bw - cw) // 2
    cy0 = fy0 + (bh - ch) // 2
    step = 1
    if cw * ch > max_samples:
        step = max(1, int(((cw * ch) / float(max_samples)) ** 0.5))
    dark = 0
    total = 0
    for y in range(cy0, cy0 + ch, step):
        base = y * full_w
        for x in range(cx0, cx0 + cw, step):
            total += 1
            if gray[base + x] <= dark_thresh:
                dark += 1
    if total == 0:
        return 0.0
    return dark / float(total)


def filter_components(comps, mask, width, height,
                      gray, full_w, full_h, stride=1,
                      min_area_frac=MIN_AREA_FRAC,
                      max_area_frac=MAX_AREA_FRAC,
                      min_aspect=MIN_ASPECT, max_aspect=MAX_ASPECT,
                      min_fill=MIN_FILL_RATIO,
                      max_border_frac=MAX_BORDER_FRAC,
                      min_box_px=MIN_BOX_PX,
                      require_outline=True,
                      dark_thresh=DARK_THRESH,
                      min_outline_frac=MIN_OUTLINE_FRAC,
                      require_text=True,
                      min_text_frac=MIN_TEXT_FRAC,
                      max_text_frac=MAX_TEXT_FRAC):
    """Keep only the components that plausibly are speech bubbles.

    Returns a list of {"bbox": ..., "area": ..., "fill": ...} dicts (grid
    coordinates). See the module docstring for what each filter catches.
    """
    page_area = float(width * height)
    border_len = float(2 * (width + height)) or 1.0
    out = []
    for c in comps:
        area = c["area"]
        frac = area / page_area
        if frac < min_area_frac or frac > max_area_frac:
            continue
        x0, y0, x1, y1 = c["bbox"]
        bw = x1 - x0 + 1
        bh = y1 - y0 + 1
        if bw * stride < min_box_px or bh * stride < min_box_px:
            continue
        aspect = bw / float(bh)
        if aspect < min_aspect or aspect > max_aspect:
            continue
        fill = area / float(bw * bh)
        if fill < min_fill:
            continue
        if c["border"] / border_len > max_border_frac:
            continue
        if require_outline:
            frac = _outline_dark_frac(mask, width, height, c["bbox"],
                                      gray, full_w, full_h, stride,
                                      dark_thresh)
            if frac < min_outline_frac:
                continue
        if require_text:
            frac = _core_text_frac(gray, full_w, full_h, c["bbox"], stride,
                                   dark_thresh)
            if frac < min_text_frac or frac > max_text_frac:
                continue
        out.append({"bbox": c["bbox"], "area": area, "fill": fill})
    return out


# --- merging -------------------------------------------------------------------

def _intersection(a, b):
    """Intersection area of two inclusive bboxes (0 when they don't touch)."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    w = min(ax1, bx1) - max(ax0, bx0) + 1
    h = min(ay1, by1) - max(ay0, by0) + 1
    if w <= 0 or h <= 0:
        return 0
    return w * h


def merge_boxes(cands, overlap_frac=0.10):
    """Merge candidates whose bboxes overlap by more than `overlap_frac` of
    the smaller box (covers nested boxes and a bubble split by its tail).
    Repeats until stable. Fill ratio is recomputed from the summed component
    areas over the merged bbox."""
    boxes = [dict(c) for c in cands]
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                inter = _intersection(a["bbox"], b["bbox"])
                if inter == 0:
                    continue
                ax0, ay0, ax1, ay1 = a["bbox"]
                bx0, by0, bx1, by1 = b["bbox"]
                sa = (ax1 - ax0 + 1) * (ay1 - ay0 + 1)
                sb = (bx1 - bx0 + 1) * (by1 - by0 + 1)
                if inter < overlap_frac * min(sa, sb):
                    continue
                nb = (min(ax0, bx0), min(ay0, by0),
                      max(ax1, bx1), max(ay1, by1))
                area = a["area"] + b["area"]
                nw = (nb[2] - nb[0] + 1) * (nb[3] - nb[1] + 1)
                boxes[i] = {"bbox": nb, "area": area,
                            "fill": min(1.0, area / float(nw))}
                del boxes[j]
                changed = True
                break
            if changed:
                break
    return boxes


# --- neck splitting (joined double bubbles) ---------------------------------

def _region_profiles(mask, width, bbox):
    """(row_profile, col_profile, area) of the white pixels inside `bbox`.
    Profiles count mask pixels per row / per column of the bbox region."""
    x0, y0, x1, y1 = bbox
    rows = []
    cols = [0] * (x1 - x0 + 1)
    area = 0
    for y in range(y0, y1 + 1):
        base = y * width
        cnt = 0
        for x in range(x0, x1 + 1):
            if mask[base + x]:
                cnt += 1
                cols[x - x0] += 1
        rows.append(cnt)
        area += cnt
    return rows, cols, area


def find_waist(profile, neck_ratio=NECK_RATIO, min_lobe_frac=MIN_LOBE_FRAC):
    """Index of the thinnest waist between two lobes of `profile`, or None.

    A waist is a local minimum thinner than `neck_ratio` x the smaller of the
    peak maxima on either side, with both sides at least `min_lobe_frac` of
    the profile length. A plain ellipse (unimodal) or rectangle (flat) has no
    such index."""
    n = len(profile)
    lobe = max(1, int(n * min_lobe_frac))
    if n < 2 * lobe + 1:
        return None
    pre = [0] * n
    m = 0
    for i, v in enumerate(profile):
        m = max(m, v)
        pre[i] = m
    suf = [0] * n
    m = 0
    for i in range(n - 1, -1, -1):
        m = max(m, profile[i])
        suf[i] = m
    best = None
    best_v = None
    for i in range(lobe, n - lobe):
        limit = neck_ratio * min(pre[i - 1], suf[i + 1])
        if profile[i] < limit:
            if best_v is None or profile[i] < best_v:
                best, best_v = i, profile[i]
    return best


def _line_is_single_run(mask, width, bbox, index, horizontal):
    """True when the white pixels on the given bbox line form (essentially)
    one contiguous run. A true neck between two joined bubbles is a single
    narrow band; a text column/row inside a bubble also dents the profile,
    but its white pixels are split into several runs — such a valley must
    NOT trigger a split."""
    x0, y0, x1, y1 = bbox
    total = 0
    longest = 0
    run = 0
    if horizontal:                       # a row (split stacked bubbles)
        base = (y0 + index) * width
        rng = range(x0, x1 + 1)

        def val(k):
            return mask[base + k]
    else:                                # a column (side-by-side bubbles)
        col = x0 + index
        rng = range(y0, y1 + 1)

        def val(k):
            return mask[k * width + col]
    for k in rng:
        if val(k):
            total += 1
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
    if total == 0:
        return False
    return longest >= 0.8 * total


def split_at_necks(mask, width, bbox, depth=2,
                   neck_ratio=NECK_RATIO, min_lobe_frac=MIN_LOBE_FRAC,
                   min_fill=MIN_FILL_RATIO, min_size=4):
    """Split the white region in `bbox` at neck(s) into candidate dicts
    ({"bbox", "area", "fill"}, grid coords). Rows are tried first (stacked
    double bubbles are the common case), then columns. Recurses on the
    halves up to `depth` times (a chain of 3-4 bubbles). When no valid neck
    exists — or a half would fail the size/fill checks — the region is
    returned unsplit."""
    rows, cols, area = _region_profiles(mask, width, bbox)
    x0, y0, x1, y1 = bbox
    if area == 0:
        return []
    fill = area / float((x1 - x0 + 1) * (y1 - y0 + 1))
    unsplit = [{"bbox": bbox, "area": area, "fill": fill}]
    if depth <= 0:
        return unsplit

    for horizontal, profile in ((True, rows), (False, cols)):
        w_idx = find_waist(profile, neck_ratio, min_lobe_frac)
        if w_idx is None:
            continue
        if not _line_is_single_run(mask, width, bbox, w_idx, horizontal):
            continue
        if horizontal:
            b1 = (x0, y0, x1, y0 + w_idx - 1)
            b2 = (x0, y0 + w_idx + 1, x1, y1)
        else:
            b1 = (x0, y0, x0 + w_idx - 1, y1)
            b2 = (x0 + w_idx + 1, y0, x1, y1)
        halves = []
        ok = True
        for hb in (b1, b2):
            hrows, hcols, harea = _region_profiles(mask, width, hb)
            if harea == 0:
                ok = False
                break
            # tighten the half's bbox to its non-empty profile range
            hx0, hy0 = hb[0], hb[1]
            ys = [i for i, v in enumerate(hrows) if v]
            xs = [i for i, v in enumerate(hcols) if v]
            tight = (hx0 + xs[0], hy0 + ys[0], hx0 + xs[-1], hy0 + ys[-1])
            tw = tight[2] - tight[0] + 1
            th = tight[3] - tight[1] + 1
            hfill = harea / float(tw * th)
            if tw < min_size or th < min_size or hfill < min_fill:
                ok = False
                break
            halves.append(tight)
        if not ok:
            continue
        out = []
        for hb in halves:
            out.extend(split_at_necks(mask, width, hb, depth - 1,
                                      neck_ratio, min_lobe_frac,
                                      min_fill, min_size))
        return out
    return unsplit


# --- top-level detection ---------------------------------------------------------

def detect_bubbles(gray, width, height,
                   bright_thresh=BRIGHT_THRESH,
                   max_grid_w=MAX_GRID_W,
                   rect_fill=RECT_FILL_RATIO,
                   require_outline=True,
                   require_text=True,
                   min_box_px=MIN_BOX_PX,
                   split_necks=True,
                   **filter_kw):
    """Detect speech bubbles in a full-resolution grayscale page.

    Returns a list of dicts in FULL-resolution coordinates:
        {"x": int, "y": int, "w": int, "h": int, "kind": "bubble",
         "shape": "round"|"rect", "fill": float}
    Extra keyword arguments are passed through to :func:`filter_components`.
    """
    grid, gw, gh, stride = downscale(gray, width, height, max_grid_w)
    if gw == 0 or gh == 0:
        return []
    mask = threshold_mask(grid, bright_thresh)
    comps = find_components(mask, gw, gh)
    cands = filter_components(comps, mask, gw, gh, gray, width, height, stride,
                              require_outline=require_outline,
                              require_text=require_text,
                              min_box_px=min_box_px, **filter_kw)
    if split_necks:
        min_size = max(2, min_box_px // stride)
        split = []
        for c in cands:
            split.extend(split_at_necks(mask, gw, c["bbox"],
                                        min_size=min_size))
        cands = split
    cands = merge_boxes(cands)
    out = []
    for c in cands:
        x0, y0, x1, y1 = c["bbox"]
        out.append({
            "x": x0 * stride,
            "y": y0 * stride,
            "w": (x1 - x0 + 1) * stride,
            "h": (y1 - y0 + 1) * stride,
            "kind": "bubble",
            "shape": "rect" if c["fill"] >= rect_fill else "round",
            "fill": c["fill"],
        })
    return out


# --- free text / SFX detection -----------------------------------------------

def _boxes_overlap(fx0, fy0, fx1, fy1, box):
    """True when the full-res rect [fx0,fy0,fx1,fy1) overlaps box (x/y/w/h)."""
    return not (fx1 <= box["x"] or box["x"] + box["w"] <= fx0 or
                fy1 <= box["y"] or box["y"] + box["h"] <= fy0)


def detect_text_blocks(gray, width, height, bubbles=(),
                       dark_thresh=SFX_DARK_THRESH,
                       max_grid_w=MAX_GRID_W,
                       min_area=SFX_MIN_AREA, max_area=SFX_MAX_AREA,
                       min_ext=SFX_MIN_EXT, max_ext=SFX_MAX_EXT,
                       gap_factor=SFX_GAP_FACTOR,
                       min_members=SFX_MIN_MEMBERS,
                       pad_frac=SFX_PAD_FRAC,
                       max_components=SFX_MAX_COMPONENTS):
    """Best-effort detection of free text (handwritten SFX, mutterings) drawn
    directly on the artwork, i.e. text WITHOUT a white bubble around it.

    Dark character-sized components on the downscaled grid are clustered by
    proximity; a cluster of >= `min_members` blobs becomes a box with
    "kind": "sfx". Blobs inside/overlapping a detected bubble are ignored
    (that is the bubble's own text). Deliberately heuristic: busy artwork
    can produce false hits — the caller offers manual removal and an off
    switch. Returns boxes in FULL-resolution coordinates like
    :func:`detect_bubbles`, with shape "rect".
    """
    grid, gw, gh, stride = downscale(gray, width, height, max_grid_w)
    if gw == 0 or gh == 0:
        return []
    table = bytes(1 if v <= dark_thresh else 0 for v in range(256))
    dmask = grid.translate(table)
    comps = find_components(dmask, gw, gh)

    chars = []
    for c in comps:
        if not (min_area <= c["area"] <= max_area):
            continue
        x0, y0, x1, y1 = c["bbox"]
        ext = max(x1 - x0 + 1, y1 - y0 + 1)
        if not (min_ext <= ext <= max_ext):
            continue
        fx0, fy0 = x0 * stride, y0 * stride
        fx1, fy1 = (x1 + 1) * stride, (y1 + 1) * stride
        if any(_boxes_overlap(fx0, fy0, fx1, fy1, b) for b in bubbles):
            continue
        chars.append((x0, y0, x1, y1, ext))
    if len(chars) < min_members or len(chars) > max_components:
        return []

    # single-link clustering via union-find
    parent = list(range(len(chars)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(chars)):
        ax0, ay0, ax1, ay1, aext = chars[i]
        for j in range(i + 1, len(chars)):
            bx0, by0, bx1, by1, bext = chars[j]
            gap_x = max(0, bx0 - ax1 - 1, ax0 - bx1 - 1)
            gap_y = max(0, by0 - ay1 - 1, ay0 - by1 - 1)
            if max(gap_x, gap_y) < gap_factor * max(aext, bext):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    clusters = {}
    for i in range(len(chars)):
        clusters.setdefault(find(i), []).append(chars[i])

    out = []
    for members in clusters.values():
        if len(members) < min_members:
            continue
        x0 = min(m[0] for m in members)
        y0 = min(m[1] for m in members)
        x1 = max(m[2] for m in members)
        y1 = max(m[3] for m in members)
        pad_x = int((x1 - x0 + 1) * pad_frac)
        pad_y = int((y1 - y0 + 1) * pad_frac)
        x0 = max(0, x0 - pad_x)
        y0 = max(0, y0 - pad_y)
        x1 = min(gw - 1, x1 + pad_x)
        y1 = min(gh - 1, y1 + pad_y)
        out.append({
            "x": x0 * stride,
            "y": y0 * stride,
            "w": (x1 - x0 + 1) * stride,
            "h": (y1 - y0 + 1) * stride,
            "kind": "sfx",
            "shape": "rect",
            "fill": 1.0,
        })
    return out


# --- reading order -----------------------------------------------------------------

def reading_order(boxes, rtl=True):
    """Sort bubble boxes into reading order; returns the sorted list.

    Boxes are dicts with x/y/w/h. Rows are built top-to-bottom: a box joins
    the current row while its vertical overlap with the row's y-interval is
    at least 50 % of the smaller height; within a row boxes are ordered by
    center-x — descending for RTL manga (default), ascending for LTR comics.

    This is a heuristic without panel detection; the docker lets the user
    renumber manually when it guesses wrong.
    """
    if not boxes:
        return []
    by_y = sorted(boxes, key=lambda b: b["y"] + b["h"] / 2.0)
    rows = []
    row = [by_y[0]]
    row_top = by_y[0]["y"]
    row_bot = by_y[0]["y"] + by_y[0]["h"]
    for b in by_y[1:]:
        top = b["y"]
        bot = b["y"] + b["h"]
        overlap = min(bot, row_bot) - max(top, row_top)
        smaller = min(bot - top, row_bot - row_top)
        if smaller > 0 and overlap >= 0.5 * smaller:
            row.append(b)
            row_top = min(row_top, top)
            row_bot = max(row_bot, bot)
        else:
            rows.append(row)
            row = [b]
            row_top, row_bot = top, bot
    rows.append(row)
    out = []
    for row in rows:
        row.sort(key=lambda b: b["x"] + b["w"] / 2.0, reverse=rtl)
        out.extend(row)
    return out


def _best_panel(box, panels):
    """Index of the panel that best contains `box`: the one covering the most
    of the box's area (>= 15 %), else the nearest panel centre. None if there
    are no panels."""
    if not panels:
        return None
    bx0, by0 = box["x"], box["y"]
    bx1, by1 = bx0 + box["w"], by0 + box["h"]
    barea = float(box["w"] * box["h"]) or 1.0
    best, best_ov = None, 0.0
    for i, p in enumerate(panels):
        ix0 = max(bx0, p["x"])
        iy0 = max(by0, p["y"])
        ix1 = min(bx1, p["x"] + p["w"])
        iy1 = min(by1, p["y"] + p["h"])
        ov = max(0, ix1 - ix0) * max(0, iy1 - iy0) / barea
        if ov > best_ov:
            best, best_ov = i, ov
    if best is not None and best_ov >= 0.15:
        return best
    cx, cy = bx0 + box["w"] / 2.0, by0 + box["h"] / 2.0
    ndist, nidx = None, None
    for i, p in enumerate(panels):
        px, py = p["x"] + p["w"] / 2.0, p["y"] + p["h"] / 2.0
        d = (cx - px) ** 2 + (cy - py) ** 2
        if ndist is None or d < ndist:
            ndist, nidx = d, i
    return nidx


def order_by_panels(boxes, panels, rtl=True):
    """Panel-aware reading order (the Magi hybrid).

    Panels themselves are put into manga reading order (rows top-to-bottom,
    right-to-left within a row for RTL), each bubble is assigned to the panel
    it sits in, and bubbles are ordered the same way WITHIN their panel. This
    fixes the common failure of the flat heuristic where bubbles from two
    side-by-side panels get interleaved. Falls back to plain reading_order
    when no panels are given."""
    if not panels:
        return reading_order(boxes, rtl)
    ordered_panels = reading_order(panels, rtl)
    buckets = [[] for _ in ordered_panels]
    leftover = []
    for b in boxes:
        idx = _best_panel(b, ordered_panels)
        (leftover if idx is None else buckets[idx]).append(b)
    out = []
    for bucket in buckets:
        out.extend(reading_order(bucket, rtl))
    out.extend(reading_order(leftover, rtl))
    return out


# --- script mapping -----------------------------------------------------------------

def map_units(bubble_count, units):
    """Map script units to bubbles 1:1 in order.

    Returns (pairs, mismatch): pairs is a list of (bubble_index, unit_index)
    for the first min(bubble_count, len(units)) positions; mismatch is True
    when the counts differ (the caller shows a warning but still places the
    pairs that exist).
    """
    n = min(bubble_count, len(units))
    pairs = [(i, i) for i in range(n)]
    return pairs, bubble_count != len(units)


def next_unplaced(assign, done_units, start):
    """Index of the next box (>= start) whose mapped unit exists and is not
    done yet, or None (the pointer stays at the end — no wrap-around).
    `done_units` is a set of unit indices that were already placed."""
    for k in range(max(0, start), len(assign)):
        u = assign[k]
        if u >= 0 and u not in done_units:
            return k
    return None


def shape_from_fill(fill, rect_fill=RECT_FILL_RATIO):
    """Classify a marked region as "rect" or "round" from its fill ratio
    (marked pixels / bounding-box area). A rectangle fills ~1.0 of its
    bbox, an ellipse only ~pi/4 = 0.785 — so at/above `rect_fill` it is a
    rectangle, below it a round/oval bubble (ellipse auto-fit). Used both
    for AI box refinement and for a hand-drawn Krita selection."""
    return "rect" if fill >= rect_fill else "round"


def ellipse_mask(w, h):
    """Row-major selection mask (bytes of length w*h): 255 for pixels inside
    the ellipse that fills the w x h box, 0 outside. Used to give a round
    bubble a matching *elliptical* Krita selection instead of a rectangle."""
    w, h = int(w), int(h)
    if w <= 0 or h <= 0:
        return b""
    data = bytearray(w * h)
    rx, ry = w / 2.0, h / 2.0
    for py in range(h):
        ny = (py + 0.5 - ry) / ry
        ny2 = ny * ny
        if ny2 > 1.0:
            continue
        base = py * w
        for px in range(w):
            nx = (px + 0.5 - rx) / rx
            if nx * nx + ny2 <= 1.0:
                data[base + px] = 255
    return bytes(data)


# ---------------------------------------------------------------------------
# Real bubble outline from the pixels (for AI boxes)
#
# A YOLO box only localises a bubble; its true shape (round, rectangular OR a
# jagged shout balloon) lives in the pixels. We crop the box, downscale it,
# take the white blob at the box centre (the balloon interior), trace its
# boundary and simplify it to a short polygon in full-page coordinates. No
# model retraining — the box says WHERE, the pixels say WHAT SHAPE.
# ---------------------------------------------------------------------------

# 8-neighbourhood, clockwise starting from North (used by the boundary tracer)
_NB8 = [(0, -1), (1, -1), (1, 0), (1, 1),
        (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def _component_at_center(mask, gw, gh):
    """4-connected white blob nearest the grid centre (the balloon interior,
    which surrounds the text). Returns (member bytearray, area) or (None, 0)."""
    n = gw * gh
    cx, cy = gw // 2, gh // 2
    seed, seed_d = -1, None
    for i in range(n):
        if mask[i]:
            dx, dy = (i % gw) - cx, (i // gw) - cy
            d = dx * dx + dy * dy
            if seed_d is None or d < seed_d:
                seed_d, seed = d, i
    if seed < 0:
        return None, 0
    member = bytearray(n)
    member[seed] = 1
    stack = [seed]
    area = 0
    while stack:
        i = stack.pop()
        area += 1
        x = i % gw
        if x > 0 and mask[i - 1] and not member[i - 1]:
            member[i - 1] = 1
            stack.append(i - 1)
        if x < gw - 1 and mask[i + 1] and not member[i + 1]:
            member[i + 1] = 1
            stack.append(i + 1)
        if i - gw >= 0 and mask[i - gw] and not member[i - gw]:
            member[i - gw] = 1
            stack.append(i - gw)
        if i + gw < n and mask[i + gw] and not member[i + gw]:
            member[i + gw] = 1
            stack.append(i + gw)
    return member, area


def _trace_boundary(member, gw, gh, max_steps=200000):
    """Moore-neighbour boundary tracing of a blob -> ordered grid points."""
    start = -1
    for i in range(gw * gh):
        if member[i]:
            start = i
            break
    if start < 0:
        return []
    sx, sy = start % gw, start // gw

    def white(x, y):
        return 0 <= x < gw and 0 <= y < gh and member[y * gw + x]

    contour = [(sx, sy)]
    cx, cy = sx, sy
    back = 6                              # we entered the start from the west
    for _step in range(max_steps):
        moved = False
        for k in range(1, 9):
            d = (back + k) % 8
            nx, ny = cx + _NB8[d][0], cy + _NB8[d][1]
            if white(nx, ny):
                back = (d + 4) % 8        # direction from the new pixel back
                cx, cy = nx, ny
                moved = True
                break
        if not moved:
            break
        if cx == sx and cy == sy:
            break
        contour.append((cx, cy))
    return contour


def _rdp(pts, eps):
    """Ramer-Douglas-Peucker polyline simplification (iterative)."""
    n = len(pts)
    if n < 3:
        return list(pts)
    keep = bytearray(n)
    keep[0] = keep[-1] = 1
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        denom = (dx * dx + dy * dy) ** 0.5 or 1.0
        idx, dmax = -1, eps
        for i in range(a + 1, b):
            px, py = pts[i]
            dist = abs((px - ax) * dy - (py - ay) * dx) / denom
            if dist > dmax:
                dmax, idx = dist, i
        if idx != -1:
            keep[idx] = 1
            stack.append((a, idx))
            stack.append((idx, b))
    return [pts[i] for i in range(n) if keep[i]]


def contour_in_box(gray, w, h, box, thresh=BRIGHT_THRESH,
                   target=150, max_points=48, min_points=6):
    """Trace the real outline of the bubble inside `box` = (x, y, bw, bh).

    `gray` is the full-page grayscale (bytes, width w, height h). Returns a
    list of [x, y] full-page points (a closed polygon), or None when no useful
    contour is found (the caller then falls back to the ellipse/rect shape)."""
    x0, y0, bw, bh = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    x0 = max(0, min(x0, w - 1))
    y0 = max(0, min(y0, h - 1))
    bw = min(bw, w - x0)
    bh = min(bh, h - y0)
    if bw < 6 or bh < 6:
        return None
    scale = max(bw, bh) / float(target)
    if scale < 1.0:
        scale = 1.0
    gw = max(2, int(round(bw / scale)))
    gh = max(2, int(round(bh / scale)))
    mask = bytearray(gw * gh)
    for gy in range(gh):
        sy = min(h - 1, y0 + int(gy * scale))
        row = sy * w
        obase = gy * gw
        for gx in range(gw):
            sx = min(w - 1, x0 + int(gx * scale))
            if gray[row + sx] >= thresh:
                mask[obase + gx] = 1
    member, area = _component_at_center(mask, gw, gh)
    if not member or area < 6:
        return None
    if area >= gw * gh * 0.985:          # fills the whole box -> a rectangle
        return None
    contour = _trace_boundary(member, gw, gh)
    if len(contour) < min_points:
        return None
    contour = _rdp(contour, max(1.5, min(gw, gh) * 0.03))
    if len(contour) < min_points:
        return None
    if len(contour) > max_points:        # uniform cap if still long
        stepc = len(contour) / float(max_points)
        contour = [contour[int(i * stepc)] for i in range(max_points)]
    poly = []
    for gx, gy in contour:
        px = min(w - 1, x0 + int((gx + 0.5) * scale))
        py = min(h - 1, y0 + int((gy + 0.5) * scale))
        poly.append([px, py])
    return poly


# ---------------------------------------------------------------------------
# SFX word database (script-line classification)
#
# Free text on a page can be SFX or dialog, and script lines can be SFX even
# without an "SFX:" tag. This vocabulary classifies SCRIPT LINES (no OCR is
# involved); the same classifier is meant to label OCR'd free-text boxes as
# sfx vs dialog for AI training later, so keep it pure.
#
# The romaji seed comes from the sibling MangaSFX plugin's rule keywords;
# deliberately NO interjections that often appear as real bubble dialogue
# ("Huh?", "Eh?", "Kyaa!") — misclassifying those would silently skip lines
# that belong in a bubble.
# ---------------------------------------------------------------------------

SFX_SEED_WORDS = (
    # -- JP romaji onomatopoeia --------------------------------------------
    # (MangaSFX rules + a curated pass over a large fan-compiled SFX
    # glossary. Deliberately EXCLUDED: interjections and words that appear
    # as real bubble dialogue or common nouns/names — a/e/un/iya/dame/oi/
    # ora/gyaa/itai/mou/chotto/pochi/rin/washi/kaachan/... — because a
    # matching line is silently skipped from the bubble mapping.)
    # impacts / hits
    "don", "dokan", "dosun", "doshin", "doga", "dogan", "dogo", "dogon",
    "doka", "dokka", "doki", "dokin", "dokun", "dosa", "dosha", "dosu",
    "dota", "dote", "doza", "dodo", "dofu", "dan", "ban", "bam", "baki",
    "bakin", "bako", "bakan", "bagu", "bakyun", "bachin", "bacha",
    "basun", "bata", "batan", "bafu", "bogo", "boka", "bokan", "boki",
    "boko", "bosu", "bota", "bote", "boto", "bomu", "bon", "gan", "gon",
    "gochi", "gosu", "goin", "goki", "gokin", "gotsu", "gakin", "kaan",
    "kiin", "poka", "pokan", "poki", "pakin", "paki", "pako", "paka",
    "pan", "pachin", "pen", "tosu", "ton", "zushin", "zugo", "zuko",
    "zun", "daan", "dadan", "gatsun", "guko",
    # rattles / clatter / mechanisms
    "gacha", "gachan", "gachi", "gachin", "gata", "gatan", "gara",
    "garan", "gasha", "gashan", "kacha", "kachan", "kachi", "kachin",
    "kata", "katan", "kapa", "kapan", "karan", "kasha", "kashan",
    "bara", "chara", "charin", "jara", "jaka", "jaki", "jakin", "koto",
    "kotsu", "goto", "goun", "buroro", "dorun", "dororo", "pinpon",
    "kinkon", "chirin", "shakin", "shaki", "batari", "battari",
    # rustles / movement / air
    "basa", "basara", "basha", "gasa", "goso", "kasa", "pasa", "para",
    "parara", "sara", "sasa", "saku", "shara", "shari", "wasa", "za",
    "zaza", "zawa", "hira", "pira", "bira", "hyu", "hyun", "hyururu",
    "byu", "byun", "byuo", "bau", "bahyu", "bohyu", "pyu", "shu",
    "shuru", "shuta", "suta", "sutata", "tatata", "dada", "dadada",
    "teku", "teke", "toko", "tote", "hyoi", "hyoko", "sucha", "supo",
    "suten", "suton", "fasa", "fuwa", "fusa", "fura", "furu", "gaba",
    "gui", "gyu", "gyun", "gyuru", "kyu", "kuru", "kururi", "guru",
    "gururu", "gurun", "gura", "guri", "gurin", "kura", "kuri", "bura",
    "buran", "burun", "buru", "bun", "buo", "buwa", "puru", "purun",
    "pura", "puran", "yura", "yusa", "yoro", "yota", "zuri", "zuru",
    "zusa", "zusha", "zuza", "zudada", "wana", "kaku", "kakun", "gaku",
    "gakun", "hena", "heto", "uro", "noro", "noso", "nosshi", "soro",
    "sorori", "choko", "chira", "kyoro", "kyoton", "suka",
    # water / liquids / wet
    "jabu", "jaba", "jabon", "japu", "zabu", "zaba", "zapu", "basshaa",
    "bashan", "bichi", "bicha", "bisha", "bisho", "bisshori", "bocha",
    "bochan", "chapu", "chapon", "picha", "pichan", "pisha", "pochan",
    "shito", "bushu", "busha", "gopo", "kopo", "jobo", "joro", "jowa",
    "juru", "jururu", "juwa", "zubi", "zuzu", "dara", "daba", "doba",
    "doro", "toro", "bota", "poro", "pota", "potsu", "gutsu", "docha",
    "becha", "becho", "becho", "beto", "betari", "neba", "nuru", "nume",
    "nucha", "gucha", "gucho", "guchu", "gushu", "pusha", "pushi",
    "pushu", "chapu",
    # fire / light / electricity
    "bo", "goo", "guoo", "mera", "pika", "kira", "gira", "chika",
    "chiri", "biri", "bachi", "pachi", "bika", "jijiji", "shubo",
    "teka", "po", "pou", "gain",
    # body / emotion / states
    "doki", "dokidoki", "bakkun", "biku", "bikun", "piku", "pikun",
    "pikut", "biki", "giku", "gikuri", "hiku", "higu", "kyun", "zoku",
    "zowa", "zozo", "zuki", "zukin", "jiwa", "jito", "jii", "jiri",
    "jori", "zori", "zari", "iraira", "ira", "muka", "mukka", "buri",
    "puri", "pun", "kusu", "kusun", "gusu", "gusun", "gushi", "beso",
    "meso", "shiku", "bien", "zubibi", "hiso", "boso", "gonyo", "koso",
    "kossori", "moji", "mozo", "moso", "muzu", "sowa", "uzu", "waku",
    "uki", "kyapi", "gera", "kera", "kuku", "kukuku", "keke", "kekeke",
    "gessori", "guttari", "kuta", "kutari", "gude", "hara", "harari",
    "shobo", "shobon", "shun", "doyon", "utouto", "uto", "utsura",
    "suya", "kuka", "gussuri", "munya", "bonyari", "atafuta",
    "awawa", "oro", "oroo", "dogimagi", "uzo", "gigi", "gogogo",
    "zumo", "zumomomo", "mowa", "moya", "moa", "powa", "howan", "fua",
    "kunka", "funka", "hunka", "nku", "suu", "shiin", "shin", "pita",
    "pito", "peta", "petan", "hita", "hishi", "gyut", "beta",
    # eating / mouth / sounds
    "paku", "gapu", "gari", "bori", "pori", "kori", "gori", "musha",
    "mosha", "mogu", "moku", "mokyu", "hamu", "hagu", "bamu", "hapu",
    "kapu", "agi", "gaji", "kaji", "baku", "gabu", "kucha", "chupa",
    "chu", "chuu", "churu", "chun", "piyo", "pipi", "gero", "geko",
    "kero", "hihin", "garuru", "wan", "nyaa", "kuun", "gebo", "gefu",
    "geho", "gohon", "goho", "keho", "kehen", "kohon", "koho", "goku",
    "gokun", "kokun", "kokuri", "koku", "guku", "gubi", "gubu", "puha",
    "pero", "peron", "perori", "bero", "beron", "berori", "rero",
    "pecha", "pecho", "chiru", "buhi", "buhihi", "mumu", "fugo",
    # smiles / faces
    "niya", "niko", "nika", "nima", "nipa", "nita", "nihe", "nihehe",
    "mufu", "mufufu", "dehe", "tehe", "ehe", "ehehe", "ahaha", "hehe",
    "haha", "huhu", "fufu", "gera", "geta", "hera", "kiri",
    # cuts / tears / scratches
    "zaku", "zakku", "supa", "supari", "zuba", "beri", "biri", "peri",
    "meki", "mishi", "michi", "gishi", "kishi", "gii", "giko", "bari",
    "pari", "giri", "kiri", "gari", "kari", "choki", "shaku", "zan",
    "zashu", "bero", "buchi", "puchi", "putsun",
    "gisu", "boro", "zuta",
    # squeeze / grab / stretch / squish
    "gashi", "gusha", "gushaa", "nigi", "munyu", "monyu", "puni",
    "punyu", "funi", "buni", "guni", "gunya", "kunya", "kune", "kuni",
    "nyoro", "nyoki", "muni", "momi", "buyo", "puyo", "puku", "buku",
    "kupa", "muchi", "mugyu", "mukyu", "gyumu", "boin", "bain", "tapu",
    "tapun", "tayun", "boyon", "boyoyon", "purin", "pyoko", "pyon",
    "byon", "byoko", "poyo", "funya", "hunya", "gunyu", "nade",
    "sasuri", "sawa", "koshi", "goshi", "kosu", "geshi", "guriguri",
    # misc mechanics / magic / dramatic
    "zappan", "zanbu", "zapa", "shuppo", "paon", "kokekokko",
    "minmin", "miin", "pipo", "pirurira", "pirururu", "chikutaku",
    "kochi", "gatangoton", "fanfan",
    "bababa", "papapa", "dokyun", "bakyuun", "gaya", "wara", "doyameki",
    "shan", "pon", "bon", "doron", "dororonpa", "poa", "fushu",
    "pusu", "jajan", "dodon", "runtata", "buncha",
    "kayaku", "poi", "pyoi", "supon", "chokon", "pokon", "kapon",
    "sukon", "gakoon", "gako", "gakon",
    # -- English comic SFX --------------------------------------------------
    "boom", "kaboom", "bam", "bang", "blam", "blast",
    "pow", "wham", "smack", "slap", "thud", "thump", "bonk",
    "crash", "smash", "crack", "clang", "clink", "clunk", "clank",
    "click", "whoosh", "woosh", "swoosh", "swish",
    "rumble", "rattle", "buzz", "bzz", "vroom", "zap",
    "splash", "drip", "plop", "munch", "chomp", "nom", "slurp",
    "psst", "shh", "grr", "growl", "snarl", "roar",
    "tap", "pat", "clap", "pop", "poof", "boing",
    "meow", "purr", "woof", "squeak", "creak", "screech",
    "knock", "ring", "ding", "dong", "beep", "tada",
    "wobble", "jiggle", "flutter", "rustle", "sizzle", "fizz",
    "twitch", "throb", "sting", "prickle", "tingle", "shiver",
    "gasp", "wheeze", "pant", "huff", "puff", "snort", "sniff",
    "sob", "whimper", "sniffle", "gurgle", "glug", "squelch",
    "squish", "stomp", "tromp", "clomp", "trot", "dash", "zoom",
    "fwoosh", "fwump", "fwip", "shing",
    # -- action descriptors common in translated scripts -------------------
    "grin", "smirk", "nod", "stare", "glare", "blush", "shrug",
    "gulp", "sweat", "tremble", "pout", "sigh", "sparkle", "shine",
    "wave", "poke", "pinch", "tug", "yank", "hug", "glomp", "pet",
    "wag", "fidget", "squirm", "wiggle", "flail", "slump", "droop",
    "wilt", "beam", "wink", "peek", "glance", "flinch", "startle",
)

_SFX_TAGS = ("sfx:", "st:")
_SFX_STRIP = "()[]{}<>\"'`*~〜♪♫★☆♥…‥・．,.!?！？;:—–-_/\\|＝=＋+（）「」『』【】"

# --- kana -> romaji (so ドキドキ matches the same vocabulary as "doki") -------

_KANA_H = ("あいうえおかきくけこがぎぐげごさしすせそざじずぜぞたちつてと"
           "だぢづでどなにぬねのはひふへほばびぶべぼぱぴぷぺぽまみむめも"
           "やゆよらりるれろわをんぁぃぅぇぉゔ")
_KANA_K = ("アイウエオカキクケコガギグゲゴサシスセソザジズゼゾタチツテト"
           "ダヂヅデドナニヌネノハヒフヘホバビブベボパピプペポマミムメモ"
           "ヤユヨラリルレロワヲンァィゥェォヴ")
_KANA_R = ("a i u e o ka ki ku ke ko ga gi gu ge go sa shi su se so "
           "za ji zu ze zo ta chi tsu te to da ji zu de do na ni nu ne no "
           "ha hi fu he ho ba bi bu be bo pa pi pu pe po ma mi mu me mo "
           "ya yu yo ra ri ru re ro wa o n a i u e o bu").split()
KANA_ROMAJI = {}
for _chars in (_KANA_H, _KANA_K):
    for _ch, _r in zip(_chars, _KANA_R):
        KANA_ROMAJI[_ch] = _r
_KANA_SMALL_Y = {"ゃ": "ya", "ゅ": "yu", "ょ": "yo",
                 "ャ": "ya", "ュ": "yu", "ョ": "yo"}
# dropped during transliteration: gemination (the letter-squeeze handles
# doubling), prolongation and the kana repetition marks
_KANA_DROP = "っッーヽヾゝゞ"


def kana_to_romaji(token):
    """Transliterate a pure-kana token to romaji, or None when the token
    contains anything that is not kana (kanji, latin, digits, ...)."""
    out = []
    i = 0
    n = len(token)
    while i < n:
        ch = token[i]
        if ch in _KANA_DROP:
            i += 1
            continue
        base = KANA_ROMAJI.get(ch)
        if base is None:
            return None
        nxt = token[i + 1] if i + 1 < n else ""
        if nxt in _KANA_SMALL_Y and base.endswith("i"):
            small = _KANA_SMALL_Y[nxt]
            if base in ("shi", "chi", "ji"):
                out.append(base[:-1] + small[1:])     # しゃ -> sha
            else:
                out.append(base[:-1] + small)         # きゃ -> kya
            i += 2
            continue
        out.append(base)
        i += 1
    return "".join(out)


def _squeeze(word):
    """Collapse runs of the same letter: 'boooom' -> 'bom'."""
    out = []
    for ch in word:
        if not out or out[-1] != ch:
            out.append(ch)
    return "".join(out)


def _sfx_token_matches(token, squeezed_words):
    """True when `token` (already squeezed) is one of the words or a pure
    repetition of one ('gogogogo' matches 'gogo', 'dokidoki' -> 'doki')."""
    for w in squeezed_words:
        if token == w:
            return True
        if len(token) > len(w) and token.replace(w, "") == "":
            return True
    return False


def is_sfx_line(text, words):
    """True when the script line consists ONLY of known SFX vocabulary.

    Conservative on purpose: every token must match (after lowercasing,
    stripping decoration and squeezing elongations), so a dialogue sentence
    that merely CONTAINS an SFX word never matches. A literal leading
    'SFX:'/'ST:' tag always counts (normally the pairing strips those tags
    before this is called — the check is a safety net for raw lines).
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    for tag in _SFX_TAGS:
        if low.startswith(tag):
            return True
    cleaned = "".join(" " if ch in _SFX_STRIP else ch for ch in low)
    tokens = [tok for tok in cleaned.split() if tok]
    if not tokens:
        return False
    squeezed_words = [_squeeze(w.lower()) for w in words if w]
    for tok in tokens:
        if not tok.isalpha():
            return False                # numbers/mixed junk: not SFX
        if not tok.isascii():
            # kana SFX (ドキドキ, ゴゴゴ …) match the same romaji words;
            # kanji or other scripts are treated as real dialogue
            tok = kana_to_romaji(tok)
            if not tok:
                return False
        if not _sfx_token_matches(_squeeze(tok), squeezed_words):
            return False
    return True


def split_units_sfx(texts, words):
    """Split the page's unit texts into (kept_indices, skipped_count):
    units classified as SFX get no bubble while SFX boxes are ignored."""
    kept = [i for i, t in enumerate(texts) if not is_sfx_line(t, words)]
    return kept, len(texts) - len(kept)


def load_sfx_db(path):
    """(seed_words, user_words) from `path`; missing/broken file -> built-in
    seed only. The file's 'words' are MERGED with the built-in seed (union),
    so plugin updates that extend the vocabulary reach old DB files too."""
    import json
    seed = list(SFX_SEED_WORDS)
    user = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            if isinstance(data.get("words"), list):
                extra = [str(w) for w in data["words"] if w]
                seed = sorted(set(seed) | set(extra))
            if isinstance(data.get("user"), list):
                user = [str(w) for w in data["user"] if w]
    except (OSError, ValueError):
        pass
    return seed, user


def save_sfx_db(path, user_words, seed_words=None):
    """Write the DB; the seed is stored too so the file is self-contained
    (and hand-editable). Returns True on success."""
    import json
    data = {"words": list(seed_words if seed_words is not None
                          else SFX_SEED_WORDS),
            "user": [str(w).strip() for w in user_words if str(w).strip()]}
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        return True
    except OSError:
        return False


def insert_gap(assign, row):
    """Insert a gap at `row`: this bubble gets no line (-1) and all later
    assignments shift down by one; the last one drops off (recoverable via a
    reset). `assign` is the per-bubble list of unit indices (-1 = none)."""
    if not (0 <= row < len(assign)):
        return list(assign)
    return list(assign[:row]) + [-1] + list(assign[row:-1])


def remove_gap(assign, row, unit_count):
    """Remove a gap at `row`: the later assignments shift up by one and the
    last row takes the next unused unit (or -1 when the script has no more
    lines). Inverse of :func:`insert_gap`."""
    if not (0 <= row < len(assign)):
        return list(assign)
    used = [u for u in assign if u >= 0]
    nxt = (max(used) + 1) if used else 0
    if nxt >= unit_count:
        nxt = -1
    return list(assign[:row]) + list(assign[row + 1:]) + [nxt]
