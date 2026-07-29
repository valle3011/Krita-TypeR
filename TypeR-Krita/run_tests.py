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
]

MODULES = [
    "typer_kr/typer_kr.py", "typer_kr/layout.py", "typer_kr/langpair.py",
    "typer_kr/fontfav.py", "typer_kr/fontfav_ui.py", "typer_kr/fontfiles.py",
    "typer_kr/imgfx.py", "typer_kr/patterngen.py",
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
# the conditional `def hyph_fn` inside `if hyphenate:` is a known false positive
noise = [ln for ln in pf.stdout.splitlines()
         if ln.strip() and "redefinition of unused 'hyph_fn'" not in ln]
if pf.returncode == 127 or "No module named pyflakes" in (pf.stderr or ""):
    print("  --   pyflakes not installed, skipped")
elif noise:
    print("\n".join(noise))
    fails.append("pyflakes")
else:
    print("  ok   no pyflakes findings")
print()

for s in SUITES:
    run(s, [s])

print("=" * 64)
if fails:
    print("RESULT: FAILED -> " + ", ".join(fails))
    sys.exit(1)
print("RESULT: all suites + static checks passed")
sys.exit(0)
