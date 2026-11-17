# -*- coding: utf-8 -*-
"""Pull the finished lettering out of the .kra pages. Reads only.

A .kra is a zip; a TypeR text layer is a `shapelayer` whose content.svg
holds one <text> with a <tspan> per line, the family and the pixel size
in its style. That is everything the shaper is judged on: the words, how
they were broken, the font, and the size a person settled on.

Writes one JSON file of blocks. Touches nothing in the chapters.
"""
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

OUT = sys.argv[1]
DIRS = sys.argv[2:]

SVG = "{http://www.w3.org/2000/svg}"


def style_of(node):
    out = {}
    for part in (node.get("style") or "").split(";"):
        if ":" in part:
            k, _s, v = part.partition(":")
            out[k.strip()] = v.strip()
    return out


def blocks_of(path):
    """Every TypeR text block on one page."""
    out = []
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        return out
    with z:
        names = z.namelist()
        main = [n for n in names if n.endswith("maindoc.xml")]
        page_w = page_h = 0
        titles = {}
        if main:
            try:
                root = ET.fromstring(z.read(main[0]))
            except ET.ParseError:
                root = None
            if root is not None:
                for img in root.iter():
                    if img.tag.endswith("IMAGE"):
                        page_w = int(img.get("width") or 0)
                        page_h = int(img.get("height") or 0)
                        break
                for lay in root.iter():
                    if lay.tag.endswith("layer"):
                        titles[lay.get("filename") or ""] = lay.get("name") or ""
        for n in names:
            if not n.endswith(".shapelayer/content.svg"):
                continue
            lid = re.search(r"/(layer\d+)\.shapelayer/", n)
            title = titles.get(lid.group(1) if lid else "", "")
            # TypeR names its layers; before it did, they are Krita's own
            # "Vector Layer N". ANY=1 takes those too, for the older
            # chapters - at the risk of picking up lettering that was not
            # done with the plugin.
            if not title.startswith("TypeR") and not os.environ.get("ANY"):
                continue
            try:
                svg = ET.fromstring(z.read(n))
            except ET.ParseError:
                continue
            for text in svg.iter(SVG + "text"):
                st = style_of(text)
                fam = st.get("font-family", "")
                try:
                    px = float(st.get("font-size", "0"))
                except ValueError:
                    px = 0.0
                lines, xs, ys = [], [], []
                for sp in text.iter(SVG + "tspan"):
                    lines.append("".join(sp.itertext()))
                    try:
                        xs.append(float(sp.get("x")))
                        ys.append(float(sp.get("y")))
                    except (TypeError, ValueError):
                        xs.append(0.0)
                        ys.append(0.0)
                if not lines or not fam or px <= 0:
                    continue
                out.append({"page": os.path.basename(path),
                            "chapter": os.path.basename(
                                os.path.dirname(os.path.dirname(path))),
                            "layer": title,
                            "font": fam,
                            "px": px,
                            "bold": st.get("font-weight", "") == "bold",
                            "lines": lines,
                            "x": xs, "y": ys,
                            "page_w": page_w, "page_h": page_h,
                            })
    return out


rows = []
pages = 0
for d in DIRS:
    for name in sorted(os.listdir(d)):
        if not name.lower().endswith(".kra"):
            continue
        pages += 1
        rows.extend(blocks_of(os.path.join(d, name)))

io.open(OUT, "w", encoding="utf-8", newline="\n").write(
    json.dumps(rows, ensure_ascii=False, indent=1))
print("%d pages read, %d text blocks" % (pages, len(rows)))
if rows:
    import collections
    ks = collections.Counter(len(r["lines"]) for r in rows)
    fams = collections.Counter(r["font"] for r in rows)
    pxs = sorted(r["px"] for r in rows)
    print("lines per block:", dict(sorted(ks.items())))
    print("sizes: min %.0f  median %.0f  max %.0f"
          % (pxs[0], pxs[len(pxs) // 2], pxs[-1]))
    print("fonts:", ", ".join("%s(%d)" % (f, n)
                              for f, n in fams.most_common(8)))
    print("wrote", OUT)
