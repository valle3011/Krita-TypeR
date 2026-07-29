# -*- coding: utf-8 -*-
"""Find installed font files by family name, and install font files for the
CURRENT USER on Windows (no admin) — used by the favourites export/import so a
bundle can carry the actual fonts and set them up on another machine.

Locating the file for a family is done by asking Qt what family each font file
declares (exact match to the names the picker uses). Installing copies the file
into the per-user font folder, registers it under HKCU and tells running apps
about it; Krita may still need a restart to list a brand-new face.
"""

import os
import re
import sys
import shutil

from PyQt5.QtGui import QFontDatabase

_FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc")


def font_dirs():
    """Directories to scan for installed font files, per platform."""
    dirs = []
    if sys.platform == "win32":
        win = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(os.path.join(win, "Fonts"))
        la = os.environ.get("LOCALAPPDATA", "")
        if la:
            dirs.append(os.path.join(la, "Microsoft", "Windows", "Fonts"))
    elif sys.platform == "darwin":
        home = os.path.expanduser("~")
        dirs += ["/System/Library/Fonts", "/Library/Fonts",
                 os.path.join(home, "Library", "Fonts")]
    else:
        home = os.path.expanduser("~")
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts",
                 os.path.join(home, ".fonts"),
                 os.path.join(home, ".local", "share", "fonts")]
    return [d for d in dirs if os.path.isdir(d)]


def _iter_font_files():
    seen = set()
    for d in font_dirs():
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith(_FONT_EXTS):
                    p = os.path.join(root, f)
                    low = p.lower()
                    if low not in seen:
                        seen.add(low)
                        yield p


def _families_of(path):
    """The family names a font file declares (via Qt), or []."""
    fid = QFontDatabase.addApplicationFont(path)
    if fid == -1:
        return []
    try:
        return list(QFontDatabase.applicationFontFamilies(fid))
    finally:
        QFontDatabase.removeApplicationFont(fid)


def _windows_registry_fonts():
    """{display_name_lower: filepath} from the HKLM + HKCU font registrations —
    a fast lookup that avoids loading every font file."""
    import winreg
    out = {}
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    suffix = re.compile(r"\s*\((?:TrueType|OpenType|All res)\)\s*$", re.I)
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(
                hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        except Exception:                               # noqa: BLE001
            continue
        try:
            i = 0
            while True:
                try:
                    name, val, _t = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                if not isinstance(val, str) or not val:
                    continue
                disp = suffix.sub("", name).strip().lower()
                path = val if os.path.isabs(val) else os.path.join(fonts_dir, val)
                if disp:
                    out.setdefault(disp, path)
        finally:
            winreg.CloseKey(key)
    return out


def find_font_files(families):
    """Map each wanted family (case-insensitively) to a font file on this
    machine. Returns {family_as_given: filepath}; families whose file isn't
    found are omitted.

    Fast path on Windows: the font registry maps display names to files, so most
    fonts are found instantly. Anything not resolved that way falls back to
    probing font files with Qt (exact family match, but slower)."""
    want = {}
    for fam in families or []:
        fl = (fam or "").strip().lower()
        if fl:
            want.setdefault(fl, fam)
    if not want:
        return {}
    found = {}
    if sys.platform == "win32":
        # Registry-only on Windows: it lists every installed font, so this is
        # instant and avoids a multi-second scan when a favourite simply isn't
        # installed (which can't be bundled anyway).
        try:
            reg = _windows_registry_fonts()
        except Exception:                               # noqa: BLE001
            reg = {}
        for fl, orig in want.items():
            p = reg.get(fl)
            if p and os.path.exists(p):
                found[orig] = p
        return found
    # other platforms: probe font files with Qt (exact family match)
    remaining = dict(want)
    for path in _iter_font_files():
        if not remaining:
            break
        for fam in _families_of(path):
            fl = fam.lower()
            if fl in remaining:
                found[remaining.pop(fl)] = path
    return found


def install_fonts(paths):
    """Install font files for the CURRENT USER (no admin) on Windows: copy into
    the per-user font folder, register under HKCU, notify running apps, and also
    load them into the running Qt app so TypeR sees them right away.

    Returns {'installed': [...], 'skipped': [...], 'failed': [...]} of base
    filenames. On non-Windows everything lands in 'failed' (nothing installed).
    """
    result = {"installed": [], "skipped": [], "failed": []}
    paths = [p for p in (paths or []) if p and os.path.exists(p)]
    if sys.platform != "win32":
        result["failed"] = [os.path.basename(p) for p in paths]
        return result
    import winreg
    import ctypes
    la = os.environ.get("LOCALAPPDATA", "")
    dest_dir = os.path.join(la, "Microsoft", "Windows", "Fonts")
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except Exception:                                   # noqa: BLE001
        result["failed"] = [os.path.basename(p) for p in paths]
        return result
    for p in paths:
        base = os.path.basename(p)
        try:
            dest = os.path.join(dest_dir, base)
            if os.path.exists(dest):
                # already there: make sure the running app can use it
                QFontDatabase.addApplicationFont(dest)
                result["skipped"].append(base)
                continue
            shutil.copy2(p, dest)
            fams = _families_of(dest)
            name = fams[0] if fams else os.path.splitext(base)[0]
            typ = ("(OpenType)" if base.lower().endswith((".otf", ".otc"))
                   else "(TrueType)")
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
                    0, winreg.KEY_SET_VALUE)
                try:
                    winreg.SetValueEx(key, "%s %s" % (name, typ), 0,
                                      winreg.REG_SZ, dest)
                finally:
                    winreg.CloseKey(key)
            except Exception:                           # noqa: BLE001
                pass
            try:
                ctypes.windll.gdi32.AddFontResourceW(dest)
                ctypes.windll.user32.SendMessageTimeoutW(
                    0xFFFF, 0x001D, 0, 0, 0, 1000, None)   # WM_FONTCHANGE
            except Exception:                           # noqa: BLE001
                pass
            QFontDatabase.addApplicationFont(dest)      # usable now, no restart
            result["installed"].append(base)
        except Exception:                               # noqa: BLE001
            result["failed"].append(base)
    return result
