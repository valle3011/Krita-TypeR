# -*- coding: utf-8 -*-
"""Find installed font files by family name, and install font files for the
CURRENT USER on Windows (no admin) — used by the favourites/preset export so a
bundle can carry the actual fonts and set them up on another machine.

Locating files is done by reading each installed font file's own ``name`` table
(the sfnt naming records) instead of trusting the Windows font registry. The
registry only knows the name a font was *registered* under, which for repacked
comic faces is routinely something else than the family Krita lists
("BadaBoom Pro BB Regular", "ImaginaryFriendBBW00-Rg"), and it holds one entry
per file, so a registry lookup silently dropped every family it couldn't spell
exactly and never picked up a family's Bold/Italic files. That is why an export
used to carry only a fraction of the fonts.

What the index does instead:

* reads family (name IDs 1 + 16), full name (4) and subfamily (2) from every
  font file found in the system/user font folders *and* every path the registry
  points at — .ttc/.otc collections included;
* matches a wanted family through :mod:`typer_kr.fontmatch`'s tolerant ladder,
  so the spelling differences above still resolve;
* returns **all** files of that family — every weight and cut, not just the one
  file whose name happened to match.

Installing copies the files into the per-user font folder, registers them under
HKCU and tells running apps about it; Krita may still need a restart to list a
brand-new face.
"""

import json
import os
import re
import struct
import sys
import shutil

from ._qt import QFontDatabase
from . import fontmatch

_FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc")

#: name-table IDs worth reading: 1 family, 2 subfamily, 4 full name,
#: 16 typographic family (what Qt reports for families with >4 cuts).
_NID_FAMILY = 1
_NID_SUBFAMILY = 2
_NID_FULL = 4
_NID_TYPO_FAMILY = 16


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
    """{display_name_lower: filepath} from the HKLM + HKCU font registrations.

    Only used as an extra source of *paths* now (a font may be registered from
    a folder nobody scans); the names it carries are not trusted for matching.
    """
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


# ---------------------------------------------------------------------------
#  Reading names straight out of the font files
# ---------------------------------------------------------------------------
def _decode_name(platform_id, encoding_id, raw):
    try:
        if platform_id in (0, 3):                       # Unicode / Windows
            return raw.decode("utf-16-be", "ignore")
        if encoding_id == 0:                            # Mac Roman
            return raw.decode("mac_roman", "ignore")
        return raw.decode("latin-1", "ignore")
    except Exception:                                   # noqa: BLE001
        return ""


def _clean_name(s):
    return re.sub(r"[\x00-\x1f]", "", s or "").strip()


def _names_of_face(fh, base):
    """(families, fulls) declared by the face whose table directory starts at
    *base* in the open file *fh*. Unreadable/odd files give empty sets."""
    fams, fulls = set(), set()
    try:
        fh.seek(base)
        head = fh.read(12)
        if len(head) < 12:
            return fams, fulls
        num_tables = struct.unpack(">H", head[4:6])[0]
        if not 0 < num_tables < 512:
            return fams, fulls
        recs = fh.read(16 * num_tables)
        off = length = 0
        for i in range(0, len(recs) - 15, 16):
            if recs[i:i + 4] == b"name":
                off, length = struct.unpack(">II", recs[i + 8:i + 16])
                break
        if not off or not length:
            return fams, fulls
        fh.seek(off)
        data = fh.read(min(length, 1 << 22))
        if len(data) < 6:
            return fams, fulls
        _fmt, count, str_off = struct.unpack(">HHH", data[:6])
        if count > 4096:
            return fams, fulls
        # Every spelling counts: a font carries its name once per language, and
        # which one Krita lists is not ours to guess ("MS Gothic" and
        # "ＭＳ ゴシック" are the same file). Keeping them all makes each a
        # lookup key; the English (0x409) records additionally form the
        # family+subfamily full name.
        all_ids = {}
        english = {}
        for i in range(count):
            p = 6 + 12 * i
            rec = data[p:p + 12]
            if len(rec) < 12:
                break
            pid, eid, lid, nid, ln, noff = struct.unpack(">6H", rec)
            if nid not in (_NID_FAMILY, _NID_SUBFAMILY, _NID_FULL,
                           _NID_TYPO_FAMILY):
                continue
            start = str_off + noff
            raw = data[start:start + ln]
            if len(raw) < ln:
                continue
            val = _clean_name(_decode_name(pid, eid, raw))
            if not val:
                continue
            all_ids.setdefault(nid, set()).add(val)
            if (pid == 3 and lid == 0x409) or (pid == 1 and lid == 0):
                english.setdefault(nid, val)
        for nid in (_NID_FAMILY, _NID_TYPO_FAMILY):
            fams |= all_ids.get(nid, set())
        fulls |= all_ids.get(_NID_FULL, set())
        fam1 = english.get(_NID_FAMILY)
        sub1 = english.get(_NID_SUBFAMILY)
        if fam1 and sub1:
            fulls.add("%s %s" % (fam1, sub1))
    except Exception:                                   # noqa: BLE001
        return fams, fulls
    return fams, fulls


def font_file_names(path):
    """(families, fulls) declared by a font file — handles .ttc/.otc bundles."""
    fams, fulls = set(), set()
    try:
        with open(path, "rb") as fh:
            tag = fh.read(4)
            if tag == b"ttcf":
                fh.seek(8)
                (num,) = struct.unpack(">I", fh.read(4))
                if not 0 < num < 256:
                    return fams, fulls
                offs = struct.unpack(">%dI" % num, fh.read(4 * num))
                for o in offs:
                    f, u = _names_of_face(fh, o)
                    fams |= f
                    fulls |= u
            else:
                f, u = _names_of_face(fh, 0)
                fams |= f
                fulls |= u
    except Exception:                                   # noqa: BLE001
        pass
    return fams, fulls


# ---------------------------------------------------------------------------
#  The index
# ---------------------------------------------------------------------------
class FontFileIndex(object):
    """Every installed font file, keyed by the names it declares.

    Lookups return *all* files of a family (Regular, Bold, Italic, …) so a
    bundle carries a usable font instead of a single cut.
    """

    def __init__(self, paths=None, names_fn=None):
        self.by_family = {}         # lower family name -> [paths]
        self.by_full = {}           # lower full name   -> [paths]
        self._full_fams = {}        # lower full name   -> set(lower families)
        self._sibling = {}          # token key         -> set(lower families)
        self._squash = {}           # squashed family   -> set(lower families)
        self._fam_names = {}        # lower -> original spelling
        names_fn = names_fn or font_file_names
        for path in (paths if paths is not None else all_font_paths()):
            fams, fulls = names_fn(path)
            if not fams and not fulls:
                continue
            lows = set()
            for fam in fams:
                low = fam.lower()
                lows.add(low)
                self.by_family.setdefault(low, []).append(path)
                self._fam_names.setdefault(low, fam)
                self._squash.setdefault(fontmatch.squash(fam), set()).add(low)
                base, _b, _i = fontmatch.split_cut(fontmatch.tokens(fam))
                if base:
                    key = "".join(sorted(base))
                    self._sibling.setdefault(key, set()).add(low)
            for full in fulls:
                fl = full.lower()
                self.by_full.setdefault(fl, []).append(path)
                if lows:
                    self._full_fams.setdefault(fl, set()).update(lows)
        self._matcher = fontmatch.FontIndex(list(self._fam_names.values()))

    # -- internals ---------------------------------------------------------
    def _files_for_families(self, lows):
        out = []
        seen = set()
        for low in lows:
            for p in self.by_family.get(low, ()):
                k = p.lower()
                if k not in seen:
                    seen.add(k)
                    out.append(p)
        return out

    def _siblings_of(self, low):
        """That family plus the cuts that live under their own family name
        ("Anime Ace" / "Anime Ace Italic" are two families on many machines)."""
        fam = self._fam_names.get(low, low)
        base, _b, _i = fontmatch.split_cut(fontmatch.tokens(fam))
        key = "".join(sorted(base)) if base else ""
        return self._sibling.get(key, {low}) | {low}

    def _expand(self, lows):
        out = set()
        for low in lows:
            out |= self._siblings_of(low)
        return self._files_for_families(out)

    def _trim_prefix(self, name):
        """Last resort: drop trailing words until what remains is a known
        family. Qt lists a variable font's named instances as families of their
        own ("Bahnschrift SemiBold Condensed") and truncates long ones ("Asap
        Condensed Condensed Regula"); the file behind them is the base family's,
        so shipping that family ships the instance too."""
        toks = re.split(r"\s+", name.strip())
        while len(toks) > 1:
            toks = toks[:-1]
            cand = " ".join(toks)
            low = cand.lower()
            if low in self.by_family:
                return self._expand({low})
            hit = self._squash.get(fontmatch.squash(cand))
            if hit:
                return self._expand(hit)
        return []

    # -- API ---------------------------------------------------------------
    def files_for(self, family):
        """All font files belonging to *family*, best effort. [] if unknown."""
        name = (family or "").strip()
        if not name:
            return []
        low = name.lower()
        if low in self.by_family:
            return self._expand({low})
        hit = self._squash.get(fontmatch.squash(name))
        if hit:
            return self._expand(hit)
        # the wanted spelling may be a *full* name ("BadaBoom Pro BB Regular")
        if low in self.by_full:
            fams = self._full_fams.get(low) or set()
            if fams:
                return self._expand(fams)
            return list(self.by_full[low])
        # tolerant ladder (tokens, cut-stripping, foundry tags, fuzzy)
        m = self._matcher.resolve(name)
        if m:
            return self._expand({m.family.lower()})
        return self._trim_prefix(name)


_INDEX = None
#: bump whenever the parser's output changes, so old caches are ignored
_CACHE_VERSION = 2


def all_font_paths():
    """Every font file on this machine worth looking at: the font folders plus
    whatever the Windows registry points at (fonts installed from elsewhere)."""
    paths = []
    seen = set()
    for p in _iter_font_files():
        low = p.lower()
        if low not in seen:
            seen.add(low)
            paths.append(p)
    if sys.platform == "win32":
        try:
            reg = _windows_registry_fonts()
        except Exception:                               # noqa: BLE001
            reg = {}
        for p in reg.values():
            low = p.lower()
            if low in seen or not p.lower().endswith(_FONT_EXTS):
                continue
            if os.path.exists(p):
                seen.add(low)
                paths.append(p)
    return paths


def _cache_path():
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        base = os.path.join(root, "TypeR-Krita")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches/typer_kr")
    else:
        base = os.path.join(
            os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
            "typer_kr")
    return os.path.join(base, "fontindex.json")


def _load_cache():
    """{path_lower: [mtime, size, [families], [fulls]]} from the last scan."""
    try:
        with open(_cache_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get("v") == _CACHE_VERSION:
            ent = data.get("entries")
            if isinstance(ent, dict):
                return ent
    except Exception:                                   # noqa: BLE001
        pass
    return {}


def _save_cache(entries):
    try:
        p = _cache_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"v": _CACHE_VERSION, "entries": entries}, fh)
        os.replace(tmp, p)              # atomic, overwrites an older cache
    except Exception:                                   # noqa: BLE001
        pass


def build_index(use_cache=True, progress=None):
    """Scan every installed font file and index the names it declares.

    Reading ~9000 font files cold takes a while, so the parsed names are cached
    on disk keyed by (mtime, size): later runs only touch files that changed and
    newly installed ones. *progress* is called as ``progress(done, total)``
    every so often, for a UI that wants to show the one slow first run.
    """
    paths = all_font_paths()
    cache = _load_cache() if use_cache else {}
    fresh = {}
    dirty = False
    parsed = {}
    total = len(paths)
    for i, p in enumerate(paths):
        if progress is not None and not i % 200:
            try:
                progress(i, total)
            except Exception:                           # noqa: BLE001
                progress = None
        key = p.lower()
        try:
            st = os.stat(p)
            sig = [int(st.st_mtime), int(st.st_size)]
        except OSError:
            continue
        old = cache.get(key)
        if (isinstance(old, list) and len(old) == 4
                and old[0] == sig[0] and old[1] == sig[1]):
            fams, fulls = set(old[2]), set(old[3])
        else:
            fams, fulls = font_file_names(p)
            dirty = True
        fresh[key] = [sig[0], sig[1], sorted(fams), sorted(fulls)]
        parsed[p] = (fams, fulls)
    if use_cache and (dirty or len(fresh) != len(cache)):
        _save_cache(fresh)
    return FontFileIndex(paths, names_fn=lambda p: parsed.get(p, (set(), set())))


def font_index(refresh=False):
    """The shared :class:`FontFileIndex` (built once, then cached)."""
    global _INDEX
    if _INDEX is None or refresh:
        _INDEX = build_index()
    return _INDEX


def index_ready():
    """True when the index is in memory (a lookup will be instant)."""
    return _INDEX is not None


def ensure_index(parent=None, label=""):
    """Build the index, showing a progress dialog while it happens.

    Only the very first run after installing a font parses anything; with a warm
    cache this returns in well under a second, and the dialog's minimum duration
    means it never flashes for that case. Falls back to a silent build if no UI
    can be put up.
    """
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    dlg = None
    try:
        from ._qt import QProgressDialog, Qt, QApplication
        dlg = QProgressDialog(label or "Reading the installed fonts…", "",
                              0, 0, parent)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(700)
        dlg.setAutoClose(False)

        def _tick(done, total):
            dlg.setMaximum(total)
            dlg.setValue(done)
            QApplication.processEvents()

        _INDEX = build_index(progress=_tick)
    except Exception:                                   # noqa: BLE001
        _INDEX = build_index()
    finally:
        if dlg is not None:
            try:
                dlg.close()
                dlg.deleteLater()
            except Exception:                           # noqa: BLE001
                pass
    return _INDEX


def invalidate_index():
    """Forget the cached index (call after installing fonts)."""
    global _INDEX
    _INDEX = None


def collect_font_files(families, parent=None, label=""):
    """Map each wanted family to **all** its font files on this machine.

    Returns ``(found, missing)`` where *found* is ``{family_as_given: [paths]}``
    (every weight/cut that belongs to the family) and *missing* lists the
    families nothing could be found for. *parent*/*label* are handed to
    :func:`ensure_index` for the progress dialog of the one slow first scan.
    """
    wanted = []
    seen = set()
    for fam in families or []:
        f = (fam or "").strip()
        if f and f.lower() not in seen:
            seen.add(f.lower())
            wanted.append(f)
    if not wanted:
        return {}, []
    idx = ensure_index(parent, label)
    found, missing = {}, []
    for fam in wanted:
        files = idx.files_for(fam)
        if files:
            found[fam] = files
        else:
            missing.append(fam)
    return found, missing


def find_font_files(families):
    """Map each wanted family to one font file — kept for callers that only
    need a single path per family. Prefer :func:`collect_font_files`."""
    found, _missing = collect_font_files(families)
    return {fam: paths[0] for fam, paths in found.items() if paths}


def add_fonts_to_zip(zf, files, folder="fonts/"):
    """Write font files into an open :class:`zipfile.ZipFile` under *folder*.

    *files* is what :func:`collect_font_files` returns (``{family: [paths]}``),
    a ``{family: path}`` mapping, or a plain iterable of paths. Files already
    written are skipped, and two different files that share a base name both
    survive (the second gets a numbered name). Returns how many were written.
    """
    if isinstance(files, dict):
        paths = []
        for v in files.values():
            paths.extend([v] if isinstance(v, str) else list(v or []))
    else:
        paths = list(files or [])
    done = set()                    # lower-case source paths already written
    used = {}                       # lower-case name in zip -> source path
    n = 0
    for p in paths:
        if not p:
            continue
        key = os.path.normcase(os.path.abspath(p))
        if key in done:
            continue
        done.add(key)
        base = os.path.basename(p)
        name = base
        i = 1
        while used.get(name.lower(), key) != key:
            root, ext = os.path.splitext(base)
            name = "%s_%d%s" % (root, i, ext)
            i += 1
        used[name.lower()] = key
        try:
            zf.write(p, folder + name)
            n += 1
        except Exception:                               # noqa: BLE001
            pass
    return n


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
    if result["installed"]:
        invalidate_index()
    return result
