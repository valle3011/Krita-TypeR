# -*- coding: utf-8 -*-
"""
SFX Helper – die eigentliche Docker-Klasse (UI + Logik).

Sprache: Standard Englisch, umschaltbar auf Deutsch (oben im Docker).
Komfort: Live-Vorschau, GROSSBUCHSTABEN-Schalter, merkt sich den zuletzt
genutzten Stil über Neustarts.
"""
import base64
import json
import math
import os
import re

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QSpinBox, QSlider, QColorDialog, QScrollArea,
    QCompleter, QInputDialog, QMessageBox, QMenu, QCheckBox,
    QDialog, QDialogButtonBox, QFileDialog, QSizePolicy, QToolButton,
    QListWidget, QListWidgetItem,
)
from PyQt5.QtGui import (
    QColor, QFontDatabase, QFont, QFontMetricsF, QPainter, QPainterPath,
    QBrush, QPen, QLinearGradient, QImage, QPixmap, QIcon,
)
from PyQt5.QtCore import (
    Qt, QTimer, QStringListModel, QEvent, QBuffer, QByteArray, QSize,
)

from krita import Krita, DockWidget

from .config import (
    SFX_FONTS, SFX_PRESETS, SFX_RULES, DEFAULTS, SHOW_ALL_SYSTEM_FONTS,
    SFX_MODES, SFX_MODE_NAMES,
)
from .svg_builder import build_sfx_svg, _xml_escape
from .rule_search import normalize_sfx, keyword_matches, rule_matches_query
from . import modes as MODES
from .presets_store import (
    load_user_presets, save_user_presets, load_font_rules, save_font_rules,
    load_language, save_language, load_settings, save_settings,
    load_view, save_view, load_usage, save_usage,
    load_rule_lang, save_rule_lang,
    load_mode, save_mode, load_separate_builtins, save_separate_builtins,
    load_hidden_builtins_modes, save_hidden_builtins_modes,
    load_hidden_builtins, save_hidden_builtins,
)

# Sprachen, für die SFX-Regeln gewählt werden können (Endonyme fürs Dropdown).
RULE_LANGS = ("en", "de", "es", "fr", "pt", "it")
RULE_LANG_NAMES = {
    "en": "English", "de": "Deutsch", "es": "Español",
    "fr": "Français", "pt": "Português", "it": "Italiano",
}
from .i18n import tr, LANGUAGES


# ---------------------------------------------------------------------------
# Mausrad-sichere Widgets
#
# Combos/Spins/Slider ändern ihren Wert bei einem Mausrad-Tick auch dann, wenn
# sie nur zufällig unter dem Cursor liegen, während man das Panel scrollt – das
# verstellt versehentlich Schrift/Größe/Regelsprache. Diese Unterklassen
# reagieren nur auf das Rad, wenn sie wirklich den Fokus haben; sonst wird das
# Ereignis weitergereicht (die ScrollArea scrollt dann).
# ---------------------------------------------------------------------------
class NoScrollComboBox(QComboBox):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class NoScrollSpinBox(QSpinBox):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class NoScrollSlider(QSlider):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


# ---------------------------------------------------------------------------
# System-Schriften nur EINMAL pro Krita-Sitzung ermitteln
#
# Das Aufzählen tausender Fonts (QFontDatabase().families()) ist teuer und
# passierte bisher bei JEDEM Öffnen des Dockers und jedem Sprachwechsel – der
# Hauptgrund fürs Ruckeln beim Öffnen. Hier wird die Liste modulweit gecacht,
# überlebt also auch das Schließen/Wieder-Öffnen des Dockers.
# ---------------------------------------------------------------------------
_SYSTEM_FAMILIES = None


def _system_families():
    global _SYSTEM_FAMILIES
    if _SYSTEM_FAMILIES is None:
        try:
            _SYSTEM_FAMILIES = sorted(QFontDatabase().families())
        except Exception:
            _SYSTEM_FAMILIES = []
    return _SYSTEM_FAMILIES


def _svg_text_content(svg):
    """First non-empty <text> content of an SVG shape, tags stripped and XML
    entities decoded. Used to read an existing SFX word back off a vector
    layer (the fill/outline/shadow copies all carry the same text)."""
    for m in re.finditer(r"<text[^>]*>(.*?)</text>", svg or "", re.S):
        t = re.sub(r"<[^>]+>", "", m.group(1))          # drop nested tspans
        t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
              .replace("&quot;", '"').replace("&apos;", "'").strip())
        if t:
            return t
    return ""


class CollapsibleSection(QWidget):
    """Abschnitt mit fetter, anklickbarer Überschrift (▾/▸) zum Ein-/Ausklappen.

    add(widget|layout) füllt den Inhalt. Der zugeklappte Zustand wird über
    on_toggle(key, collapsed) an den Docker zum Speichern gemeldet. Ein-/
    Ausblenden des GANZEN Abschnitts macht der Docker über setVisible()."""

    def __init__(self, title, key, on_toggle=None):
        super().__init__()
        self.key = key
        self._on_toggle = on_toggle
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        self.setLayout(outer)

        self.header = QToolButton()
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.DownArrow)
        self.header.setAutoRaise(True)
        self.header.setFocusPolicy(Qt.NoFocus)
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header.setStyleSheet(
            "QToolButton { font-weight: bold; border: none; padding: 2px 0; }")
        self.header.toggled.connect(self._toggled)
        outer.addWidget(self.header)

        self.body = QWidget()
        self._body_lay = QVBoxLayout()
        self._body_lay.setContentsMargins(10, 0, 0, 4)   # leichte Einrückung
        self._body_lay.setSpacing(4)
        self.body.setLayout(self._body_lay)
        outer.addWidget(self.body)

    def add(self, item):
        if isinstance(item, (QHBoxLayout, QVBoxLayout, QGridLayout)):
            self._body_lay.addLayout(item)
        else:
            self._body_lay.addWidget(item)

    def body_layout(self):
        """Body-Layout für Helfer, die direkt in ein Layout bauen wollen."""
        return self._body_lay

    def set_collapsed(self, collapsed):
        self.header.setChecked(not collapsed)
        self.body.setVisible(not collapsed)
        self.header.setArrowType(Qt.RightArrow if collapsed else Qt.DownArrow)

    def _toggled(self, expanded):
        self.body.setVisible(expanded)
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        if self._on_toggle:
            self._on_toggle(self.key, not expanded)


# ---------------------------------------------------------------------------
# Lautmuster-Heuristik
#
# Ordnet ein UNBEKANNTES SFX (für das keine Regel direkt matcht) anhand seines
# Klangbilds einer der vorhandenen Gruppen zu. Bewusst grob – nur als Fallback,
# damit auch erfundene SFX ("DKKBAM", "fwooosh") einen Vorschlag bekommen.
# ---------------------------------------------------------------------------

_SFX_HARD = set("bdgkpqt")          # harte Plosive  -> Aufprall/Knall
_SFX_SIB = set("fsz")               # Zischlaute     -> Wisch/Energie
_SFX_NASAL = set("mn")
_SFX_LIQUID = set("lr")
_END_VOWEL_RE = re.compile(r"([aeiouy])\1{2,}$")   # 3+ gleiche End-Vokale


def classify_sfx(word, available=None):
    """Grobe Stimmungs-Schätzung für ein unbekanntes SFX anhand von Lautmustern.

    Gibt bis zu zwei Gruppennamen zurück (nur solche, die in `available`
    enthalten sind, falls angegeben). Greift im Docker nur, wenn keine echte
    Regel matcht."""
    raw = (word or "").strip()
    letters = [c for c in raw.lower() if c.isalpha()]
    if len(letters) < 2:
        return []
    s = "".join(letters)
    n = len(s)
    hard = sum(1 for c in s if c in _SFX_HARD)
    sib = sum(1 for c in s if c in _SFX_SIB) + s.count("sh") + s.count("wh")
    nasal = sum(1 for c in s if c in _SFX_NASAL)
    liquid = sum(1 for c in s if c in _SFX_LIQUID)
    z = s.count("z")
    g = s.count("g")
    r = s.count("r")
    caps = raw.isupper() and n >= 2
    bang = "!" in raw
    only_z = set(s) <= {"z"}
    end_vowel_run = bool(_END_VOWEL_RE.search(s))

    score = {}

    def add(group, pts):
        if pts > 0:
            score[group] = score.get(group, 0) + pts

    if only_z:                                  # "zzz" -> Schlaf
        add("Breath / Sleep", 5)
    elif z:                                     # sonst Strom/Energie
        add("Electric / Spark", 2 + z)
    if hard >= 2:
        add("Boom / Explosion", hard + (1 if caps else 0) + (1 if bang else 0))
    if hard >= 1 and n <= 5:
        add("Hit / Punch", hard + (1 if caps else 0))
    if sib >= 1 and ("w" in s or "f" in s or s.count("sh")):
        add("Whoosh / Dash", sib + 1)
    if end_vowel_run:
        add("Scream / Shout", 3 + (1 if caps else 0) + (1 if bang else 0))
    if g >= 1 and r >= 1:
        add("Roar / Growl", g + r + 1)
    if (s.count("sp") or s.count("dr") or s.count("pl") or s.count("bl")
            or s.count("gl")):
        add("Water / Liquid", 2)
    if (nasal + liquid) >= 2 and hard == 0 and not caps and not bang:
        add("Whisper / Silence", nasal + liquid)
    if bang and not score:
        add("Scream / Shout", 2)

    if not score:
        return []
    ordered = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
    if available is not None:
        ordered = [(grp, pts) for grp, pts in ordered if grp in available]
    if not ordered:
        return []
    top = ordered[0][1]
    return [grp for grp, pts in ordered if pts >= max(2, top * 0.6)][:2]


class SFXPreview(QWidget):
    """WYSIWYG-Vorschau des SFX-Texts.

    Zeichnet den Text per QPainterPath in der Reihenfolge
    Schatten -> Kontur -> Füllung (wie die eingefügte Ebene), eingepasst in die
    Vorschaufläche. Kontur- und Schattenstärke bleiben proportional zur
    eingestellten Größe, damit die Wirkung dem späteren Ergebnis entspricht."""

    _MARGIN = 8

    def __init__(self):
        super().__init__()
        self._opts = None
        self._fit_cache = (None, 0)      # (key, best_size) – Repaints nicht neu rechnen
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, opts):
        """opts: dict mit text, family, size_ref, bold, italic, fill (QColor),
        outline (bool), outline_color (QColor), outline_px (float),
        shadow (bool), shadow_color (QColor), shadow_dx, shadow_dy."""
        self._opts = opts
        self.update()

    def _fit_size(self, o, text, avail_w, avail_h):
        """Größte ganzzahlige Pixelgröße, bei der der Text in die Fläche passt.
        Ergebnis wird gecacht, damit ein reiner Repaint (Fokus/Hover) nicht die
        Binärsuche samt QFontMetricsF erneut ausführt."""
        key = (text, o.get("family"), bool(o.get("bold")), bool(o.get("italic")),
               int(avail_w), int(avail_h))
        if self._fit_cache[0] == key:
            return self._fit_cache[1]
        lo, hi, best = 6, 240, 6
        while lo <= hi:
            mid = (lo + hi) // 2
            fn = self._font(o, mid)
            fm = QFontMetricsF(fn)
            if fm.horizontalAdvance(text) <= avail_w and fm.height() <= avail_h:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        self._fit_cache = (key, best)
        return best

    def _font(self, o, px):
        fn = QFont(o["family"]) if o["family"] else QFont()
        fn.setItalic(bool(o.get("italic")))
        fn.setBold(bool(o.get("bold")))
        fn.setPixelSize(max(1, int(px)))
        return fn

    def paintEvent(self, _ev):
        # A preview paint must never be able to take Krita down: guard the whole
        # drawing and always release the painter, whatever happens inside.
        p = QPainter(self)
        try:
            self._paint(p)
        except Exception:
            pass
        finally:
            p.end()

    def _paint(self, p):
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        self._paint_background(p, w, h)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(0, 0, w - 1, h - 1)

        o = self._opts
        text = (o or {}).get("text", "").strip() if o else ""
        if not o or not text:
            p.setPen(QColor(0, 0, 0, 110))
            f = QFont()
            f.setItalic(True)
            f.setPixelSize(13)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "Aa")
            return

        m = self._MARGIN
        avail_w = max(10, w - 2 * m)
        avail_h = max(10, h - 2 * m)
        fs = self._fit_size(o, text, avail_w, avail_h)
        fn = self._font(o, fs)
        fm = QFontMetricsF(fn)
        adv = fm.horizontalAdvance(text)
        # waagerecht + senkrecht zentrieren
        x = m + (avail_w - adv) / 2.0
        baseline = m + (avail_h - fm.height()) / 2.0 + fm.ascent()

        path = QPainterPath()
        path.addText(x, baseline, fn, text)

        # Rotation um den optischen Mittelpunkt des Textes
        angle = o.get("rotate", 0)
        if angle:
            cx = x + adv / 2.0
            cy = baseline - fm.ascent() / 2.0
            p.translate(cx, cy)
            p.rotate(angle)
            p.translate(-cx, -cy)

        size_ref = max(1, int(o.get("size_ref", fs)))
        scale = fs / float(size_ref)

        if o.get("shadow") and (o.get("shadow_dx") or o.get("shadow_dy")):
            sp = QPainterPath(path)
            sp.translate(o["shadow_dx"] * scale, o["shadow_dy"] * scale)
            p.fillPath(sp, QBrush(o["shadow_color"]))
        # äußere Kontur zuerst (breiter); an die erste Outline gekoppelt
        if o.get("outline") and o.get("outline2_px", 0) > 0:
            pen2 = QPen(o["outline2_color"])
            pen2.setWidthF(max(0.5, 2.0 * o["outline2_px"] * scale))
            pen2.setJoinStyle(Qt.RoundJoin)
            pen2.setCapStyle(Qt.RoundCap)
            p.strokePath(path, pen2)
        if o.get("outline") and o.get("outline_px", 0) > 0:
            pen = QPen(o["outline_color"])
            pen.setWidthF(max(0.5, 2.0 * o["outline_px"] * scale))
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            p.strokePath(path, pen)
        pat = o.get("pattern_img")
        f2 = o.get("fill2")
        if pat is not None:
            tw, th = o.get("pattern_tile", (0, 0))
            tw = max(1, int(tw * scale))
            th = max(1, int(th * scale))
            pm = QPixmap.fromImage(pat).scaled(
                tw, th, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            p.fillPath(path, QBrush(pm))
        elif f2 is not None:
            br = path.boundingRect()
            grad = QLinearGradient(0.0, br.top(), 0.0, br.bottom())
            grad.setColorAt(0.0, o["fill"])
            grad.setColorAt(1.0, f2)
            p.fillPath(path, QBrush(grad))
        else:
            p.fillPath(path, QBrush(o["fill"]))

        # Tolerant preview: if the chosen family is not installed, Qt already
        # substituted one above; flag it here so the result is honest instead of
        # silently misleading.
        if o.get("missing") and o.get("missing_label"):
            p.resetTransform()
            badge = QFont()
            badge.setPixelSize(11)
            badge.setBold(True)
            p.setFont(badge)
            p.setPen(QColor(0xC9, 0x96, 0x2B))     # amber, as the font chips use
            p.drawText(self.rect().adjusted(4, 0, -4, -3),
                       Qt.AlignLeft | Qt.AlignBottom, o["missing_label"])

    def _paint_background(self, p, w, h):
        """Hellgraues Schachbrett – zeigt helle wie dunkle Textfarben gut."""
        p.fillRect(0, 0, w, h, QColor(0x9A, 0x9A, 0x9A))
        tile = 8
        p.setPen(Qt.NoPen)
        c = QColor(0x88, 0x88, 0x88)
        y = 0
        row = 0
        while y < h:
            x = (row % 2) * tile
            while x < w:
                p.fillRect(x, y, tile, tile, c)
                x += 2 * tile
            y += tile
            row += 1


class MangaSFXDocker(DockWidget):
    """Dockbares Panel zum schnellen Setzen von Manga-SFX (Anzeigename: SFX Helper)."""

    # Standardwerte für das Layout-Panel (Größen + ein-/ausblenden + Klappstatus)
    _VIEW_DEFAULTS = {
        "open": False,
        "preview_show": True, "preview_h": 56,
        "suggest_show": True,
        "font_show": True,
        "style_show": True,
        "shadow_show": True,
        "presets_show": True,
        "rules_show": True,
        "clear_after": False,
        # eingeklappt (Body verborgen) pro Abschnitt
        "collapse_preview": False, "collapse_suggest": False,
        "collapse_font": False, "collapse_style": False,
        "collapse_shadow": False, "collapse_presets": False,
        "collapse_rules": False,
    }

    # Abschnitts-Schlüssel -> (Section-Attribut, Show-Checkbox-Attribut)
    _SECTIONS = (
        ("preview", "sec_preview", "v_preview_chk"),
        ("suggest", "sec_suggest", "v_suggest_chk"),
        ("font", "sec_font", "v_font_chk"),
        ("style", "sec_style", "v_style_chk"),
        ("shadow", "sec_shadow", "v_shadow_chk"),
        ("presets", "sec_presets", "v_presets_chk"),
        ("rules", "sec_rules", "v_rules_chk"),
    )

    def __init__(self):
        super().__init__()
        self._lang = load_language("en")          # Standard: Englisch
        self._user_presets = load_user_presets()  # eigene Presets (persistiert)
        self._font_rules = load_font_rules()      # Stichwort -> Font(s) (persistiert)
        self._pattern_path = ""                   # Textur-/Muster-Bild (Datei) für die Füllung
        self._pattern_krita_name = ""             # ODER ein in Krita gespeichertes Muster
        self._pattern_img = None                  # geladenes QImage (Cache)
        self._pending_state = load_settings()     # zuletzt genutzter Stil
        self._view = self._load_view_merged()     # Layout-/Anzeige-Einstellungen
        self._families_cache = None               # System-Fonts nur einmal laden
        self._usage = load_usage()                # gelernte Wort->Font-Häufigkeit
        self._group_fonts_cache = None            # Gruppenname -> Fonts (gefiltert)
        self._rule_lang = self._load_rule_lang_merged()  # aktive Regelsprache
        self._rule_query = ""                     # Regel-Suchtext (nur Anzeige)
        # Work mode (manga/manhwa/doujin) + per-mode built-in hiding.
        self._mode = self._load_mode_merged()
        self._separate_builtins = load_separate_builtins(True)
        self._hidden_modes = load_hidden_builtins_modes()   # { mode: [keys] }
        self._hidden_global = load_hidden_builtins()        # [keys] (sep off)
        self._migrate_rule_modes()                 # legacy rules adopt the mode
        self._font_model = None                    # Completer-Modell (lazy gefüllt)
        # Collected lines for the 'note' strategy, until they are placed at the
        # panel edge. Per page, so _place_note_list() empties it.
        self._notes = []
        # Tippen entprellen: Vorschau + Vorschläge erst nach kurzer Pause neu
        # bauen, damit schnelles Tippen den Docker nicht ausbremst.
        self._pending_text = ""
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._on_debounced)
        self.setWindowTitle(self.t("window_title"))
        self._build_ui()

    def _load_rule_lang_merged(self):
        """Gespeicherte Regelsprache; sonst die UI-Sprache (falls Regeln dafür
        denkbar sind), sonst Englisch."""
        saved = load_rule_lang(default="")
        if saved in RULE_LANGS:
            return saved
        return self._lang if self._lang in RULE_LANGS else "en"

    def _load_mode_merged(self):
        """Saved work mode if valid, else the first mode."""
        saved = load_mode(default="")
        if saved in SFX_MODES:
            return saved
        return SFX_MODES[0] if SFX_MODES else "manga"

    def _migrate_rule_modes(self):
        """One-time migration: own rules without a mode adopt the active mode,
        so the modes stay cleanly separated. The mode then stays stored."""
        changed = False
        for rr in self._font_rules:
            if not rr.get("mode"):
                rr["mode"] = self._mode
                changed = True
        if changed:
            save_font_rules(self._font_rules)

    def _families(self):
        """Liste aller System-Font-Familien – modulweit nur EINMAL ermittelt
        (siehe _system_families), überlebt das Schließen/Öffnen des Dockers und
        jeden Sprachwechsel. Das wiederholte Laden war der Hauptgrund fürs
        Ruckeln beim Öffnen."""
        return _system_families()

    def _load_view_merged(self):
        """Gespeicherte View-Einstellungen mit den Standards auffüllen."""
        v = dict(self._VIEW_DEFAULTS)
        saved = load_view()
        if isinstance(saved, dict):
            v.update({k: saved[k] for k in saved if k in v})
        return v

    # ------------------------------------------------------------------
    # Pflicht-Override der DockWidget-API (wird hier nicht gebraucht)
    # ------------------------------------------------------------------
    def canvasChanged(self, canvas):
        pass

    # ------------------------------------------------------------------
    # Übersetzungs-Kurzform
    # ------------------------------------------------------------------
    def t(self, key, **kw):
        return tr(self._lang, key, **kw)

    # ==================================================================
    #  UI-Aufbau (wird bei Sprachwechsel komplett neu aufgebaut)
    # ==================================================================
    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        root.setLayout(layout)

        # --- Sprachauswahl --------------------------------------------
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(self.t("lang_label") + ":"))
        self.lang_combo = NoScrollComboBox()
        for code, label in LANGUAGES:
            self.lang_combo.addItem(label, code)
        li = self.lang_combo.findData(self._lang)
        self.lang_combo.setCurrentIndex(li if li >= 0 else 0)
        # erst nach dem Setzen verbinden, sonst feuert es beim Aufbau
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self.lang_combo, 1)
        layout.addLayout(lang_row)

        # --- einklappbares "Layout & Größen"-Panel --------------------
        # Lässt den Nutzer Teile des Dockers vergrößern/verkleinern oder ganz
        # ausblenden; die Wahl wird über Neustarts gemerkt.
        self.view_toggle = QPushButton(self.t("view_toggle"))
        self.view_toggle.setCheckable(True)
        self.view_toggle.setChecked(bool(self._view["open"]))
        self.view_toggle.toggled.connect(self._on_view_toggle)
        layout.addWidget(self.view_toggle)

        self.view_box = QWidget()
        vlay = QVBoxLayout()
        vlay.setContentsMargins(6, 2, 6, 2)
        vlay.setSpacing(4)
        self.view_box.setLayout(vlay)
        hint = QLabel(self.t("view_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        vlay.addWidget(hint)

        vgrid = QGridLayout()
        vgrid.setHorizontalSpacing(8)
        self.v_preview_chk = QCheckBox(self.t("view_preview"))
        self.v_preview_chk.setChecked(bool(self._view["preview_show"]))
        self.v_preview_h = NoScrollSpinBox()
        self.v_preview_h.setRange(28, 600)
        self.v_preview_h.setSingleStep(8)
        self.v_preview_h.setSuffix(" px")
        self.v_preview_h.setValue(int(self._view["preview_h"]))
        self.v_suggest_chk = QCheckBox(self.t("view_suggest"))
        self.v_suggest_chk.setChecked(bool(self._view["suggest_show"]))
        self.v_font_chk = QCheckBox(self.t("view_font"))
        self.v_font_chk.setChecked(bool(self._view["font_show"]))
        self.v_style_chk = QCheckBox(self.t("view_style"))
        self.v_style_chk.setChecked(bool(self._view["style_show"]))
        self.v_shadow_chk = QCheckBox(self.t("view_shadow"))
        self.v_shadow_chk.setChecked(bool(self._view["shadow_show"]))
        self.v_presets_chk = QCheckBox(self.t("view_presets"))
        self.v_presets_chk.setChecked(bool(self._view["presets_show"]))
        self.v_rules_chk = QCheckBox(self.t("view_rules"))
        self.v_rules_chk.setChecked(bool(self._view["rules_show"]))
        # zweispaltig anordnen
        vgrid.addWidget(self.v_preview_chk, 0, 0)
        vgrid.addWidget(self.v_preview_h, 0, 1)
        vgrid.addWidget(self.v_suggest_chk, 1, 0)
        vgrid.addWidget(self.v_font_chk, 1, 1)
        vgrid.addWidget(self.v_style_chk, 2, 0)
        vgrid.addWidget(self.v_shadow_chk, 2, 1)
        vgrid.addWidget(self.v_presets_chk, 3, 0)
        vgrid.addWidget(self.v_rules_chk, 3, 1)
        vgrid.setColumnStretch(0, 1)
        vgrid.setColumnStretch(1, 1)
        vlay.addLayout(vgrid)

        # Workflow-Optionen
        self.v_clear_after_chk = QCheckBox(self.t("view_clear_after"))
        self.v_clear_after_chk.setChecked(bool(self._view["clear_after"]))
        vlay.addWidget(self.v_clear_after_chk)

        btn_row = QHBoxLayout()
        self.compact_btn = QPushButton(self.t("view_compact"))
        self.compact_btn.setToolTip(self.t("view_compact_tip"))
        self.compact_btn.clicked.connect(self._on_compact)
        self.view_reset_btn = QPushButton(self.t("view_reset"))
        self.view_reset_btn.clicked.connect(self._on_view_reset)
        btn_row.addWidget(self.compact_btn)
        btn_row.addWidget(self.view_reset_btn)
        vlay.addLayout(btn_row)
        layout.addWidget(self.view_box)
        self.view_box.setVisible(self.view_toggle.isChecked())

        # nach dem Setzen der Startwerte verbinden (sonst feuert es beim Aufbau)
        for _w in (self.v_preview_chk, self.v_suggest_chk, self.v_font_chk,
                   self.v_style_chk, self.v_shadow_chk, self.v_presets_chk,
                   self.v_rules_chk, self.v_clear_after_chk):
            _w.toggled.connect(self._on_view_changed)
        self.v_preview_h.valueChanged.connect(self._on_view_changed)

        # --- 0) Strategie ---------------------------------------------
        # Wie mit dem japanischen Soundwort umgegangen wird. Das war bisher
        # jedes Mal eine Handentscheidung; hier steht sie einmal und steuert,
        # was "Einfügen" tut. Siehe modes.py.
        strat_row = QHBoxLayout()
        self.lbl_strategy = QLabel(self.t("strategy"))
        strat_row.addWidget(self.lbl_strategy)
        self.strategy_combo = NoScrollComboBox()
        for _sid in MODES.STRATEGY_IDS:
            self.strategy_combo.addItem(self.t("strategy_" + _sid), _sid)
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)
        strat_row.addWidget(self.strategy_combo, 1)
        layout.addLayout(strat_row)
        self.strategy_hint = QLabel()
        self.strategy_hint.setWordWrap(True)
        self.strategy_hint.setStyleSheet("color:#999;")
        layout.addWidget(self.strategy_hint)

        # 'note' is the one strategy that needs two things: the original sound
        # (text box, usually read off the layer) and what it MEANS. Its row only
        # appears for that strategy.
        self.note_row = QWidget()
        _nl = QHBoxLayout(self.note_row)
        _nl.setContentsMargins(0, 0, 0, 0)
        self.lbl_note_meaning = QLabel(self.t("note_meaning"))
        _nl.addWidget(self.lbl_note_meaning)
        self.note_meaning_input = QLineEdit()
        self.note_meaning_input.setPlaceholderText(self.t("note_meaning_ph"))
        _nl.addWidget(self.note_meaning_input, 1)
        self.note_list_btn = QPushButton(self.t("note_place_list"))
        self.note_list_btn.setToolTip(self.t("note_place_list_tip"))
        self.note_list_btn.clicked.connect(self._place_note_list)
        _nl.addWidget(self.note_list_btn)
        layout.addWidget(self.note_row)
        self.note_row.setVisible(False)

        # --- 1) Texteingabe -------------------------------------------
        layout.addWidget(self._heading(self.t("sfx_text")))
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText(self.t("sfx_placeholder"))
        self.text_input.setClearButtonEnabled(True)
        self.text_input.returnPressed.connect(self._insert_sfx)  # Enter = einfügen
        self.text_input.installEventFilter(self)                 # Esc = leeren
        txt_row = QHBoxLayout()
        txt_row.addWidget(self.text_input, 1)
        self.from_layer_btn = QPushButton(self.t("from_layer"))
        self.from_layer_btn.setToolTip(self.t("from_layer_tip"))
        self.from_layer_btn.clicked.connect(self._sfx_from_layer)
        txt_row.addWidget(self.from_layer_btn)
        layout.addLayout(txt_row)

        # Schalter: GROSSBUCHSTABEN / Fett / Kursiv (2-spaltig, damit nichts
        # bei schmalem Docker abgeschnitten wird)
        opt_grid = QGridLayout()
        self.upper_chk = QCheckBox(self.t("uppercase"))
        self.upper_chk.setChecked(True)
        self.upper_chk.toggled.connect(self._on_upper_toggled)
        self.bold_chk = QCheckBox(self.t("bold"))
        self.bold_chk.toggled.connect(lambda _c: self._update_preview())
        self.italic_chk = QCheckBox(self.t("italic"))
        self.italic_chk.toggled.connect(lambda _c: self._update_preview())
        opt_grid.addWidget(self.upper_chk, 0, 0)
        opt_grid.addWidget(self.bold_chk, 0, 1)
        opt_grid.addWidget(self.italic_chk, 1, 0)
        opt_grid.setColumnStretch(2, 1)
        layout.addLayout(opt_grid)

        # ============================================================
        #  Inhalts-Abschnitte: jeweils einklappbar (Klick auf die fette
        #  Überschrift) UND über das Layout-Panel einzeln ausblendbar.
        # ============================================================
        # --- Live-Vorschau (WYSIWYG) ---
        self.sec_preview = CollapsibleSection(self.t("preview"), "preview",
                                              self._on_section_collapsed)
        self.preview = SFXPreview()
        self.sec_preview.add(self.preview)
        layout.addWidget(self.sec_preview)

        # --- Live-Vorschläge ---
        self.sec_suggest = CollapsibleSection(self.t("section_suggest"), "suggest",
                                              self._on_section_collapsed)
        self.suggest_box = QVBoxLayout()
        self.suggest_box.setSpacing(3)
        self.sec_suggest.add(self.suggest_box)
        layout.addWidget(self.sec_suggest)
        # textChanged erst jetzt verbinden – suggest_box/preview müssen existieren
        self.text_input.textChanged.connect(self._on_text_changed)

        # --- Schrift ---
        self.sec_font = CollapsibleSection(self.t("font"), "font",
                                           self._on_section_collapsed)
        self.font_combo = self._build_font_combo()
        self.font_combo.currentTextChanged.connect(lambda _t: self._update_preview())
        # "Use" applies the font typed/searched in the box (also on Enter), the
        # same as clicking a suggestion — so a self-searched font is one click.
        self.use_font_btn = QPushButton(self.t("use_font_btn"))
        self.use_font_btn.setToolTip(self.t("use_font_btn_tip"))
        self.use_font_btn.clicked.connect(self._apply_typed_font)
        _le = self.font_combo.lineEdit()
        if _le is not None:
            _le.returnPressed.connect(self._apply_typed_font)
        _frow = QHBoxLayout()
        _frow.setContentsMargins(0, 0, 0, 0)
        _frow.addWidget(self.font_combo, 1)
        _frow.addWidget(self.use_font_btn)
        _fw = QWidget()
        _fw.setLayout(_frow)
        self.sec_font.add(_fw)
        layout.addWidget(self.sec_font)

        # --- Größe & Farben ---
        self.sec_style = CollapsibleSection(self.t("section_style"), "style",
                                            self._on_section_collapsed)
        sb = self.sec_style.body_layout()
        self.size_slider, self.size_spin = self._slider_spin_row(
            sb, self.t("font_size"), 10, 600, DEFAULTS["size"])
        self.size_spin.valueChanged.connect(lambda _v: self._update_preview())
        sb.addWidget(self._heading(self.t("fill_color")))
        self.fill_btn = QPushButton()
        self.fill_btn.setFixedHeight(26)
        self._set_btn_color(self.fill_btn, QColor(DEFAULTS["fill"]))
        self.fill_btn.clicked.connect(lambda: self._pick_color(self.fill_btn))
        sb.addWidget(self.fill_btn)
        # Verlaufsfüllung: zweite Farbe (oben fill -> unten fill2)
        grad_row = QHBoxLayout()
        self.grad_chk = QCheckBox(self.t("gradient_fill"))
        self.grad_chk.toggled.connect(lambda _v: (self._update_grad_enabled(),
                                                  self._update_preview()))
        grad_row.addWidget(self.grad_chk)
        self.fill2_btn = QPushButton()
        self.fill2_btn.setFixedHeight(26)
        self._set_btn_color(self.fill2_btn, QColor(DEFAULTS["fill"]))
        self.fill2_btn.clicked.connect(lambda: self._pick_color(self.fill2_btn))
        grad_row.addWidget(self.fill2_btn, 1)
        sb.addLayout(grad_row)
        self._update_grad_enabled()
        # Textur-/Muster-Füllung: den Text mit einem Bild (Screentone o. Ä.)
        # füllen statt einfarbig. Hat Vorrang vor der Verlaufsfüllung.
        pat_row = QHBoxLayout()
        self.pattern_chk = QCheckBox(self.t("pattern_fill"))
        self.pattern_chk.toggled.connect(
            lambda _v: (self._update_pattern_enabled(), self._update_preview()))
        pat_row.addWidget(self.pattern_chk)
        self.pattern_btn = QPushButton(self.t("pattern_choose"))
        self.pattern_btn.clicked.connect(self._pick_pattern)
        pat_row.addWidget(self.pattern_btn, 1)
        self.pattern_krita_btn = QPushButton(self.t("pattern_krita"))
        self.pattern_krita_btn.setToolTip(self.t("pattern_krita_tip"))
        self.pattern_krita_btn.clicked.connect(self._pick_krita_pattern)
        pat_row.addWidget(self.pattern_krita_btn)
        self.pattern_clear_btn = QPushButton("✕")
        self.pattern_clear_btn.setFixedWidth(28)
        self.pattern_clear_btn.setToolTip(self.t("pattern_clear"))
        self.pattern_clear_btn.clicked.connect(self._clear_pattern)
        pat_row.addWidget(self.pattern_clear_btn)
        sb.addLayout(pat_row)
        self.pattern_scale_slider, self.pattern_scale_spin = \
            self._slider_spin_row(sb, self.t("pattern_scale"), 10, 400, 100)
        self.pattern_scale_spin.valueChanged.connect(
            lambda _v: self._update_preview())
        self._update_pattern_enabled()
        sb.addWidget(self._heading(self.t("outline_color")))
        self.outline_btn = QPushButton()
        self.outline_btn.setFixedHeight(26)
        self._set_btn_color(self.outline_btn, QColor(DEFAULTS["outline"]))
        self.outline_btn.clicked.connect(lambda: self._pick_color(self.outline_btn))
        sb.addWidget(self.outline_btn)
        self.out_slider, self.out_spin = self._slider_spin_row(
            sb, self.t("outline_width"), 0, 60, DEFAULTS["outline_px"])
        self.out_spin.valueChanged.connect(lambda _v: self._update_preview())
        # zweite (äußere) Outline für den doppelten Rand (z. B. außen weiß,
        # innen schwarz, dann Text). Breite 0 = aus.
        sb.addWidget(self._heading(self.t("outline2_color")))
        self.outline2_btn = QPushButton()
        self.outline2_btn.setFixedHeight(26)
        self._set_btn_color(self.outline2_btn, QColor(DEFAULTS["outline2"]))
        self.outline2_btn.clicked.connect(
            lambda: self._pick_color(self.outline2_btn))
        sb.addWidget(self.outline2_btn)
        self.out2_slider, self.out2_spin = self._slider_spin_row(
            sb, self.t("outline2_width"), 0, 80, DEFAULTS["outline2_px"])
        self.out2_spin.valueChanged.connect(lambda _v: self._update_preview())
        # Rotation (Grad): dreht die ganze SFX um ihren Mittelpunkt.
        self.rot_slider, self.rot_spin = self._slider_spin_row(
            sb, self.t("rotation"), -180, 180, 0)
        self.rot_spin.valueChanged.connect(lambda _v: self._update_preview())
        layout.addWidget(self.sec_style)

        # --- Schatten ---
        self.sec_shadow = CollapsibleSection(self.t("shadow"), "shadow",
                                             self._on_section_collapsed)
        shb = self.sec_shadow.body_layout()
        self.shadow_chk = QCheckBox(self.t("shadow_enable"))
        self.shadow_chk.setChecked(bool(DEFAULTS.get("shadow", False)))
        self.shadow_chk.toggled.connect(self._on_shadow_toggled)
        shb.addWidget(self.shadow_chk)
        self.shadow_btn = QPushButton(self.t("shadow_color"))
        self.shadow_btn.setFixedHeight(26)
        self._set_btn_color(self.shadow_btn,
                            QColor(DEFAULTS.get("shadow_color", "#000000")))
        self.shadow_btn.clicked.connect(lambda: self._pick_color(self.shadow_btn))
        shb.addWidget(self.shadow_btn)
        shb.addWidget(QLabel(self.t("shadow_offset")))
        sh_row = QHBoxLayout()
        self.shadow_dx = NoScrollSpinBox()
        self.shadow_dx.setRange(-100, 100)
        self.shadow_dx.setValue(int(DEFAULTS.get("shadow_dx", 6)))
        self.shadow_dx.valueChanged.connect(lambda _v: self._update_preview())
        self.shadow_dy = NoScrollSpinBox()
        self.shadow_dy.setRange(-100, 100)
        self.shadow_dy.setValue(int(DEFAULTS.get("shadow_dy", 6)))
        self.shadow_dy.valueChanged.connect(lambda _v: self._update_preview())
        sh_row.addWidget(self.shadow_dx)
        sh_row.addWidget(self.shadow_dy)
        sh_row.addStretch(1)
        shb.addLayout(sh_row)
        layout.addWidget(self.sec_shadow)
        self._update_shadow_enabled()

        # --- Presets (integriert + selbst angelegte) ---
        self.sec_presets = CollapsibleSection(self.t("presets"), "presets",
                                              self._on_section_collapsed)
        self.preset_box = QVBoxLayout()
        self.sec_presets.add(self.preset_box)
        self.save_preset_btn = QPushButton(self.t("save_preset_btn"))
        self.save_preset_btn.setToolTip(self.t("save_preset_tip"))
        self.save_preset_btn.clicked.connect(self._save_current_as_preset)
        self.sec_presets.add(self.save_preset_btn)
        layout.addWidget(self.sec_presets)
        self._rebuild_presets()

        # --- Font-Vorschläge verwalten (Regeln) ---
        self.sec_rules = CollapsibleSection(self.t("font_suggestions"), "rules",
                                            self._on_section_collapsed)
        rb = self.sec_rules.body_layout()
        # Arbeits-Modus: eigene Regeln gelten nur im Modus, in dem sie entstanden.
        mode_row = QHBoxLayout()
        self.lbl_mode = QLabel(self.t("mode"))
        self.lbl_mode.setToolTip(self.t("mode_tip"))
        mode_row.addWidget(self.lbl_mode)
        self.mode_combo = NoScrollComboBox()
        for code in SFX_MODES:
            self.mode_combo.addItem(SFX_MODE_NAMES.get(code, code), code)
        mi = self.mode_combo.findData(self._mode)
        self.mode_combo.setCurrentIndex(mi if mi >= 0 else 0)
        self.mode_combo.setToolTip(self.t("mode_tip"))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._make_shrinkable(self.mode_combo)
        mode_row.addWidget(self.mode_combo, 1)
        rb.addLayout(mode_row)
        # Regelsprache: nur Regeln dieser Sprache (+ "*") werden gezeigt/aktiv.
        rl_row = QHBoxLayout()
        self.lbl_rule_lang = QLabel(self.t("rule_lang"))
        rl_row.addWidget(self.lbl_rule_lang)
        self.rule_lang_combo = NoScrollComboBox()
        for code in RULE_LANGS:
            self.rule_lang_combo.addItem(RULE_LANG_NAMES.get(code, code), code)
        ri = self.rule_lang_combo.findData(self._rule_lang)
        self.rule_lang_combo.setCurrentIndex(ri if ri >= 0 else 0)
        self.rule_lang_combo.currentIndexChanged.connect(self._on_rule_lang_changed)
        self._make_shrinkable(self.rule_lang_combo)
        rl_row.addWidget(self.rule_lang_combo, 1)
        rb.addLayout(rl_row)
        # „Eingebaute pro Modus“ + Alle ausblenden / zurücksetzen.
        self.sep_builtins_chk = QCheckBox(self.t("builtins_per_mode"))
        self.sep_builtins_chk.setToolTip(self.t("builtins_per_mode_tip"))
        self.sep_builtins_chk.setChecked(bool(self._separate_builtins))
        self.sep_builtins_chk.toggled.connect(self._on_sep_builtins_changed)
        rb.addWidget(self.sep_builtins_chk)
        bi_row = QHBoxLayout()
        self.hide_all_btn = QPushButton(self.t("hide_all_builtins"))
        self.hide_all_btn.setToolTip(self.t("hide_all_builtins_tip"))
        self.hide_all_btn.clicked.connect(self._hide_all_builtins)
        self._make_shrinkable(self.hide_all_btn)
        self.restore_builtins_btn = QPushButton(self.t("restore_builtins"))
        self.restore_builtins_btn.setToolTip(self.t("restore_builtins_tip"))
        self.restore_builtins_btn.clicked.connect(self._restore_builtins)
        self._make_shrinkable(self.restore_builtins_btn)
        bi_row.addWidget(self.hide_all_btn)
        bi_row.addWidget(self.restore_builtins_btn)
        rb.addLayout(bi_row)
        rules_hint = QLabel(self.t("rules_hint"))
        rules_hint.setWordWrap(True)
        rb.addWidget(rules_hint)
        # Suchfeld: filtert nur die Anzeige, nie die aktiven Regeln.
        self.rule_search = QLineEdit(self._rule_query)
        self.rule_search.setPlaceholderText(self.t("rule_search_ph"))
        self.rule_search.setToolTip(self.t("rule_search_tip"))
        self.rule_search.setClearButtonEnabled(True)
        self.rule_search.textChanged.connect(self._on_rule_search)
        self.rule_search.installEventFilter(self)                 # Esc = leeren
        self._make_shrinkable(self.rule_search)
        rb.addWidget(self.rule_search)
        self.rules_box = QVBoxLayout()
        self.rules_box.setSpacing(3)
        rb.addLayout(self.rules_box)
        self.rule_count_lbl = QLabel("")
        self.rule_count_lbl.setVisible(False)
        rb.addWidget(self.rule_count_lbl)
        self.add_rule_btn = QPushButton(self.t("add_rule_btn"))
        self.add_rule_btn.setToolTip(self.t("add_rule_tip"))
        self.add_rule_btn.clicked.connect(self._add_font_rule)
        rb.addWidget(self.add_rule_btn)
        layout.addWidget(self.sec_rules)
        self._rebuild_rules()

        # --- 5) Einfügen ----------------------------------------------
        self.insert_btn = QPushButton(self.t("insert_btn"))
        self.insert_btn.setMinimumHeight(34)
        self.insert_btn.clicked.connect(self._insert_sfx)
        layout.addWidget(self.insert_btn)
        self.restyle_btn = QPushButton(self.t("restyle_btn"))
        self.restyle_btn.setToolTip(self.t("restyle_tip"))
        self.restyle_btn.clicked.connect(self._restyle_sfx)
        layout.addWidget(self.restyle_btn)

        # --- Status / Hinweise ----------------------------------------
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # --- Import / Export (eigene Presets + Font-Regeln) -----------
        io_row = QHBoxLayout()
        self.import_btn = QPushButton(self.t("import_btn"))
        self.import_btn.clicked.connect(self._import_data)
        self.export_btn = QPushButton(self.t("export_btn"))
        self.export_btn.clicked.connect(self._export_data)
        io_row.addWidget(self.import_btn)
        io_row.addWidget(self.export_btn)
        layout.addLayout(io_row)

        # --- Zurücksetzen ---------------------------------------------
        self.reset_btn = QPushButton(self.t("reset_btn"))
        self.reset_btn.setToolTip(self.t("reset_tip"))
        self.reset_btn.clicked.connect(self._reset)
        layout.addWidget(self.reset_btn)

        layout.addStretch(1)

        # Last: the strategy drives insert_btn's label and the note row, and
        # both are only built by now.
        self._on_strategy_changed()

        # In ScrollArea verpacken; alte (bei Sprachwechsel) sauber entsorgen
        old = self.widget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(root)
        self.setWidget(scroll)
        if old is not None:
            old.setParent(None)
            old.deleteLater()

        # zuletzt genutzten / vor dem Sprachwechsel gemerkten Stil anwenden
        self._apply_state(self._pending_state)
        self._apply_view()
        self._update_preview()
        self.text_input.setFocus()             # gleich lostippen können

    def eventFilter(self, obj, event):
        """Esc im SFX-Feld und in der Regelsuche leert das jeweilige Feld."""
        if (event.type() == QEvent.KeyPress
                and event.key() == Qt.Key_Escape):
            if obj is getattr(self, "text_input", None):
                self.text_input.clear()
                return True
            if obj is getattr(self, "rule_search", None):
                self.rule_search.clear()
                return True
        return super().eventFilter(obj, event)

    # ==================================================================
    #  Layout / Anzeige (Größen + ein-/ausblenden)
    # ==================================================================
    def _apply_view(self):
        """Sichtbarkeit, Klappstatus und Vorschauhöhe gemäß View setzen."""
        for key, sec_attr, chk_attr in self._SECTIONS:
            sec = getattr(self, sec_attr)
            sec.setVisible(getattr(self, chk_attr).isChecked())
            sec.set_collapsed(bool(self._view.get("collapse_" + key, False)))
        # Vorschauhöhe
        h = self.v_preview_h.value()
        self.preview.setMinimumHeight(h)
        self.preview.setMaximumHeight(h)
        self.v_preview_h.setEnabled(self.v_preview_chk.isChecked())
        # ein gerade eingeblendeter Abschnitt soll gleich aktuellen Inhalt zeigen
        self._update_preview()
        if self.v_suggest_chk.isChecked():
            self._refresh_suggestions(self.text_input.text())

    def _capture_view(self):
        v = dict(self._view)               # bestehende Klapp-/Zusatzwerte behalten
        v.update({
            "open": self.view_toggle.isChecked(),
            "preview_show": self.v_preview_chk.isChecked(),
            "preview_h": self.v_preview_h.value(),
            "suggest_show": self.v_suggest_chk.isChecked(),
            "font_show": self.v_font_chk.isChecked(),
            "style_show": self.v_style_chk.isChecked(),
            "shadow_show": self.v_shadow_chk.isChecked(),
            "presets_show": self.v_presets_chk.isChecked(),
            "rules_show": self.v_rules_chk.isChecked(),
            "clear_after": self.v_clear_after_chk.isChecked(),
        })
        return v

    def _on_section_collapsed(self, key, collapsed):
        """Klick auf eine Abschnitts-Überschrift -> Klappstatus merken."""
        self._view["collapse_" + key] = bool(collapsed)
        save_view(self._view)

    def _on_compact(self):
        """Kompaktmodus: selten genutzte Abschnitte (Schatten + Regeln) auf
        einen Schlag aus-/wieder einblenden."""
        compact = self.v_shadow_chk.isChecked() or self.v_rules_chk.isChecked()
        for chk in (self.v_shadow_chk, self.v_rules_chk):
            chk.blockSignals(True)
            chk.setChecked(not compact)
            chk.blockSignals(False)
        self._view = self._capture_view()
        save_view(self._view)
        self._apply_view()

    def _on_view_changed(self, *_a):
        self._view = self._capture_view()
        save_view(self._view)
        self._apply_view()

    def _on_view_toggle(self, checked):
        self.view_box.setVisible(checked)
        self._view = self._capture_view()
        save_view(self._view)

    def _on_view_reset(self):
        # Klappstatus behalten, nur Sichtbarkeit/Größe auf Standard zurück
        keep = {k: self._view[k] for k in self._view if k.startswith("collapse_")}
        self._view = dict(self._VIEW_DEFAULTS)
        self._view.update(keep)
        self._view["open"] = self.view_toggle.isChecked()  # Panel offen lassen
        save_view(self._view)
        widgets = (self.v_preview_chk, self.v_suggest_chk, self.v_font_chk,
                   self.v_style_chk, self.v_shadow_chk, self.v_presets_chk,
                   self.v_rules_chk, self.v_clear_after_chk, self.v_preview_h)
        for w in widgets:
            w.blockSignals(True)
        self.v_preview_chk.setChecked(self._view["preview_show"])
        self.v_preview_h.setValue(self._view["preview_h"])
        self.v_suggest_chk.setChecked(self._view["suggest_show"])
        self.v_font_chk.setChecked(self._view["font_show"])
        self.v_style_chk.setChecked(self._view["style_show"])
        self.v_shadow_chk.setChecked(self._view["shadow_show"])
        self.v_presets_chk.setChecked(self._view["presets_show"])
        self.v_rules_chk.setChecked(self._view["rules_show"])
        self.v_clear_after_chk.setChecked(self._view["clear_after"])
        for w in widgets:
            w.blockSignals(False)
        self._apply_view()

    # ==================================================================
    #  Sprache
    # ==================================================================
    def _on_lang_changed(self, _idx):
        code = self.lang_combo.currentData()
        if code and code != self._lang:
            self._set_language(code)

    def _set_language(self, lang):
        self._pending_state = self._capture_state()   # Eingaben nicht verlieren
        self._lang = lang
        save_language(lang)
        self.setWindowTitle(self.t("window_title"))
        self._build_ui()                               # komplett neu in neuer Sprache

    # ==================================================================
    #  kleine UI-Helfer
    # ==================================================================
    def _heading(self, text):
        lbl = QLabel(text)
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        return lbl

    @staticmethod
    def _elide(text, limit=34):
        """Lange Texte für Buttons kürzen (voller Text bleibt im Tooltip)."""
        text = text or ""
        return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"

    @staticmethod
    def _make_shrinkable(widget):
        """Damit sich der Docker schmal ziehen lässt: das Widget darf horizontal
        beliebig schrumpfen und erzwingt keine große Mindestbreite mehr."""
        sp = widget.sizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.Ignored)
        widget.setSizePolicy(sp)
        widget.setMinimumWidth(0)
        return widget

    def _slider_spin_row(self, parent_layout, title, lo, hi, value):
        """Erzeugt 'Überschrift + Slider + SpinBox' und synchronisiert beide."""
        parent_layout.addWidget(self._heading(title))
        row = QHBoxLayout()
        slider = NoScrollSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(value)
        spin = NoScrollSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(value)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        row.addWidget(slider, 1)
        row.addWidget(spin, 0)
        parent_layout.addLayout(row)
        return slider, spin

    def _set_btn_color(self, btn, qcolor):
        """Färbt einen Button als Farb-Swatch und schreibt den Hexcode drauf."""
        btn._color = qcolor
        txt = "#000000" if qcolor.lightness() > 128 else "#ffffff"
        btn.setText(qcolor.name())
        btn.setStyleSheet(
            f"background-color: {qcolor.name()}; color: {txt};"
            f" border: 1px solid #555; padding: 3px;")

    def _pick_color(self, btn):
        c = QColorDialog.getColor(btn._color, self.widget(), self.t("choose_color"))
        if c.isValid():
            self._set_btn_color(btn, c)
            self._update_preview()

    # --- Strategie ----------------------------------------------------
    def _strategy(self):
        return self.strategy_combo.currentData() or "redraw"

    def _on_strategy_changed(self, *_a):
        sid = self._strategy()
        self.strategy_hint.setText(self.t("strategy_" + sid + "_hint"))
        inserts = MODES.inserts_text(sid)
        # 'ignore' places nothing, so Insert is really Skip.
        self.insert_btn.setText(
            self.t("insert_btn") if inserts else self.t("skip_btn"))
        # romaji and note read the ORIGINAL sound; the rest take the English.
        self.text_input.setPlaceholderText(
            self.t("sfx_placeholder_jp") if sid in ("romaji", "note")
            else self.t("sfx_placeholder"))
        self.note_row.setVisible(sid == "note")
        self._update_note_btn()
        self._update_preview()

    def _update_note_btn(self):
        n = len(self._notes)
        self.note_list_btn.setEnabled(bool(n))
        self.note_list_btn.setText(
            self.t("note_place_list") + (" ({})".format(n) if n else ""))

    def _place_note_list(self):
        """Put the collected notes at the panel edge, as one text block.

        Bottom-left of the page, small: this is a reader's aid, not lettering.
        The typesetter drags it wherever the panel actually has room."""
        doc = Krita.instance().activeDocument()
        if doc is None:
            self._warn(self.t("st_no_doc"))
            return
        if not self._notes:
            return
        size = max(10, int(round(self.size_spin.value() * 0.28)))
        img_w, img_h = doc.width(), doc.height()
        x = int(img_w * 0.04)
        y = int(img_h - size * (len(self._notes) + 1) * 1.35)
        lines = []
        for i, line in enumerate(self._notes):
            lines.append(
                '<tspan x="{x}" y="{y:.0f}">{t}</tspan>'.format(
                    x=x, y=y + i * size * 1.35, t=_xml_escape(line)))
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
            '<text text-anchor="start" fill="#000000" font-family="{f}" '
            'font-size="{s}">{body}</text></svg>'
        ).format(w=img_w, h=img_h, f=_xml_escape("Segoe UI"), s=size,
                 body="".join(lines))
        try:
            node = doc.createVectorLayer("SFX notes")
            doc.rootNode().addChildNode(node, None)
            node.addShapesFromSvg(svg)
            doc.refreshProjection()
        except Exception as e:                      # noqa: BLE001
            self._warn(self.t("st_insert_fail", err=e))
            return
        self._info(self.t("st_notes_placed", n=len(self._notes)))
        self._notes = []
        self._update_note_btn()

    # --- Vorschau / Großbuchstaben ------------------------------------
    def _effective_text(self):
        """Der Text, der wirklich eingefügt wird.

        The strategy decides what that is: 'romaji' transliterates whatever was
        typed/read from the layer (so the typesetter never types the romaji by
        hand), the rest use the word as given. Uppercase is applied last, so it
        applies to the romaji too."""
        txt = self.text_input.text().strip()
        if self._strategy() == "romaji":
            txt = MODES.to_romaji(txt)
        if getattr(self, "upper_chk", None) and self.upper_chk.isChecked():
            txt = txt.upper()
        return txt

    def _on_upper_toggled(self, _checked):
        self._update_preview()

    def _on_shadow_toggled(self, _checked):
        self._update_shadow_enabled()
        self._update_preview()

    def _update_shadow_enabled(self):
        """Schattenfarbe + Versatz nur bei aktivem Schatten bedienbar."""
        on = self.shadow_chk.isChecked()
        self.shadow_btn.setEnabled(on)
        self.shadow_dx.setEnabled(on)
        self.shadow_dy.setEnabled(on)

    def _update_grad_enabled(self):
        """Zweite Farbe nur bei aktiver Verlaufsfüllung bedienbar."""
        self.fill2_btn.setEnabled(self.grad_chk.isChecked())

    # --- Textur-/Muster-Füllung ---------------------------------------
    def _update_pattern_enabled(self):
        """Bild/Skala nur bedienbar, wenn Musterfüllung aktiv ist; der Button
        zeigt die aktive Quelle (Datei-Name oder Krita-Muster)."""
        on = self.pattern_chk.isChecked()
        for w in (self.pattern_btn, self.pattern_krita_btn,
                  self.pattern_clear_btn, self.pattern_scale_slider,
                  self.pattern_scale_spin):
            w.setEnabled(on)
        if self._pattern_path:
            name = os.path.basename(self._pattern_path)
        elif self._pattern_krita_name:
            name = self._pattern_krita_name
        else:
            name = self.t("pattern_choose")
        self.pattern_btn.setText(self._elide(name, 20))

    def _pick_pattern(self):
        """Bilddatei (Screentone/Textur) für die Musterfüllung wählen."""
        path, _ = QFileDialog.getOpenFileName(
            self.widget(), self.t("pattern_choose"), self._pattern_path or "",
            self.t("pattern_filter"))
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            self._warn(self.t("warn_pattern_bad"))
            return
        self._pattern_path = path
        self._pattern_krita_name = ""
        self._pattern_img = img
        if not self.pattern_chk.isChecked():
            self.pattern_chk.setChecked(True)      # löst update+preview aus
        self._update_pattern_enabled()
        self._update_preview()

    def _krita_pattern_image(self, name):
        """QImage eines in Krita gespeicherten Musters (oder None)."""
        try:
            res = Krita.instance().resources("pattern")
            r = res.get(name) if res else None
            img = r.image() if r is not None else None
            if img is not None and not img.isNull():
                return img
        except Exception:
            pass
        return None

    def _pick_krita_pattern(self):
        """Aus den in Krita gespeicherten Mustern (Pattern-Ressourcen) wählen."""
        try:
            res = Krita.instance().resources("pattern")
        except Exception:
            res = None
        if not res:
            self._warn(self.t("warn_no_krita_patterns"))
            return
        dlg = QDialog(self.widget())
        dlg.setWindowTitle(self.t("pattern_krita_title"))
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        lst.setViewMode(QListWidget.IconMode)
        lst.setIconSize(QSize(64, 64))
        lst.setResizeMode(QListWidget.Adjust)
        lst.setMovement(QListWidget.Static)
        lst.setMinimumSize(430, 340)
        for nm in sorted(res.keys(), key=lambda s: s.lower()):
            img = self._krita_pattern_image(nm)
            if img is None:
                continue
            it = QListWidgetItem(self._elide(nm, 22))
            it.setData(Qt.UserRole, nm)
            it.setToolTip(nm)
            it.setIcon(QIcon(QPixmap.fromImage(img).scaled(
                64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            lst.addItem(it)
        if lst.count() == 0:
            self._warn(self.t("warn_no_krita_patterns"))
            return
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        lay.addWidget(lst)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec_() != QDialog.Accepted:
            return
        it = lst.currentItem()
        if it is None:
            return
        nm = it.data(Qt.UserRole)
        img = self._krita_pattern_image(nm)
        if img is None:
            self._warn(self.t("warn_pattern_bad"))
            return
        self._pattern_krita_name = nm
        self._pattern_path = ""
        self._pattern_img = QImage(img)            # eigene Kopie behalten
        if not self.pattern_chk.isChecked():
            self.pattern_chk.setChecked(True)
        self._update_pattern_enabled()
        self._update_preview()

    def _clear_pattern(self):
        self._pattern_path = ""
        self._pattern_krita_name = ""
        self._pattern_img = None
        self._update_pattern_enabled()
        self._update_preview()

    def _ensure_pattern_img(self):
        """QImage lazy laden (Cache); None wenn kein/ungültiges Bild. Quelle ist
        eine Datei ODER ein in Krita gespeichertes Muster."""
        if self._pattern_img is not None and not self._pattern_img.isNull():
            return self._pattern_img
        if self._pattern_path and os.path.exists(self._pattern_path):
            img = QImage(self._pattern_path)
            if not img.isNull():
                self._pattern_img = img
                return img
        if self._pattern_krita_name:
            img = self._krita_pattern_image(self._pattern_krita_name)
            if img is not None:
                self._pattern_img = QImage(img)
                return self._pattern_img
        return None

    def _pattern_active(self):
        return bool(getattr(self, "pattern_chk", None)
                    and self.pattern_chk.isChecked()) \
            and self._ensure_pattern_img() is not None

    def _pattern_tile(self):
        """Kachelgröße (w, h) in Nutzer-/Seitenpixeln = Bildgröße * Skala%."""
        img = self._ensure_pattern_img()
        if img is None or not hasattr(self, "pattern_scale_spin"):
            return (0, 0)
        s = self.pattern_scale_spin.value() / 100.0
        return (max(1, int(img.width() * s)), max(1, int(img.height() * s)))

    def _pattern_data_uri(self):
        """data:-URI des Musters. Datei: unverändert eingebettet. Krita-Muster
        (kein Dateipfad): das QImage als PNG kodiert."""
        if self._pattern_path and os.path.exists(self._pattern_path):
            ext = os.path.splitext(self._pattern_path)[1].lower().lstrip(".")
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif",
                    "bmp": "bmp", "webp": "webp"}.get(ext, "png")
            try:
                with open(self._pattern_path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode("ascii")
            except Exception:
                return None
            return "data:image/%s;base64,%s" % (mime, b64)
        img = self._ensure_pattern_img()
        if img is None:
            return None
        try:
            im = img.convertToFormat(QImage.Format_ARGB32)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.WriteOnly)
            im.save(buf, "PNG")
            buf.close()
            b64 = bytes(ba.toBase64()).decode("ascii")
        except Exception:
            return None
        return "data:image/png;base64," + b64

    def _update_preview(self):
        """WYSIWYG-Vorschau mit Font/Größe/Farben/Outline/Schatten neu zeichnen."""
        needed = ("preview", "font_combo", "size_spin", "fill_btn",
                  "outline_btn", "out_spin", "shadow_chk", "shadow_btn",
                  "shadow_dx", "shadow_dy", "bold_chk", "italic_chk")
        if not all(hasattr(self, a) for a in needed):
            return
        chk = getattr(self, "v_preview_chk", None)
        if chk is not None and not chk.isChecked():
            return                       # ausgeblendet -> nicht rechnen/zeichnen
        fam = self.font_combo.currentText()
        self.preview.set_data({
            "text": self._effective_text(),
            "family": fam,
            # Tolerant preview: never abort the fit when a font is unresolved;
            # just flag it so the preview shows "not installed" (Qt substitutes
            # a fallback family for the actual drawing).
            "missing": bool(fam.strip()) and not self._is_installed(fam),
            "missing_label": self.t("not_installed"),
            "size_ref": max(1, self.size_spin.value()),
            "bold": self.bold_chk.isChecked(),
            "italic": self.italic_chk.isChecked(),
            "fill": QColor(self.fill_btn._color),
            "outline": self.out_spin.value() > 0,
            "outline_color": QColor(self.outline_btn._color),
            "outline_px": float(self.out_spin.value()),
            "outline2_color": QColor(self.outline2_btn._color),
            "outline2_px": float(self.out2_spin.value()),
            "shadow": self.shadow_chk.isChecked(),
            "shadow_color": QColor(self.shadow_btn._color),
            "shadow_dx": float(self.shadow_dx.value()),
            "shadow_dy": float(self.shadow_dy.value()),
            "rotate": float(self.rot_spin.value()),
            "fill2": (QColor(self.fill2_btn._color)
                      if self.grad_chk.isChecked() else None),
            "pattern_img": (self._ensure_pattern_img()
                            if self._pattern_active() else None),
            "pattern_tile": self._pattern_tile(),
        })

    # --- Stand sichern / wiederherstellen -----------------------------
    def _capture_state(self):
        return {
            "text": self.text_input.text(),
            "font": self.font_combo.currentText(),
            "size": self.size_spin.value(),
            "fill": self.fill_btn._color.name(),
            "outline": self.outline_btn._color.name(),
            "outline_px": self.out_spin.value(),
            "outline2": self.outline2_btn._color.name(),
            "outline2_px": self.out2_spin.value(),
            "pattern": self._pattern_path,
            "pattern_krita": self._pattern_krita_name,
            "pattern_on": self.pattern_chk.isChecked(),
            "pattern_scale": self.pattern_scale_spin.value(),
            "uppercase": self.upper_chk.isChecked(),
            "bold": self.bold_chk.isChecked(),
            "italic": self.italic_chk.isChecked(),
            "shadow": self.shadow_chk.isChecked(),
            "shadow_color": self.shadow_btn._color.name(),
            "shadow_dx": self.shadow_dx.value(),
            "shadow_dy": self.shadow_dy.value(),
        }

    def _apply_state(self, st):
        if not st:
            return
        if st.get("text"):
            self.text_input.setText(st["text"])
        if st.get("font"):
            self._select_font(st["font"], warn=False)
        for key, spin in (("size", self.size_spin), ("outline_px", self.out_spin),
                          ("outline2_px", self.out2_spin),
                          ("shadow_dx", self.shadow_dx),
                          ("shadow_dy", self.shadow_dy)):
            if key in st:
                try:
                    spin.setValue(int(st[key]))
                except (TypeError, ValueError):
                    pass
        if st.get("fill"):
            self._set_btn_color(self.fill_btn, QColor(st["fill"]))
        if st.get("outline"):
            self._set_btn_color(self.outline_btn, QColor(st["outline"]))
        if st.get("outline2"):
            self._set_btn_color(self.outline2_btn, QColor(st["outline2"]))
        if st.get("shadow_color"):
            self._set_btn_color(self.shadow_btn, QColor(st["shadow_color"]))
        if "uppercase" in st:
            self.upper_chk.setChecked(bool(st["uppercase"]))
        if "bold" in st:
            self.bold_chk.setChecked(bool(st["bold"]))
        if "italic" in st:
            self.italic_chk.setChecked(bool(st["italic"]))
        if "shadow" in st:
            self.shadow_chk.setChecked(bool(st["shadow"]))
        self._restore_pattern(st)
        self._update_shadow_enabled()

    def _restore_pattern(self, st):
        """Muster (Pfad/Skala/An) aus Zustand oder Preset setzen. Fehlt die
        Datei, bleibt die Musterfüllung schlicht aus."""
        if not hasattr(self, "pattern_chk"):
            return
        self._pattern_path = st.get("pattern", "") or ""
        self._pattern_krita_name = st.get("pattern_krita", "") or ""
        self._pattern_img = None
        if "pattern_scale" in st:
            try:
                self.pattern_scale_spin.setValue(int(st["pattern_scale"]))
            except (TypeError, ValueError):
                pass
        # on only if the image (file or Krita muster) actually resolves
        want = bool(st.get("pattern_on")) and self._ensure_pattern_img() is not None
        self.pattern_chk.blockSignals(True)
        self.pattern_chk.setChecked(want)
        self.pattern_chk.blockSignals(False)
        self._update_pattern_enabled()

    def _preset_tooltip(self, p):
        lines = [
            self.t("tip_font", v=p["font"]),
            self.t("tip_size", v=p["size"]),
            self.t("tip_fill", v=p["fill"]),
            self.t("tip_outline", c=p["outline"], w=p["outline_px"]),
        ]
        kws = p.get("keywords") or []
        if kws:
            lines.append(self.t("tip_keywords", v=", ".join(kws)))
        lines.append(self.t("tip_user_preset") if p.get("user")
                     else self.t("tip_builtin"))
        return "\n".join(lines)

    # ==================================================================
    #  Presets
    # ==================================================================
    def _apply_preset(self, preset):
        self._select_font(preset["font"])
        self.size_spin.setValue(preset["size"])
        self.out_spin.setValue(preset["outline_px"])
        self.out2_spin.setValue(int(preset.get("outline2_px",
                                               DEFAULTS.get("outline2_px", 0))))
        self._set_btn_color(self.fill_btn, QColor(preset["fill"]))
        self._set_btn_color(self.outline_btn, QColor(preset["outline"]))
        self._set_btn_color(self.outline2_btn,
                            QColor(preset.get("outline2",
                                              DEFAULTS.get("outline2", "#000000"))))
        self.bold_chk.setChecked(bool(preset.get("bold", False)))
        self.italic_chk.setChecked(bool(preset.get("italic", False)))
        # Schatten (in alten Presets nicht vorhanden -> Standard aus)
        self.shadow_chk.setChecked(bool(preset.get("shadow", False)))
        if preset.get("shadow_color"):
            self._set_btn_color(self.shadow_btn, QColor(preset["shadow_color"]))
        self.shadow_dx.setValue(int(preset.get("shadow_dx",
                                               DEFAULTS.get("shadow_dx", 6))))
        self.shadow_dy.setValue(int(preset.get("shadow_dy",
                                               DEFAULTS.get("shadow_dy", 6))))
        self._restore_pattern(preset)
        self._update_shadow_enabled()
        self._update_preview()
        self.status_label.setText(self.t("st_preset_loaded", name=preset["name"]))

    def _all_presets(self):
        """Integrierte Presets (aus config.py) + eigene (persistiert)."""
        builtin = [dict(p, user=False) for p in SFX_PRESETS]
        return builtin + self._user_presets

    def _rebuild_presets(self):
        """Baut die Preset-Buttons neu auf (nach Anlegen/Löschen aufrufen)."""
        self._clear_layout(self.preset_box)
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, preset in enumerate(self._all_presets()):
            btn = QPushButton(self._elide(preset["name"], 18))
            btn.setToolTip(self._preset_tooltip(preset))
            self._make_shrinkable(btn)
            btn.clicked.connect(lambda _c=False, p=preset: self._apply_preset(p))
            if preset.get("user"):
                btn.setContextMenuPolicy(Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda pos, p=preset, b=btn: self._show_preset_menu(p, b, pos))
            grid.addWidget(btn, i // 2, i % 2)
        self.preset_box.addLayout(grid)

    def _clear_layout(self, layout):
        """Entfernt alle Widgets/Unterlayouts aus einem Layout."""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                child = item.layout()
                if child is not None:
                    self._clear_layout(child)

    def _current_settings_as_preset(self, name, keywords):
        """Liest die aktuellen Regler aus und baut daraus ein Preset-Dict."""
        return {
            "name": name,
            "font": self.font_combo.currentText(),
            "size": self.size_spin.value(),
            "fill": self.fill_btn._color.name(),
            "outline": self.outline_btn._color.name(),
            "outline_px": self.out_spin.value(),
            "outline2": self.outline2_btn._color.name(),
            "outline2_px": self.out2_spin.value(),
            "pattern": self._pattern_path,
            "pattern_krita": self._pattern_krita_name,
            "pattern_on": self.pattern_chk.isChecked(),
            "pattern_scale": self.pattern_scale_spin.value(),
            "bold": self.bold_chk.isChecked(),
            "italic": self.italic_chk.isChecked(),
            "shadow": self.shadow_chk.isChecked(),
            "shadow_color": self.shadow_btn._color.name(),
            "shadow_dx": self.shadow_dx.value(),
            "shadow_dy": self.shadow_dy.value(),
            "keywords": keywords,
            "user": True,
        }

    def _save_current_as_preset(self):
        """Fragt Name (+ optionale Schlüsselwörter) ab und speichert das Preset."""
        name, ok = QInputDialog.getText(
            self.widget(), self.t("dlg_save_title"), self.t("dlg_save_name"))
        if not ok:
            return
        name = name.strip()
        if not name:
            self._warn(self.t("warn_no_name"))
            return

        kw_text, ok2 = QInputDialog.getText(
            self.widget(), self.t("dlg_kw_opt_title"), self.t("dlg_kw_opt_label"))
        keywords = []
        if ok2 and kw_text.strip():
            keywords = [k.strip().lower() for k in kw_text.split(",") if k.strip()]

        preset = self._current_settings_as_preset(name, keywords)
        self._user_presets = [p for p in self._user_presets
                              if p.get("name") != name]
        self._user_presets.append(preset)
        save_user_presets(self._user_presets)
        self._rebuild_presets()
        self.status_label.setText(self.t("st_preset_saved", name=name))

    def _show_preset_menu(self, preset, button, pos):
        """Kontextmenü für ein eigenes Preset (Rechtsklick)."""
        menu = QMenu(self.widget())
        act_rename = menu.addAction(self.t("menu_rename"))
        act_keywords = menu.addAction(self.t("menu_edit_keywords"))
        act_overwrite = menu.addAction(self.t("menu_overwrite"))
        menu.addSeparator()
        act_delete = menu.addAction(self.t("menu_delete"))

        chosen = menu.exec_(button.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_rename:
            self._rename_user_preset(preset)
        elif chosen == act_keywords:
            self._edit_keywords(preset)
        elif chosen == act_overwrite:
            self._overwrite_user_preset(preset)
        elif chosen == act_delete:
            self._delete_user_preset(preset)

    def _rename_user_preset(self, preset):
        old = preset.get("name", "")
        new, ok = QInputDialog.getText(
            self.widget(), self.t("dlg_rename_title"), self.t("dlg_rename_label"),
            text=old)
        if not ok:
            return
        new = new.strip()
        if not new:
            self._warn(self.t("warn_no_name"))
            return
        if new == old:
            return
        if any(p is not preset and p.get("name") == new for p in self._user_presets):
            self._warn(self.t("warn_name_exists", name=new))
            return
        preset["name"] = new
        save_user_presets(self._user_presets)
        self._rebuild_presets()
        self.status_label.setText(self.t("st_preset_renamed", name=new))

    def _edit_keywords(self, preset):
        current = ", ".join(preset.get("keywords", []))
        txt, ok = QInputDialog.getText(
            self.widget(), self.t("dlg_editkw_title"), self.t("dlg_editkw_label"),
            text=current)
        if not ok:
            return
        preset["keywords"] = [k.strip().lower() for k in txt.split(",") if k.strip()]
        save_user_presets(self._user_presets)
        self._rebuild_presets()
        self._on_text_changed(self.text_input.text())
        self.status_label.setText(self.t("st_keywords_updated", name=preset["name"]))

    def _overwrite_user_preset(self, preset):
        reply = QMessageBox.question(
            self.widget(), self.t("dlg_overwrite_title"),
            self.t("dlg_overwrite_q", name=preset["name"]),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        preset["font"] = self.font_combo.currentText()
        preset["size"] = self.size_spin.value()
        preset["fill"] = self.fill_btn._color.name()
        preset["outline"] = self.outline_btn._color.name()
        preset["outline_px"] = self.out_spin.value()
        preset["outline2"] = self.outline2_btn._color.name()
        preset["outline2_px"] = self.out2_spin.value()
        preset["pattern"] = self._pattern_path
        preset["pattern_krita"] = self._pattern_krita_name
        preset["pattern_on"] = self.pattern_chk.isChecked()
        preset["pattern_scale"] = self.pattern_scale_spin.value()
        preset["bold"] = self.bold_chk.isChecked()
        preset["italic"] = self.italic_chk.isChecked()
        preset["shadow"] = self.shadow_chk.isChecked()
        preset["shadow_color"] = self.shadow_btn._color.name()
        preset["shadow_dx"] = self.shadow_dx.value()
        preset["shadow_dy"] = self.shadow_dy.value()
        save_user_presets(self._user_presets)
        self._rebuild_presets()
        self.status_label.setText(self.t("st_preset_overwritten", name=preset["name"]))

    def _delete_user_preset(self, preset):
        name = preset.get("name", "")
        reply = QMessageBox.question(
            self.widget(), self.t("dlg_delpreset_title"),
            self.t("dlg_delpreset_q", name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._user_presets = [p for p in self._user_presets if p is not preset]
        save_user_presets(self._user_presets)
        self._rebuild_presets()
        self.status_label.setText(self.t("st_preset_deleted", name=name))

    # ==================================================================
    #  Font-Dropdown
    # ==================================================================
    def _quick_fonts(self):
        """Schnellwahl fürs Dropdown: Favoriten + zuletzt benutzte Schriften."""
        quick = []
        for f in list(SFX_FONTS) + self._recent_fonts():
            if f and f not in quick:
                quick.append(f)
        return quick

    def _recent_fonts(self, limit=8):
        """Zuletzt/oft benutzte Schriften, aus der Lern-Statistik aggregiert
        (häufigste zuerst). Kommen im Dropdown direkt nach den Favoriten."""
        counts = {}
        for d in self._usage.values():
            for fnt, c in (d or {}).items():
                counts[fnt] = counts.get(fnt, 0) + c
        return [f for f, _c in sorted(counts.items(), key=lambda kv: kv[1],
                                      reverse=True)][:limit]

    def _build_font_combo(self):
        """Schnelle Schriftauswahl. Das Dropdown enthält nur Favoriten + zuletzt
        benutzte Schriften (sofort da); ein Completer durchsucht ALLE System-
        Fonts. Die volle Liste wird erst NACH dem Öffnen nachgeladen
        (QTimer.singleShot) – früher wurden tausende Fonts beim Aufbau ins Combo
        gekippt, das war der zweite Grund fürs Ruckeln."""
        combo = NoScrollComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)

        quick = self._quick_fonts()
        combo.addItems(quick)

        # Completer über ein eigenes Modell (anfangs nur die Schnellwahl).
        self._font_model = QStringListModel(list(quick))
        completer = QCompleter(self._font_model, combo)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        combo.setCompleter(completer)

        # Breite an einer kurzen Mindestlänge ausrichten statt am längsten
        # Fontnamen – sonst zwingt das Dropdown den ganzen Docker breit.
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(6)
        self._make_shrinkable(combo)
        combo.setCurrentIndex(0)

        if SHOW_ALL_SYSTEM_FONTS:
            QTimer.singleShot(0, self._populate_font_model)
        return combo

    def _populate_font_model(self):
        """Vollständige System-Fontliste lazy ins Completer-Modell laden (nach
        dem Anzeigen des Dockers, damit das Öffnen sofort wirkt)."""
        if getattr(self, "_font_model", None) is None:
            return
        quick = self._quick_fonts()
        seen = set(quick)
        full = quick + [f for f in self._families() if f not in seen]
        self._font_model.setStringList(full)

    def _installed_set(self):
        if getattr(self, "_inst_set", None) is None:
            self._inst_set = set(self._families())
        return self._inst_set

    def _is_installed(self, family):
        return bool(family) and family in self._installed_set()

    def _best_alternative(self):
        """A really-installed fallback: the first installed favourite, else the
        first system family."""
        for fav in SFX_FONTS:
            if self._is_installed(fav):
                return fav
        fams = self._families()
        return fams[0] if fams else ""

    def _select_font(self, font_name, warn=True):
        """Wählt den Font im Dropdown. Ist die Schrift nicht installiert, wird
        (bei warn=True) gewarnt und eine installierte Alternative gesetzt."""
        if font_name and not self._is_installed(font_name):
            alt = self._best_alternative()
            if warn:
                self._warn(self.t("st_font_missing", font=font_name,
                                  alt=alt or "?"))
            if alt:
                font_name = alt
        idx = self.font_combo.findText(font_name)
        if idx >= 0:
            self.font_combo.setCurrentIndex(idx)
        else:
            self.font_combo.setCurrentText(font_name)

    def _apply_typed_font(self):
        """Apply the font typed/searched in the combo box (validated the same way
        as a clicked suggestion)."""
        name = self.font_combo.currentText().strip()
        if name:
            self._select_font(name)

    # ==================================================================
    #  Live-Vorschläge
    # ==================================================================
    def _on_text_changed(self, txt):
        # nicht bei jedem Tastendruck synchron alles neu bauen -> entprellen
        self._pending_text = txt
        self._debounce.start()

    def _on_debounced(self):
        self._update_preview()
        self._refresh_suggestions(self._pending_text)

    def _add_suggestion_btn(self, fnt):
        """Ein anklickbarer Vorschlags-Button für eine Schrift (kurz + schrumpfbar)."""
        btn = QPushButton(self.t("sug_font", name=self._elide(fnt, 28)))
        if self._is_installed(fnt):
            btn.setToolTip(self.t("sug_font_tip", name=fnt))
        else:
            btn.setToolTip(self.t("sug_font_missing_tip", name=fnt))
            btn.setStyleSheet("color: #c9962b;")   # amber = not installed
        self._make_shrinkable(btn)
        btn.clicked.connect(lambda _c=False, ff=fnt: self._select_font(ff))
        self.suggest_box.addWidget(btn)

    def _refresh_suggestions(self, text):
        """Baut die Vorschlagszeile neu: vorher benutzte Schrift -> passende
        Fonts (echte Regel oder Heuristik-Schätzung) -> passendes Preset.
        Ist der Vorschlags-Abschnitt ausgeblendet, wird gar nichts gebaut."""
        chk = getattr(self, "v_suggest_chk", None)
        if chk is not None and not chk.isChecked():
            self._clear_layout(self.suggest_box)
            return
        self._clear_layout(self.suggest_box)
        norm = normalize_sfx(text)
        learned = self._learned_fonts(norm)
        groups = self._suggested_groups(text)
        guessed = False
        if not groups:                       # keine echte Regel -> Heuristik
            groups = self._heuristic_groups(text)
            guessed = bool(groups)
        preset = self._find_matching_preset(text)
        if not learned and not groups and preset is None:
            return

        header = self.t("suggestions_guess") if (guessed and not learned) \
            else self.t("suggestions")
        info = QLabel(header)
        info.setWordWrap(True)
        self.suggest_box.addWidget(info)

        # Fonts gruppenübergreifend nur einmal zeigen, Gesamtzahl begrenzen.
        shown = set()
        remaining = 8
        # 1) vorher für genau dieses Wort benutzte Schriften zuerst
        if learned:
            self.suggest_box.addWidget(
                self._mini_heading(self.t("suggestions_learned")))
            for fnt in learned:
                if remaining <= 0:
                    break
                if fnt in shown:
                    continue
                shown.add(fnt)
                remaining -= 1
                self._add_suggestion_btn(fnt)
        # 2) Fonts aus Regeln/Heuristik
        for group, fonts in groups:
            if remaining <= 0:
                break
            new_fonts = [f for f in fonts if f not in shown][:remaining]
            if not new_fonts:
                continue
            if group:                       # Gruppen-Überschrift (z. B. "Shout")
                self.suggest_box.addWidget(self._mini_heading(group))
            for fnt in new_fonts:
                shown.add(fnt)
                self._add_suggestion_btn(fnt)
            remaining -= len(new_fonts)

        if preset is not None:
            btn = QPushButton(self.t("sug_preset", name=preset["name"],
                                     font=self._elide(preset["font"], 22)))
            btn.setToolTip(self.t("sug_preset_tip"))
            self._make_shrinkable(btn)
            btn.clicked.connect(lambda _c=False, p=preset: self._apply_preset(p))
            self.suggest_box.addWidget(btn)

    def _group_fonts(self):
        """Gruppenname -> Fonts (erste passende eingebaute Regel)."""
        if self._group_fonts_cache is None:
            cache = {}
            for r in SFX_RULES:
                cache.setdefault(r.get("group", ""), list(r.get("fonts", [])))
            self._group_fonts_cache = cache
        return self._group_fonts_cache

    def _heuristic_groups(self, text):
        """Fallback-Vorschläge per Lautmuster-Heuristik (nur ohne echten Treffer)."""
        gf = self._group_fonts()
        out = []
        for g in classify_sfx(text, available=set(gf.keys())):
            fonts = gf.get(g) or []
            if fonts:
                out.append((g, list(fonts)))
        return out

    def _learned_fonts(self, norm):
        """Für dieses (normalisierte) Wort früher gewählte Schriften, häufigste
        zuerst."""
        if not norm:
            return []
        d = self._usage.get(norm) or {}
        return [f for f, _c in sorted(d.items(),
                                      key=lambda kv: kv[1], reverse=True)]

    def _record_usage(self, text, font):
        """Merkt sich: für dieses Wort wurde diese Schrift gewählt (lernt dazu)."""
        norm = normalize_sfx(text)
        if not norm or not font:
            return
        d = self._usage.setdefault(norm, {})
        d[font] = d.get(font, 0) + 1
        if len(d) > 8:                       # pro Wort höchstens 8 Schriften
            self._usage[norm] = dict(
                sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:8])
        try:
            save_usage(self._usage)
        except Exception:
            pass

    def _all_rules(self):
        """(rule, is_builtin) for the rules active RIGHT NOW: built-ins of the
        active rule language MINUS the ones hidden in this mode, plus own rules
        of the active language AND the active work mode.

        Own rules without a mode apply in every mode (legacy/imported); built-in
        rules apply in every mode. For own rules the original dict is returned so
        edit/delete keeps working by identity."""
        active = self._rule_lang

        def lang_ok(r):
            lang = r.get("lang", "*")
            return lang == "*" or lang == active

        def mode_ok(r):
            m = r.get("mode", "")
            return not m or m == self._mode

        hidden = self._hidden_set()
        rules = [(r, True) for r in SFX_RULES
                 if lang_ok(r) and self._builtin_key(r) not in hidden]
        rules += [(r, False) for r in self._font_rules
                  if lang_ok(r) and mode_ok(r)]
        return rules

    def _on_rule_lang_changed(self, _idx):
        """Regelsprache gewechselt: speichern, Regel-Liste + Vorschläge neu."""
        code = self.rule_lang_combo.currentData()
        if not code or code == self._rule_lang:
            return
        self._rule_lang = code
        save_rule_lang(code)
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())

    # ------------------------------------------------------------------
    #  Work mode + built-in hiding (per mode)
    # ------------------------------------------------------------------
    def _on_mode_changed(self, _idx):
        """Work mode switched: save, rebuild rule list + suggestions."""
        code = self.mode_combo.currentData()
        if not code or code == self._mode:
            return
        self._mode = code
        save_mode(code)
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())

    def _on_sep_builtins_changed(self, checked):
        """Toggle whether hidden built-ins are stored per mode or globally."""
        self._separate_builtins = bool(checked)
        save_separate_builtins(self._separate_builtins)
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())

    @staticmethod
    def _builtin_key(rule):
        """Stable identity of a built-in rule for the hidden list (group+lang)."""
        return (rule.get("group") or "") + "\n" + (rule.get("lang") or "*")

    def _hidden_arr(self):
        """The hidden-key list for the current store: per mode when
        'built-ins per mode' is on, else global. Created on demand."""
        if self._separate_builtins:
            return self._hidden_modes.setdefault(self._mode, [])
        return self._hidden_global

    def _hidden_set(self):
        return set(self._hidden_arr())

    def _save_hidden(self):
        if self._separate_builtins:
            save_hidden_builtins_modes(self._hidden_modes)
        else:
            save_hidden_builtins(self._hidden_global)

    def _hide_builtin(self, key):
        arr = self._hidden_arr()
        if key not in arr:
            arr.append(key)

    def _hide_all_builtins(self):
        """Hide every built-in rule in the current store so this mode can start
        empty. 'Restore built-ins' brings them all back."""
        arr = self._hidden_arr()
        for r in SFX_RULES:
            key = self._builtin_key(r)
            if key not in arr:
                arr.append(key)
        self._save_hidden()
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())
        self.status_label.setText(self.t("st_builtins_hidden"))

    def _restore_builtins(self):
        """Un-hide the built-ins hidden in the current store."""
        if self._separate_builtins:
            self._hidden_modes[self._mode] = []
        else:
            self._hidden_global = []
        self._save_hidden()
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())
        self.status_label.setText(self.t("st_builtins_restored"))

    def _suggested_groups(self, text):
        """[(group, [fonts]), ...] für Regeln, deren Stichwort im Text vorkommt.

        Nutzt normalisiertes Matching, sodass gedehnte SFX ("BOOOOM") und
        Schreibweisen mit Satzzeichen ("ka-boom!") sicher erkannt werden.
        Gruppen mit einem EXAKTEN Worttreffer (ganzes Wort) werden nach vorne
        sortiert, damit der treffendste Vorschlag zuerst kommt."""
        norm = normalize_sfx(text)
        if not norm:
            return []
        result = []                       # je Eintrag: [group, [fonts], exact]
        index = {}
        for rule, _builtin in self._all_rules():
            matched = [kw for kw in rule.get("keywords", [])
                       if keyword_matches(kw, norm)]
            if not matched:
                continue
            exact = any(normalize_sfx(kw) == norm for kw in matched)
            g = rule.get("group") or ""
            if g not in index:
                index[g] = len(result)
                result.append([g, [], exact])
            entry = result[index[g]]
            entry[2] = entry[2] or exact
            for f in rule.get("fonts", []):
                if f and f not in entry[1]:
                    entry[1].append(f)
        # stabile Sortierung: exakte Treffer zuerst, sonst Reihenfolge erhalten
        result.sort(key=lambda e: 0 if e[2] else 1)
        return [(g, fonts) for g, fonts, _ex in result]

    def _mini_heading(self, text):
        """Kleine, fette Zwischenüberschrift (für Gruppen)."""
        lbl = QLabel(text)
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        return lbl

    def _find_matching_preset(self, text):
        """Erstes Preset, dessen Schlüsselwort im Text vorkommt (oder None).
        Gleiches normalisiertes Matching wie bei den Font-Regeln."""
        norm = normalize_sfx(text)
        if not norm:
            return None
        for preset in self._all_presets():
            for kw in preset.get("keywords", []):
                if keyword_matches(kw, norm):
                    return preset
        return None

    # ==================================================================
    #  Font-Vorschläge (Stichwort -> Font(s)), im Docker verwaltbar
    # ==================================================================
    def _rebuild_rules(self):
        """Baut die Regel-Buttons neu auf, nach Gruppen sortiert.

        Eingebaute Regeln (aus config.py) sind immer dabei und nur lesbar
        (Klick übernimmt ihren ersten Font). Eigene Regeln sind links-/rechts-
        klickbar zum Bearbeiten/Löschen.

        Das Suchfeld filtert nur diese Anzeige – aktiv bleiben alle Regeln."""
        self._clear_layout(self.rules_box)
        all_rules = self._all_rules()
        # Restore only helps when something is hidden; Hide-all only while a
        # built-in is still visible. Both act on ALL rules, so they ignore the
        # search filter.
        self.restore_builtins_btn.setEnabled(bool(self._hidden_arr()))
        self.hide_all_btn.setEnabled(any(is_b for _r, is_b in all_rules))
        query = self._rule_query.strip()
        shown = [(r, b) for r, b in all_rules if rule_matches_query(r, query)]
        self._update_rule_count(len(shown), len(all_rules), query)
        if not all_rules:
            hint = QLabel(self.t("no_rules"))
            hint.setWordWrap(True)
            self.rules_box.addWidget(hint)
            return
        if not shown:
            hint = QLabel(self.t("no_rule_match", q=query))
            hint.setWordWrap(True)
            self.rules_box.addWidget(hint)
            return
        for group in self._ordered_groups():
            in_group = [(r, b) for r, b in shown
                        if (r.get("group") or "") == group]
            if not in_group:                       # ganz weggefiltert
                continue
            self.rules_box.addWidget(
                self._mini_heading(group if group else self.t("group_none")))
            for rule, is_builtin in in_group:
                kw = ", ".join(rule.get("keywords", []))
                fo = ", ".join(rule.get("fonts", []))
                full = f"{kw}  →  {fo}"
                # Show the mode tag on each own rule (built-ins apply everywhere).
                mode = rule.get("mode") if not is_builtin else ""
                prefix = ("[{}] ".format(SFX_MODE_NAMES.get(mode, mode))
                          if mode else "")
                btn = QPushButton(
                    prefix + f"{self._elide(kw, 22)}  →  {self._elide(fo, 22)}")
                self._make_shrinkable(btn)
                if is_builtin:
                    btn.setToolTip(full + "\n" + self.t("rule_builtin_tip"))
                    fonts = rule.get("fonts") or []
                    if fonts:
                        first = fonts[0]
                        btn.clicked.connect(
                            lambda _c=False, f=first: self._select_font(f))
                    btn.setContextMenuPolicy(Qt.CustomContextMenu)
                    btn.customContextMenuRequested.connect(
                        lambda pos, r=rule, b=btn:
                            self._show_builtin_menu(r, b, pos))
                else:
                    tip = full + "\n" + self.t("rule_tip")
                    if mode:
                        tip += "\n" + self.t(
                            "rule_mode_tip", mode=SFX_MODE_NAMES.get(mode, mode))
                    btn.setToolTip(tip)
                    btn.clicked.connect(
                        lambda _c=False, r=rule: self._edit_font_rule(r))
                    btn.setContextMenuPolicy(Qt.CustomContextMenu)
                    btn.customContextMenuRequested.connect(
                        lambda pos, r=rule, b=btn: self._show_rule_menu(r, b, pos))
                self.rules_box.addWidget(btn)

    def _on_rule_search(self, text):
        """Suchfeld getippt: nur die Anzeige neu aufbauen."""
        self._rule_query = text or ""
        self._rebuild_rules()

    def _update_rule_count(self, shown, total, query):
        """„n von m Regeln“ – nur solange gesucht wird."""
        lbl = getattr(self, "rule_count_lbl", None)
        if lbl is None:                            # noch im Aufbau
            return
        if query:
            lbl.setText(self.t("rules_count", n=shown, total=total))
            lbl.setVisible(True)
        else:
            lbl.setVisible(False)

    def _ordered_groups(self):
        """Gruppen in Reihenfolge des ersten Auftretens; 'ohne Gruppe' ans Ende.
        Berücksichtigt eingebaute UND eigene Regeln."""
        order = []
        has_empty = False
        for rule, _b in self._all_rules():
            g = rule.get("group") or ""
            if g == "":
                has_empty = True
            elif g not in order:
                order.append(g)
        if has_empty:
            order.append("")
        return order

    def _existing_groups(self):
        """Vorhandene (nicht-leere) Gruppennamen – für die Auswahl im Dialog.
        Eingebaute Gruppen sind dabei, damit eigene Regeln sie erweitern können."""
        seen = []
        for rule, _b in self._all_rules():
            g = (rule.get("group") or "").strip()
            if g and g not in seen:
                seen.append(g)
        return seen

    def _show_rule_menu(self, rule, button, pos):
        menu = QMenu(self.widget())
        act_edit = menu.addAction(self.t("menu_edit"))
        menu.addSeparator()
        act_del = menu.addAction(self.t("menu_delete"))
        chosen = menu.exec_(button.mapToGlobal(pos))
        if chosen == act_edit:
            self._edit_font_rule(rule)
        elif chosen == act_del:
            self._delete_font_rule(rule)

    def _show_builtin_menu(self, rule, button, pos):
        """Context menu for a built-in rule: edit (hides the original and adds an
        editable own copy in the active mode) or hide it. Left click still just
        uses the rule's first font."""
        menu = QMenu(self.widget())
        act_edit = menu.addAction(self.t("menu_edit"))
        menu.addSeparator()
        act_hide = menu.addAction(self.t("menu_hide"))
        chosen = menu.exec_(button.mapToGlobal(pos))
        if chosen == act_edit:
            self._edit_builtin_rule(rule)
        elif chosen == act_hide:
            self._hide_builtin_rule(rule)

    def _hide_builtin_rule(self, rule):
        """Hide a single built-in rule in the current store (per mode/global)."""
        self._hide_builtin(self._builtin_key(rule))
        self._save_hidden()
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())
        self.status_label.setText(self.t("st_builtin_hidden"))

    def _edit_builtin_rule(self, rule):
        """Edit a built-in: hide the original and add an editable own copy that
        keeps the built-in's language and belongs to the active mode."""
        res = self._prompt_font_rule(
            rule.get("group", ""),
            ", ".join(rule.get("keywords", [])),
            ", ".join(rule.get("fonts", [])))
        if res is None:
            return
        group, keywords, fonts = res
        self._hide_builtin(self._builtin_key(rule))
        self._save_hidden()
        self._font_rules.append(
            {"group": group, "keywords": keywords, "fonts": fonts,
             "lang": rule.get("lang", "*"), "mode": self._mode})
        save_font_rules(self._font_rules)
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())
        self.status_label.setText(self.t("st_rule_updated"))

    def _ask_fonts(self, fonts_init):
        """
        Dialog zum Auswählen der Font(s) für eine Regel.

        Bietet ein durchsuchbares Dropdown ALLER Fonts (Namen nachschlagen!)
        + 'Hinzufügen'-Knopf, der den gewählten Font an die Liste anhängt.
        Die Liste bleibt frei editierbar, also auch mehrere Fonts per Hand
        möglich. Rückgabe: Komma-String oder None bei Abbruch.
        """
        dlg = QDialog(self.widget())
        dlg.setWindowTitle(self.t("dlg_rule_fonts_title"))
        lay = QVBoxLayout(dlg)
        lbl = QLabel(self.t("dlg_rule_fonts_label"))
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        # Durchsuchbares Dropdown aller Fonts + Hinzufügen-Knopf
        pick_row = QHBoxLayout()
        combo = self._build_font_combo()
        pick_row.addWidget(combo, 1)
        add_btn = QPushButton(self.t("add_font_btn"))
        pick_row.addWidget(add_btn, 0)
        lay.addLayout(pick_row)

        # frei editierbare, Komma-getrennte Liste (mehrere Fonts möglich)
        line = QLineEdit(fonts_init)
        lay.addWidget(line)

        def add_current():
            name = combo.currentText().strip()
            if not name:
                return
            existing = [f.strip() for f in line.text().split(",") if f.strip()]
            if name not in existing:
                existing.append(name)
            line.setText(", ".join(existing))

        add_btn.clicked.connect(add_current)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)

        if dlg.exec_() != QDialog.Accepted:
            return None
        return line.text()

    def _prompt_font_rule(self, group_init, kw_init, fonts_init):
        """Fragt Gruppe + Stichwörter + Fonts ab; (group, keywords, fonts) oder None."""
        # Gruppe: vorhandene Gruppen zur Auswahl, editierbar (neue eintippbar)
        items = list(self._existing_groups())
        if group_init and group_init not in items:
            items.insert(0, group_init)
        if not items:
            items = [""]
        current = items.index(group_init) if group_init in items else 0
        group, ok = QInputDialog.getItem(
            self.widget(), self.t("dlg_rule_group_title"),
            self.t("dlg_rule_group_label"), items, current, True)
        if not ok:
            return None
        group = group.strip()

        kw_text, ok2 = QInputDialog.getText(
            self.widget(), self.t("dlg_rule_kw_title"), self.t("dlg_rule_kw_label"),
            text=kw_init)
        if not ok2:
            return None
        keywords = [k.strip().lower() for k in kw_text.split(",") if k.strip()]
        if not keywords:
            self._warn(self.t("warn_no_keyword"))
            return None

        fonts_text = self._ask_fonts(fonts_init)
        if fonts_text is None:
            return None
        fonts = [f.strip() for f in fonts_text.split(",") if f.strip()]
        if not fonts:
            self._warn(self.t("warn_no_font"))
            return None
        return group, keywords, fonts

    def _add_font_rule(self):
        res = self._prompt_font_rule("", "", self.font_combo.currentText())
        if res is None:
            return
        group, keywords, fonts = res
        # neue Regel gehört zur aktiven Regelsprache UND zum aktiven Modus
        self._font_rules.append(
            {"group": group, "keywords": keywords, "fonts": fonts,
             "lang": self._rule_lang, "mode": self._mode})
        save_font_rules(self._font_rules)
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())
        self.status_label.setText(self.t("st_rule_added"))

    def _edit_font_rule(self, rule):
        res = self._prompt_font_rule(
            rule.get("group", ""),
            ", ".join(rule.get("keywords", [])),
            ", ".join(rule.get("fonts", [])))
        if res is None:
            return
        rule["group"], rule["keywords"], rule["fonts"] = res
        save_font_rules(self._font_rules)
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())
        self.status_label.setText(self.t("st_rule_updated"))

    def _delete_font_rule(self, rule):
        reply = QMessageBox.question(
            self.widget(), self.t("dlg_delrule_title"), self.t("dlg_delrule_q"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._font_rules = [r for r in self._font_rules if r is not rule]
        save_font_rules(self._font_rules)
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())
        self.status_label.setText(self.t("st_rule_deleted"))

    # ==================================================================
    #  Kern: SFX einfügen
    # ==================================================================
    def _sfx_from_layer(self):
        """Read the SFX word off the active vector layer (its text shapes) and
        drop it into the input, so an existing SFX can be re-suggested/-styled."""
        doc = Krita.instance().activeDocument()
        node = doc.activeNode() if doc else None
        if node is None:
            self._warn(self.t("st_no_layer_text"))
            return
        txt = ""
        try:
            shapes = node.shapes() if hasattr(node, "shapes") else []
            for sh in shapes:
                txt = _svg_text_content(sh.toSvg())
                if txt:
                    break
        except Exception:
            txt = ""
        if not txt:
            self._warn(self.t("st_no_layer_text"))
            return
        self.text_input.setText(txt)
        self.text_input.setFocus()

    def _build_svg(self, text, tx, ty, img_w, img_h, size=None,
                   outline_px=None):
        """Build the SFX SVG from the current controls at anchor (tx, ty).

        `size`/`outline_px` override the controls — the overlay and romaji
        strategies set a small word with a forced halo, because they sit ON the
        artwork next to the untouched original rather than replacing it."""
        return build_sfx_svg(
            text=text,
            font_family=self.font_combo.currentText(),
            font_size=size if size is not None else self.size_spin.value(),
            fill=self.fill_btn._color.name(),
            outline=self.outline_btn._color.name(),
            outline_px=(outline_px if outline_px is not None
                        else self.out_spin.value()),
            outline2=self.outline2_btn._color.name(),
            outline2_px=self.out2_spin.value(),
            bold=self.bold_chk.isChecked(),
            italic=self.italic_chk.isChecked(),
            x=tx, y=ty, anchor="middle", img_w=img_w, img_h=img_h,
            shadow=self.shadow_chk.isChecked(),
            shadow_color=self.shadow_btn._color.name(),
            shadow_dx=self.shadow_dx.value(),
            shadow_dy=self.shadow_dy.value(),
            rotate=self.rot_spin.value(),
            fill2=(self.fill2_btn._color.name()
                   if self.grad_chk.isChecked() else None),
            pattern_uri=(self._pattern_data_uri()
                         if self._pattern_active() else None),
            pattern_w=self._pattern_tile()[0],
            pattern_h=self._pattern_tile()[1],
        )

    def _restyle_sfx(self):
        """Re-render the active SFX layer with the current style, keeping its
        word and position. Vector layers are restyled in place; with a texture
        fill active the layer is replaced by a fresh raster layer (vector text
        can't take a pattern)."""
        doc = Krita.instance().activeDocument()
        node = doc.activeNode() if doc else None
        if node is None:
            self._warn(self.t("st_no_sfx_layer"))
            return
        is_vector = node.type() == "vectorlayer"
        pattern_mode = self._pattern_active()
        # only a vector SFX can be restyled in place; a texture render can start
        # from any SFX layer (word from the input, position from its bounds)
        if not is_vector and not pattern_mode:
            self._warn(self.t("st_no_sfx_layer"))
            return
        shapes = node.shapes() if (is_vector and hasattr(node, "shapes")) else []
        # word: the input if filled, else read it back off a vector layer
        text = self._effective_text()
        if not text:
            for sh in shapes:
                text = _svg_text_content(sh.toSvg())
                if text:
                    break
        if not text:
            self._warn(self.t("st_no_layer_text"))
            return
        img_w, img_h = doc.width(), doc.height()
        b = node.bounds()
        if b.width() > 0 and b.height() > 0:
            cx = b.x() + b.width() / 2.0
            cy = b.y() + b.height() / 2.0
        else:
            cx, cy = img_w / 2.0, img_h / 2.0
        ty = cy + self.size_spin.value() * 0.35

        if pattern_mode:
            new_node, _created = self._insert_sfx_raster(
                doc, text, cx, ty, self.size_spin.value(), None)
            if new_node is None:
                self._warn(self.t("st_insert_fail", err="texture"))
                return
            try:
                node.remove()          # replace the old layer with the raster one
            except Exception:
                pass
            doc.setActiveNode(new_node)
        else:
            try:
                for sh in list(shapes):
                    sh.remove()
            except Exception:
                pass            # if shapes cannot be removed, we add over them
            svg = self._build_svg(text, cx, ty, img_w, img_h)
            try:
                ok = node.addShapesFromSvg(svg)
            except Exception as e:                   # noqa: BLE001
                self._warn(self.t("st_insert_fail", err=e))
                return
            if ok is False:
                self._warn(self.t("st_svg_fail"))
                return
        doc.refreshProjection()
        self._record_usage(text, self.font_combo.currentText())
        self.status_label.setText(self.t("st_restyled"))

    def _render_sfx_qimage(self, text, size, outline_px=None):
        """Render the current SFX (texture fill + double outline + shadow +
        rotation) to an ARGB QImage. Returns (image, ax, ay) where (ax, ay) is
        the pixel matching the SVG anchor: horizontal centre + baseline. This is
        the raster twin of build_sfx_svg for the texture-fill fallback, and it
        paints exactly what the live preview paints (same layer order)."""
        fn = QFont(self.font_combo.currentText())
        fn.setPixelSize(max(1, int(size)))
        fn.setBold(self.bold_chk.isChecked())
        fn.setItalic(self.italic_chk.isChecked())
        fm = QFontMetricsF(fn)
        adv = fm.horizontalAdvance(text)
        asc, desc = fm.ascent(), fm.descent()

        o1 = float(outline_px if outline_px is not None else self.out_spin.value())
        o2 = float(self.out2_spin.value())
        margin = int(max(o1, o2) * 2 + 6)
        shadow_on = self.shadow_chk.isChecked()
        sdx = float(self.shadow_dx.value()) if shadow_on else 0.0
        sdy = float(self.shadow_dy.value()) if shadow_on else 0.0

        # content rectangle relative to the anchor (h-centre, baseline) at origin
        x0 = -adv / 2.0 - margin + min(0.0, sdx)
        x1 = adv / 2.0 + margin + max(0.0, sdx)
        y0 = -asc - margin + min(0.0, sdy)
        y1 = desc + margin + max(0.0, sdy)
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        angle = float(self.rot_spin.value())
        if angle:
            a = math.radians(angle)
            ca, sa = math.cos(a), math.sin(a)
            corners = [(cx * ca - cy * sa, cx * sa + cy * ca) for cx, cy in corners]
        rx0 = min(c[0] for c in corners)
        rx1 = max(c[0] for c in corners)
        ry0 = min(c[1] for c in corners)
        ry1 = max(c[1] for c in corners)
        w = max(1, int(math.ceil(rx1 - rx0)))
        h = max(1, int(math.ceil(ry1 - ry0)))
        ax, ay = -rx0, -ry0                       # anchor inside the image

        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.translate(ax, ay)
        if angle:
            p.rotate(angle)
        path = QPainterPath()
        path.addText(-adv / 2.0, 0.0, fn, text)   # h-centred, baseline at 0

        if shadow_on and (sdx or sdy):
            sp = QPainterPath(path)
            sp.translate(sdx, sdy)
            p.fillPath(sp, QBrush(QColor(self.shadow_btn._color)))
        if o1 > 0 and o2 > 0:              # 2nd outline coupled to the first
            pen2 = QPen(QColor(self.outline2_btn._color))
            pen2.setWidthF(max(0.5, 2.0 * o2))
            pen2.setJoinStyle(Qt.RoundJoin)
            pen2.setCapStyle(Qt.RoundCap)
            p.strokePath(path, pen2)
        if o1 > 0:
            pen = QPen(QColor(self.outline_btn._color))
            pen.setWidthF(max(0.5, 2.0 * o1))
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            p.strokePath(path, pen)
        pimg = self._ensure_pattern_img()
        if pimg is not None:
            tw, th = self._pattern_tile()
            pm = QPixmap.fromImage(pimg).scaled(
                max(1, tw), max(1, th), Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation)
            p.fillPath(path, QBrush(pm))
        else:                                     # safety: solid if no image
            p.fillPath(path, QBrush(QColor(self.fill_btn._color)))
        p.end()
        return img, ax, ay

    def _insert_sfx_raster(self, doc, text, tx, ty, size, outline_px):
        """Place the texture-filled SFX on a NEW paint layer (pixels), since
        Krita's vector text cannot take a pattern fill. Returns (node, created)
        or (None, False) on failure."""
        try:
            img, ax, ay = self._render_sfx_qimage(text, size, outline_px)
        except Exception:                         # noqa: BLE001
            return None, False
        img_w, img_h = doc.width(), doc.height()
        px = int(round(tx - ax))
        py = int(round(ty - ay))
        # clip to the canvas
        cx0, cy0 = max(0, px), max(0, py)
        cx1 = min(img_w, px + img.width())
        cy1 = min(img_h, py + img.height())
        if cx1 <= cx0 or cy1 <= cy0:
            return None, False
        if (cx0, cy0, cx1, cy1) != (px, py, px + img.width(), py + img.height()):
            img = img.copy(cx0 - px, cy0 - py, cx1 - cx0, cy1 - cy0)
        img = img.convertToFormat(QImage.Format_ARGB32)   # memory layout = BGRA
        node = doc.createNode("SFX", "paintlayer")
        root = doc.rootNode()
        kids = root.childNodes()
        root.addChildNode(node, kids[-1] if kids else None)
        doc.setActiveNode(node)
        nbytes = (img.sizeInBytes() if hasattr(img, "sizeInBytes")
                  else img.byteCount())
        buf = img.constBits()
        buf.setsize(nbytes)
        node.setPixelData(bytes(buf), cx0, cy0, img.width(), img.height())
        return node, True

    def _insert_sfx(self):
        doc = Krita.instance().activeDocument()
        if doc is None:
            self._warn(self.t("st_no_doc"))
            return

        sid = self._strategy()

        # 'ignore' is a real decision, not a no-op: the Japanese stays as drawn.
        # Record it and move on without touching the page.
        if not MODES.inserts_text(sid):
            raw = self.text_input.text().strip()
            self._info(self.t("st_sfx_ignored", word=raw or "—"))
            if self.v_clear_after_chk.isChecked():
                self.text_input.clear()
            return

        # 'note' leaves the artwork alone: what goes on the page is a small
        # numbered marker, and the reading + meaning collect into a list that
        # _place_note_list() puts at the panel edge.
        note_index = 0
        if sid == "note":
            source = self.text_input.text().strip()
            if not source:
                self._warn(self.t("st_no_text"))
                return
            note_index = len(self._notes) + 1
            self._notes.append(MODES.note_line(
                note_index, source, self.note_meaning_input.text().strip()))
            self._update_note_btn()     # the list button counts them
            text = MODES.note_marker(note_index)
        else:
            text = self._effective_text()
            if not text:
                self._warn(self.t("st_no_text"))
                return

        # Eine Textur-/Musterfüllung kann Kritas Vektor-Text nicht darstellen
        # (füllt einfarbig) -> dann rendern wir die SFX als Pixel-Ebene.
        pattern_mode = self._pattern_active()

        # Aktive Ebene prüfen – für Vektor: ist es keine Vektor-Ebene, neue anlegen.
        node = doc.activeNode()
        created = False
        if not pattern_mode and (node is None or node.type() != "vectorlayer"):
            node = doc.createVectorLayer("SFX")
            rootnode = doc.rootNode()
            children = rootnode.childNodes()
            above = children[-1] if children else None   # möglichst ganz oben
            rootnode.addChildNode(node, above)
            doc.setActiveNode(node)
            created = True

        # Zielmitte bestimmen: wenn eine Auswahl aktiv ist, deren Mitte,
        # sonst die Bildmitte (damit der SFX nicht mehr oben links klebt).
        img_w, img_h = doc.width(), doc.height()
        box_x, box_y, box_w, box_h = 0, 0, img_w, img_h
        sel = doc.selection()
        if sel is not None:
            try:
                if sel.width() > 0 and sel.height() > 0:
                    box_x, box_y = sel.x(), sel.y()
                    box_w, box_h = sel.width(), sel.height()
            except Exception:
                pass
        # Where and how big depends on the strategy. Redraw replaces the
        # original, so it takes the box at full size. Romaji and overlay sit
        # BESIDE an original that is still there: small, just under the box, and
        # with a halo whether or not the style asked for one — they land on
        # artwork and would be unreadable without it.
        fsize = self.size_spin.value()
        size = fsize
        outline_px = None
        if sid == "note":
            # a marker, not lettering: small, haloed, tucked at the box's corner
            size = max(10, int(round(fsize * 0.35)))
            outline_px = max(2, self.out_spin.value())
            tx = box_x + size * 0.6
            ty = box_y + size
        elif sid in ("romaji", "overlay"):
            size = max(8, int(round(fsize * 0.45)))
            outline_px = max(2, self.out_spin.value())
            tx = box_x + box_w / 2.0
            ty = box_y + box_h + size * 0.9
        else:
            tx = box_x + box_w / 2.0
            ty = box_y + box_h / 2.0 + size * 0.35   # grobe senkrechte Zentrierung

        # Keep it on the page. "Just below the original" runs off the bottom
        # whenever there is no selection — the box is then the whole image — and
        # the layer lands where nobody can see it.
        ty = min(ty, img_h - size * 0.3)
        ty = max(ty, size)
        tx = min(max(tx, size * 0.5), img_w - size * 0.5)

        if pattern_mode:
            node, created = self._insert_sfx_raster(
                doc, text, tx, ty, size, outline_px)
            if node is None:
                self._warn(self.t("st_insert_fail", err="texture"))
                return
            ok = True
        else:
            svg = self._build_svg(text, tx, ty, img_w, img_h,
                                  size=size, outline_px=outline_px)
            try:
                ok = node.addShapesFromSvg(svg)
            except Exception as e:                  # noqa: BLE001
                self._warn(self.t("st_insert_fail", err=e))
                return
        doc.refreshProjection()

        if ok is False:
            self._warn(self.t("st_svg_fail"))
            return

        # zuletzt genutzten Stil merken (ohne den Text selbst)
        style = self._capture_state()
        style.pop("text", None)
        save_settings(style)

        # dazulernen: welche Schrift wurde für dieses Wort gewählt
        self._record_usage(text, self.font_combo.currentText())

        self.status_label.setText(
            self.t("st_layer_created") if created else self.t("st_inserted"))

        # optional: Feld leeren + Fokus zurück, um SFX nach SFX schnell zu setzen
        if getattr(self, "v_clear_after_chk", None) and \
                self.v_clear_after_chk.isChecked():
            self.text_input.clear()
            self.text_input.setFocus()

    # ==================================================================
    #  Zurücksetzen
    # ==================================================================
    def _reset(self):
        """Zurücksetzen – wahlweise nur Stil oder alles (Presets + Regeln)."""
        box = QMessageBox(self.widget())
        box.setWindowTitle(self.t("reset_title"))
        box.setText(self.t("reset_q"))
        btn_style = box.addButton(self.t("reset_style"), QMessageBox.AcceptRole)
        btn_all = box.addButton(self.t("reset_all"), QMessageBox.DestructiveRole)
        box.addButton(self.t("cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(btn_style)
        box.exec_()
        clicked = box.clickedButton()

        if clicked is btn_all:
            self._user_presets = []
            self._font_rules = []
            self._hidden_modes = {}
            self._hidden_global = []
            save_user_presets(self._user_presets)
            save_font_rules(self._font_rules)
            save_hidden_builtins_modes(self._hidden_modes)
            save_hidden_builtins(self._hidden_global)
            self._rebuild_presets()
            self._rebuild_rules()
            msg = self.t("st_reset_all")
        elif clicked is btn_style:
            msg = self.t("st_reset_style")
        else:
            return  # Abbrechen

        self._reset_style_to_defaults()
        save_settings({})                 # gemerkten Stil verwerfen
        self.status_label.setText(msg)

    def _reset_style_to_defaults(self):
        """Setzt Font/Größe/Farben/Outline/Großschreibung auf die Startwerte."""
        if SFX_FONTS:
            self._select_font(SFX_FONTS[0], warn=False)
        else:
            self.font_combo.setCurrentIndex(0)
        self.size_spin.setValue(DEFAULTS["size"])
        self.out_spin.setValue(DEFAULTS["outline_px"])
        self.out2_spin.setValue(DEFAULTS.get("outline2_px", 0))
        self._set_btn_color(self.fill_btn, QColor(DEFAULTS["fill"]))
        self._set_btn_color(self.outline_btn, QColor(DEFAULTS["outline"]))
        self._set_btn_color(self.outline2_btn,
                            QColor(DEFAULTS.get("outline2", "#000000")))
        self.pattern_scale_spin.setValue(100)
        self._clear_pattern()
        self.pattern_chk.setChecked(False)
        self.shadow_chk.setChecked(bool(DEFAULTS.get("shadow", False)))
        self._set_btn_color(self.shadow_btn,
                            QColor(DEFAULTS.get("shadow_color", "#000000")))
        self.shadow_dx.setValue(int(DEFAULTS.get("shadow_dx", 6)))
        self.shadow_dy.setValue(int(DEFAULTS.get("shadow_dy", 6)))
        self._update_shadow_enabled()
        self.upper_chk.setChecked(True)
        self.bold_chk.setChecked(False)
        self.italic_chk.setChecked(False)
        self.text_input.clear()
        self._update_preview()

    def _warn(self, msg):
        self.status_label.setText("⚠ " + msg)

    def _info(self, msg):
        self.status_label.setText(msg)

    # ==================================================================
    #  Import / Export (eigene Presets + Font-Regeln)
    # ==================================================================
    def _export_data(self):
        """Schreibt eigene Presets + Font-Regeln in eine .json-Datei."""
        path, _flt = QFileDialog.getSaveFileName(
            self.widget(), self.t("export_title"),
            "manga_sfx_presets.json", "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        data = {
            "manga_sfx": 1,
            "presets": self._user_presets,
            "font_rules": self._font_rules,
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except OSError as e:                        # noqa: BLE001
            self._warn(self.t("st_export_fail", err=e))
            return
        self.status_label.setText(self.t(
            "st_exported", p=len(self._user_presets), r=len(self._font_rules)))

    def _import_data(self):
        """Liest Presets + Regeln aus einer .json-Datei (Zusammenführen/Ersetzen)."""
        path, _flt = QFileDialog.getOpenFileName(
            self.widget(), self.t("import_title"), "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:          # noqa: BLE001
            self._warn(self.t("st_import_fail", err=e))
            return
        if not isinstance(data, dict):
            self._warn(self.t("st_import_bad"))
            return

        presets = self._sanitize_presets(data.get("presets", []))
        rules = self._sanitize_rules(data.get("font_rules", []))
        # Imported rules without a mode adopt the active mode (like the
        # reference), so they show up in the mode the user imported them into.
        for rr in rules:
            if not rr.get("mode"):
                rr["mode"] = self._mode
        if not presets and not rules:
            self._warn(self.t("st_import_empty"))
            return

        # Zusammenführen oder ersetzen?
        box = QMessageBox(self.widget())
        box.setWindowTitle(self.t("import_title"))
        box.setText(self.t("import_q", p=len(presets), r=len(rules)))
        btn_merge = box.addButton(self.t("import_merge"), QMessageBox.AcceptRole)
        btn_replace = box.addButton(self.t("import_replace"),
                                    QMessageBox.DestructiveRole)
        box.addButton(self.t("cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(btn_merge)
        box.exec_()
        clicked = box.clickedButton()

        if clicked is btn_replace:
            self._user_presets = presets
            self._font_rules = rules
        elif clicked is btn_merge:
            self._merge_presets(presets)
            self._merge_rules(rules)
        else:
            return  # Abbrechen

        save_user_presets(self._user_presets)
        save_font_rules(self._font_rules)
        self._rebuild_presets()
        self._rebuild_rules()
        self._refresh_suggestions(self.text_input.text())
        self.status_label.setText(self.t(
            "st_imported", p=len(presets), r=len(rules)))

    # --- Hilfen für den Import ----------------------------------------
    def _as_int(self, value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _sanitize_presets(self, raw):
        """Macht importierte Presets robust (fehlende Felder auffüllen)."""
        out = []
        if not isinstance(raw, list):
            return out
        for p in raw:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            kws = p.get("keywords", [])
            out.append({
                "name": str(p.get("name", "")).strip(),
                "font": str(p.get("font", "")),
                "size": self._as_int(p.get("size"), DEFAULTS["size"]),
                "fill": str(p.get("fill", DEFAULTS["fill"])),
                "outline": str(p.get("outline", DEFAULTS["outline"])),
                "outline_px": self._as_int(p.get("outline_px"),
                                           DEFAULTS["outline_px"]),
                "outline2": str(p.get("outline2", DEFAULTS.get("outline2",
                                                               "#000000"))),
                "outline2_px": self._as_int(p.get("outline2_px"),
                                            DEFAULTS.get("outline2_px", 0)),
                "pattern": str(p.get("pattern", "")),
                "pattern_krita": str(p.get("pattern_krita", "")),
                "pattern_on": bool(p.get("pattern_on", False)),
                "pattern_scale": self._as_int(p.get("pattern_scale"), 100),
                "bold": bool(p.get("bold", False)),
                "italic": bool(p.get("italic", False)),
                "shadow": bool(p.get("shadow", False)),
                "shadow_color": str(p.get("shadow_color",
                                          DEFAULTS.get("shadow_color", "#000000"))),
                "shadow_dx": self._as_int(p.get("shadow_dx"),
                                          DEFAULTS.get("shadow_dx", 6)),
                "shadow_dy": self._as_int(p.get("shadow_dy"),
                                          DEFAULTS.get("shadow_dy", 6)),
                "keywords": ([str(k).strip().lower() for k in kws if str(k).strip()]
                             if isinstance(kws, list) else []),
                "user": True,
            })
        return out

    def _sanitize_rules(self, raw):
        """Macht importierte Font-Regeln robust; verwirft unvollständige."""
        out = []
        if not isinstance(raw, list):
            return out
        for r in raw:
            if not isinstance(r, dict):
                continue
            kws = r.get("keywords", [])
            fonts = r.get("fonts", [])
            if not isinstance(kws, list) or not isinstance(fonts, list):
                continue
            keywords = [str(k).strip().lower() for k in kws if str(k).strip()]
            fontlist = [str(f).strip() for f in fonts if str(f).strip()]
            if not keywords or not fontlist:
                continue
            lang = str(r.get("lang", "")).strip() or "*"   # alt -> "*" = immer
            out.append({
                "group": str(r.get("group", "")).strip(),
                "keywords": keywords,
                "fonts": fontlist,
                "lang": lang,
                "mode": str(r.get("mode", "")).strip(),
            })
        return out

    def _merge_presets(self, imported):
        """Fügt importierte Presets hinzu; gleicher Name ersetzt das alte."""
        names = {p["name"] for p in imported}
        self._user_presets = [p for p in self._user_presets
                              if p.get("name") not in names]
        self._user_presets.extend(imported)

    def _merge_rules(self, imported):
        """Fügt importierte Regeln hinzu. Gibt es bereits eine eigene Regel mit
        gleicher (Gruppe, Sprache), werden Stichwörter und Fonts dort vereinigt
        (statt eine zweite Regel mit gleicher Gruppe anzulegen); sonst wird die
        Regel angehängt. So bleibt die Liste beim mehrfachen Import sauber."""
        def key(r):
            return ((r.get("group") or "").strip().lower(),
                    r.get("lang") or "*", r.get("mode") or "")
        index = {}
        for i, r in enumerate(self._font_rules):
            index.setdefault(key(r), i)
        for r in imported:
            k = key(r)
            if k in index:
                tgt = self._font_rules[index[k]]
                for kw in r.get("keywords", []):
                    if kw not in tgt["keywords"]:
                        tgt["keywords"].append(kw)
                for f in r.get("fonts", []):
                    if f not in tgt["fonts"]:
                        tgt["fonts"].append(f)
            else:
                index[k] = len(self._font_rules)
                self._font_rules.append(r)
