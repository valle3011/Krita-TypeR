# -*- coding: utf-8 -*-
"""SVG-structure tests (SFX vector builder) and i18n integrity tests.
Qt-free / Krita-free: the SVG builder is pure, and the language checks parse the
source with `ast`/regex instead of importing the Krita-bound module.

Run:  python test_svg_i18n.py
"""
import ast
import importlib.util
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(mod, *parts):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(_HERE, "typer_kr", *parts))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SB = _load("svg_builder", "sfx", "svg_builder.py")

_pass = _fail = 0


def check(name, cond):
    global _pass, _fail
    if cond:
        _pass += 1
        print("  ok   " + name)
    else:
        _fail += 1
        print("  FAIL " + name)


def texts(svg):
    """(fill, stroke, stroke_width) for each <text> element, in document order."""
    out = []
    for t in re.findall(r"<text[^>]*>", svg):
        fill = re.search(r'fill="([^"]*)"', t)
        stroke = re.search(r'stroke="([^"]*)"', t)
        sw = re.search(r'stroke-width="([^"]*)"', t)
        out.append((fill.group(1) if fill else None,
                    stroke.group(1) if stroke else None,
                    float(sw.group(1)) if sw else 0.0))
    return out


# =====================================================================
# SFX SVG structure (build_sfx_svg)
# =====================================================================
print("--- svg structure ---")

# plain: exactly one text layer (the fill), no stroke
_svg = SB.build_sfx_svg("BOOM", "Arial", 100, fill="#000000",
                        outline="#ffffff", outline_px=0)
check("no outline -> a single fill text layer",
      len(texts(_svg)) == 1 and texts(_svg)[0][2] == 0.0)

# single outline: outline layer under the fill, stroke = 2*px (SFX convention)
_svg = SB.build_sfx_svg("BOOM", "Arial", 100, fill="#000000",
                        outline="#ffffff", outline_px=8)
_t = texts(_svg)
check("single outline -> outline layer then fill layer",
      len(_t) == 2 and _t[0][1] == "#ffffff" and _t[0][2] == 16.0
      and _t[1][2] == 0.0)

# double outline: outer(wide) -> inner -> fill, widths ordered, colours right
_svg = SB.build_sfx_svg("BOOM", "Arial", 100, fill="#ffffff",
                        outline="#000000", outline_px=6,
                        outline2="#ffffff", outline2_px=14)
_t = texts(_svg)
check("double outline -> 3 layers: outer(white,28) / inner(black,12) / fill",
      len(_t) == 3
      and _t[0][0] == "#ffffff" and _t[0][2] == 28.0     # outer, widest, first
      and _t[1][0] == "#000000" and _t[1][2] == 12.0     # inner
      and _t[2][2] == 0.0)                               # fill on top

# the 2nd outline is coupled to the first: outline_px=0 -> no 2nd outline either
_svg = SB.build_sfx_svg("BOOM", "Arial", 100, fill="#fff", outline="#000",
                        outline_px=0, outline2="#000", outline2_px=14)
check("1st outline off (px 0) -> 2nd outline is off too (only fill)",
      len(texts(_svg)) == 1)

# shadow takes the WIDEST outline so the silhouette stays covered
_svg = SB.build_sfx_svg("BOOM", "Arial", 100, fill="#fff", outline="#000",
                        outline_px=6, outline2="#fff", outline2_px=14,
                        shadow=True, shadow_color="#333",
                        shadow_dx=5, shadow_dy=5)
_t = texts(_svg)
check("shadow layer uses the widest outline stroke (2*14=28)",
      _t[0][1] == "#333" and _t[0][2] == 28.0)

# gradient fill: a <linearGradient> def and the fill references it
_svg = SB.build_sfx_svg("BOOM", "Arial", 100, fill="#000", outline="#000",
                        outline_px=0, fill2="#ff0000")
check("gradient fill -> <linearGradient> def + url(#sfxgrad) fill",
      "<linearGradient" in _svg and 'fill="url(#sfxgrad)"' in _svg)

# pattern/texture fill: a <pattern> with the image, fill references it, xlink ns
_svg = SB.build_sfx_svg("BOOM", "Arial", 100, fill="#000", outline="#fff",
                        outline_px=8, pattern_uri="data:image/png;base64,AAAA",
                        pattern_w=40, pattern_h=40)
check("pattern fill -> <pattern> def, url(#sfxpat) fill, xlink namespace",
      "<pattern" in _svg and 'fill="url(#sfxpat)"' in _svg
      and "xmlns:xlink" in _svg)
check("pattern fill only touches the FILL layer (outline stays solid)",
      texts(_svg)[0][1] == "#fff")     # outline layer keeps its solid stroke

# rotation wraps every layer in one rotate group (so all parts turn together)
_svg = SB.build_sfx_svg("BOOM", "Arial", 100, fill="#000", outline="#fff",
                        outline_px=8, rotate=30)
check("rotation -> a single <g transform=\"rotate\"> group",
      _svg.count("rotate(") == 1)

# =====================================================================
# i18n integrity (duplicate keys + used-but-undefined)
# =====================================================================
print("--- i18n integrity ---")


def dict_key_dups(source):
    """Every string-keyed dict literal whose keys repeat (last value wins -> the
    earlier one is dead). Returns list of (lineno, key)."""
    dups = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            seen = set()
            for kn in node.keys:
                if isinstance(kn, ast.Constant) and isinstance(kn.value, str):
                    if kn.value in seen:
                        dups.append((kn.lineno, kn.value))
                    seen.add(kn.value)
    return dups


def defined_keys(source):
    keys = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            for kn in node.keys:
                if isinstance(kn, ast.Constant) and isinstance(kn.value, str):
                    keys.add(kn.value)
    return keys


# a COMPLETE key only: the string must be immediately followed by ')' (no args)
# or ',' (format kwargs). A following '+' means a runtime-built key (e.g.
# t("shaper_" + mode)) — those are prefixes, not real keys, so they're skipped.
_TR_CALL = re.compile(r'(?:self\.)?(?:_tr|\bt)\(\s*"([^"]+)"\s*[),]')


def used_keys(source):
    return set(_TR_CALL.findall(source))


for rel in [("typer_kr.py",), ("sfx", "sfx_docker.py"), ("sfx", "i18n.py")]:
    path = os.path.join(_HERE, "typer_kr", *rel)
    src = open(path, encoding="utf-8").read()
    name = "/".join(rel)
    dups = dict_key_dups(src)
    check("%s: no duplicate dict keys" % name, not dups)
    if dups:
        for ln, k in dups[:10]:
            print("        dup key '%s' at line %d" % (k, ln))

# every key referenced by t()/_tr() must be defined in some language dict
_typer_src = open(os.path.join(_HERE, "typer_kr", "typer_kr.py"),
                  encoding="utf-8").read()
_missing = used_keys(_typer_src) - defined_keys(_typer_src)
check("typer_kr.py: every t()/_tr() key is defined", not _missing)
if _missing:
    print("        undefined keys: " + ", ".join(sorted(_missing)[:15]))

_sfx_src = open(os.path.join(_HERE, "typer_kr", "sfx", "sfx_docker.py"),
                encoding="utf-8").read()
_i18n_src = open(os.path.join(_HERE, "typer_kr", "sfx", "i18n.py"),
                 encoding="utf-8").read()
_sfx_missing = used_keys(_sfx_src) - defined_keys(_i18n_src)
check("sfx: every self.t() key is defined in i18n.py", not _sfx_missing)
if _sfx_missing:
    print("        undefined SFX keys: " + ", ".join(sorted(_sfx_missing)[:15]))

print("\n%d passed, %d failed" % (_pass, _fail))
sys.exit(1 if _fail else 0)
