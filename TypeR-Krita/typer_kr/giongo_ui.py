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

import time as _time

from ._qt import Qt, QTimer, QSize, QPointF, QTransform
from .nowheel import (NoScrollComboBox, NoScrollDoubleSpinBox,
                      NoScrollSlider, NoScrollSpinBox)
from ._qt import QColor, QPixmap, QIcon, QImage, QPainter
from ._qt import QFont
from ._qt import QKeySequence
from ._qt import QPen, QPainterPath, QRectF
from ._qt import QPainterPathStroker
from ._qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit,
    QComboBox, QCheckBox, QSlider, QSpinBox, QPlainTextEdit, QToolButton,
    QColorDialog, QFileDialog, QSizePolicy, QDoubleSpinBox, QDialog,
    QScrollArea, QFrame, QApplication, QShortcut,
    QListWidget, QListWidgetItem,
)
from ._qt import QGuiApplication, QPoint

from . import giongo as G
from . import giongo_dict as GD
from . import giongo_warp as W
from . import giongo_nodes as N
from . import giongo_brush as BR
from . import userfonts as UF
from . import giongo_trace as TR
from . import report as RP
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
    "gi_font_load": "+",
    "gi_font_load_tip": ("Load a font file that is not installed "
                         "(.ttf, .otf, .ttc). It stays loaded, and comes "
                         "back the next time Krita starts."),
    "gi_font_pick": "\U0001f50d",
    "gi_font_pick_tip": "Pick a font by looking at it",
    "gi_font_pick_title": "Pick a font",
    "gi_font_pick_search": "Search a font",
    "gi_font_pick_use": "Use it",
    "gi_font_pick_more": "\u2026 and {n} more. Narrow the search.",
    "gi_font_pick_count": "{n} fonts",
    "gi_font_pick_auto": "The type\u2019s own font",
    "gi_window_hint": "This tab has a lot in it \u2014 it works best in its "
                      "own window:",
    "gi_tab_only": ("Drawn sound effects need room: a canvas and the "
                    "settings beside it. The tab opens them in a window of "
                    "their own \u2014 close it and everything comes back "
                    "here."),
    "gi_font_loaded": "Loaded: {f}",
    "gi_font_load_bad": "Could not read: {f}",
    "gi_set": "Lettering:",
    "gi_set_none": "The font",
    "gi_set_tip": ("Your own drawn letters instead of a font. A letter the "
                   "set does not have is drawn by the font as usual."),
    "gi_set_import": "Import\u2026",
    "gi_set_import_tip": ("Trace images of drawn letters into a set. Pick "
                          "images, a folder or a ZIP; each file is the "
                          "letter its name is (\u30c9.png is \u30c9)."),
    "gi_set_done": "{n} letters traced into \u201c{s}\u201d: {l}",
    "gi_set_skipped": " \u00b7 {n} skipped",
    "gi_set_none_found": "No letters found. A file is the letter its name is.",
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
    "gi_forward": "↷ Forward",
    "gi_forward_tip": "The step that was just undone, back again (Ctrl+Y)",
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
    "gi_nothing_there": "Nothing under the brush there.",
    "gi_tool_move": "\u2725 Move",
    "gi_tool_liquify": "\u25d0 Liquify",
    "gi_tool_points": "\u25c7 Points",
    "gi_tool_erase": "\u232b Erase",
    "gi_tool_move_tip": ("Drag a letter to move it, the ring above it to "
                         "turn it, the square to resize it. Double-click "
                         "puts it back. The path has handles too: the end "
                         "aims the whole effect, the middle bends it."),
    "gi_tool_erase_tip": ("Wipe parts of a letter away. The brush size is "
                          "the one under Liquify."),
    "gi_legend_move": ("click a letter, then: \u2192 sideways \u00b7 "
                       "\u2191 up/down \u00b7 \u25a1 free \u00b7 "
                       "\u25cb turn \u00b7 \u25a0 size \u00b7 "
                       "double-click = back  \u2502  path: \u25cf end = "
                       "aim \u00b7 \u25c7 middle = bend"),
    "gi_legend_liquify": ("drag over a letter to push it about \u00b7 Alt "
                          "turns the tool round \u00b7 size, force and "
                          "hardness are under Liquify"),
    "gi_legend_points": ("drag a point or its handle \u00b7 Shift+click "
                         "gathers several, or drag a rectangle over them "
                         "\u00b7 the gizmo moves, turns and resizes what "
                         "is gathered \u00b7 double-click the outline = a "
                         "new point, a point = corner \u21c4 curve \u00b7 "
                         "Alt+click deletes"),
    "gi_legend_erase": ("drag to wipe parts of a letter away \u00b7 the "
                        "letter keeps everything else, and undo takes the "
                        "whole stroke back"),
    "gi_erased": "Wiped away. Undo takes it back.",
    "gi_frozen_font": ("{n} letter(s) have an outline of their own and "
                       "keep it \u2014 \u201cReset all points\u201d under "
                       "the canvas gives them back to the font."),
    "gi_act_del": "Delete point",
    "gi_act_smooth": "Corner \u21c4 curve",
    "gi_act_reset_letter": "Reset this letter",
    "gi_act_reset_pts": "Reset all points",
    "gi_act_reset_warp": "Undo all warping",
    "gi_act_reset_moves": "Reset letter edits",
    "gi_act_count": "letters with edited points: {n}",
    "gi_sec_points": "Points",
    "gi_pts_on": "Edit points (drag in the preview)",
    "gi_pts_on_tip": ("Take hold of the outline itself. Click a letter to "
                      "open it, drag its points and handles; click the "
                      "outline between two points to add one; Alt+click a "
                      "point to delete it, Shift+click to switch between a "
                      "corner and a curve."),
    "gi_pts_opened": "{n} points on this letter.",
    "gi_pts_reset": "Back to the font's outline",
    "gi_pts_reset_done": "Every letter is back to the outline the font drew.",
    "gi_sec_liquify": "Liquify",
    "gi_liq_on": "Brush on (drag in the preview)",
    "gi_liq_on_tip": ("While this is on, dragging in the preview pushes the "
                      "letter about instead of moving it. Hold Alt to turn "
                      "the tool round."),
    "gi_liq_tool": "Tool:",
    "gi_liq_push": "Push",
    "gi_liq_inflate": "Inflate",
    "gi_liq_pinch": "Pinch",
    "gi_liq_twirl": "Twirl",
    "gi_liq_size": "Brush size",
    "gi_liq_force": "Force",
    "gi_liq_hard": "Hardness",
    "gi_liq_reset": "Undo all warping",
    "gi_liq_reset_done": "Every letter is back to the shape the font drew.",
    "gi_sec_deco": "Decorations",
    "gi_deco": "Around it:",
    "gi_deco_off": "None",
    "gi_deco_rays": "Impact rays",
    "gi_deco_debris": "Debris",
    "gi_deco_sparkle": "Sparkle",
    "gi_deco_drops": "Drops",
    "gi_deco_n": "How many",
    "gi_deco_size": "Their size",
    "gi_deco_dist": "How far out",
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
    "gi_fill_tone_grad": "Halftone gradient",
    "gi_fill2": "to",
    "gi_caption": "Caption:",
    "gi_caption_ph": "e.g. BOOM",
    "gi_caption_tip": ("A small reading or translation beside the effect. "
                       "Set plainly: none of the shaping touches it."),
    "gi_caption_pos": "Where:",
    "gi_caption_below": "Below",
    "gi_caption_above": "Above",
    "gi_caption_right": "Right",
    "gi_caption_left": "Left",
    "gi_caption_size": "Caption size",
    "gi_fill_negative": "Negative",
    "gi_fill_line": "Line only",
    "gi_fill_line_tone": "Line in halftone",
    "gi_fill_line_w": "Line width",
    "gi_neg_pad": "Area around",
    "gi_dict": "\U0001f4d6",
    "gi_dict_tip": "Known sound effects to pick from (sets the type too)",
    "gi_dict_title": "Sound effects",
    "gi_dict_search": "Search: kana, reading or meaning",
    "gi_dict_hint": "Double-click a sound to use it",
    "gi_dict_take": "Use it",
    "gi_dict_took": "{s} \u2014 {m} \u00b7 type \u201c{k}\u201d",
    "gi_dakuten": "\u309b",
    "gi_dakuten_tip": ("Put a dakuten \u309b on the letter before the cursor "
                       "\u2014 any letter, the way a scream is drawn "
                       "(\u30a2\u3099, \u30f3\u3099)."),
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
    "gi_noise_lines": "Noise lines",
    "gi_noise_style": "Drawn with:",
    "gi_noise_hand": "Hand-drawn",
    "gi_noise_dry": "Dry brush",
    "gi_noise_fuzzy": "Fuzzy",
    "gi_noise_amp": "Noise width",
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
    "gi_save_zip": "Layers (ZIP)\u2026",
    "gi_save_zip_tip": ("Every layer as its own PNG, all on the same "
                        "canvas: text, outlines, shadow, afterimage, "
                        "decorations, noise."),
    "gi_save_psd": "PSD\u2026",
    "gi_save_psd_tip": ("The same layers as a Photoshop file, written by "
                        "Krita itself. Needs a running Krita."),
    "gi_scale": "Size:",
    "gi_scale_tip": "What PNG and ZIP are rendered at",
    "gi_saved_zip": "{n} layers written to {p}",
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
    "gi_set": "Lettering:",
    "gi_set_none": "Die Schrift",
    "gi_set_tip": ("Eigene gezeichnete Buchstaben statt einer Schrift. Was "
                   "der Satz nicht hat, zeichnet weiterhin die Schrift."),
    "gi_set_import": "Importieren\u2026",
    "gi_set_import_tip": ("Bilder gezeichneter Buchstaben zu einem Satz "
                          "nachzeichnen. Bilder, Ordner oder ZIP w\u00e4hlen; "
                          "jede Datei ist der Buchstabe, nach dem sie "
                          "hei\u00dft (\u30c9.png ist \u30c9)."),
    "gi_set_done": "{n} Buchstaben nachgezeichnet in \u201e{s}\u201c: {l}",
    "gi_set_skipped": " \u00b7 {n} \u00fcbersprungen",
    "gi_set_none_found": ("Keine Buchstaben gefunden. Eine Datei ist der "
                          "Buchstabe, nach dem sie hei\u00dft."),
    "gi_font_auto": "Schrift der Art ({f})",
    "gi_font_none": "Standard-Sans",
    "gi_bold": "Fett",
    "gi_font_load": "+",
    "gi_font_load_tip": ("Eine nicht installierte Schriftdatei laden "
                         "(.ttf, .otf, .ttc). Sie bleibt geladen und ist "
                         "beim n\u00e4chsten Krita-Start wieder da."),
    "gi_font_pick": "\U0001f50d",
    "gi_font_pick_tip": "Eine Schrift aussuchen, indem man sie ansieht",
    "gi_font_pick_title": "Schrift aussuchen",
    "gi_font_pick_search": "Schrift suchen",
    "gi_font_pick_use": "Nehmen",
    "gi_font_pick_more": "\u2026 und {n} weitere. Suche eingrenzen.",
    "gi_font_pick_count": "{n} Schriften",
    "gi_font_pick_auto": "Die Schrift der Art",
    "gi_window_hint": "In diesem Tab steckt viel \u2014 am besten im "
                      "eigenen Fenster:",
    "gi_tab_only": ("Gezeichnete Soundeffekte brauchen Platz: eine "
                    "Leinwand und die Einstellungen daneben. Der Tab "
                    "\u00f6ffnet sie in einem eigenen Fenster \u2014 "
                    "schlie\u00dfen, und alles ist wieder hier."),
    "gi_font_loaded": "Geladen: {f}",
    "gi_font_load_bad": "Nicht lesbar: {f}",
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
    "gi_forward": "↷ Vor",
    "gi_forward_tip": ("Der gerade zurückgenommene Schritt, wieder hin "
                       "(Strg+Y)"),
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
    "gi_nothing_there": "Dort ist nichts unter dem Pinsel.",
    "gi_tool_move": "\u2725 Bewegen",
    "gi_tool_liquify": "\u25d0 Verfl\u00fcssigen",
    "gi_tool_points": "\u25c7 Punkte",
    "gi_tool_erase": "\u232b Wischen",
    "gi_tool_move_tip": ("Buchstaben ziehen verschiebt ihn, der Ring "
                         "dreht, das Quadrat skaliert. Doppelklick setzt "
                         "zur\u00fcck. Der Pfad hat auch Griffe: das Ende "
                         "richtet den Effekt aus, die Mitte beugt ihn."),
    "gi_tool_erase_tip": ("Teile eines Buchstabens wegwischen. Die "
                          "Pinselgr\u00f6\u00dfe ist die unter "
                          "Verfl\u00fcssigen."),
    "gi_legend_move": ("Buchstabe anklicken, dann: \u2192 seitw\u00e4rts "
                       "\u00b7 \u2191 hoch/runter \u00b7 \u25a1 frei "
                       "\u00b7 \u25cb drehen \u00b7 \u25a0 "
                       "Gr\u00f6\u00dfe \u00b7 Doppelklick = zur\u00fcck"
                       "  \u2502  Pfad: \u25cf Ende = ausrichten \u00b7 "
                       "\u25c7 Mitte = beugen"),
    "gi_legend_liquify": ("\u00fcber einen Buchstaben ziehen schiebt ihn "
                          "herum \u00b7 Alt kehrt das Werkzeug um \u00b7 "
                          "Gr\u00f6\u00dfe, St\u00e4rke und H\u00e4rte "
                          "stehen unter Verfl\u00fcssigen"),
    "gi_legend_points": ("Punkt oder Anfasser ziehen \u00b7 Umschalt+Klick "
                         "sammelt mehrere, oder ein Rechteck darum ziehen "
                         "\u00b7 der Gizmo verschiebt, dreht und skaliert "
                         "das Gesammelte \u00b7 Doppelklick auf die Kontur "
                         "= neuer Punkt, auf einen Punkt = Ecke \u21c4 "
                         "Kurve \u00b7 Alt+Klick l\u00f6scht"),
    "gi_legend_erase": ("ziehen wischt Teile eines Buchstabens weg \u00b7 "
                        "alles andere bleibt, und ein Undo nimmt den "
                        "ganzen Strich zur\u00fcck"),
    "gi_erased": "Weggewischt. Undo holt es zur\u00fcck.",
    "gi_frozen_font": ("{n} Buchstabe(n) haben eine eigene Kontur und "
                       "behalten sie \u2014 \u201eAlle Punkte "
                       "zur\u00fccksetzen\u201c unter der Leinwand gibt "
                       "sie der Schrift zur\u00fcck."),
    "gi_act_del": "Punkt l\u00f6schen",
    "gi_act_smooth": "Ecke \u21c4 Kurve",
    "gi_act_reset_letter": "Diesen Buchstaben zur\u00fccksetzen",
    "gi_act_reset_pts": "Alle Punkte zur\u00fccksetzen",
    "gi_act_reset_warp": "Alles Verformen zur\u00fccknehmen",
    "gi_act_reset_moves": "Buchstaben-\u00c4nderungen zur\u00fccksetzen",
    "gi_act_count": "Buchstaben mit bearbeiteten Punkten: {n}",
    "gi_sec_points": "Punkte",
    "gi_pts_on": "Punkte bearbeiten (in der Vorschau ziehen)",
    "gi_pts_on_tip": ("Die Kontur selbst anfassen. Buchstabe anklicken "
                      "\u00f6ffnet ihn; Punkte und Anfasser ziehen; ein "
                      "Klick auf die Kontur zwischen zwei Punkten setzt "
                      "einen neuen; Alt+Klick l\u00f6scht einen Punkt, "
                      "Umschalt+Klick macht aus einer Ecke eine Kurve und "
                      "zur\u00fcck."),
    "gi_pts_opened": "{n} Punkte auf diesem Buchstaben.",
    "gi_pts_reset": "Zur\u00fcck zur Kontur der Schrift",
    "gi_pts_reset_done": ("Jeder Buchstabe hat wieder die Kontur, die die "
                          "Schrift gezeichnet hat."),
    "gi_sec_liquify": "Verfl\u00fcssigen",
    "gi_liq_on": "Pinsel an (in der Vorschau ziehen)",
    "gi_liq_on_tip": ("Solange das an ist, schiebt Ziehen in der Vorschau "
                      "den Buchstaben herum, statt ihn zu versetzen. Alt "
                      "halten kehrt das Werkzeug um."),
    "gi_liq_tool": "Werkzeug:",
    "gi_liq_push": "Schieben",
    "gi_liq_inflate": "Aufblasen",
    "gi_liq_pinch": "Zusammenziehen",
    "gi_liq_twirl": "Drehen",
    "gi_liq_size": "Pinselgr\u00f6\u00dfe",
    "gi_liq_force": "St\u00e4rke",
    "gi_liq_hard": "H\u00e4rte",
    "gi_liq_reset": "Alles Verformen zur\u00fccknehmen",
    "gi_liq_reset_done": ("Jeder Buchstabe hat wieder die Form, die die "
                          "Schrift gezeichnet hat."),
    "gi_sec_deco": "Deko",
    "gi_deco": "Drumherum:",
    "gi_deco_off": "Nichts",
    "gi_deco_rays": "Aufprallstrahlen",
    "gi_deco_debris": "Tr\u00fcmmer",
    "gi_deco_sparkle": "Funkeln",
    "gi_deco_drops": "Tropfen",
    "gi_deco_n": "Wie viele",
    "gi_deco_size": "Ihre Gr\u00f6\u00dfe",
    "gi_deco_dist": "Wie weit drau\u00dfen",
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
    "gi_fill_tone_grad": "Rasterverlauf",
    "gi_fill2": "bis",
    "gi_caption": "Beischrift:",
    "gi_caption_ph": "z.\u202fB. BOOM",
    "gi_caption_tip": ("Eine kleine Lesung oder \u00dcbersetzung neben dem "
                       "Effekt. Schlicht gesetzt: keine der Verformungen "
                       "fasst sie an."),
    "gi_caption_pos": "Wo:",
    "gi_caption_below": "Unten",
    "gi_caption_above": "Oben",
    "gi_caption_right": "Rechts",
    "gi_caption_left": "Links",
    "gi_caption_size": "Gr\u00f6\u00dfe der Beischrift",
    "gi_fill_negative": "Negativ",
    "gi_fill_line": "Nur Linie",
    "gi_fill_line_tone": "Linie im Raster",
    "gi_fill_line_w": "Linienbreite",
    "gi_neg_pad": "Fl\u00e4che drumherum",
    "gi_dict": "\U0001f4d6",
    "gi_dict_tip": ("Bekannte Lauteffekte zum Ausw\u00e4hlen (setzt auch "
                    "die Art)"),
    "gi_dict_title": "Lauteffekte",
    "gi_dict_search": "Suche: Kana, Lesung oder Bedeutung",
    "gi_dict_hint": "Doppelklick auf einen Laut \u00fcbernimmt ihn",
    "gi_dict_take": "\u00dcbernehmen",
    "gi_dict_took": "{s} \u2014 {m} \u00b7 Art \u201e{k}\u201c",
    "gi_dakuten": "\u309b",
    "gi_dakuten_tip": ("Setzt ein Dakuten \u309b auf den Buchstaben vor dem "
                       "Cursor \u2014 auf jeden, so wie ein Schrei gezeichnet "
                       "wird (\u30a2\u3099, \u30f3\u3099)."),
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
    "gi_noise_lines": "Rauschlinien",
    "gi_noise_style": "Gezeichnet mit:",
    "gi_noise_hand": "Hand",
    "gi_noise_dry": "Trockener Pinsel",
    "gi_noise_fuzzy": "Flaum",
    "gi_noise_amp": "Rauschbreite",
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
    "gi_save_zip": "Ebenen (ZIP)\u2026",
    "gi_save_zip_tip": ("Jede Ebene als eigenes PNG, alle auf derselben "
                        "Fl\u00e4che: Text, Konturen, Schatten, Nachbild, "
                        "Deko, Rauschen."),
    "gi_save_psd": "PSD\u2026",
    "gi_save_psd_tip": ("Dieselben Ebenen als Photoshop-Datei, von Krita "
                        "selbst geschrieben. Braucht ein laufendes Krita."),
    "gi_scale": "Gr\u00f6\u00dfe:",
    "gi_scale_tip": "Womit PNG und ZIP gerendert werden",
    "gi_saved_zip": "{n} Ebenen in {p} geschrieben",
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
    ("noise_lines", "gi_noise_lines", 0, 4, 1),
    ("noise_amp", "gi_noise_amp", 0, 150, 1),
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



class SoundDialog(QDialog):
    """Known sound effects, to pick from instead of typing them.

    Not modal: the preview behind it keeps working, and picking several
    sounds in a row is one window, not one window per sound.
    """

    def __init__(self, panel):
        super().__init__(panel.window())
        self._panel = panel
        self.setModal(False)
        self.setWindowTitle(panel._t("gi_dict_title"))
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(panel._t("gi_dict_search"))
        self.search.textChanged.connect(self._refill)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._take())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.hint = QLabel(panel._t("gi_dict_hint"))
        self.hint.setStyleSheet("color: gray;")
        row.addWidget(self.hint, 1)
        self.take_btn = QPushButton(panel._t("gi_dict_take"))
        self.take_btn.clicked.connect(self._take)
        row.addWidget(self.take_btn)
        self.close_btn = QPushButton(panel._t("gi_close"))
        self.close_btn.clicked.connect(self.close)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.resize(460, 520)
        self._refill()

    def _refill(self, *_a):
        lang = self._panel._lang_fn() or "en"
        self.list.clear()
        for e in GD.find(self.search.text(), lang):
            it = QListWidgetItem("%s   %s\n%s" % (e["kana"], e["romaji"],
                                                  GD.gloss(e, lang)))
            it.setData(Qt.ItemDataRole.UserRole, e)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _take(self):
        it = self.list.currentItem()
        if it is not None:
            self._panel.take_sound(it.data(Qt.ItemDataRole.UserRole))



class FontPickDialog(QDialog):
    """The installed fonts, each drawn in itself, with a search box.

    At most `SHOWN` rows at a time: with a few thousand families the
    list is of no use anyway until it has been narrowed down, and the
    count under it says how much is still hidden.
    """

    SHOWN = 400

    def __init__(self, panel):
        super().__init__(panel.window())
        self._panel = panel
        self.setModal(False)
        self.setWindowTitle(panel._t("gi_font_pick_title"))
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(panel._t("gi_font_pick_search"))
        self.search.textChanged.connect(self._refill)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._take())
        lay.addWidget(self.list, 1)
        self.count_lbl = QLabel()
        self.count_lbl.setStyleSheet("color: gray;")
        lay.addWidget(self.count_lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        self.take_btn = QPushButton(panel._t("gi_font_pick_use"))
        self.take_btn.clicked.connect(self._take)
        row.addWidget(self.take_btn)
        self.close_btn = QPushButton(panel._t("gi_close"))
        self.close_btn.clicked.connect(self.close)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.resize(460, 560)
        self._refill()

    def _sample(self):
        txt = " ".join(self._panel.text().split())[:8]
        return txt or "\u30c9\u30ab\u30fc\u30f3"

    def _refill(self, *_a):
        q = self.search.text().strip().lower()
        fams = [f for f in self._panel.families() if not q or q in f.lower()]
        self.list.clear()
        auto = QListWidgetItem(self._panel._t("gi_font_pick_auto"))
        auto.setData(Qt.ItemDataRole.UserRole, "")
        self.list.addItem(auto)
        sample = self._sample()
        for fam in fams[:self.SHOWN]:
            it = QListWidgetItem("%s    %s" % (fam, sample))
            it.setData(Qt.ItemDataRole.UserRole, fam)
            f = QFont(fam)
            f.setPointSize(13)
            it.setFont(f)
            self.list.addItem(it)
        left = len(fams) - self.SHOWN
        self.count_lbl.setText(
            self._panel._t("gi_font_pick_more", n=left) if left > 0
            else self._panel._t("gi_font_pick_count", n=len(fams)))
        cur = self._panel.params().get("font", "")
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == cur:
                self.list.setCurrentRow(i)
                break
        else:
            self.list.setCurrentRow(0)

    def _take(self):
        it = self.list.currentItem()
        if it is not None:
            self._panel.take_font(it.data(Qt.ItemDataRole.UserRole))


class GiongoWindow(QDialog):
    """A plain window holding the panel. Not modal: Krita stays usable.

    The panel sits in a scroll area. Without one the window inherits the
    panel's minimum height - over 1100 px with every section open - and
    a window that cannot be made shorter than the screen hangs off the
    bottom of it with no way to pull it back.
    """

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setModal(False)
        self.setSizeGripEnabled(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        # the scroll area holds a plain widget for its whole life and the
        # panel sits in that. Handing the panel back with
        # QScrollArea.takeWidget() while the window is closing crashed
        # Krita outright (ensureWidgetVisible on a widget that is being
        # reparented away, twice in the crash log).
        self.holder = QWidget()
        hold = QVBoxLayout(self.holder)
        hold.setContentsMargins(0, 0, 0, 0)
        hold.addWidget(panel)
        self.scroll.setWidget(self.holder)
        lay.addWidget(self.scroll)

    def release_panel(self):
        """Hand the panel out of the holder, still alive."""
        panel = self._panel
        if panel is not None and panel.parent() is self.holder:
            self.holder.layout().removeWidget(panel)
            panel.setParent(None)
        return panel

    def closeEvent(self, ev):           # noqa: N802 (Qt API)
        # hand the panel back before the window goes, or it would be
        # destroyed along with it
        self._panel.dock_back()
        super().closeEvent(ev)


class GiongoPreview(QLabel):
    """The preview, with the path and the letters as things you can drag.

    It knows nothing about parameters: it finds what is under the pointer,
    reports the drag to the panel in scene coordinates, and draws the
    handles. Everything the drag means is decided in `giongo.py`, where it
    can be tested without a mouse.
    """

    HANDLE = 7              # radius of a drawn handle, in screen px
    GRAB = 11               # how near the pointer has to be to take one

    def __init__(self, panel):
        super().__init__()
        self._panel = panel
        self._k = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._pix = (0, 0)      # where the pixmap sits inside the label
        self._places = []
        self._path = []
        self._sel = None        # (group, index) of the selected letter
        self._drag = None       # what is being dragged
        self._brush_r = 0.0     # liquify brush, in scene units
        self._points = False    # point editing: nodes instead of handles
        self._grabbed = None    # which node or handle is being dragged
        self._band = None       # the rectangle being drawn, in widget px
        self._cursor = None     # where it is, in widget pixels
        self.setMouseTracking(True)
        self._from = (0.0, 0.0)
        self._start = None      # the letter's edit when the drag began
        self.setMouseTracking(False)

    # -- what the panel hands over after every render --------------------
    def set_frame(self, k, ox, oy, pix_w, pix_h, places, path):
        self._k, self._ox, self._oy = k, ox, oy
        self._pix = (pix_w, pix_h)
        self._places = list(places or [])
        self._path = list(path or [])
        if self._sel is not None and not self._find(self._sel):
            self._sel = None    # the text changed under the selection
        self.update()

    def selected(self):
        return self._sel

    def clear_selection(self):
        self._sel = None
        self.update()

    def set_points(self, on):
        """Show the outline's own points instead of the letter handles."""
        self._points = bool(on)
        self.update()

    def select(self, key):
        self._sel = key
        self.update()

    def set_brush(self, radius):
        """The liquify brush to draw under the pointer; 0 hides it."""
        self._brush_r = float(radius or 0.0)
        self.update()

    def _find(self, key):
        for pl in self._places:
            if (pl["group"], pl["index"]) == key:
                return pl
        return None

    # -- coordinates ------------------------------------------------------
    def _to_widget(self, pt):
        px = (self.width() - self._pix[0]) / 2.0
        py = (self.height() - self._pix[1]) / 2.0
        return (px + self._ox + pt[0] * self._k,
                py + self._oy + pt[1] * self._k)

    def _to_scene(self, pos):
        if self._k <= 0:
            return None
        px = (self.width() - self._pix[0]) / 2.0
        py = (self.height() - self._pix[1]) / 2.0
        return ((pos.x() - px - self._ox) / self._k,
                (pos.y() - py - self._oy) / self._k)

    def _arrow(self, p, cx, cy, tx, ty):
        """A line with a head on the end, pointing from the middle out."""
        import math as _m
        p.drawLine(QPointF(cx, cy), QPointF(tx, ty))
        ang = _m.atan2(ty - cy, tx - cx)
        for side in (2.6, -2.6):
            p.drawLine(QPointF(tx, ty),
                       QPointF(tx + _m.cos(ang + side) * 8,
                               ty + _m.sin(ang + side) * 8))

    def _draw_gizmo(self, p, cx, cy, r):
        """What a drag on this letter will do, handle by handle."""
        ring = QColor(225, 120, 110)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(ring, 1.4))
        p.drawEllipse(QPointF(cx, cy), r + 12, r + 12)      # rotate
        p.setPen(QPen(QColor(215, 150, 40), 1.6))
        self._arrow(p, cx, cy, cx, cy - r * 0.78)           # up/down
        p.setPen(QPen(QColor(60, 150, 220), 1.6))
        self._arrow(p, cx, cy, cx + r * 0.78, cy)           # sideways
        p.setPen(QPen(QColor(70, 70, 70), 1.2))
        p.setBrush(QColor(255, 255, 255))
        h = self.HANDLE - 1
        p.drawRect(QRectF(cx - h, cy - h, 2 * h, 2 * h))    # free
        p.setPen(QPen(ring, 1.2))
        p.drawEllipse(QPointF(cx, cy - r - 14), self.HANDLE, self.HANDLE)
        p.setPen(QPen(QColor(70, 70, 70), 1.2))
        p.drawRect(QRectF(cx + r + 10 - self.HANDLE,
                          cy + r + 10 - self.HANDLE,
                          2 * self.HANDLE, 2 * self.HANDLE))

    def _point_gizmo(self):
        """((cx, cy), r) of the chosen points, in widget pixels, or None."""
        if not self._points:
            return None
        try:
            got = self._panel.point_gizmo()
        except Exception:               # noqa: BLE001
            return None
        if not got:
            return None
        (sx, sy), r = got
        pt = self._to_widget((sx, sy))
        rw = max(22.0, r * self._k)
        if not self._sane(pt, (rw, rw)):
            return None
        return pt, rw

    def _point_gizmo_handles(self):
        got = self._point_gizmo()
        if got is None:
            return []
        (cx, cy), r = got
        return [("protate", (cx, cy - r - 14)),
                ("pscale", (cx + r + 10, cy + r + 10)),
                ("pmovex", (cx + r * 0.78, cy)),
                ("pmovey", (cx, cy - r * 0.78)),
                ("pfree", (cx, cy))]

    def _point_gizmo_hit(self, pos):
        for name, pt in reversed(self._point_gizmo_handles()):
            if abs(pos.x() - pt[0]) <= self.GRAB \
                    and abs(pos.y() - pt[1]) <= self.GRAB:
                return name
        return None

    def _overlay_transform(self):
        """Scene units -> this widget, the same mapping `_to_widget` is."""
        px = (self.width() - self._pix[0]) / 2.0
        py = (self.height() - self._pix[1]) / 2.0
        tr = QTransform()
        tr.translate(px + self._ox, py + self._oy)
        tr.scale(self._k, self._k)
        return tr

    def _selection_shape(self):
        """The selected letter's outline, in widget coordinates."""
        if not self._sel or self._k <= 0:
            return None
        try:
            path = self._panel.selection_outline(self._sel)
        except Exception:               # noqa: BLE001
            return None
        if path is None or path.isEmpty():
            return None
        out = self._overlay_transform().map(path)
        r = out.boundingRect()
        if not self._sane((r.x(), r.y()), (r.width(), r.height())):
            return None
        return out

    def _handles(self):
        """Everything grabbable, as (name, widget point), nearest last."""
        out = []
        if len(self._path) >= 3:
            out.append(("bend", self._to_widget(self._path[1])))
            out.append(("end", self._to_widget(self._path[2])))
        pl = self._find(self._sel) if self._sel else None
        if pl is not None:
            r = max(10.0, pl["size"] * 0.5 * self._k)
            cx, cy = self._to_widget((pl["x"], pl["y"]))
            out.append(("rotate", (cx, cy - r - 14)))
            out.append(("scale", (cx + r + 10, cy + r + 10)))
            # what each drag will do, said with a handle for each
            out.append(("movex", (cx + r * 0.78, cy)))
            out.append(("movey", (cx, cy - r * 0.78)))
            out.append(("free", (cx, cy)))
        return out

    # -- mouse ------------------------------------------------------------
    @staticmethod
    def _alt(ev):
        return bool(ev.modifiers() & Qt.KeyboardModifier.AltModifier)

    def mousePressEvent(self, ev):                      # noqa: N802
        pos = ev.position() if hasattr(ev, "position") else ev.pos()
        if self._panel.liquify_armed():
            scene = self._to_scene(pos)
            if scene is None:
                return
            self._drag = "liquify"
            self._from = scene
            self._panel.liquify_step(scene, scene, self._alt(ev))
            return
        if self._panel.erase_armed():
            scene = self._to_scene(pos)
            if scene is None:
                return
            self._drag = "erase"
            self._from = scene
            self._panel.erase_step(scene, scene)
            return
        if self._points:
            scene = self._to_scene(pos)
            if scene is None:
                return
            name = self._point_gizmo_hit(pos)
            if name is not None:
                self._drag = "pgizmo"
                self._grabbed = name
                self._from = scene
                return
            grabbed = self._panel.point_press(
                scene, self.GRAB, self._k, self._alt(ev),
                bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            if grabbed and grabbed[0] == "band":
                self._drag = "band"
                self._band = ((pos.x(), pos.y()), (pos.x(), pos.y()))
                self._grabbed = None
            else:
                self._drag = "point" if grabbed else None
                self._grabbed = grabbed
            self.update()
            return
        for name, pt in reversed(self._handles()):
            if (abs(pos.x() - pt[0]) <= self.GRAB
                    and abs(pos.y() - pt[1]) <= self.GRAB):
                self._drag = name
                self._from = self._to_scene(pos) or (0.0, 0.0)
                self._start = self._panel.letter_edit_of(self._sel) \
                    if self._sel else None
                return
        scene = self._to_scene(pos)
        if scene is None:
            return
        pl = G.nearest_letter(self._places, scene)
        if pl is None:
            self._sel = None
            self.update()
            return
        self._sel = (pl["group"], pl["index"])
        self._drag = "move"
        self._from = scene
        self._start = self._panel.letter_edit_of(self._sel)
        self.update()

    def mouseMoveEvent(self, ev):                       # noqa: N802
        pos = ev.position() if hasattr(ev, "position") else ev.pos()
        if self._brush_r:
            self._cursor = (pos.x(), pos.y())
            self.update()
        if self._drag is None:
            return
        scene = self._to_scene(pos)
        if scene is None:
            return
        if self._drag == "liquify":
            self._panel.liquify_step(scene, self._from, self._alt(ev))
            self._from = scene
            return
        if self._drag == "point":
            self._panel.point_drag(self._grabbed, scene)
            self.update()
            return
        if self._drag == "pgizmo":
            self._panel.point_gizmo_drag(self._grabbed, scene, self._from)
            self._from = scene
            self.update()
            return
        if self._drag == "band":
            self._band = (self._band[0], (pos.x(), pos.y()))
            self.update()
            return
        if self._drag == "erase":
            self._panel.erase_step(scene, self._from)
            self._from = scene
            return
        self._panel.preview_drag(self._drag, scene, self._from, self._sel,
                                 self._start)

    def mouseReleaseEvent(self, ev):                    # noqa: N802
        if self._drag == "band" and self._band is not None:
            (x0, y0), (x1, y1) = self._band
            a = self._to_scene(QPointF(x0, y0))
            b = self._to_scene(QPointF(x1, y1))
            self._band = None
            if a is not None and b is not None \
                    and (abs(x1 - x0) > 3 or abs(y1 - y0) > 3):
                self._panel.point_band(
                    a[0], a[1], b[0], b[1],
                    bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            self.update()
        if self._drag is not None:
            self._drag = None
            self._panel.preview_drag_done()

    def mouseDoubleClickEvent(self, ev):                # noqa: N802
        pos = ev.position() if hasattr(ev, "position") else ev.pos()
        scene = self._to_scene(pos)
        if scene is None:
            return
        if self._points:
            self._panel.point_double(scene, self.GRAB, self._k)
            self.update()
            return
        pl = G.nearest_letter(self._places, scene)
        if pl is not None:
            self._panel.reset_letter((pl["group"], pl["index"]))

    # -- drawing ----------------------------------------------------------
    @staticmethod
    def _sane(*points):
        """True when every point is a number Qt can be asked to draw at."""
        for pt in points:
            for v in pt:
                if v != v or v in (float("inf"), float("-inf")):
                    return False
                if abs(v) > 1e6:
                    return False
        return True

    def _draw_points(self, p):
        """The outline's points: squares for corners, circles for curves."""
        try:
            items = self._panel.point_overlay()
        except Exception:               # noqa: BLE001
            return
        for it in items:
            pt = self._to_widget(it["p"])
            if not self._sane(pt):
                continue
            for which in ("in", "out"):
                h = it.get(which)
                if h is None:
                    continue
                hp = self._to_widget(h)
                if not self._sane(hp):
                    continue
                p.setPen(QPen(QColor(70, 140, 220, 160), 1))
                p.drawLine(QPointF(*pt), QPointF(*hp))
                p.setBrush(QColor(255, 255, 255))
                p.drawEllipse(QPointF(*hp), 3.0, 3.0)
            chosen = it.get("chosen")
            p.setPen(QPen(QColor(0, 150, 200) if chosen
                          else QColor(200, 60, 140), 1.4 if chosen else 1))
            if chosen:
                p.setBrush(QColor(0, 180, 220))
            else:
                p.setBrush(QColor(255, 255, 255) if it["smooth"]
                           else QColor(255, 220, 120))
            if it["smooth"]:
                p.drawEllipse(QPointF(*pt), 4.5 if chosen else 4.0,
                              4.5 if chosen else 4.0)
            else:
                h = 4.5 if chosen else 3.5
                p.drawRect(QRectF(pt[0] - h, pt[1] - h, 2 * h, 2 * h))

    def _draw_brush(self, p):
        """The liquify brush: a ring the size it really works at."""
        if not (self._brush_r and self._cursor):
            return
        r = self._brush_r * self._k
        if not (r > 0.5 and r < 1e5):
            return
        x, y = self._cursor
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(40, 170, 120), 1))
        p.drawEllipse(QPointF(x, y), r, r)
        p.setPen(QPen(QColor(40, 170, 120, 90), 1, Qt.PenStyle.DotLine))
        p.drawEllipse(QPointF(x, y), r * 0.35, r * 0.35)

    def paintEvent(self, ev):                           # noqa: N802
        super().paintEvent(ev)
        if self.width() <= 0 or self.height() <= 0:
            return
        if self._brush_r or self._points:
            # the brush or the points are doing the dragging now: the
            # letter handles and the selection box would only be in the way
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._draw_brush(p)
            if self._points:
                self._draw_points(p)
                got = self._point_gizmo()
                if got is not None:
                    (gx, gy), gr = got
                    self._draw_gizmo(p, gx, gy, gr)
                if self._band is not None:
                    (x0, y0), (x1, y1) = self._band
                    p.setBrush(QColor(0, 180, 220, 30))
                    p.setPen(QPen(QColor(0, 150, 200), 1,
                                  Qt.PenStyle.DashLine))
                    p.drawRect(QRectF(min(x0, x1), min(y0, y1),
                                      abs(x1 - x0), abs(y1 - y0)))
            return
        if not self._path and not self._places:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if len(self._path) >= 3:
            a = self._to_widget(self._path[0])
            m = self._to_widget(self._path[1])
            b = self._to_widget(self._path[2])
        else:
            a = m = b = None
        if a is not None and self._sane(a, m, b):
            pen = QPen(QColor(70, 140, 220, 150))
            pen.setWidth(1)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            path = QPainterPath(QPointF(*a))
            # the drawn curve is the quadratic the layout uses, so the line
            # under the pointer is the line the letters sit on
            path.quadTo(QPointF(2 * m[0] - (a[0] + b[0]) / 2.0,
                                2 * m[1] - (a[1] + b[1]) / 2.0),
                        QPointF(*b))
            p.drawPath(path)
            p.setPen(QPen(QColor(70, 140, 220)))
            p.setBrush(QColor(255, 255, 255))
            for pt in (m, b):
                p.drawEllipse(QPointF(*pt), self.HANDLE, self.HANDLE)
        pl = self._find(self._sel) if self._sel else None
        if pl is not None:
            r = max(10.0, min(1e5, pl["size"] * 0.5 * self._k))
            cx, cy = self._to_widget((pl["x"], pl["y"]))
        if pl is not None and self._sane((cx, cy), (r, r)):
            shape = self._selection_shape()
            if shape is not None:
                # the letter itself is the selection, filled and outlined
                p.setBrush(QColor(0, 180, 220, 48))
                p.setPen(QPen(QColor(0, 170, 215), 1.6))
                p.drawPath(shape)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(0, 170, 215), 1, Qt.PenStyle.DashLine))
                p.drawRect(QRectF(cx - r, cy - r, 2 * r, 2 * r))
            self._draw_gizmo(p, cx, cy, r)
        p.end()


#: which row of the fill section each control sits in. They used to be
#: written out at the call sites and three of them collided.
_R_FILL = 0
_R_TONE = 1
_R_PATTERN = 2
_R_PATSCALE = 3
_R_NEG = 4
_R_LINEW = 5
_R_THICKEN = 6
_R_OUTLINES = 7


#: the tool in hand, said loudly enough to see at a glance. A checked
#: QPushButton is nearly invisible in a dark theme.
_TOOL_ON = ("QPushButton { border: 2px solid #1e90ff; "
            "background: rgba(30, 144, 255, 60); font-weight: bold; }")
_TOOL_OFF = "QPushButton { font-weight: normal; }"


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
        self._dict_win = None       # the sound dictionary
        self._pt_sel = []           # which points are chosen
        self._font_win = None       # the font list
        self._future = []           # undone steps, waiting to be redone
        self._hist_key = None       # which slider the last step was, and
        self._hist_at = 0.0         # when, so one drag is one step
        self._drag_open = False     # a drag in the preview is one step
        self._blocks = []           # the groups the grid arranges
        self._canvas_block = None   # the one with the canvas in it
        self._cols = 0              # how many columns they sit in now
        self._home = None           # the layout to go back to
        self._window = None
        self._pending = True        # owes a preview as soon as it is shown
        self._places = []           # where the letters landed, for the mouse
        self._last_size = (0, 0)    # what the last preview was rendered for
        self._fonts_filled = False  # the family list is filled on first show
        UF.load_all(UF.from_json(self._get("giongoUserFonts", "[]")))
        try:
            _sets = json.loads(self._get("giongoLetterSets", "[]"))
        except ValueError:
            _sets = []
        for _p in _sets if isinstance(_sets, list) else []:
            _d = TR.load_set(_p) if isinstance(_p, str) else None
            if _d:
                TR.register(_d, _p)
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
        #: a drag draws while it is happening, see `_schedule_live`
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(30)
        self._live_timer.timeout.connect(self._refresh_preview)
        self._last_live = 0.0
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._save_state)
        self._build()
        self.retranslate()
        self._keys = []
        for seq, slot in (("Ctrl+Z", self.on_undo_key),
                          ("Ctrl+Y", self.on_redo_key),
                          ("Ctrl+Shift+Z", self.on_redo_key)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
            self._keys.append(sc)
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
        if not self._blocks:
            # the first block holds the canvas: it takes what it is given
            box.setSizePolicy(QSizePolicy.Policy.Preferred,
                              QSizePolicy.Policy.Expanding)
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
        self.window_hint = QLabel()
        self.window_hint.setWordWrap(True)
        self.window_hint.setStyleSheet("color: #806000;")
        row.addWidget(self.window_hint, 1)
        self.popout_btn = QPushButton()
        self.popout_btn.clicked.connect(self.on_popout)
        row.addWidget(self.popout_btn)
        lay.addLayout(row)
        self.tab_only = QLabel()
        self.tab_only.setWordWrap(True)
        self.tab_only.setStyleSheet("color: gray;")
        lay.addWidget(self.tab_only)
        # everything below is the work itself, and the work happens in the
        # window: in the tab only this first group is shown
        lay = self._new_block()

        self.text_edit = QPlainTextEdit()
        self.text_edit.setFixedHeight(58)
        self.text_edit.setPlainText(self._get("giongoText", "ドーーン！"))
        self.text_edit.textChanged.connect(self._on_text)
        trow = QHBoxLayout()
        trow.addWidget(self.text_edit, 1)
        self.dict_btn = QPushButton()
        self.dict_btn.setFixedWidth(34)
        self.dict_btn.clicked.connect(self.on_dictionary)
        trow.addWidget(self.dict_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.dakuten_btn = QPushButton()
        self.dakuten_btn.setFixedWidth(34)
        self.dakuten_btn.clicked.connect(self.on_dakuten)
        trow.addWidget(self.dakuten_btn, 0,
                       Qt.AlignmentFlag.AlignTop)
        lay.addLayout(trow)

        crow = QHBoxLayout()
        self.caption_lbl = QLabel()
        crow.addWidget(self.caption_lbl)
        self.caption_edit = QLineEdit()
        self.caption_edit.textChanged.connect(
            lambda s: self._set_param("caption", s))
        crow.addWidget(self.caption_edit, 1)
        self.caption_pos = NoScrollComboBox()
        for where in G.R_CAPTION_POS:
            self.caption_pos.addItem("", where)
        self.caption_pos.currentIndexChanged.connect(
            lambda _i: self._set_param("caption_pos",
                                       self.caption_pos.currentData()))
        crow.addWidget(self.caption_pos)
        lay.addLayout(crow)
        cgrid = QGridLayout()
        self._add_slider(cgrid, 0, "caption_size", "gi_caption_size",
                         8, 120, 1)
        lay.addLayout(cgrid)

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
        self.font_pick_btn = QPushButton()
        self.font_pick_btn.setFixedWidth(26)
        self.font_pick_btn.clicked.connect(self.on_pick_font)
        row.addWidget(self.font_pick_btn)
        self.font_load_btn = QPushButton()
        self.font_load_btn.setFixedWidth(26)
        self.font_load_btn.clicked.connect(self.on_load_font)
        row.addWidget(self.font_load_btn)
        self.bold_chk = QCheckBox()
        self.bold_chk.toggled.connect(lambda on: self._set_param("bold", on))
        row.addWidget(self.bold_chk)
        lay.addLayout(row)
        srow = QHBoxLayout()
        self.set_lbl = QLabel()
        srow.addWidget(self.set_lbl)
        self.set_combo = NoScrollComboBox()
        self.set_combo.addItem("", "")
        self.set_combo.currentIndexChanged.connect(
            lambda _i: self._set_param("letterset",
                                       self.set_combo.currentData() or ""))
        srow.addWidget(self.set_combo, 1)
        self.set_import_btn = QPushButton()
        self.set_import_btn.clicked.connect(self.on_import_lettering)
        srow.addWidget(self.set_import_btn)
        lay.addLayout(srow)
        self.font_hint = QLabel()
        self.font_hint.setWordWrap(True)
        self.font_hint.setStyleSheet("color: gray; font-size: 10px;")
        lay.addWidget(self.font_hint)

        tbar = QHBoxLayout()
        self.tool_btns = {}
        for _key in ("move", "liquify", "points", "erase"):
            _b = QPushButton()
            _b.setCheckable(True)
            _b.clicked.connect(lambda _c=False, k=_key: self.set_tool(k))
            tbar.addWidget(_b)
            self.tool_btns[_key] = _b
        self.tool_btns["move"].setChecked(True)
        tbar.addStretch(1)
        self.bg_lbl = QLabel()
        tbar.addWidget(self.bg_lbl)
        self.bg_combo = NoScrollComboBox()
        for val, _k in _BACKGROUNDS:
            self.bg_combo.addItem("", val)
        bg = self._get("giongoBg", "check")
        self.bg_combo.setCurrentIndex(max(0, self.bg_combo.findData(bg)))
        self.bg_combo.currentIndexChanged.connect(self._on_bg)
        tbar.addWidget(self.bg_combo)
        self.back_btn = QPushButton()
        self.back_btn.clicked.connect(self.on_back)
        self.back_btn.setEnabled(False)
        tbar.addWidget(self.back_btn)
        self.fwd_btn = QPushButton()
        self.fwd_btn.clicked.connect(self.on_forward)
        self.fwd_btn.setEnabled(False)
        tbar.addWidget(self.fwd_btn)
        self.size_lbl = QLabel()
        self.size_lbl.setStyleSheet("color: gray;")
        tbar.addWidget(self.size_lbl)
        lay.addLayout(tbar)

        self._canvas_block = self._blocks[-1]
        self.preview = GiongoPreview(self)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(200)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored,
                                   QSizePolicy.Policy.Expanding)
        self.preview.setStyleSheet("border: 1px solid #888;")
        lay.addWidget(self.preview, 1)

        self.legend_lbl = QLabel()
        self.legend_lbl.setWordWrap(True)
        self.legend_lbl.setStyleSheet("color: gray; font-size: 10px;")
        lay.addWidget(self.legend_lbl)

        arow = QHBoxLayout()
        self.act_btns = {}
        for _key, _slot in (("del", self.points_delete_chosen),
                            ("smooth", self.points_smooth_chosen),
                            ("reset_letter", self.reset_points_letter),
                            ("reset_pts", self.on_reset_points),
                            ("reset_warp", self.on_reset_warps),
                            ("reset_moves", self.reset_letters)):
            _b = QPushButton()
            _b.clicked.connect(lambda _c=False, s=_slot: s())
            arow.addWidget(_b)
            self.act_btns[_key] = _b
        self.act_count = QLabel()
        self.act_count.setStyleSheet("color: gray;")
        arow.addWidget(self.act_count)
        arow.addStretch(1)
        lay.addLayout(arow)

        # the gacha and the macros are their own group: the canvas column
        # is as tall as the window, and anything put after the canvas can
        # only be reached by scrolling past it
        lay = self._new_block()

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
        self._add_slider(g, _R_TONE, "tone_dot", "gi_tone_dot",
                         3, 60, 1)
        prow = QHBoxLayout()
        self.pattern_btn = QPushButton()
        self.pattern_btn.clicked.connect(self.on_pick_pattern)
        prow.addWidget(self.pattern_btn)
        self.pattern_lbl = QLabel()
        self.pattern_lbl.setStyleSheet("color: gray;")
        prow.addWidget(self.pattern_lbl, 1)
        g.addLayout(prow, _R_PATTERN, 0, 1, 3)
        self._add_slider(g, _R_NEG, "neg_pad", "gi_neg_pad", 0, 120, 1)
        self._add_slider(g, _R_LINEW, "fill_line_w", "gi_fill_line_w",
                         1, 40, 1)
        self._add_slider(g, _R_PATSCALE, "fill_pattern_scale",
                         "gi_pattern_scale", 10, 400, 1)

        self._add_slider(g, _R_THICKEN, "thicken", "gi_thicken",
                         0, 12, 4)
        self._outline_rows = []
        for i in range(G.MAX_OUTLINES):
            chk = QCheckBox()
            chk.toggled.connect(self._on_outlines)
            g.addWidget(chk, _R_OUTLINES + i, 0)
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
            g.addLayout(orow, _R_OUTLINES + i, 1, 1, 2)
            self._outline_rows.append((chk, btn, spin))
        r = _R_OUTLINES + G.MAX_OUTLINES
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
        self.noise_style_lbl = QLabel()
        g.addWidget(self.noise_style_lbl, len(_SHADOW_SLIDERS), 0)
        self.noise_style = NoScrollComboBox()
        for st in G.NOISE_STYLES:
            self.noise_style.addItem("", st)
        self.noise_style.currentIndexChanged.connect(
            lambda _i: self._set_param("noise_style",
                                       self.noise_style.currentData()))
        g.addWidget(self.noise_style, len(_SHADOW_SLIDERS), 1, 1, 2)
        self.shadow_lbl = QLabel()
        g.addWidget(self.shadow_lbl, len(_SHADOW_SLIDERS) + 1, 0)
        self.shadow_btn = self._color_button(
            lambda b: self._pick_color(
                b, lambda c: self._set_param("shadow_color", c)))
        g.addWidget(self.shadow_btn, len(_SHADOW_SLIDERS) + 1, 1)
        lay = self._new_block()
        lay.addWidget(self.sec_shadow)

        self.sec_liquify = _Section("liquify",
                                    self._open.get("liquify", False),
                                    self._on_section)
        g = self.sec_liquify.grid
        self.liq_chk = QCheckBox()
        self.liq_chk.toggled.connect(self._on_liquify_armed)
        g.addWidget(self.liq_chk, 0, 0, 1, 3)
        self.liq_tool_lbl = QLabel()
        g.addWidget(self.liq_tool_lbl, 1, 0)
        self.liq_tool = NoScrollComboBox()
        for m in W.MODES:
            self.liq_tool.addItem("", m)
        self.liq_tool.currentIndexChanged.connect(
            lambda _i: self._set_param("liquify_mode",
                                       self.liq_tool.currentData()))
        g.addWidget(self.liq_tool, 1, 1, 1, 2)
        self._add_slider(g, 2, "liquify_size", "gi_liq_size", 5, 200, 1)
        self._add_slider(g, 3, "liquify_force", "gi_liq_force", 1, 100, 1)
        self._add_slider(g, 4, "liquify_hard", "gi_liq_hard", 0, 95, 1)
        self.liq_reset_btn = QPushButton()
        self.liq_reset_btn.clicked.connect(self.on_reset_warps)
        g.addWidget(self.liq_reset_btn, 5, 0, 1, 3)
        lay = self._new_block()
        lay.addWidget(self.sec_liquify)

        self.sec_points = _Section("points",
                                   self._open.get("points", False),
                                   self._on_section)
        g = self.sec_points.grid
        self.pts_chk = QCheckBox()
        self.pts_chk.toggled.connect(self._on_points_armed)
        g.addWidget(self.pts_chk, 0, 0, 1, 3)
        self.pts_hint = QLabel()
        self.pts_hint.setWordWrap(True)
        self.pts_hint.setStyleSheet("color: gray;")
        g.addWidget(self.pts_hint, 1, 0, 1, 3)
        self.pts_reset_btn = QPushButton()
        self.pts_reset_btn.clicked.connect(self.on_reset_points)
        g.addWidget(self.pts_reset_btn, 2, 0, 1, 3)
        lay = self._new_block()
        lay.addWidget(self.sec_points)

        self.sec_deco = _Section("deco", self._open.get("deco", False),
                                 self._on_section)
        g = self.sec_deco.grid
        self.deco_lbl = QLabel()
        g.addWidget(self.deco_lbl, 0, 0)
        self.deco_combo = NoScrollComboBox()
        for d in G.DECOS:
            self.deco_combo.addItem("", d)
        self.deco_combo.currentIndexChanged.connect(
            lambda _i: self._set_param("deco", self.deco_combo.currentData()))
        g.addWidget(self.deco_combo, 0, 1, 1, 2)
        self._add_slider(g, 1, "deco_n", "gi_deco_n", 0, 60, 1)
        self._add_slider(g, 2, "deco_size", "gi_deco_size", 1, 100, 1)
        self._add_slider(g, 3, "deco_dist", "gi_deco_dist", 0, 150, 1)
        lay = self._new_block()
        lay.addWidget(self.sec_deco)

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
        self.save_zip_btn = QPushButton()
        self.save_zip_btn.clicked.connect(lambda *_a: self.on_save("zip"))
        row.addWidget(self.save_zip_btn)
        self.save_psd_btn = QPushButton()
        self.save_psd_btn.clicked.connect(lambda *_a: self.on_save("psd"))
        row.addWidget(self.save_psd_btn)
        self.scale_lbl = QLabel()
        row.addWidget(self.scale_lbl)
        self.scale_combo = NoScrollComboBox()
        for _k in (1, 2, 3, 4):
            self.scale_combo.addItem("%d\u00d7" % _k, _k)
        try:
            _sk = int(self._get("giongoScale", "1"))
        except ValueError:
            _sk = 1
        self.scale_combo.setCurrentIndex(
            max(0, self.scale_combo.findData(_sk)))
        self.scale_combo.currentIndexChanged.connect(
            lambda _i: self._set("giongoScale",
                                 str(self.scale_combo.currentData() or 1)))
        row.addWidget(self.scale_combo)
        lay.addLayout(row)
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
        self.fwd_btn.setText(t("gi_forward"))
        self.fwd_btn.setToolTip(t("gi_forward_tip"))
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
                         (self.sec_shadow, "gi_sec_shadow"),
                         (self.sec_deco, "gi_sec_deco"),
                         (self.sec_liquify, "gi_sec_liquify"),
                         (self.sec_points, "gi_sec_points")):
            sec.btn.setText(t(key).replace("&", "&&"))
        self.deco_lbl.setText(t("gi_deco"))
        for _k, _b in self.act_btns.items():
            _b.setText(t("gi_act_" + _k))
        for _k, _b in self.tool_btns.items():
            _b.setText(t("gi_tool_" + _k))
        self.tool_btns["move"].setToolTip(t("gi_tool_move_tip"))
        self.tool_btns["liquify"].setToolTip(t("gi_liq_on_tip"))
        self.tool_btns["points"].setToolTip(t("gi_pts_on_tip"))
        self.tool_btns["erase"].setToolTip(t("gi_tool_erase_tip"))
        self._refresh_legend()
        self._refresh_action_bar()
        self.pts_chk.setText(t("gi_pts_on"))
        self.pts_chk.setToolTip(t("gi_pts_on_tip"))
        self.pts_hint.setText(t("gi_pts_on_tip"))
        self.pts_reset_btn.setText(t("gi_pts_reset"))
        self.liq_chk.setText(t("gi_liq_on"))
        self.liq_chk.setToolTip(t("gi_liq_on_tip"))
        self.liq_tool_lbl.setText(t("gi_liq_tool"))
        self.liq_reset_btn.setText(t("gi_liq_reset"))
        for i, m in enumerate(W.MODES):
            self.liq_tool.setItemText(i, t("gi_liq_" + m))
        self.noise_style_lbl.setText(t("gi_noise_style"))
        for i, st in enumerate(G.NOISE_STYLES):
            self.noise_style.setItemText(i, t("gi_noise_" + st))
        for i, d in enumerate(G.DECOS):
            self.deco_combo.setItemText(i, t("gi_deco_" + d))
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
        self.save_zip_btn.setText(t("gi_save_zip"))
        self.save_zip_btn.setToolTip(t("gi_save_zip_tip"))
        self.save_psd_btn.setText(t("gi_save_psd"))
        self.save_psd_btn.setToolTip(t("gi_save_psd_tip"))
        self.scale_lbl.setText(t("gi_scale"))
        self.scale_combo.setToolTip(t("gi_scale_tip"))
        self.pattern_btn.setText(t("gi_pattern_pick"))
        self.pattern_btn.setToolTip(t("gi_pattern_tip"))
        self._refresh_pattern_name()
        self.pen_lbl.setText(t("gi_pen"))
        self.pen_combo.setToolTip(t("gi_pen_tip"))
        for i, name in enumerate(G.PENS):
            self.pen_combo.setItemText(i, t("gi_pen_" + name))
        self._refresh_pen_hint()
        self.reset_btn.setText(t("gi_reset"))
        self.dict_btn.setText(t("gi_dict"))
        self.dict_btn.setToolTip(t("gi_dict_tip"))
        self.dakuten_btn.setText(t("gi_dakuten"))
        self.caption_lbl.setText(t("gi_caption"))
        self.caption_edit.setPlaceholderText(t("gi_caption_ph"))
        self.caption_edit.setToolTip(t("gi_caption_tip"))
        for i, where in enumerate(G.R_CAPTION_POS):
            self.caption_pos.setItemText(i, t("gi_caption_" + where))
        self.dakuten_btn.setToolTip(t("gi_dakuten_tip"))
        self.popout_btn.setText(t("gi_popin") if self._popped
                                else t("gi_popout"))
        self.window_hint.setText("" if self._popped
                                 else t("gi_window_hint"))
        self.tab_only.setText(t("gi_tab_only"))
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
            self.caption_edit.setText(p.get("caption", ""))
            self.caption_pos.setCurrentIndex(
                max(0, self.caption_pos.findData(
                    p.get("caption_pos", "below"))))
            self.fill_mode.setCurrentIndex(
                max(0, self.fill_mode.findData(p["fill_mode"])))
            self.deco_combo.setCurrentIndex(
                max(0, self.deco_combo.findData(p.get("deco", "off"))))
            self.liq_tool.setCurrentIndex(
                max(0, self.liq_tool.findData(
                    p.get("liquify_mode", "push"))))
            self.noise_style.setCurrentIndex(
                max(0, self.noise_style.findData(
                    p.get("noise_style", "hand"))))
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
            self._refresh_sets()
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
                w.setEnabled(p["fill_mode"] in ("tone", "tone_grad",
                                                "line_tone"))
        for key in ("deco_n", "deco_size", "deco_dist"):
            sl = self._sliders.get(key)
            if sl:
                for w in sl[:3]:
                    w.setEnabled(p.get("deco", "off") != "off")
        on = int(p.get("noise_lines", 0)) > 0
        self.noise_style.setEnabled(on)
        self.noise_style_lbl.setEnabled(on)
        sl = self._sliders.get("noise_amp")
        if sl:
            for w in sl[:3]:
                w.setEnabled(on)
        sl = self._sliders.get("fill_line_w")
        if sl:
            for w in sl[:3]:
                w.setEnabled(p["fill_mode"] in ("line", "line_tone"))
        sl = self._sliders.get("fill_pattern_scale")
        if sl:
            for w in sl[:3]:
                w.setEnabled(p["fill_mode"] == "pattern")
        sl = self._sliders.get("neg_pad")
        if sl:
            for w in sl[:3]:
                w.setEnabled(p["fill_mode"] == "negative")
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
        self.set_lbl.setText(self._t("gi_set"))
        self.set_combo.setToolTip(self._t("gi_set_tip"))
        self.set_import_btn.setText(self._t("gi_set_import"))
        self.set_import_btn.setToolTip(self._t("gi_set_import_tip"))
        self.font_pick_btn.setText(self._t("gi_font_pick"))
        self.font_pick_btn.setToolTip(self._t("gi_font_pick_tip"))
        self.font_load_btn.setText(self._t("gi_font_load"))
        self.font_load_btn.setToolTip(self._t("gi_font_load_tip"))
        self.font_hint.setVisible(missing)
        if missing:
            self.font_hint.setText(self._t("gi_font_missing",
                                           f=", ".join(t["fonts"])))

    def _set_param(self, key, value):
        if self._loading:
            return
        if self._params.get(key) != value:
            self._push_history(key)
        self._params[key] = value
        if key in ("fill", "fill2", "shadow_color"):
            btn = {"fill": self.fill_btn, "fill2": self.fill2_btn,
                   "shadow_color": self.shadow_btn}[key]
            self._paint_swatch(btn, value)
        if key in ("fill_mode", "deco", "noise_lines"):
            self._refresh_enabled()
        if key == "seed":
            self.seed_spin.blockSignals(True)
            self.seed_spin.setValue(int(value))
            self.seed_spin.blockSignals(False)
        self._schedule()

    def _on_slider(self, key, v, steps):
        if key == "liquify_size" and self.liquify_armed():
            self.preview.set_brush(W.radius_for(v / float(steps)))
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

    def on_dictionary(self, *_a):
        """The list of known sounds, to pick from."""
        if self._dict_win is None:
            self._dict_win = SoundDialog(self)
        self._dict_win.show()
        self._dict_win.raise_()
        self._dict_win.search.setFocus()

    def take_sound(self, entry):
        """A sound picked from the dictionary: its kana at the cursor, and
        the look that belongs to it."""
        if not entry:
            return
        self._push_history()
        cur = self.text_edit.textCursor()
        cur.insertText(entry["kana"])
        self.text_edit.setTextCursor(cur)
        tid = entry.get("type")
        if tid and tid != self._params.get("type"):
            self._params = G.apply_type(self._params, tid)
            self._params["font"] = ""
            self._load_into_widgets()
        self._schedule()
        self._status(self._tr_sound(entry))

    def _tr_sound(self, entry):
        lang = self._lang_fn() or "en"
        return self._t("gi_dict_took", s=entry["kana"],
                       k=self._t("gi_type_" + entry["type"]),
                       m=GD.gloss(entry, lang))

    def on_dakuten(self, *_a):
        """Put a ゛ on the letter before the cursor.

        The combining mark, not the standalone one: `tokenize` hangs it on
        the letter in front of it, so ア゛ is drawn and laid out as one
        letter instead of two.
        """
        cur = self.text_edit.textCursor()
        if cur.position() <= 0:
            return
        cur.insertText("\u3099")
        self.text_edit.setTextCursor(cur)

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

    def _refresh_sets(self):
        """The lettering sets that are loaded, in the combo."""
        self.set_combo.blockSignals(True)
        want = self._params.get("letterset", "")
        self.set_combo.clear()
        self.set_combo.addItem(self._t("gi_set_none"), "")
        for name in TR.names():
            self.set_combo.addItem("%s (%d)" % (name, len(TR.letters(name))),
                                   name)
        self.set_combo.setCurrentIndex(max(0, self.set_combo.findData(want)))
        self.set_combo.blockSignals(False)

    def load_lettering(self, paths):
        """Load saved sets from disk and make them available."""
        names = []
        for p in paths or []:
            data = TR.load_set(p)
            if data:
                got = TR.register(data, p)
                if got:
                    names.append(got)
        if names:
            self._refresh_sets()
        return names

    def on_import_lettering(self, *_a):
        """Pick images, a folder or a ZIP and trace them into a set."""
        last = self._get("giongoSaveDir", "")
        files, _f = QFileDialog.getOpenFileNames(
            self, self._t("gi_set_import_tip"), last,
            "Lettering (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff "
            "*.zip)")
        if not files:
            folder = QFileDialog.getExistingDirectory(
                self, self._t("gi_set_import_tip"), last)
            if not folder:
                return
            files = [folder]
        self.import_lettering(files)

    def import_lettering(self, paths, name=None):
        """Trace `paths` into a set, save it beside them and use it."""
        base = paths[0] if paths else ""
        name = name or os.path.splitext(os.path.basename(
            base.rstrip("\\/")))[0] or "lettering"
        data, skipped = TR.build_set(name, paths)
        if not data["glyphs"]:
            self._status(self._t("gi_set_none_found"))
            return ""
        folder = base if os.path.isdir(base) else os.path.dirname(base)
        try:
            where = TR.save_set(data, os.path.join(
                folder, name + ".typer-lettering.json"))
        except OSError:
            where = ""
        got = TR.register(data, where)
        self._remember_sets()
        self._refresh_sets()
        self._push_history()
        self._params["letterset"] = got
        self._load_into_widgets()
        self._schedule()
        msg = self._t("gi_set_done", n=len(data["glyphs"]), s=got,
                      l=" ".join(sorted(data["glyphs"])[:24]))
        if skipped:
            msg += self._t("gi_set_skipped", n=len(skipped))
        self._status(msg)
        return got

    def _remember_sets(self):
        paths = [TR.path_of(n) for n in TR.names() if TR.path_of(n)]
        self._set("giongoLetterSets", json.dumps(paths))

    def on_pick_font(self, *_a):
        """The font list, to look at rather than to remember."""
        if self._font_win is None:
            self._font_win = FontPickDialog(self)
        self._font_win._refill()
        self._font_win.show()
        self._font_win.raise_()
        self._font_win.search.setFocus()

    def take_font(self, family):
        """Draw with this family from now on ("" = the type's own)."""
        if self._params.get("font", "") == (family or ""):
            return
        self._push_history()
        self._params["font"] = family or ""
        self._load_into_widgets()
        self._schedule()
        self._say_frozen()

    def _say_frozen(self):
        """Say it when something that draws the letters cannot reach some
        of them, rather than letting the change look broken."""
        n = len(self._params.get("nodes") or {})
        if n:
            self._status(self._t("gi_frozen_font", n=n))

    def on_load_font(self, *_a):
        """Pick font files and use them without installing them."""
        names, _f = QFileDialog.getOpenFileNames(
            self, self._t("gi_font_load_tip"), "",
            "Fonts (*.ttf *.otf *.ttc *.otc)")
        if not names:
            return
        self.add_font_files(names)

    def add_font_files(self, names):
        """Load font files, remember them, and pick the first one."""
        fams, bad = UF.load_all(names)
        self._set("giongoUserFonts", UF.to_json())
        if fams:
            self._families = None       # the list has new names in it
            self._fonts_filled = False
            self._fill_fonts()
            self._push_history()
            self._params["font"] = fams[0]
            self._load_into_widgets()
            self._schedule()
            self._status(self._t("gi_font_loaded", f=", ".join(fams)))
        if bad:
            self._status(self._t("gi_font_load_bad",
                                 f=", ".join(os.path.basename(b)
                                             for b in bad)))
        return fams

    def _on_font(self, _i):
        fam = self.font_combo.currentData()
        if fam is None:
            # typed into the editable box: take it when it is a real family
            txt = self.font_combo.currentText().strip()
            fam = txt if txt in self.families() else ""
        self._params["font"] = fam or ""
        self._refresh_font_ui()
        self._say_frozen()
        self._schedule()

    def _on_bg(self, _i):
        self._set("giongoBg", self.bg_combo.currentData() or "check")
        self._schedule()

    def _on_section(self, key, on):
        self._open[key] = bool(on)
        self._set("giongoOpen", json.dumps(self._open))

    # --- the preview you can grab ------------------------------------------
    def letter_edit_of(self, key):
        """The four numbers of one letter's edit, for a drag to start from."""
        if not key:
            return None
        return G.letter_edit(self._params, key[0], key[1])

    # --- liquify -----------------------------------------------------------

    def selection_outline(self, key=None):
        """The chosen letter's own shape, in scene units, or None.

        Everything it is made of is in it - the font or a traced
        lettering, a pen, thickening, a warp, edited points - because it
        comes out of the same cache the drawing does.
        """
        key = key or self.preview.selected()
        pl = self._placement(key) if key else None
        if pl is None:
            return None
        p = G.effective(self._params)
        pen = p.get("pen", "off")
        try:
            _k, thick, _base = R.letter_shapes(
                pl, G.resolve_font(p, self.families()), p["bold"],
                p["thicken"], pen, p["seed"], p.get("pen_width", 100),
                BR.style_from(p, pen),
                W.warp_of(p, key[0], key[1]), N.nodes_of(p, key[0], key[1]),
                p.get("letterset", ""))
        except Exception:               # noqa: BLE001
            return None
        return thick.translated(pl["x"], pl["y"])

    def liquify_armed(self):
        """Is the brush on? The preview asks before it moves a letter."""
        return bool(self.liq_chk.isChecked())

    def _on_liquify_armed(self, on):
        if on:
            self.set_tool("liquify")
            return
        if self.tool() == "liquify":
            self.set_tool("move")
            return
        self.preview.set_brush(W.radius_for(self._params["liquify_size"])
                               if on else 0.0)
        self._status(self._t("gi_liq_on_tip") if on else "")

    def _touches_ink(self, pl, scene):
        """Is there any of this letter under the brush, where it is?

        A drag in the gap between two letters moves nothing and wipes
        nothing, and without this it does so in silence.
        """
        try:
            shape = self.selection_outline((pl["group"], pl["index"]))
        except Exception:               # noqa: BLE001
            return True
        if shape is None:
            return True
        r = W.radius_for(self._params["liquify_size"]) \
            * max(1e-6, pl["size"]) / R._REF
        here = QRectF(scene[0] - r, scene[1] - r, 2 * r, 2 * r)
        return shape.intersects(here)

    def liquify_step(self, scene, prev, alt=False):
        """One step of a drag with the brush, at a point in scene units."""
        pl = G.nearest_letter(self._places, scene)
        if pl is None:
            # nothing within reach at all, not even a letter to miss
            self._status(self._t("gi_nothing_there"))
            return
        tr, ok = R.letter_transform(pl).inverted()
        if not ok:
            return
        here = tr.map(QPointF(scene[0], scene[1]))
        was = tr.map(QPointF(prev[0], prev[1]))
        if not self._touches_ink(pl, scene):
            self._status(self._t("gi_nothing_there"))
            return
        dabs = W.dabs_for(self._params.get("liquify_mode", "push"),
                          was.x(), was.y(), here.x(), here.y(),
                          self._params["liquify_size"],
                          self._params["liquify_force"],
                          self._params["liquify_hard"])
        if alt:
            dabs = [W.invert(d) for d in dabs]
        if not self._drag_open:     # one undo step for the whole stroke
            self._drag_open = True
            self._history.append(G.sanitize(self._params))
            del self._history[:-_HISTORY]
            self._future = []
            self._refresh_history_ui()
        for d in dabs:
            W.add_dab(self._params, pl["group"], pl["index"], d)
        self._schedule_live()

    def on_reset_warps(self, *_a):
        """Every letter back to the shape the font drew."""
        if not W.has_warp(self._params):
            return
        self._push_history()
        W.clear_warp(self._params)
        self._schedule()
        self._status(self._t("gi_liq_reset_done"))

    # --- the outline's own points ------------------------------------------

    # --- which tool the pointer is -----------------------------------------

    TOOLS = ("move", "liquify", "points", "erase")

    def tool(self):
        return getattr(self, "_tool", "move")

    #: which actions belong to which tool, in the order they are offered
    TOOL_ACTIONS = {
        "move": ("reset_moves",),
        "liquify": ("reset_warp",),
        "points": ("del", "smooth", "reset_letter", "reset_pts"),
        "erase": ("reset_letter", "reset_pts"),
    }

    def _refresh_action_bar(self):
        """Only the actions of the tool in hand, and what is edited."""
        want = self.TOOL_ACTIONS.get(self.tool(), ())
        for key, btn in self.act_btns.items():
            btn.setVisible(key in want)
        chosen = len(self.point_selection())
        for key in ("del", "smooth"):
            if key in self.act_btns:
                self.act_btns[key].setEnabled(chosen > 0)
        # said whatever tool is in hand: a letter with its own outline
        # stops following the font, and that must not be invisible
        n = len(self._params.get("nodes") or {})
        self.act_count.setText(self._t("gi_act_count", n=n) if n else "")

    def points_delete_chosen(self):
        """Take the chosen points away."""
        key = self.preview.selected()
        chosen = self.point_selection()
        if not key or not chosen:
            return
        cs = self.point_contours(key)
        self._push_history()
        N.set_nodes(self._params, key[0], key[1], N.delete_nodes(cs, chosen))
        self.set_point_selection([])
        self._schedule()

    def points_smooth_chosen(self):
        """Corner or curve, for everything chosen."""
        key = self.preview.selected()
        chosen = self.point_selection()
        if not key or not chosen:
            return
        cs = self.point_contours(key)
        want = not cs[chosen[0][0]][chosen[0][1]][6]
        self._push_history()
        N.set_nodes(self._params, key[0], key[1],
                    N.smooth_nodes(cs, chosen, want))
        self._schedule()

    def reset_points_letter(self):
        """This letter back to the outline the font drew."""
        key = self.preview.selected()
        if not key or not N.has_nodes(self._params, key[0], key[1]):
            return
        self._push_history()
        N.clear_nodes(self._params, key[0], key[1])
        W.clear_warp(self._params, key[0], key[1])
        self.set_point_selection([])
        self._schedule()

    def set_tool(self, key):
        """Pick the tool the preview answers to. One at a time."""
        key = key if key in self.TOOLS else "move"
        self._tool = key
        for k, b in self.tool_btns.items():
            b.setChecked(k == key)
            b.setStyleSheet(_TOOL_ON if k == key else _TOOL_OFF)
        self.liq_chk.blockSignals(True)
        self.liq_chk.setChecked(key == "liquify")
        self.liq_chk.blockSignals(False)
        self.pts_chk.blockSignals(True)
        self.pts_chk.setChecked(key == "points")
        self.pts_chk.blockSignals(False)
        self.preview.set_points(key == "points")
        self.preview.set_brush(
            W.radius_for(self._params["liquify_size"])
            if key in ("liquify", "erase") else 0.0)
        self._refresh_legend()
        self._refresh_action_bar()
        self._status("")

    def erase_armed(self):
        return self.tool() == "erase"

    def _refresh_legend(self):
        self.legend_lbl.setText(self._t("gi_legend_" + self.tool()))

    def erase_step(self, scene, prev):
        """Wipe the letter under the pointer along the way just travelled.

        The whole step is taken off at once, as a line with round ends,
        so a fast drag leaves a stroke and not a row of bites.
        """
        key = self.preview.selected()
        pl = self._placement(key) if key else None
        if pl is None or pl["bar"]:
            pl = G.nearest_letter(self._places, scene)
            if pl is None or pl["bar"]:
                return
            key = (pl["group"], pl["index"])
            self.preview.select(key)
        if not self._touches_ink(pl, scene):
            self._status(self._t("gi_nothing_there"))
            return
        if not self._drag_open:     # one undo step for the whole stroke,
            self._drag_open = True  # opening the letter included
            self._history.append(G.sanitize(self._params))
            del self._history[:-_HISTORY]
            self._future = []
            self._refresh_history_ui()
        cs = self.open_points(key)
        if not cs:
            return
        tr, ok = R.letter_transform(pl).inverted()
        if not ok:
            return
        here = tr.map(QPointF(scene[0], scene[1]))
        was = tr.map(QPointF(prev[0], prev[1]))
        r = W.radius_for(self._params["liquify_size"])
        cut = QPainterPath()
        cut.moveTo(was)
        cut.lineTo(here)
        # Qt's boolean ops hand back an odd-even path; the nodes are
        # redrawn winding, which would fill the hole that was just cut.
        # simplified() rewinds the contours so a hole stays a hole.
        left = R.path_from_nodes(cs).subtracted(R._ring_cut(cut, r))
        # Qt fills what it gives back odd-even, an outline of nodes is
        # filled non-zero: the holes have to be wound to match
        N.set_nodes(self._params, key[0], key[1],
                    N.rewind(R.nodes_from_path(left)))
        self._schedule_live()
        self._status(self._t("gi_erased"))

    def points_armed(self):
        return bool(self.pts_chk.isChecked())

    def _on_points_armed(self, on):
        if on:
            self.set_tool("points")
            return
        if self.tool() == "points":
            self.set_tool("move")
            return
        self.preview.set_points(on)
        self._status(self._t("gi_pts_on_tip") if on else "")

    def _letter_space(self, key):
        """(placement, scene -> em transform) for one letter, or None."""
        pl = self._placement(key) if key else None
        if pl is None or pl["bar"]:
            return None, None
        inv, ok = R.letter_transform(pl).inverted()
        return (pl, inv) if ok else (pl, None)

    def open_points(self, key):
        """Freeze a letter's outline so its points can be taken hold of.

        Whatever it looks like now - the font, a pen, a warp - becomes
        the points. The warp is folded in and cleared, or it would be
        applied a second time on top of the outline it is already in.
        """
        pl = self._placement(key)
        if pl is None or pl["bar"]:
            return []
        if N.has_nodes(self._params, key[0], key[1]):
            return N.nodes_of(self._params, key[0], key[1])
        pen = self._params.get("pen", "off")
        shape = R.em_shape(pl, G.resolve_font(self._params, self.families()),
                           self._params["bold"], pen, self._params["seed"],
                           self._params.get("pen_width", 100),
                           BR.style_from(G.effective(self._params), pen),
                           W.warp_of(self._params, key[0], key[1]), ())
        cs = R.nodes_from_path(shape)
        if not cs:
            return []
        if not self._drag_open:
            # a drag that begins by opening a letter is one step, not two
            self._push_history()
        N.set_nodes(self._params, key[0], key[1], cs)
        W.clear_warp(self._params, key[0], key[1])
        self._schedule()
        self._status(self._t("gi_pts_opened", n=N.count(cs)))
        return cs

    def point_selection(self):
        """Which points are chosen, as (contour, node) pairs."""
        cs = self.point_contours()
        return N.valid_keys(cs, getattr(self, "_pt_sel", []))

    def set_point_selection(self, keys):
        self._pt_sel = list(keys or [])
        self._refresh_action_bar()
        self.preview.update()

    def point_gizmo(self):
        """(centre, radius) of the chosen points, in scene units."""
        key = self.preview.selected()
        pl, _inv = self._letter_space(key)
        if pl is None:
            return None
        cs = self.point_contours(key)
        keys = N.valid_keys(cs, getattr(self, "_pt_sel", []))
        if not keys:
            return None
        box = N.nodes_bounds(cs, keys)
        tr = R.letter_transform(pl)
        mid = tr.map(QPointF((box[0] + box[2]) / 2.0,
                             (box[1] + box[3]) / 2.0))
        corner = tr.map(QPointF(box[2], box[3]))
        r = max(18.0, abs(corner.x() - mid.x()), abs(corner.y() - mid.y()))
        return (mid.x(), mid.y()), r

    def point_band(self, x0, y0, x1, y1, add=False):
        """Choose every point inside a rectangle drawn on the preview."""
        key = self.preview.selected()
        pl, inv = self._letter_space(key)
        if pl is None or inv is None:
            return
        cs = self.point_contours(key)
        a = inv.map(QPointF(x0, y0))
        b = inv.map(QPointF(x1, y1))
        got = N.nodes_in_rect(cs, a.x(), a.y(), b.x(), b.y())
        if add:
            got = [k for k in self._pt_sel if k not in got] + got
        self.set_point_selection(got)

    def point_gizmo_drag(self, what, scene, prev):
        """One step of a drag on the gizmo over the chosen points."""
        import math as _m
        key = self.preview.selected()
        pl, inv = self._letter_space(key)
        if pl is None or inv is None:
            return
        cs = self.point_contours(key)
        keys = N.valid_keys(cs, getattr(self, "_pt_sel", []))
        if not keys:
            return
        here = inv.map(QPointF(scene[0], scene[1]))
        was = inv.map(QPointF(prev[0], prev[1]))
        self._open_drag_step()
        cx, cy = N.nodes_centre(cs, keys)
        if what in ("pfree", "pmovex", "pmovey"):
            dx = here.x() - was.x() if what != "pmovey" else 0.0
            dy = here.y() - was.y() if what != "pmovex" else 0.0
            N.move_nodes(cs, keys, dx, dy)
        elif what == "protate":
            a0 = _m.degrees(_m.atan2(was.y() - cy, was.x() - cx))
            a1 = _m.degrees(_m.atan2(here.y() - cy, here.x() - cx))
            N.rotate_nodes(cs, keys, cx, cy, a1 - a0)
        elif what == "pscale":
            d0 = _m.hypot(was.x() - cx, was.y() - cy)
            d1 = _m.hypot(here.x() - cx, here.y() - cy)
            if d0 > 1e-6:
                N.scale_nodes(cs, keys, cx, cy,
                              max(0.05, min(20.0, d1 / d0)))
        else:
            return
        N.set_nodes(self._params, key[0], key[1], cs)
        self._schedule_live()

    def _open_drag_step(self):
        """The first step of a drag opens one step in the history."""
        if self._drag_open:
            return
        self._drag_open = True
        self._history.append(G.sanitize(self._params))
        del self._history[:-_HISTORY]
        self._future = []
        self._refresh_history_ui()

    def point_double(self, scene, grab_px, scale):
        """Double-click in points mode: on a point, corner <-> curve; on
        the outline, a new point there."""
        key = self.preview.selected()
        pl, inv = self._letter_space(key)
        if pl is None or inv is None:
            return False
        cs = self.point_contours(key)
        if not cs:
            return False
        here = inv.map(QPointF(scene[0], scene[1]))
        x, y = here.x(), here.y()
        tol = grab_px / max(1e-6, scale) * (R._REF / max(1.0, pl["size"]))
        hit = N.nearest_node(cs, x, y, tol)
        if hit is not None:
            self._push_history()
            chosen = self.point_selection()
            if hit in chosen and len(chosen) > 1:
                N.smooth_nodes(cs, chosen, not cs[hit[0]][hit[1]][6])
            else:
                N.toggle_smooth(cs, hit[0], hit[1])
            N.set_nodes(self._params, key[0], key[1], cs)
            self._schedule()
            return True
        seg = N.nearest_segment(cs, x, y)
        if seg is not None and seg[3] <= tol * 2.0:
            self._push_history()
            N.set_nodes(self._params, key[0], key[1],
                        N.insert_node(cs, seg[0], seg[1], seg[2]))
            self.set_point_selection([(seg[0], seg[1] + 1)])
            self._schedule()
            return True
        return False

    def point_contours(self, key=None):
        """The nodes of the letter being edited, in its own em."""
        key = key or self.preview.selected()
        if not key:
            return []
        return N.nodes_of(self._params, key[0], key[1])

    def point_overlay(self):
        """What the preview draws: points and handles in scene units."""
        key = self.preview.selected()
        pl, _inv = self._letter_space(key)
        if pl is None:
            return []
        cs = self.point_contours(key)
        if not cs:
            return []
        _chosen = set(self.point_selection())
        tr = R.letter_transform(pl)
        out = []
        for ci, ring in enumerate(cs):
            for ni, n in enumerate(ring):
                pt = tr.map(QPointF(n[0], n[1]))
                item = {"ci": ci, "ni": ni, "smooth": bool(n[6]),
                        "chosen": (ci, ni) in _chosen,
                        "p": (pt.x(), pt.y()), "in": None, "out": None}
                if n[2] or n[3]:
                    h = tr.map(QPointF(n[0] + n[2], n[1] + n[3]))
                    item["in"] = (h.x(), h.y())
                if n[4] or n[5]:
                    h = tr.map(QPointF(n[0] + n[4], n[1] + n[5]))
                    item["out"] = (h.x(), h.y())
                out.append(item)
        return out

    def point_press(self, scene, grab_px, scale, alt=False, shift=False):
        """A press in points mode. Returns what is now being dragged."""
        key = self.preview.selected()
        pl, inv = self._letter_space(key)
        if pl is None or inv is None:
            pl2 = G.nearest_letter(self._places, scene)
            if pl2 is None or pl2["bar"]:
                return None
            self.preview.select((pl2["group"], pl2["index"]))
            self.open_points((pl2["group"], pl2["index"]))
            return None
        cs = self.point_contours(key)
        if not cs:
            self.open_points(key)
            cs = self.point_contours(key)
            if not cs:
                return None
        here = inv.map(QPointF(scene[0], scene[1]))
        x, y = here.x(), here.y()
        # the pointer's reach, in the letter's own units
        tol = grab_px / max(1e-6, scale) * (R._REF / max(1.0, pl["size"]))
        if not (alt or shift):
            # a plain drag may take a handle; Alt and Shift mean the point
            hit = N.nearest_handle(cs, x, y, tol)
            if hit is not None:
                return ("handle", hit[0], hit[1], hit[2])
        hit = N.nearest_node(cs, x, y, tol)
        if hit is not None:
            ci, ni = hit
            if alt:
                self._push_history()
                N.set_nodes(self._params, key[0], key[1],
                            N.delete_nodes(cs, self.point_selection()
                                           or [(ci, ni)]))
                self.set_point_selection([])
                self._schedule()
                return None
            if shift:
                # Shift gathers points up instead of changing one
                sel = list(getattr(self, "_pt_sel", []))
                if (ci, ni) in sel:
                    sel.remove((ci, ni))
                else:
                    sel.append((ci, ni))
                self.set_point_selection(sel)
                return None
            if (ci, ni) in self.point_selection() \
                    and len(self.point_selection()) > 1:
                return ("nodes", ci, ni, None)   # drag what is chosen
            self.set_point_selection([(ci, ni)])
            return ("node", ci, ni, None)
        # a single click on the outline starts a rectangle like anywhere
        # else; adding a point is a double-click, as in the original
        # on another letter: pick that one up. On empty space: start a
        # rectangle to gather points with
        other = G.nearest_letter(self._places, scene)
        if other is not None and (other["group"], other["index"]) != key \
                and not other["bar"]:
            _ol = self.selection_outline((other["group"], other["index"]))
            if _ol is not None and _ol.contains(QPointF(scene[0], scene[1])):
                self.preview.select((other["group"], other["index"]))
                self.set_point_selection([])
                self.open_points((other["group"], other["index"]))
                return None
        if not shift:
            self.set_point_selection([])
        return ("band", scene[0], scene[1], None)

    def point_drag(self, what, scene):
        """Move the point or handle that is being dragged."""
        kind, ci, ni, which = what
        key = self.preview.selected()
        pl, inv = self._letter_space(key)
        if pl is None or inv is None:
            return
        cs = self.point_contours(key)
        if ci >= len(cs) or ni >= len(cs[ci]):
            return
        here = inv.map(QPointF(scene[0], scene[1]))
        if not self._drag_open:
            self._drag_open = True
            self._history.append(G.sanitize(self._params))
            del self._history[:-_HISTORY]
            self._future = []
            self._refresh_history_ui()
        if kind == "handle":
            N.move_handle(cs, ci, ni, which, here.x(), here.y())
        elif kind == "nodes":
            n = cs[ci][ni]
            N.move_nodes(cs, self.point_selection(),
                         here.x() - n[0], here.y() - n[1])
        else:
            n = cs[ci][ni]
            N.move_node(cs, ci, ni, here.x() - n[0], here.y() - n[1])
        N.set_nodes(self._params, key[0], key[1], cs)
        self._schedule_live()

    def on_reset_points(self, *_a):
        if not N.has_nodes(self._params):
            return
        self._push_history()
        N.clear_nodes(self._params)
        self._schedule()
        self._status(self._t("gi_pts_reset_done"))

    def preview_drag(self, what, scene, start, key, before):
        """One step of a drag in the preview, in scene coordinates.

        The panel decides what the gesture means and writes it into the
        parameters; the widget only says where the pointer went.
        """
        before_all = G.sanitize(self._params)
        if what in ("end", "bend"):
            if what == "end":
                G.set_path_end(self._params, self.text(), scene,
                               self._advance_fn())
            else:
                G.set_path_bend(self._params, self.text(), scene,
                                self._advance_fn())
            self._load_into_widgets()
        elif key is not None and before is not None:
            dx0, dy0, rot0, sc0 = before
            pl = self._placement(key)
            if pl is None:
                return
            if what in ("move", "free", "movex", "movey"):
                # the arrows hold one direction still, which is what they
                # are for: nudging a letter sideways without drifting
                mx = what != "movey"
                my = what != "movex"
                G.set_letter_edit(
                    self._params, key[0], key[1],
                    dx=dx0 + (scene[0] - start[0] if mx else 0.0),
                    dy=dy0 + (scene[1] - start[1] if my else 0.0))
            elif what == "rotate":
                # the angle the pointer makes with the letter, against the
                # angle it made when the drag began
                import math as _m
                cx, cy = pl["x"], pl["y"]
                a0 = _m.degrees(_m.atan2(start[1] - cy, start[0] - cx))
                a1 = _m.degrees(_m.atan2(scene[1] - cy, scene[0] - cx))
                G.set_letter_edit(self._params, key[0], key[1],
                                  rot=rot0 + (a1 - a0))
            elif what == "scale":
                import math as _m
                cx, cy = pl["x"], pl["y"]
                d0 = _m.hypot(start[0] - cx, start[1] - cy)
                d1 = _m.hypot(scene[0] - cx, scene[1] - cy)
                if d0 > 1.0:
                    G.set_letter_edit(self._params, key[0], key[1],
                                      scale=sc0 * d1 / d0)
        else:
            return
        if not self._drag_open:     # one step for the whole drag, pushed
            self._drag_open = True  # with the parameters it started from
            self._history.append(G.sanitize(before_all))
            del self._history[:-_HISTORY]
            self._future = []
            self._refresh_history_ui()
        self._schedule_live()

    def preview_drag_done(self):
        """A drag is one step in the history, not one per mouse move."""
        self._drag_open = False
        self._save_state()

    def reset_letter(self, key):
        """Double-click: this letter goes back to what the parameters say."""
        self._push_history()
        G.set_letter_edit(self._params, key[0], key[1], dx=0.0, dy=0.0,
                          rot=0.0, scale=1.0)
        W.clear_warp(self._params, key[0], key[1])
        self._schedule()

    def reset_letters(self):
        self._push_history()
        G.clear_letter_edits(self._params)
        W.clear_warp(self._params)
        self._schedule()
        self._status(self._t("gi_letters_reset"))

    def _placement(self, key):
        for pl in self._places:
            if (pl["group"], pl["index"]) == key:
                return pl
        return None

    def _advance_fn(self, params=None):
        """Letter advances from the real font, so the path handles sit where
        the letters really end.

        From the *effective* parameters, like the renderer: the macros
        change the thickening and the shear, and an advance taken from
        the raw settings would be a different letter's.
        """
        p = params if params is not None else G.effective(self._params)
        return R.advance_fn(p, G.resolve_font(p, self.families()))

    # --- preview -----------------------------------------------------------

    def _schedule(self):
        self._preview_timer.start()
        self._save_timer.start()

    def _schedule_live(self):
        """While a drag is running: keep up with the pointer.

        `_schedule` waits for 90 ms of quiet, which a moving hand never
        gives it, so the preview only caught up when the drag stopped.
        """
        self._save_timer.start()
        now = _time.monotonic()
        if now - self._last_live >= 0.04:
            self._last_live = now
            self._live_timer.stop()
            self._refresh_preview()
        else:
            self._live_timer.start()        # the last step must still land

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

    def _split_blocks(self, cols):
        """Which block goes in which column, in reading order.

        The block with the canvas in it keeps a column of its own as soon
        as there are two; the heading goes with the settings.
        """
        blocks = [b for b in self._blocks if b is not None]
        if not blocks:
            return []
        canvas = self._canvas_block if self._canvas_block in blocks \
            else blocks[0]
        rest = [b for b in blocks if b is not canvas]
        if cols <= 1:
            return [[canvas] + rest if canvas is blocks[0] else blocks]
        if cols == 2:
            return [[canvas], rest]
        half = (len(rest) + 1) // 2
        return [[canvas], rest[:half], rest[half:]]

    def _apply_docked_view(self):
        """In the tab: the heading and the button, nothing else."""
        for b in self._blocks:
            if b is None:
                continue
            b.setVisible(self._popped or b is self._blocks[0])
        if hasattr(self, "tab_only"):
            self.tab_only.setVisible(not self._popped)

    def _recheck_columns(self):
        """Re-read the width once the layout has settled.

        Right after a move the panel still reports the width it had in the
        place it came from, so asking straight away gives the old answer.
        """
        self._place_blocks(self._columns_for(self.width()))

    def _place_blocks(self, cols):
        """(Re)arrange the groups. Does nothing when the count is unchanged."""
        cols = max(1, int(cols))
        # the height is re-read even when the columns did not change: the
        # window can be resized without the count ever moving
        if cols > 1:
            room = max(260, self.height() - 400)
            self.preview.setMinimumHeight(min(int(self.height() * 0.45),
                                              room))
            self.preview.setMaximumHeight(room)
        else:
            self.preview.setMinimumHeight(200)
            self.preview.setMaximumHeight(16777215)
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
            if c > 0 or cols <= 1:
                for r, block in enumerate(column):
                    grid.addWidget(block, r, c)
                    block.setParent(self)
                    block.show()
                rows = max(rows, len(column))
            # the first column carries the preview, so it may take more room
            grid.setColumnStretch(c, 3 if c == 0 else 2)
        for c in range(len(columns), 4):
            grid.setColumnStretch(c, 0)
        if cols > 1 and columns and columns[0]:
            # the canvas column spans every row there is, the stretch row
            # included, so the preview fills the height of the window
            block = columns[0][0]
            grid.addWidget(block, 0, 0, max(1, rows) + 1, 1)
            block.setParent(self)
            block.show()
        self._apply_docked_view()
        for r in range(rows):
            grid.setRowStretch(r, 0)
        grid.setRowStretch(rows, 1)
        # in a window the canvas is the point of the thing: it gets most
        # of the height outright, rather than whatever the other widgets
        # in its column leave over

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
        self._apply_docked_view()
        self._apply_active()
        win.show()
        self._layout_timer.start()

    def dock_back(self):
        """Put the panel back where it came from."""
        if not self._popped:
            return
        if self._window is not None:
            self._remember_geometry(self._window)
            self._window.release_panel()
        self._popped = False
        self._window = None
        if self._home is not None:
            self._home.addWidget(self)
        self.popout_btn.setText(self._t("gi_popout"))
        self._apply_docked_view()
        self._apply_active()
        self._layout_timer.start()

    def _remember_geometry(self, win):
        g = win.geometry()
        self._set("giongoWinGeom", "%d,%d,%d,%d"
                  % (g.x(), g.y(), g.width(), g.height()))

    @staticmethod
    def _screen_area(x, y, fallback):
        """The usable area of the screen at (x, y), or of `fallback`'s."""
        try:
            scr = QGuiApplication.screenAt(QPoint(int(x), int(y)))
        except Exception:               # noqa: BLE001
            scr = None
        if scr is None:
            scr = fallback.screen() if hasattr(fallback, "screen") else None
        if scr is None:
            scr = QGuiApplication.primaryScreen()
        return scr.availableGeometry() if scr is not None else None

    def _restore_geometry(self, win):
        """Put the window back where it was, if that is still on a screen.

        Whatever is stored, the window has to end up somewhere the user
        can reach: inside one screen's usable area, title bar included.
        """
        raw = self._get("giongoWinGeom", "")
        parts = [p for p in str(raw).split(",") if p.strip()]
        x = y = None
        w, h = 1180, 760
        if len(parts) == 4:
            try:
                sx, sy, sw, sh = (int(p) for p in parts)
            except ValueError:
                sx = sy = sw = sh = 0
            if sw >= 420 and sh >= 320:
                x, y, w, h = sx, sy, sw, sh
        area = self._screen_area(x if x is not None else 0,
                                 y if y is not None else 0, win)
        if area is not None:
            w = max(420, min(w, area.width() - 40))
            h = max(320, min(h, area.height() - 60))
            if x is None or y is None:
                x = area.x() + (area.width() - w) // 2
                y = area.y() + (area.height() - h) // 2
            x = max(area.x(), min(x, area.x() + area.width() - w))
            y = max(area.y(), min(y, area.y() + area.height() - h))
        if x is None or y is None:
            win.resize(w, h)
            return
        win.setGeometry(int(x), int(y), int(w), int(h))

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
            RP.record("giongo preview", exc)
            self.preview.setText(str(exc))
            return
        self.preview.setPixmap(QPixmap.fromImage(img))
        self._refresh_action_bar()
        # what the preview may be grabbed by: where every letter landed and
        # where the path runs, in the same coordinates, with the transform
        # that maps them onto the image just drawn
        try:
            # exactly what the renderer did, or the mouse points at
            # letters that are not where they are drawn
            eff = G.effective(self._params)
            adv = self._advance_fn(eff)
            self._places = G.layout(self.text(), eff, advance_fn=adv)
            k, ox, oy = R.thumb_transform(scene, w, h)
            self.preview.set_frame(k, ox, oy, img.width(), img.height(),
                                   self._places,
                                   G.path_points(self.text(), eff, 0, adv))
        except Exception:               # noqa: BLE001
            self._places = []

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

    def _push_history(self, key=None):
        """Remember what the parameters are, before they change.

        `key` coalesces: dragging a slider calls this on every tick, and
        forty steps of the same slider are one thing the user did, not
        forty. A different slider, or a second of quiet, starts a new
        step. Anything that is one action anyway passes no key.
        """
        now = _time.monotonic()
        if key is not None and key == self._hist_key \
                and now - self._hist_at < 1.0:
            self._hist_at = now
            return
        self._hist_key, self._hist_at = key, now
        self._history.append(G.sanitize(self._params))
        del self._history[:-_HISTORY]
        self._future = []
        self._refresh_history_ui()

    def _refresh_history_ui(self):
        self.back_btn.setEnabled(bool(self._history))
        self.fwd_btn.setEnabled(bool(self._future))

    def on_back(self, *_a):
        if not self._history:
            return
        self._future.append(G.sanitize(self._params))
        del self._future[:-_HISTORY]
        self._params = self._history.pop()
        self._hist_key = None
        self._load_into_widgets()
        self._refresh_history_ui()
        self._schedule()

    def on_forward(self, *_a):
        """The step that was just undone, back again."""
        if not self._future:
            return
        self._history.append(G.sanitize(self._params))
        del self._history[:-_HISTORY]
        self._params = self._future.pop()
        self._hist_key = None
        self._load_into_widgets()
        self._refresh_history_ui()
        self._schedule()

    def _editor_under_focus(self):
        """The text field the user is typing in, if it is one of ours."""
        w = QApplication.focusWidget()
        if isinstance(w, (QPlainTextEdit, QLineEdit)) and self.isAncestorOf(w):
            return w
        return None

    def on_undo_key(self):
        """Ctrl+Z. While typing it belongs to the field, not to us."""
        w = self._editor_under_focus()
        if w is not None:
            w.undo()
            return
        self.on_back()

    def on_redo_key(self):
        w = self._editor_under_focus()
        if w is not None:
            w.redo()
            return
        self.on_forward()

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

    def save_scale(self):
        """What PNG and ZIP are rendered at, 1 to 4."""
        try:
            return max(1, min(4, int(self.scale_combo.currentData() or 1)))
        except (TypeError, ValueError):
            return 1

    def save_zip(self, path, scene=None, scale=None):
        """Every layer as its own PNG in one ZIP. Returns how many."""
        import zipfile
        scene = scene or self.scene()
        pngs = R.layer_pngs(scene, scale=scale or self.save_scale())
        if not pngs:
            return 0
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for name, data in pngs:
                    z.writestr(name, data)
                z.writestr("README.txt", self._zip_readme(pngs))
        except OSError as exc:
            RP.record("giongo save zip", exc, path)
            return 0
        self._set("giongoSaveDir", os.path.dirname(path))
        return len(pngs)

    def _zip_readme(self, pngs):
        return ("TypeR / Giongo - one PNG per layer, all the same size and\n"
                "all on the same canvas, so stacking them in this order\n"
                "gives the lettering back:\n\n"
                + "".join("  %s\n" % n for n, _d in pngs))

    def save_psd(self, path, scene=None, scale=None):
        """The layers as a PSD, written by Krita. None without Krita."""
        try:
            from krita import Krita, InfoObject
        except ImportError:
            return None
        scene = scene or self.scene()
        imgs = R.render_layers(scene, scale=scale or self.save_scale())
        if not imgs:
            return None
        w, h = imgs[0][1].width(), imgs[0][1].height()
        app = Krita.instance()
        doc = app.createDocument(w, h, "Giongo", "RGBA", "U8", "", 300.0)
        root = doc.rootNode()
        for old in list(root.childNodes()):
            root.removeChildNode(old)
        for name, img in imgs:
            img = img.convertToFormat(QImage.Format.Format_ARGB32)
            node = doc.createNode(name, "paintlayer")
            root.addChildNode(node, None)
            nbytes = (img.sizeInBytes() if hasattr(img, "sizeInBytes")
                      else img.byteCount())
            buf = img.constBits()
            buf.setsize(nbytes)
            node.setPixelData(bytes(buf), 0, 0, img.width(), img.height())
        doc.refreshProjection()
        try:
            ok = doc.exportImage(path, InfoObject())
        except Exception:               # noqa: BLE001
            ok = doc.saveAs(path)
        doc.close()
        if ok:
            self._set("giongoSaveDir", os.path.dirname(path))
        return len(imgs) if ok else None

    def on_save(self, kind):
        scene = self.scene()
        if scene.is_empty():
            self._status(self._t("gi_empty"))
            return
        last = self._get("giongoSaveDir", "")
        filt = {"png": "PNG (*.png)", "svg": "SVG (*.svg)",
                "zip": "ZIP (*.zip)",
                "psd": "Photoshop (*.psd)"}.get(kind, "PNG (*.png)")
        path, _f = QFileDialog.getSaveFileName(self, "", last, filt)
        if not path:
            return
        if not path.lower().endswith("." + kind):
            path += "." + kind
        if kind == "zip":
            n = self.save_zip(path, scene)
            self._status(self._t("gi_saved_zip", n=n, p=path) if n
                         else self._t("gi_save_fail", p=path))
            return
        if kind == "psd":
            n = self.save_psd(path, scene)
            self._status(self._t("gi_saved", p=path) if n
                         else self._t("gi_save_fail", p=path))
            return
        ok = self.save_to(path, scene)
        self._status(self._t("gi_saved" if ok else "gi_save_fail", p=path))

    def save_to(self, path, scene=None):
        """Write the lettering to `path` (.png or .svg). True on success."""
        scene = scene or self.scene()
        try:
            if path.lower().endswith(".svg"):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(R.to_svg(scene))
                ok = True
            else:
                img, _tl = R.render_image(scene, scale=self.save_scale())
                ok = bool(img.save(path, "PNG"))
        except OSError as exc:
            RP.record("giongo save", exc, path)
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
            RP.record("giongo insert", exc)
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
