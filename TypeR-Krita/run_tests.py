# -*- coding: utf-8 -*-
"""Run every TypeR test suite + static checks in one go.

    python run_tests.py

Exit code is non-zero if anything fails. No real Krita needed; PyQt5 is only
required for the integration suite (skipped cleanly if missing).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

SUITES = [
    "test_typer_logic.py",     # #1 unit logic (langpair, layout, sfx, bubbles…)
    "test_metamorphic.py",     # #2 regression #3 metamorphic #4 fuzz #5 boundary #9 round-trip
    "test_svg_i18n.py",        # #6 SVG structure #10 i18n integrity
    "test_integration.py",     # #12 Krita-stub integration #13 font picker
    "test_fontfav.py",         # font-favourites core (categories, 1..n links)
    "test_fontmatch.py",       # tolerant font-family matching (spelling drift)
]

MODULES = [
    "typer_kr/typer_kr.py", "typer_kr/layout.py", "typer_kr/langpair.py",
    "typer_kr/fontfav.py", "typer_kr/fontfav_ui.py", "typer_kr/fontfiles.py",
    "typer_kr/fontmatch.py",
    "typer_kr/imgfx.py", "typer_kr/patterngen.py", "typer_kr/xlsx.py",
    "typer_kr/bubbles.py", "typer_kr/balloons.py", "typer_kr/comments.py",
    "typer_kr/texttypes.py", "typer_kr/sfx/sfx_docker.py",
    "typer_kr/sfx/svg_builder.py", "typer_kr/sfx/i18n.py",
    "typer_kr/sfx/config.py",
]

fails = []


def run(label, argv):
    print("=" * 64)
    print("RUN  " + label)
    print("=" * 64)
    rc = subprocess.run([PY] + argv, cwd=HERE).returncode
    if rc != 0:
        fails.append(label)
    print()


# #11 static: syntax (always) + pyflakes (if available)
print("=" * 64)
print("STATIC  py_compile (syntax)")
print("=" * 64)
rc = subprocess.run([PY, "-m", "py_compile"] + MODULES, cwd=HERE).returncode
if rc != 0:
    fails.append("py_compile")
else:
    print("  ok   all modules compile")
print()

print("=" * 64)
print("STATIC  pyflakes (undefined names, dup keys, unused)")
print("=" * 64)
pf = subprocess.run([PY, "-m", "pyflakes", "typer_kr"], cwd=HERE,
                    capture_output=True, text=True)
# the conditional `def hyph_fn` inside `if hyphenate:` is a known false positive;
# _qt.py is a pure PyQt5/PyQt6 re-export shim, so its star imports (deliberately
# re-exported) are expected and can't be analysed by pyflakes.
def _keep(ln):
    return (ln.strip()
            and "redefinition of unused 'hyph_fn'" not in ln
            and "_qt.py" not in ln)
noise = [ln for ln in pf.stdout.splitlines() if _keep(ln)]
if pf.returncode == 127 or "No module named pyflakes" in (pf.stderr or ""):
    print("  --   pyflakes not installed, skipped")
elif noise:
    print("\n".join(noise))
    fails.append("pyflakes")
else:
    print("  ok   no pyflakes findings")
print()

# #12 static: guard the PyQt5/PyQt6 dual-compat (most CI runs only have PyQt5,
# so scan the source for spellings that would break under Krita 6 / PyQt6).
print("=" * 64)
print("STATIC  Qt5/Qt6 dual-binding compatibility")
print("=" * 64)
import glob
import re as _re
_bad = []
_flat_color = _re.compile(r"\bQt\.(white|black|red|green|blue|gray|grey|"
                          r"transparent|darkGray|lightGray|yellow|cyan|magenta)\b")
_flag_wrap = _re.compile(r"\bQt\.(Orientations|Alignment|MouseButtons|"
                         r"KeyboardModifiers|WindowFlags|ItemFlags)\(")
for _f in glob.glob(os.path.join(HERE, "typer_kr", "**", "*.py"), recursive=True):
    if os.path.basename(_f) == "_qt.py":
        continue                       # the shim is the one allowed PyQt5 site
    _txt = open(_f, encoding="utf-8").read()
    _rel = os.path.relpath(_f, HERE)
    if _re.search(r"\bfrom PyQt5\b|\bimport PyQt5\b", _txt):
        _bad.append("%s: imports PyQt5 directly (use `from ._qt import …`)" % _rel)
    if ".exec_(" in _txt:
        _bad.append("%s: uses .exec_() (removed in PyQt6 — use .exec())" % _rel)
    if _flat_color.search(_txt):
        _bad.append("%s: flat Qt colour (use Qt.GlobalColor.*)" % _rel)
    if _flag_wrap.search(_txt):
        _bad.append("%s: Qt flag wrapper ctor (dropped in PyQt6)" % _rel)
if _bad:
    print("\n".join("  " + b for b in _bad))
    fails.append("qt6-compat")
else:
    print("  ok   no PyQt6-incompatible spellings")
print()

for s in SUITES:
    run(s, [s])

print("=" * 64)
if fails:
    print("RESULT: FAILED -> " + ", ".join(fails))
    sys.exit(1)
print("RESULT: all suites + static checks passed")
sys.exit(0)
