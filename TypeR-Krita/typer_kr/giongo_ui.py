# -*- coding: utf-8 -*-
"""Qt panel for the Giongo tab: type a sound, get drawn SFX lettering.

Drives :mod:`giongo` (rules, layout) and :mod:`giongo_render` (drawing).
Decoupled from the docker the way the Swap panel is — a language getter,
two settings callbacks and a font list — so the main file barely grows and
the panel can be built in a plain Qt app for testing. Krita itself is only
imported when something is actually put on the page.

The flow follows the browser tool it is modelled on (MIYADAIKU's
擬音ジェネレーター): type the sound, let **✨ Auto** pick a type from how it
sounds, roll **🎲 Gacha** / **🧬 Mutate** for a sheet of options and click
the one that fits, then fine-tune with the three macro sliders or the
individual settings below them.
"""
import json
import os
import random

from ._qt import Qt, QTimer, QSize, QPointF, QTransform
from .nowheel import (NoScrollComboBox, NoScrollDoubleSpinBox,
                      NoScrollSlider, NoScrollSpinBox)
from ._qt import QColor, QPixmap, QIcon, QImage, QPainter
from ._qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QSlider, QSpinBox, QPlainTextEdit, QToolButton,
    QColorDialog, QFileDialog, QSizePolicy, QDoubleSpinBox, QDialog,
)

from . import giongo as G
from . import giongo_render as R
from . import strokefont as SF

_EN = {
    "gi_intro": ("Type a sound effect and get drawn manga lettering. Line "
                 "breaks split it into groups. Inspired by MIYADAIKU's "
                 "擬音ジェネレーター (Oyasumi Game Dev)."),
    "gi_text_ph": "e.g. ドーーン！ or BOOM!",
    "gi_type": "Type:",
    "gi_auto": "✨ Auto",
    "gi_auto_tip": ("Picks the type from how the sound is built (゛, ッ, ー, "
                    "ン, repeats) with a fixed rule table — no AI."),
    "gi_auto_done": "Switched to “{k}” (other good fits: {o})",
    "gi_font": "Font:",
    "gi_font_auto": "Type's font ({f})",
    "gi_font_none": "default sans",
    "gi_bold": "Bold",
    "gi_font_missing": ("None of this type's suggested fonts is installed "
                        "({f}). They are free on Google Fonts; the default "
                        "sans is used meanwhile."),
    "gi_bg": "Preview background:",
    "gi_bg_check": "Checkerboard",
    "gi_bg_white": "White",
    "gi_bg_gray": "Gray",
    "gi_bg_dark": "Dark",
    "gi_reroll": "🎲 Other shape",
    "gi_reroll_tip": "Same type and settings, a new random wobble",
    "gi_gacha": "🎲 Gacha",
    "gi_gacha_tip": ("A sheet of options: mostly the types the sound "
                     "suggests, now and then another"),
    "gi_mutate": "🧬 Mutate",
    "gi_mutate_tip": "A sheet of variations of the current look",
    "gi_wild": "Wild",
    "gi_wild_tip": "Gacha also shakes Power, Roughness and Momentum hard",
    "gi_back": "↶ Back",
    "gi_back_tip": "Back to the settings before the last Auto/Gacha/pick",
    "gi_pick_tip": "Use option {n}: {k}",
    "gi_close": "✕",
    "gi_macro": "Power / Roughness / Momentum",
    "gi_power": "Power",
    "gi_power_tip": "Thickness, size progression and outlines together",
    "gi_rough": "Roughness",
    "gi_rough_tip": "Wobble, angle and size variation together",
    "gi_momentum": "Momentum",
    "gi_momentum_tip": "Lean, slant, stretch and rise together",
    "gi_sec_pen": "Stroke lettering",
    "gi_pen": "Pen:",
    "gi_pen_tip": ("Draws each letter along the middle of its strokes, "
                   "in the order and the direction a hand writes them, "
                   "instead of filling the font's outline. Kana, Latin, "
                   "digits and punctuation are covered; anything else keeps "
                   "the font."),
    "gi_pen_off": "Off (use the font)",
    "gi_pen_pen": "Pen - thin and even",
    "gi_pen_marker": "Marker - one weight",
    "gi_pen_brush": "Brush - heavy, runs out",
    "gi_pen_board": "Board - heaviest, cut ends",
    "gi_pen_lightning": "Lightning - splintered",
    "gi_pen_rough": "Dry - scratchy, specks",
    "gi_pen_width": "Weight",
    "gi_pen_taper": "Taper",
    "gi_pen_wobble": "Wobble",
    "gi_pen_angle": "Cut angle",
    "gi_pen_dry": "Dry gaps",
    "gi_pen_missing": "{n} character(s) have no stroke lines: {chars}",
    "gi_sec_layout": "Layout",
    "gi_sec_var": "Variation",
    "gi_sec_fill": "Fill & outlines",
    "gi_sec_shadow": "Shadow & motion",
    "gi_letter_px": "Letter size (px):",
    "gi_vertical": "Vertical",
    "gi_merge_bars": "ーー as one long stroke",
    "gi_spacing": "Spacing",
    "gi_rise": "Rise",
    "gi_bend": "Bend",
    "gi_size_start": "Start size",
    "gi_size_end": "End size",
    "gi_size_tip": ("Letter size at the start / end of the path (%). Larger "
                    "letters come toward you, smaller ones recede."),
    "gi_lean": "Lean",
    "gi_lean_tip": "0 = letters stand upright · 100 = they lean with the path",
    "gi_slant": "Slant",
    "gi_stretch": "Stretch",
    "gi_bounce": "Bounce",
    "gi_jitter": "Wobble",
    "gi_rot_var": "Angle var.",
    "gi_size_var": "Size var.",
    "gi_seed": "Seed:",
    "gi_fill": "Fill",
    "gi_fill_solid": "Solid",
    "gi_fill_gradient": "Gradient",
    "gi_fill_tone": "Halftone",
    "gi_fill2": "to",
    "gi_fill_pattern": "Pattern",
    "gi_pattern_pick": "Choose tile\u2026",
    "gi_pattern_none": "no tile chosen",
    "gi_pattern_scale": "Tile size",
    "gi_pattern_tip": ("Fills the letters with a tile from your pattern "
                       "library - the generated ones and the ones lifted "
                       "from a crop of a page. Inserted as pixels, like a "
                       "halftone."),
    "gi_tone_dot": "Dot spacing",
    "gi_thicken": "Thicken",
    "gi_outline_n": "Outline {n}",
    "gi_outline_mode": "Outlines:",
    "gi_outline_letter": "Per letter",
    "gi_outline_merged": "Merged",
    "gi_outline_mode_tip": ("Per letter = each nearer letter's outline cuts "
                            "into the one behind · Merged = one outline "
                            "around the whole word"),
    "gi_shadow_dx": "Shadow X",
    "gi_shadow_dy": "Shadow Y",
    "gi_shadow_color": "Shadow",
    "gi_extrude": "3D steps",
    "gi_shake": "Shake",
    "gi_afterimage": "Afterimage",
    "gi_fit": "Fit into the selection",
    "gi_fit_tip": ("With a selection, the lettering is scaled to fill it; "
                   "otherwise it is placed at the letter size."),
    "gi_popout": "↗ Own window",
    "gi_popout_tip": ("Move this panel into a window of its own. It gets "
                      "wider there and arranges itself in columns; Krita "
                      "stays usable. Closing the window puts it back in "
                      "the tab."),
    "gi_popin": "↙ Back into the tab",
    "gi_window": "Giongo – drawn sound effects",
    "gi_insert_vec": "Insert (vector)",
    "gi_insert_vec_tip": ("Editable shapes on a new vector layer. A halftone "
                          "fill is inserted as pixels instead."),
    "gi_insert_px": "Insert (pixels)",
    "gi_save_png": "Save PNG…",
    "gi_save_svg": "Save SVG…",
    "gi_reset": "Reset",
    "gi_no_doc": "Open a document first.",
    "gi_empty": "Type a sound effect first.",
    "gi_inserted": "Inserted “{t}” as a {kind} layer.",
    "gi_kind_vector": "vector",
    "gi_kind_paint": "paint",
    "gi_tone_raster": " (halftone → pixels)",
    "gi_saved": "Saved {p}",
    "gi_save_fail": "Could not save {p}",
    "gi_fail": "Could not insert: {e}",
    "gi_type_impact": "Impact & crash",
    "gi_type_rumble": "Rumble & menace",
    "gi_type_slash": "Slash & speed",
    "gi_type_cute": "Soft & cute",
    "gi_type_drops": "Drops & splashes",
    "gi_type_small": "Small everyday sounds",
    "gi_type_glare": "Glare & presence",
    "gi_type_pop": "Pop, gags & shrieks",
    "gi_type_machine": "Machines & electronics",
}

_DE = {
    "gi_intro": ("Soundeffekt eintippen und als gezeichneten Manga-Schriftzug "
                 "bekommen. Zeilenumbrüche teilen ihn in Gruppen. Nach "
                 "MIYADAIKUs 擬音ジェネレーター (Oyasumi Game Dev)."),
    "gi_text_ph": "z. B. ドーーン！ oder BUMM!",
    "gi_type": "Art:",
    "gi_auto": "✨ Automatisch",
    "gi_auto_tip": ("Wählt die Art daran, wie der Laut gebaut ist (゛, ッ, ー, "
                    "ン, Wiederholungen) – feste Regeltabelle, keine KI."),
    "gi_auto_done": "Auf „{k}“ gestellt (passt auch: {o})",
    "gi_font": "Schrift:",
    "gi_font_auto": "Schrift der Art ({f})",
    "gi_font_none": "Standard-Sans",
    "gi_bold": "Fett",
    "gi_font_missing": ("Keine der vorgeschlagenen Schriften dieser Art ist "
                        "installiert ({f}). Sie sind kostenlos bei Google "
                        "Fonts; bis dahin wird die Standard-Sans benutzt."),
    "gi_bg": "Vorschau-Hintergrund:",
    "gi_bg_check": "Schachbrett",
    "gi_bg_white": "Weiß",
    "gi_bg_gray": "Grau",
    "gi_bg_dark": "Dunkel",
    "gi_reroll": "🎲 Andere Form",
    "gi_reroll_tip": "Gleiche Art und Einstellungen, neues zufälliges Wackeln",
    "gi_gacha": "🎲 Gacha",
    "gi_gacha_tip": ("Ein Blatt mit Vorschlägen: meist die Arten, die der "
                     "Laut nahelegt, ab und zu eine andere"),
    "gi_mutate": "🧬 Mutieren",
    "gi_mutate_tip": "Ein Blatt mit Abwandlungen des aktuellen Looks",
    "gi_wild": "Wild",
    "gi_wild_tip": "Gacha schüttelt auch Wucht, Rauheit und Schwung kräftig",
    "gi_back": "↶ Zurück",
    "gi_back_tip": ("Zurück zu den Einstellungen vor dem letzten "
                    "Automatisch/Gacha/Übernehmen"),
    "gi_pick_tip": "Vorschlag {n} übernehmen: {k}",
    "gi_close": "✕",
    "gi_macro": "Wucht / Rauheit / Schwung",
    "gi_power": "Wucht",
    "gi_power_tip": "Dicke, Größenverlauf und Konturen zusammen",
    "gi_rough": "Rauheit",
    "gi_rough_tip": "Wackeln, Winkel- und Größenstreuung zusammen",
    "gi_momentum": "Schwung",
    "gi_momentum_tip": "Neigung, Schräge, Streckung und Anstieg zusammen",
    "gi_sec_pen": "Strichschrift",
    "gi_pen": "Stift:",
    "gi_pen_tip": ("Zeichnet jeden Buchstaben entlang der Mitte seiner "
                   "Striche – in der Reihenfolge und der Richtung, in der "
                   "man sie schreibt –, statt den Umriss der Schrift zu "
                   "füllen. Kana, Latein, Ziffern und Satzzeichen sind "
                   "abgedeckt; alles andere behält die Schrift."),
    "gi_pen_off": "Aus (Schrift benutzen)",
    "gi_pen_pen": "Stift – dünn und gleichmäßig",
    "gi_pen_marker": "Marker – eine Stärke",
    "gi_pen_brush": "Pinsel – schwer, läuft aus",
    "gi_pen_board": "Brett – am schwersten, geschnitten",
    "gi_pen_lightning": "Blitz – gesplittert",
    "gi_pen_rough": "Trocken – kratzig, Spritzer",
    "gi_pen_width": "Stärke",
    "gi_pen_taper": "Auslauf",
    "gi_pen_wobble": "Wackeln",
    "gi_pen_angle": "Schnittwinkel",
    "gi_pen_dry": "Trockenlücken",
    "gi_pen_missing": "{n} Zeichen haben keine Strichlinien: {chars}",
    "gi_sec_layout": "Anordnung",
    "gi_sec_var": "Streuung",
    "gi_sec_fill": "Füllung & Konturen",
    "gi_sec_shadow": "Schatten & Bewegung",
    "gi_letter_px": "Zeichengröße (px):",
    "gi_vertical": "Senkrecht",
    "gi_merge_bars": "ーー als ein langer Strich",
    "gi_spacing": "Abstand",
    "gi_rise": "Anstieg",
    "gi_bend": "Biegung",
    "gi_size_start": "Größe Anfang",
    "gi_size_end": "Größe Ende",
    "gi_size_tip": ("Zeichengröße am Anfang / Ende des Pfads (%). Größere "
                    "Zeichen kommen auf dich zu, kleinere gehen nach hinten."),
    "gi_lean": "Neigung",
    "gi_lean_tip": ("0 = Zeichen stehen aufrecht · 100 = sie neigen sich mit "
                    "dem Pfad"),
    "gi_slant": "Schräge",
    "gi_stretch": "Streckung",
    "gi_bounce": "Hüpfen",
    "gi_jitter": "Wackeln",
    "gi_rot_var": "Winkelstreuung",
    "gi_size_var": "Größenstreuung",
    "gi_seed": "Seed:",
    "gi_fill": "Füllung",
    "gi_fill_solid": "Einfarbig",
    "gi_fill_gradient": "Verlauf",
    "gi_fill_tone": "Raster",
    "gi_fill2": "bis",
    "gi_fill_pattern": "Muster",
    "gi_pattern_pick": "Kachel wählen\u2026",
    "gi_pattern_none": "keine Kachel gewählt",
    "gi_pattern_scale": "Kachelgröße",
    "gi_pattern_tip": ("Füllt die Buchstaben mit einer Kachel aus deiner "
                       "Musterbibliothek – den erzeugten und den aus einem "
                       "Ausschnitt geholten. Wird als Pixel eingefügt, wie "
                       "ein Raster."),
    "gi_tone_dot": "Punktabstand",
    "gi_thicken": "Verdicken",
    "gi_outline_n": "Kontur {n}",
    "gi_outline_mode": "Konturen:",
    "gi_outline_letter": "Pro Zeichen",
    "gi_outline_merged": "Zusammen",
    "gi_outline_mode_tip": ("Pro Zeichen = die Kontur des vorderen Zeichens "
                            "schneidet in das dahinter · Zusammen = eine "
                            "Kontur um das ganze Wort"),
    "gi_shadow_dx": "Schatten X",
    "gi_shadow_dy": "Schatten Y",
    "gi_shadow_color": "Schatten",
    "gi_extrude": "3D-Stufen",
    "gi_shake": "Zittern",
    "gi_afterimage": "Nachbild",
    "gi_fit": "In die Auswahl einpassen",
    "gi_fit_tip": ("Mit Auswahl wird der Schriftzug auf ihre Größe skaliert, "
                   "sonst in der Zeichengröße eingesetzt."),
    "gi_popout": "↗ Eigenes Fenster",
    "gi_popout_tip": ("Verschiebt dieses Panel in ein eigenes Fenster. Dort "
                      "ist es breiter und ordnet sich in Spalten; Krita "
                      "bleibt bedienbar. Schließt du das Fenster, sitzt es "
                      "wieder im Tab."),
    "gi_popin": "↙ Zurück in den Tab",
    "gi_window": "Giongo – gezeichnete Soundeffekte",
    "gi_insert_vec": "Einfügen (Vektor)",
    "gi_insert_vec_tip": ("Bearbeitbare Formen auf einer neuen Vektorebene. "
                          "Eine Rasterfüllung wird stattdessen als Pixel "
                          "eingefügt."),
    "gi_insert_px": "Einfügen (Pixel)",
    "gi_save_png": "PNG speichern…",
    "gi_save_svg": "SVG speichern…",
    "gi_reset": "Zurücksetzen",
    "gi_no_doc": "Bitte zuerst ein Dokument öffnen.",
    "gi_empty": "Bitte zuerst einen Soundeffekt eintippen.",
    "gi_inserted": "„{t}“ als {kind} eingefügt.",
    "gi_kind_vector": "Vektorebene",
    "gi_kind_paint": "Malebene",
    "gi_tone_raster": " (Raster → Pixel)",
    "gi_saved": "Gespeichert: {p}",
    "gi_save_fail": "Konnte {p} nicht speichern",
    "gi_fail": "Einfügen fehlgeschlagen: {e}",
    "gi_type_impact": "Aufprall & Krach",
    "gi_type_rumble": "Grollen & Bedrohung",
    "gi_type_slash": "Hieb & Tempo",
    "gi_type_cute": "Weich & niedlich",
    "gi_type_drops": "Tropfen & Spritzer",
    "gi_type_small": "Kleine Alltagsgeräusche",
    "gi_type_glare": "Starren & Präsenz",
    "gi_type_pop": "Pop, Gags & Schreie",
    "gi_type_machine": "Maschinen & Elektronik",
}

STRINGS = {"en": _EN, "de": _DE}

# (key, label key, slider min, max, steps per unit). Float settings use more
# than one step per unit so the slider stays an int.
_LAYOUT_SLIDERS = [
    ("spacing", "gi_spacing", -60, 150, 1),
    ("rise", "gi_rise", -60, 60, 1),
    ("bend", "gi_bend", -80, 80, 1),
    ("size_start", "gi_size_start", 20, 300, 1),
    ("size_end", "gi_size_end", 20, 300, 1),
    ("lean", "gi_lean", 0, 100, 1),
    ("slant", "gi_slant", -45, 45, 1),
    ("stretch", "gi_stretch", -60, 150, 1),
    ("bounce", "gi_bounce", 0, 100, 1),
]
_VAR_SLIDERS = [
    ("jitter", "gi_jitter", 0, 100, 1),
    ("rot_var", "gi_rot_var", 0, 60, 1),
    ("size_var", "gi_size_var", 0, 60, 1),
]
_SHADOW_SLIDERS = [
    ("shadow_dx", "gi_shadow_dx", -40, 40, 2),
    ("shadow_dy", "gi_shadow_dy", -40, 40, 2),
    ("extrude", "gi_extrude", 0, 30, 1),
    ("shake", "gi_shake", 0, 5, 1),
    ("afterimage", "gi_afterimage", 0, 6, 1),
]
_MACROS = [("power", "gi_power"), ("rough", "gi_rough"),
           ("momentum", "gi_momentum")]
_TIPS = {"size_start": "gi_size_tip", "size_end": "gi_size_tip",
         "lean": "gi_lean_tip"}
_BACKGROUNDS = [("check", "gi_bg_check"), ("#ffffff", "gi_bg_white"),
                ("#9a9a9a", "gi_bg_gray"), ("#2b2b2b", "gi_bg_dark")]
_N_OPTIONS = 6
_HISTORY = 30


def _checker(w, h, cell=8):
    img = QImage(max(1, w), max(1, h), QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    grey = QColor("#d6d6d6")
    for y in range(0, h, cell):
        for x in range((y // cell) % 2 * cell, w, cell * 2):
            p.fillRect(x, y, cell, cell, grey)
    p.end()
    return img


class _Section(QWidget):
    """A heading button that shows / hides its body; open state remembered."""

    def __init__(self, key, opened, on_toggle, parent=None):
        super().__init__(parent)
        self.key = key
        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.setLayout(lay)
        self.btn = QToolButton()
        self.btn.setCheckable(True)
        self.btn.setChecked(opened)
        self.btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Fixed)
        self.btn.setStyleSheet("QToolButton { border: none; "
                               "font-weight: bold; text-align: left; }")
        lay.addWidget(self.btn)
        self.body = QWidget()
        self.grid = QGridLayout()
        self.grid.setContentsMargins(10, 0, 0, 4)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(2)
        self.body.setLayout(self.grid)
        lay.addWidget(self.body)
        self._on_toggle = on_toggle
        self.btn.toggled.connect(self._toggled)
        self._toggled(opened, save=False)

    def _toggled(self, on, save=True):
        self.body.setVisible(on)
        self.btn.setArrowType(Qt.ArrowType.DownArrow if on
                              else Qt.ArrowType.RightArrow)
        if save:
            self._on_toggle(self.key, on)


class GiongoWindow(QDialog):
    """A plain window holding the panel. Not modal: Krita stays usable."""

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setModal(False)
        self.setSizeGripEnabled(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(panel)

    def closeEvent(self, ev):           # noqa: N802 (Qt API)
        # hand the panel back before the window goes, or it would be
        # destroyed along with it
        self._panel.dock_back()
        super().closeEvent(ev)


class GiongoPanel(QWidget):
    """Text in, a sheet of options, lettering on the page."""

    def __init__(self, lang_fn=None, get_setting=None, set_setting=None,
                 families_fn=None, pick_pattern_fn=None, parent=None):
        super().__init__(parent)
        self._lang_fn = lang_fn or (lambda: "en")
        self._get = get_setting or (lambda _k, d="": d)
        self._set = set_setting or (lambda _k, _v: None)
        self._families_fn = families_fn or (lambda: [])
        self._pick_pattern_fn = pick_pattern_fn
        self._families = None
        self._params = G.from_json(self._get("giongoParams", "")) \
            if self._get("giongoParams", "") else G.default_params("impact")
        self._history = []
        self._options = []          # [(params, button)]
        self._sliders = {}          # key -> (slider, value label, label, steps)
        self._loading = False
        self._rng = random.Random()
        self._active = True         # the docker turns this off for a tab
        self._tab_active = True     # ...kept apart from the window, which is
        self._popped = False        # on screen whatever the tab is doing
        self._blocks = []           # the groups the grid arranges
        self._cols = 0              # how many columns they sit in now
        self._home = None           # the layout to go back to
        self._window = None
        self._pending = True        # owes a preview as soon as it is shown
        self._last_size = (0, 0)    # what the last preview was rendered for
        self._fonts_filled = False  # the family list is filled on first show
        try:
            self._open = json.loads(self._get("giongoOpen", "{}")) or {}
        except ValueError:
            self._open = {}
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(90)
        self._preview_timer.timeout.connect(self._refresh_preview)
        # owned by the panel, so it cannot fire into a panel that is gone
        # (a bare QTimer.singleShot once took Krita down that way)
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(0)
        self._layout_timer.timeout.connect(self._recheck_columns)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._save_state)
        self._build()
        self.retranslate()
        self._load_into_widgets()
        self._schedule()

    # --- helpers -----------------------------------------------------------

    def _t(self, key, **kw):
        lang = self._lang_fn() or "en"
        text = STRINGS.get(lang, _EN).get(key) or _EN.get(key, key)
        return text.format(**kw) if kw else text

    def families(self):
        if self._families is None:
            try:
                self._families = list(self._families_fn() or [])
            except Exception:           # noqa: BLE001
                self._families = []
        return self._families

    def font_family(self):
        return G.resolve_font(self._params, self.families())

    def text(self):
        return self.text_edit.toPlainText()

    def params(self):
        return G.sanitize(self._params)

    def scene(self, params=None):
        p = params if params is not None else self._params
        return R.build_scene(self.text(), p,
                             G.resolve_font(p, self.families()))

    def _status(self, msg):
        self.status_lbl.setText(msg)

    def _color_button(self, on_pick):
        btn = QPushButton()
        btn.setFixedWidth(42)
        btn.clicked.connect(lambda *_a: on_pick(btn))
        return btn

    @staticmethod
    def _paint_swatch(btn, color):
        btn.setStyleSheet("QPushButton { background: %s; border: 1px solid "
                          "#777; min-height: 16px; }" % color)
        btn.setProperty("giColor", color)

    def _pick_color(self, btn, apply):
        cur = QColor(btn.property("giColor") or "#000000")
        col = QColorDialog.getColor(cur, self)
        if col.isValid():
            apply(col.name())

    # --- building ----------------------------------------------------------

    def _new_block(self):
        """Start a new group. Everything added after this lands in it.

        The build code below keeps writing to `lay` as it always did; only
        where a new group begins does `lay` come to point at a fresh one.
        """
        box = QWidget()
        inner = QVBoxLayout(box)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(6)
        self._blocks.append(box)
        return inner

    def _build(self):
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(6)
        self.setLayout(self._grid)
        lay = self._new_block()

        self.intro = QLabel()
        self.intro.setWordWrap(True)
        self.intro.setStyleSheet("color: gray;")
        lay.addWidget(self.intro)
        row = QHBoxLayout()
        row.addStretch(1)
        self.popout_btn = QPushButton()
        self.popout_btn.clicked.connect(self.on_popout)
        row.addWidget(self.popout_btn)
        lay.addLayout(row)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setFixedHeight(58)
        self.text_edit.setPlainText(self._get("giongoText", "ドーーン！"))
        self.text_edit.textChanged.connect(self._on_text)
        lay.addWidget(self.text_edit)

        row = QHBoxLayout()
        self.type_lbl = QLabel()
        row.addWidget(self.type_lbl)
        self.type_combo = NoScrollComboBox()
        for tid in G.TYPE_IDS:
            self.type_combo.addItem("", tid)
        self.type_combo.currentIndexChanged.connect(self._on_type)
        row.addWidget(self.type_combo, 1)
        self.auto_btn = QPushButton()
        self.auto_btn.clicked.connect(self.on_auto)
        row.addWidget(self.auto_btn)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.font_lbl = QLabel()
        row.addWidget(self.font_lbl)
        self.font_combo = NoScrollComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.font_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.font_combo.setMinimumContentsLength(8)
        self.font_combo.addItem("", "")
        # the families are added on first show: at Krita's startup nobody is
        # looking at this tab, and there can be a few thousand of them
        self.font_combo.activated.connect(self._on_font)
        row.addWidget(self.font_combo, 1)
        self.bold_chk = QCheckBox()
        self.bold_chk.toggled.connect(lambda on: self._set_param("bold", on))
        row.addWidget(self.bold_chk)
        lay.addLayout(row)
        self.font_hint = QLabel()
        self.font_hint.setWordWrap(True)
        self.font_hint.setStyleSheet("color: gray; font-size: 10px;")
        lay.addWidget(self.font_hint)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(170)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored,
                                   QSizePolicy.Policy.Preferred)
        self.preview.setStyleSheet("border: 1px solid #888;")
        lay.addWidget(self.preview)

        row = QHBoxLayout()
        self.bg_lbl = QLabel()
        row.addWidget(self.bg_lbl)
        self.bg_combo = NoScrollComboBox()
        for val, _k in _BACKGROUNDS:
            self.bg_combo.addItem("", val)
        bg = self._get("giongoBg", "check")
        self.bg_combo.setCurrentIndex(max(0, self.bg_combo.findData(bg)))
        self.bg_combo.currentIndexChanged.connect(self._on_bg)
        row.addWidget(self.bg_combo, 1)
        self.back_btn = QPushButton()
        self.back_btn.clicked.connect(self.on_back)
        row.addWidget(self.back_btn)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.reroll_btn = QPushButton()
        self.reroll_btn.clicked.connect(self.on_reroll)
        row.addWidget(self.reroll_btn)
        self.gacha_btn = QPushButton()
        self.gacha_btn.clicked.connect(lambda *_a: self.on_gacha())
        row.addWidget(self.gacha_btn)
        self.mutate_btn = QPushButton()
        self.mutate_btn.clicked.connect(lambda *_a: self.on_mutate())
        row.addWidget(self.mutate_btn)
        self.wild_chk = QCheckBox()
        row.addWidget(self.wild_chk)
        lay.addLayout(row)

        # the sheet of options (hidden until rolled)
        self.options_box = QWidget()
        og = QGridLayout()
        og.setContentsMargins(0, 0, 0, 0)
        og.setSpacing(4)
        self.options_box.setLayout(og)
        self._option_btns = []
        for i in range(_N_OPTIONS):
            b = QToolButton()
            b.setIconSize(QSize(150, 84))
            b.setAutoRaise(True)
            b.clicked.connect(lambda *_a, n=i: self.on_pick(n))
            og.addWidget(b, i // 2, i % 2)
            self._option_btns.append(b)
        self.close_opts_btn = QToolButton()
        self.close_opts_btn.clicked.connect(
            lambda *_a: self.options_box.setVisible(False))
        og.addWidget(self.close_opts_btn, 0, 2,
                     Qt.AlignmentFlag.AlignTop)
        self.options_box.setVisible(False)
        lay.addWidget(self.options_box)

        # macro sliders
        self.macro_lbl = QLabel()
        self.macro_lbl.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.macro_lbl)
        mg = QGridLayout()
        mg.setContentsMargins(10, 0, 0, 0)
        mg.setVerticalSpacing(2)
        for r, (key, lk) in enumerate(_MACROS):
            self._add_slider(mg, r, key, lk, -100, 100, 1)
        lay.addLayout(mg)

        # individual settings
        self.sec_layout = _Section("layout", self._open.get("layout", False),
                                   self._on_section)
        g = self.sec_layout.grid
        self.letter_lbl = QLabel()
        g.addWidget(self.letter_lbl, 0, 0)
        self.letter_spin = NoScrollSpinBox()
        self.letter_spin.setRange(*G.RANGES["letter_px"])
        self.letter_spin.valueChanged.connect(
            lambda v: self._set_param("letter_px", v))
        g.addWidget(self.letter_spin, 0, 1, 1, 2)
        self.vertical_chk = QCheckBox()
        self.vertical_chk.toggled.connect(
            lambda on: self._set_param("vertical", on))
        g.addWidget(self.vertical_chk, 1, 0, 1, 3)
        self.bars_chk = QCheckBox()
        self.bars_chk.toggled.connect(
            lambda on: self._set_param("merge_bars", on))
        g.addWidget(self.bars_chk, 2, 0, 1, 3)
        for r, spec in enumerate(_LAYOUT_SLIDERS, start=3):
            self._add_slider(g, r, *spec)
        lay = self._new_block()
        lay.addWidget(self.sec_layout)

        self.sec_var = _Section("var", self._open.get("var", False),
                                self._on_section)
        g = self.sec_var.grid
        for r, spec in enumerate(_VAR_SLIDERS):
            self._add_slider(g, r, *spec)
        self.seed_lbl = QLabel()
        g.addWidget(self.seed_lbl, len(_VAR_SLIDERS), 0)
        self.seed_spin = NoScrollSpinBox()
        self.seed_spin.setRange(*G.RANGES["seed"])
        self.seed_spin.valueChanged.connect(
            lambda v: self._set_param("seed", v))
        g.addWidget(self.seed_spin, len(_VAR_SLIDERS), 1, 1, 2)
        lay = self._new_block()
        self.sec_pen = _Section("pen", self._open.get("pen", True),
                                self._on_section)
        g = self.sec_pen.grid
        self.pen_lbl = QLabel()
        g.addWidget(self.pen_lbl, 0, 0)
        self.pen_combo = NoScrollComboBox()
        for name in G.PENS:
            self.pen_combo.addItem("", name)
        self.pen_combo.currentIndexChanged.connect(
            lambda *_a: self._set_param("pen",
                                        self.pen_combo.currentData() or "off"))
        g.addWidget(self.pen_combo, 0, 1, 1, 2)
        self.pen_hint = QLabel()
        self.pen_hint.setWordWrap(True)
        self.pen_hint.setStyleSheet("color: #a07000;")
        self.pen_hint.setVisible(False)
        g.addWidget(self.pen_hint, 1, 0, 1, 3)
        for r, (key, lk) in enumerate(
                (("pen_width", "gi_pen_width"),
                 ("pen_taper", "gi_pen_taper"),
                 ("pen_wobble", "gi_pen_wobble"),
                 ("pen_angle", "gi_pen_angle"),
                 ("pen_dry", "gi_pen_dry"))):
            lo, hi = G.RANGES[key]
            self._add_slider(g, r + 2, key, lk, lo, hi, 1)
        lay.addWidget(self.sec_pen)

        lay = self._new_block()
        lay.addWidget(self.sec_var)

        self.sec_fill = _Section("fill", self._open.get("fill", True),
                                 self._on_section)
        g = self.sec_fill.grid
        self.fill_lbl = QLabel()
        g.addWidget(self.fill_lbl, 0, 0)
        frow = QHBoxLayout()
        self.fill_btn = self._color_button(
            lambda b: self._pick_color(b, lambda c: self._set_param("fill",
                                                                    c)))
        frow.addWidget(self.fill_btn)
        self.fill_mode = NoScrollComboBox()
        for m in G.FILL_MODES:
            self.fill_mode.addItem("", m)
        self.fill_mode.currentIndexChanged.connect(
            lambda _i: self._set_param("fill_mode",
                                       self.fill_mode.currentData()))
        frow.addWidget(self.fill_mode, 1)
        self.fill2_lbl = QLabel()
        frow.addWidget(self.fill2_lbl)
        self.fill2_btn = self._color_button(
            lambda b: self._pick_color(b, lambda c: self._set_param("fill2",
                                                                    c)))
        frow.addWidget(self.fill2_btn)
        g.addLayout(frow, 0, 1, 1, 2)
        self._add_slider(g, 1, "tone_dot", "gi_tone_dot", 3, 60, 1)
        prow = QHBoxLayout()
        self.pattern_btn = QPushButton()
        self.pattern_btn.clicked.connect(self.on_pick_pattern)
        prow.addWidget(self.pattern_btn)
        self.pattern_lbl = QLabel()
        self.pattern_lbl.setStyleSheet("color: gray;")
        prow.addWidget(self.pattern_lbl, 1)
        g.addLayout(prow, 2, 0, 1, 3)
        self._add_slider(g, 3, "fill_pattern_scale", "gi_pattern_scale",
                         10, 400, 1)

        self._add_slider(g, 2, "thicken", "gi_thicken", 0, 12, 4)
        self._outline_rows = []
        for i in range(G.MAX_OUTLINES):
            chk = QCheckBox()
            chk.toggled.connect(self._on_outlines)
            g.addWidget(chk, 3 + i, 0)
            orow = QHBoxLayout()
            btn = QPushButton()
            btn.setFixedWidth(42)
            btn.clicked.connect(lambda *_a, n=i: self._pick_outline(n))
            orow.addWidget(btn)
            spin = NoScrollDoubleSpinBox()
            spin.setRange(0.2, 40.0)
            spin.setSingleStep(0.5)
            spin.setDecimals(1)
            spin.setSuffix(" %")
            spin.valueChanged.connect(self._on_outlines)
            orow.addWidget(spin, 1)
            g.addLayout(orow, 3 + i, 1, 1, 2)
            self._outline_rows.append((chk, btn, spin))
        r = 3 + G.MAX_OUTLINES
        self.omode_lbl = QLabel()
        g.addWidget(self.omode_lbl, r, 0)
        self.omode_combo = NoScrollComboBox()
        for m in G.OUTLINE_MODES:
            self.omode_combo.addItem("", m)
        self.omode_combo.currentIndexChanged.connect(
            lambda _i: self._set_param("outline_mode",
                                       self.omode_combo.currentData()))
        g.addWidget(self.omode_combo, r, 1, 1, 2)
        lay = self._new_block()
        lay.addWidget(self.sec_fill)

        self.sec_shadow = _Section("shadow", self._open.get("shadow", False),
                                   self._on_section)
        g = self.sec_shadow.grid
        for r, spec in enumerate(_SHADOW_SLIDERS):
            self._add_slider(g, r, *spec)
        self.shadow_lbl = QLabel()
        g.addWidget(self.shadow_lbl, len(_SHADOW_SLIDERS), 0)
        self.shadow_btn = self._color_button(
            lambda b: self._pick_color(
                b, lambda c: self._set_param("shadow_color", c)))
        g.addWidget(self.shadow_btn, len(_SHADOW_SLIDERS), 1)
        lay = self._new_block()
        lay.addWidget(self.sec_shadow)

        # output
        lay = self._new_block()
        self.fit_chk = QCheckBox()
        self.fit_chk.setChecked(self._get("giongoFit", "true") == "true")
        self.fit_chk.toggled.connect(
            lambda on: self._set("giongoFit", "true" if on else "false"))
        lay.addWidget(self.fit_chk)
        row = QHBoxLayout()
        self.insert_vec_btn = QPushButton()
        self.insert_vec_btn.clicked.connect(
            lambda *_a: self.insert(raster=False))
        row.addWidget(self.insert_vec_btn)
        self.insert_px_btn = QPushButton()
        self.insert_px_btn.clicked.connect(
            lambda *_a: self.insert(raster=True))
        row.addWidget(self.insert_px_btn)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.save_png_btn = QPushButton()
        self.save_png_btn.clicked.connect(lambda *_a: self.on_save("png"))
        row.addWidget(self.save_png_btn)
        self.save_svg_btn = QPushButton()
        self.save_svg_btn.clicked.connect(lambda *_a: self.on_save("svg"))
        row.addWidget(self.save_svg_btn)
        self.reset_btn = QPushButton()
        self.reset_btn.clicked.connect(self.on_reset)
        row.addWidget(self.reset_btn)
        lay.addLayout(row)

        self.status_lbl = QLabel()
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("color: gray;")
        lay.addWidget(self.status_lbl)
        lay.addStretch(1)
        self._place_blocks(1)

    def _add_slider(self, grid, row, key, label_key, lo, hi, steps):
        lbl = QLabel()
        grid.addWidget(lbl, row, 0)
        sl = NoScrollSlider(Qt.Orientation.Horizontal)
        sl.setRange(int(lo * steps), int(hi * steps))
        sl.valueChanged.connect(
            lambda v, k=key, s=steps: self._on_slider(k, v, s))
        grid.addWidget(sl, row, 1)
        val = QLabel()
        val.setMinimumWidth(34)
        val.setAlignment(Qt.AlignmentFlag.AlignRight |
                         Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(val, row, 2)
        self._sliders[key] = (sl, val, lbl, steps, label_key)

    # --- language ----------------------------------------------------------

    def retranslate(self):
        t = self._t
        self.intro.setText(t("gi_intro"))
        self.text_edit.setPlaceholderText(t("gi_text_ph"))
        self.type_lbl.setText(t("gi_type"))
        for i in range(self.type_combo.count()):
            self.type_combo.setItemText(
                i, t("gi_type_" + self.type_combo.itemData(i)))
        self.auto_btn.setText(t("gi_auto"))
        self.auto_btn.setToolTip(t("gi_auto_tip"))
        self.font_lbl.setText(t("gi_font"))
        self.bold_chk.setText(t("gi_bold"))
        self.bg_lbl.setText(t("gi_bg"))
        for i, (_v, k) in enumerate(_BACKGROUNDS):
            self.bg_combo.setItemText(i, t(k))
        self.back_btn.setText(t("gi_back"))
        self.back_btn.setToolTip(t("gi_back_tip"))
        self.reroll_btn.setText(t("gi_reroll"))
        self.reroll_btn.setToolTip(t("gi_reroll_tip"))
        self.gacha_btn.setText(t("gi_gacha"))
        self.gacha_btn.setToolTip(t("gi_gacha_tip"))
        self.mutate_btn.setText(t("gi_mutate"))
        self.mutate_btn.setToolTip(t("gi_mutate_tip"))
        self.wild_chk.setText(t("gi_wild"))
        self.wild_chk.setToolTip(t("gi_wild_tip"))
        self.close_opts_btn.setText(t("gi_close"))
        self.macro_lbl.setText(t("gi_macro"))
        for key, (_sl, _val, lbl, _st, lk) in self._sliders.items():
            lbl.setText(t(lk))
            tip = t(lk + "_tip") if (lk + "_tip") in _EN else \
                (t(_TIPS[key]) if key in _TIPS else "")
            lbl.setToolTip(tip)
            _sl.setToolTip(tip)
        # "&" would turn into a shortcut underline on a button
        for sec, key in ((self.sec_layout, "gi_sec_layout"),
                         (self.sec_var, "gi_sec_var"),
                         (self.sec_fill, "gi_sec_fill"),
                         (self.sec_shadow, "gi_sec_shadow")):
            sec.btn.setText(t(key).replace("&", "&&"))
        self.letter_lbl.setText(t("gi_letter_px"))
        self.vertical_chk.setText(t("gi_vertical"))
        self.bars_chk.setText(t("gi_merge_bars"))
        self.seed_lbl.setText(t("gi_seed"))
        self.fill_lbl.setText(t("gi_fill"))
        for i, m in enumerate(G.FILL_MODES):
            self.fill_mode.setItemText(i, t("gi_fill_" + m))
        self.fill2_lbl.setText(t("gi_fill2"))
        for i, (chk, _b, _s) in enumerate(self._outline_rows):
            chk.setText(t("gi_outline_n", n=i + 1))
        self.omode_lbl.setText(t("gi_outline_mode"))
        for i, m in enumerate(G.OUTLINE_MODES):
            self.omode_combo.setItemText(i, t("gi_outline_" + m))
        self.omode_combo.setToolTip(t("gi_outline_mode_tip"))
        self.shadow_lbl.setText(t("gi_shadow_color"))
        self.fit_chk.setText(t("gi_fit"))
        self.fit_chk.setToolTip(t("gi_fit_tip"))
        self.insert_vec_btn.setText(t("gi_insert_vec"))
        self.insert_vec_btn.setToolTip(t("gi_insert_vec_tip"))
        self.insert_px_btn.setText(t("gi_insert_px"))
        self.save_png_btn.setText(t("gi_save_png"))
        self.save_svg_btn.setText(t("gi_save_svg"))
        self.pattern_btn.setText(t("gi_pattern_pick"))
        self.pattern_btn.setToolTip(t("gi_pattern_tip"))
        self._refresh_pattern_name()
        self.pen_lbl.setText(t("gi_pen"))
        self.pen_combo.setToolTip(t("gi_pen_tip"))
        for i, name in enumerate(G.PENS):
            self.pen_combo.setItemText(i, t("gi_pen_" + name))
        self._refresh_pen_hint()
        self.reset_btn.setText(t("gi_reset"))
        self.popout_btn.setText(t("gi_popin") if self._popped
                                else t("gi_popout"))
        self.popout_btn.setToolTip(t("gi_popout_tip"))
        self._refresh_font_ui()
        self._refresh_option_tips()

    # --- params <-> widgets ------------------------------------------------

    def _load_into_widgets(self):
        p = self._params = G.sanitize(self._params)
        self._loading = True
        try:
            self.type_combo.setCurrentIndex(
                max(0, self.type_combo.findData(p["type"])))
            self.bold_chk.setChecked(p["bold"])
            self.letter_spin.setValue(p["letter_px"])
            self.vertical_chk.setChecked(p["vertical"])
            self.bars_chk.setChecked(p["merge_bars"])
            self.seed_spin.setValue(p["seed"])
            for key, (sl, val, _l, steps, _lk) in self._sliders.items():
                sl.setValue(int(round(p[key] * steps)))
                val.setText(self._fmt(p[key], steps))
            self._paint_swatch(self.fill_btn, p["fill"])
            self._paint_swatch(self.fill2_btn, p["fill2"])
            self._paint_swatch(self.shadow_btn, p["shadow_color"])
            self.fill_mode.setCurrentIndex(
                max(0, self.fill_mode.findData(p["fill_mode"])))
            self.omode_combo.setCurrentIndex(
                max(0, self.omode_combo.findData(p["outline_mode"])))
            outs = p["outlines"]
            for i, (chk, btn, spin) in enumerate(self._outline_rows):
                on = i < len(outs)
                col, w = outs[i] if on else ("#ffffff" if i % 2 == 0
                                             else "#111111", 4.0)
                chk.setChecked(on)
                self._paint_swatch(btn, col)
                spin.setValue(w)
            self._refresh_enabled()
            self._refresh_font_ui()
        finally:
            self._loading = False

    @staticmethod
    def _fmt(v, steps):
        return ("%.1f" % v) if steps > 1 else str(int(round(v)))

    def _refresh_enabled(self):
        p = self._params
        self.fill2_btn.setEnabled(p["fill_mode"] == "gradient")
        self.fill2_lbl.setEnabled(p["fill_mode"] == "gradient")
        sl = self._sliders.get("tone_dot")
        if sl:
            for w in sl[:3]:
                w.setEnabled(p["fill_mode"] == "tone")
        sl = self._sliders.get("fill_pattern_scale")
        if sl:
            for w in sl[:3]:
                w.setEnabled(p["fill_mode"] == "pattern")
        if hasattr(self, "pattern_lbl"):
            self.pattern_lbl.setEnabled(p["fill_mode"] == "pattern")
        # outline k only makes sense when the ones before it are on
        prev_on = True
        for chk, btn, spin in self._outline_rows:
            chk.setEnabled(prev_on)
            btn.setEnabled(prev_on and chk.isChecked())
            spin.setEnabled(prev_on and chk.isChecked())
            prev_on = prev_on and chk.isChecked()

    def _refresh_font_ui(self):
        p = self._params
        t = G.type_info(p["type"]) or G.TYPES[0]
        resolved = G.resolve_font(dict(p, font=""), self.families())
        self.font_combo.setItemText(
            0, self._t("gi_font_auto", f=resolved or self._t("gi_font_none")))
        idx = self.font_combo.findData(p["font"]) if p["font"] else 0
        self.font_combo.setCurrentIndex(max(0, idx))
        missing = not p["font"] and not resolved
        self.font_hint.setVisible(missing)
        if missing:
            self.font_hint.setText(self._t("gi_font_missing",
                                           f=", ".join(t["fonts"])))

    def _set_param(self, key, value):
        if self._loading:
            return
        self._params[key] = value
        if key in ("fill", "fill2", "shadow_color"):
            btn = {"fill": self.fill_btn, "fill2": self.fill2_btn,
                   "shadow_color": self.shadow_btn}[key]
            self._paint_swatch(btn, value)
        if key == "fill_mode":
            self._refresh_enabled()
        if key == "seed":
            self.seed_spin.blockSignals(True)
            self.seed_spin.setValue(int(value))
            self.seed_spin.blockSignals(False)
        self._schedule()

    def _on_slider(self, key, v, steps):
        val = v / float(steps)
        if steps == 1:
            val = int(v)
        sl = self._sliders[key]
        sl[1].setText(self._fmt(val, steps))
        self._set_param(key, val)

    def _on_outlines(self, *_a):
        if self._loading:
            return
        outs = []
        for chk, btn, spin in self._outline_rows:
            if not chk.isChecked():
                break
            outs.append([btn.property("giColor") or "#ffffff", spin.value()])
        self._params["outlines"] = outs
        self._refresh_enabled()
        self._schedule()

    def _pick_outline(self, n):
        chk, btn, _spin = self._outline_rows[n]

        def apply(c):
            self._paint_swatch(btn, c)
            self._on_outlines()
        self._pick_color(btn, apply)

    def _on_text(self):
        self._schedule()

    def _on_type(self, _i):
        if self._loading:
            return
        tid = self.type_combo.currentData()
        if tid and tid != self._params.get("type"):
            self._push_history()
            self._params = G.apply_type(self._params, tid)
            self._load_into_widgets()
            self._schedule()

    def _on_font(self, _i):
        fam = self.font_combo.currentData()
        if fam is None:
            # typed into the editable box: take it when it is a real family
            txt = self.font_combo.currentText().strip()
            fam = txt if txt in self.families() else ""
        self._params["font"] = fam or ""
        self._refresh_font_ui()
        self._schedule()

    def _on_bg(self, _i):
        self._set("giongoBg", self.bg_combo.currentData() or "check")
        self._schedule()

    def _on_section(self, key, on):
        self._open[key] = bool(on)
        self._set("giongoOpen", json.dumps(self._open))

    # --- preview -----------------------------------------------------------

    def _schedule(self):
        self._preview_timer.start()
        self._save_timer.start()

    def _background(self):
        bg = self.bg_combo.currentData() or "check"
        return None if bg == "check" else bg

    def _framed(self, scene, w, h):
        bg = self._background()
        img = R.render_thumb(scene, w, h, background=bg)
        if bg is None:
            base = _checker(w, h)
            p = QPainter(base)
            p.drawImage(0, 0, img)
            p.end()
            img = base
        return img

    def _fill_fonts(self):
        if self._fonts_filled:
            return
        self._fonts_filled = True
        keep = self._params.get("font") or ""
        self.font_combo.blockSignals(True)
        for fam in sorted(self.families(), key=lambda s: s.lower()):
            self.font_combo.addItem(fam, fam)
        self.font_combo.blockSignals(False)
        self._refresh_font_ui()
        if keep:
            idx = self.font_combo.findData(keep)
            if idx >= 0:
                self.font_combo.setCurrentIndex(idx)

    # --- arranging in columns ---------------------------------------

    def _columns_for(self, width):
        """How many columns this width can carry.

        A Krita docker is rarely wider than 500 px, so it gets one; a window
        the user has pulled open gets two or three.
        """
        if width < 780:
            return 1
        if width < 1180:
            return 2
        return 3

    def _split_blocks(self, cols):
        """Which block goes in which column, in reading order.

        The first block holds the text and the preview and is what the eye
        goes to, so it keeps a column of its own as soon as there are two.
        """
        blocks = [b for b in self._blocks if b is not None]
        if not blocks:
            return []
        if cols <= 1:
            return [blocks]
        if cols == 2:
            return [[blocks[0]], blocks[1:]]
        rest = blocks[1:]
        half = (len(rest) + 1) // 2
        return [[blocks[0]], rest[:half], rest[half:]]

    def _recheck_columns(self):
        """Re-read the width once the layout has settled.

        Right after a move the panel still reports the width it had in the
        place it came from, so asking straight away gives the old answer.
        """
        self._place_blocks(self._columns_for(self.width()))

    def _place_blocks(self, cols):
        """(Re)arrange the groups. Does nothing when the count is unchanged."""
        cols = max(1, int(cols))
        if cols == self._cols:
            return
        self._cols = cols
        grid = self._grid
        for i in reversed(range(grid.count())):
            item = grid.takeAt(i)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)       # self._blocks still holds it
        columns = self._split_blocks(cols)
        rows = 0
        for c, column in enumerate(columns):
            for r, block in enumerate(column):
                grid.addWidget(block, r, c)
                block.setParent(self)
                block.show()
            rows = max(rows, len(column))
            # the first column carries the preview, so it may take more room
            grid.setColumnStretch(c, 3 if c == 0 else 2)
        for c in range(len(columns), 4):
            grid.setColumnStretch(c, 0)
        grid.setRowStretch(rows, 1)

    # --- tab or window ------------------------------------------------------

    def on_popout(self, *_a):
        """The button: out into a window, or back into the tab."""
        if self._popped:
            if self._window is not None:
                self._window.close()    # its closeEvent docks the panel back
            return
        self.pop_out()

    def pop_out(self):
        """Move this panel into a window of its own."""
        if self._popped:
            if self._window is not None:
                self._window.raise_()
            return
        parent = self.parentWidget()
        self._home = parent.layout() if parent is not None else None
        win = GiongoWindow(self, self.window())
        win.setWindowTitle(self._t("gi_window"))
        self._window = win
        self._popped = True
        self._restore_geometry(win)
        self.popout_btn.setText(self._t("gi_popin"))
        self._apply_active()
        win.show()
        self._layout_timer.start()

    def dock_back(self):
        """Put the panel back where it came from."""
        if not self._popped:
            return
        if self._window is not None:
            self._remember_geometry(self._window)
        self._popped = False
        self._window = None
        if self._home is not None:
            self._home.addWidget(self)
        self.popout_btn.setText(self._t("gi_popout"))
        self._apply_active()
        self._layout_timer.start()

    def _remember_geometry(self, win):
        g = win.geometry()
        self._set("giongoWinGeom", "%d,%d,%d,%d"
                  % (g.x(), g.y(), g.width(), g.height()))

    def _restore_geometry(self, win):
        """Put the window back where it was, if that is still on a screen."""
        raw = self._get("giongoWinGeom", "")
        parts = [p for p in str(raw).split(",") if p.strip()]
        if len(parts) == 4:
            try:
                x, y, w, h = (int(p) for p in parts)
            except ValueError:
                x = y = w = h = 0
            if w >= 420 and h >= 320:
                win.setGeometry(x, y, w, h)
                return
        win.resize(1180, 760)

    def set_active(self, on):
        """The docker calls this when its tab comes to the front or leaves.

        A panel nobody can see must not render: Krita builds every docker tab
        at startup, and a preview drawn into a hidden widget cost 2.2 s of the
        UI thread (measured) to show the result to nobody.
        """
        self._tab_active = bool(on)
        self._apply_active()

    def _apply_active(self):
        """A window is on screen whatever the tab behind it is doing."""
        on = self._tab_active or self._popped
        was = self._active
        self._active = on
        if on and not was:
            self._fill_fonts()
            if self._pending:
                self._preview_timer.start()

    def on_pick_pattern(self, *_a):
        """Ask the docker for a tile out of the pattern library."""
        if self._pick_pattern_fn is None:
            self._status(self._t("gi_pattern_none"))
            return
        try:
            img, path = self._pick_pattern_fn()
        except Exception:                           # noqa: BLE001
            img, path = None, ""
        if not path:
            return
        self._push_history()
        self._set_param("fill_pattern", path)
        self._set_param("fill_mode", "pattern")
        self.fill_mode.setCurrentIndex(
            max(0, self.fill_mode.findData("pattern")))
        self._refresh_pattern_name()
        self._refresh_enabled()
        self._schedule()

    def _refresh_pattern_name(self):
        """Show which tile is in use, by its file name."""
        if not hasattr(self, "pattern_lbl"):
            return
        path = self._params.get("fill_pattern", "")
        self.pattern_lbl.setText(os.path.basename(path) if path
                                 else self._t("gi_pattern_none"))

    def _refresh_pen_hint(self):
        """Say which characters the pen cannot draw, if any.

        Silence would be worse than a note: a kanji simply keeps the font's
        outline, and seeing one letter in a different hand without being told
        why looks like a fault.
        """
        if not hasattr(self, "pen_hint"):
            return
        if self._params.get("pen", "off") == "off":
            self.pen_hint.setVisible(False)
            return
        missing = SF.missing(self.text())
        self.pen_hint.setVisible(bool(missing))
        if missing:
            self.pen_hint.setText(self._t("gi_pen_missing").format(
                n=len(missing), chars=" ".join(missing[:12])))

    def _refresh_preview(self):
        if not self._active:
            self._pending = True
            return
        self._pending = False
        self._refresh_pen_hint()
        w = max(240, self.preview.width() - 4)
        h = max(160, self.preview.height() - 4)
        self._last_size = (self.preview.width(), self.preview.height())
        try:
            scene = self.scene()
            img = self._framed(scene, w, h)
        except Exception as exc:        # noqa: BLE001
            self.preview.setText(str(exc))
            return
        self.preview.setPixmap(QPixmap.fromImage(img))

    def showEvent(self, ev):            # noqa: N802 (Qt API)
        super().showEvent(ev)
        if not self._popped:
            self.set_active(True)
        self._place_blocks(self._columns_for(self.width()))

    def resizeEvent(self, ev):          # noqa: N802 (Qt API)
        super().resizeEvent(ev)
        # Only when the preview really has a different size to fill. A new
        # pixmap changes the label's size hint, so an unconditional reschedule
        # here lets a layout pass feed itself.
        self._place_blocks(self._columns_for(self.width()))
        size = (self.preview.width(), self.preview.height())
        if size != self._last_size:
            self._preview_timer.start()

    def _save_state(self):
        self._set("giongoParams", G.to_json(self._params))
        self._set("giongoText", self.text())

    # --- history -----------------------------------------------------------

    def _push_history(self):
        self._history.append(G.sanitize(self._params))
        del self._history[:-_HISTORY]

    def on_back(self, *_a):
        if not self._history:
            return
        self._params = self._history.pop()
        self._load_into_widgets()
        self._schedule()

    # --- auto, gacha, mutate -----------------------------------------------

    def on_auto(self, *_a):
        tid, others = G.omakase(self.text())
        self._push_history()
        self._params = G.apply_type(self._params, tid)
        self._params["font"] = ""
        self._load_into_widgets()
        self._schedule()
        self._status(self._t("gi_auto_done", k=self._t("gi_type_" + tid),
                             o=", ".join(self._t("gi_type_" + o)
                                         for o in others)))

    def on_reroll(self, *_a):
        self._params = G.reroll(self._params, self._rng)
        self._load_into_widgets()
        self._schedule()

    def on_gacha(self):
        wild = self.wild_chk.isChecked()
        sets = [G.gacha(self.text(), self._params, self._rng, wild=wild)
                for _i in range(_N_OPTIONS)]
        self._show_options(sets)

    def on_mutate(self):
        sets = [G.mutate(self._params, self._rng,
                         amount=0.15 + 0.06 * i) for i in range(_N_OPTIONS)]
        self._show_options(sets)

    def _show_options(self, sets):
        self._options = sets
        for btn, p in zip(self._option_btns, sets):
            try:
                img = self._framed(self.scene(p), 150, 84)
                btn.setIcon(QIcon(QPixmap.fromImage(img)))
            except Exception:           # noqa: BLE001
                btn.setIcon(QIcon())
        self._refresh_option_tips()
        self.options_box.setVisible(True)

    def _refresh_option_tips(self):
        for i, btn in enumerate(self._option_btns):
            if i < len(self._options):
                k = self._t("gi_type_" + self._options[i]["type"])
                btn.setToolTip(self._t("gi_pick_tip", n=i + 1, k=k))

    def on_pick(self, n):
        if n >= len(self._options):
            return
        self._push_history()
        self._params = G.sanitize(self._options[n])
        self._load_into_widgets()
        self._schedule()

    def on_reset(self, *_a):
        self._push_history()
        self._params = G.default_params(self._params.get("type", "impact"))
        self._load_into_widgets()
        self._schedule()

    # --- output ------------------------------------------------------------

    def on_save(self, kind):
        scene = self.scene()
        if scene.is_empty():
            self._status(self._t("gi_empty"))
            return
        last = self._get("giongoSaveDir", "")
        filt = "PNG (*.png)" if kind == "png" else "SVG (*.svg)"
        path, _f = QFileDialog.getSaveFileName(self, "", last, filt)
        if not path:
            return
        if not path.lower().endswith("." + kind):
            path += "." + kind
        ok = self.save_to(path, scene)
        self._status(self._t("gi_saved" if ok else "gi_save_fail", p=path))

    def save_to(self, path, scene=None):
        """Write the lettering to `path` (.png or .svg). True on success."""
        import os
        scene = scene or self.scene()
        try:
            if path.lower().endswith(".svg"):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(R.to_svg(scene))
                ok = True
            else:
                img, _tl = R.render_image(scene)
                ok = bool(img.save(path, "PNG"))
        except OSError:
            return False
        if ok:
            self._set("giongoSaveDir", os.path.dirname(path))
        return ok

    def placement(self, scene, doc_w, doc_h, sel=None):
        """scene → page transform: centred on the selection (or the canvas),
        scaled to fit the selection when asked. `sel` = (x, y, w, h)."""
        b = scene.bounds
        if sel:
            cx, cy = sel[0] + sel[2] / 2.0, sel[1] + sel[3] / 2.0
        else:
            cx, cy = doc_w / 2.0, doc_h / 2.0
        k = 1.0
        if sel and self.fit_chk.isChecked() and b.width() > 0 \
                and b.height() > 0:
            k = min(sel[2] / b.width(), sel[3] / b.height()) * 0.96
        tr = QTransform()
        tr.translate(cx, cy)
        tr.scale(k, k)
        tr.translate(-b.center().x(), -b.center().y())
        return tr, k

    def insert(self, raster=False):
        try:
            from krita import Krita
        except ImportError:
            return None
        doc = Krita.instance().activeDocument()
        if doc is None:
            self._status(self._t("gi_no_doc"))
            return None
        scene = self.scene()
        if scene.is_empty():
            self._status(self._t("gi_empty"))
            return None
        W, H = doc.width(), doc.height()
        sel = None
        s = doc.selection()
        if s is not None:
            try:
                if s.width() > 0 and s.height() > 0:
                    sel = (s.x(), s.y(), s.width(), s.height())
            except Exception:           # noqa: BLE001
                sel = None
        tr, k = self.placement(scene, W, H, sel)
        name = "Giongo " + " ".join(self.text().split())[:24]
        tone = scene.needs_raster() and not raster
        try:
            if raster or tone:
                node = self._insert_raster(doc, scene, tr, k, name)
                kind = "gi_kind_paint"
            else:
                node = doc.createVectorLayer(name)
                root = doc.rootNode()
                kids = root.childNodes()
                root.addChildNode(node, kids[-1] if kids else None)
                node.addShapesFromSvg(R.to_svg(scene, tr, W, H))
                doc.setActiveNode(node)
                kind = "gi_kind_vector"
            doc.refreshProjection()
        except Exception as exc:        # noqa: BLE001
            self._status(self._t("gi_fail", e=exc))
            return None
        if node is None:
            self._status(self._t("gi_fail", e="outside the canvas"))
            return None
        msg = self._t("gi_inserted", t=" ".join(self.text().split()),
                      kind=self._t(kind))
        if tone:
            msg += self._t("gi_tone_raster")
        self._status(msg)
        return node

    def _insert_raster(self, doc, scene, tr, k, name):
        img, tl = R.render_image(scene, scale=k, margin=2)
        # tl is the image's top-left in scaled scene units; the page position
        # of scene point s is tr(s) = c + k·(s − centre)
        origin = tr.map(QPointF(0, 0))
        px = int(round(origin.x() + tl.x()))
        py = int(round(origin.y() + tl.y()))
        W, H = doc.width(), doc.height()
        x0, y0 = max(0, px), max(0, py)
        x1 = min(W, px + img.width())
        y1 = min(H, py + img.height())
        if x1 <= x0 or y1 <= y0:
            return None
        if (x0, y0, x1, y1) != (px, py, px + img.width(), py + img.height()):
            img = img.copy(x0 - px, y0 - py, x1 - x0, y1 - y0)
        img = img.convertToFormat(QImage.Format.Format_ARGB32)  # BGRA bytes
        node = doc.createNode(name, "paintlayer")
        root = doc.rootNode()
        kids = root.childNodes()
        root.addChildNode(node, kids[-1] if kids else None)
        doc.setActiveNode(node)
        nbytes = (img.sizeInBytes() if hasattr(img, "sizeInBytes")
                  else img.byteCount())
        buf = img.constBits()
        buf.setsize(nbytes)
        node.setPixelData(bytes(buf), x0, y0, img.width(), img.height())
        return node
