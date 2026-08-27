# -*- coding: utf-8 -*-
"""
TypeR for Krita
===============

A Krita docker that recreates the core of the Photoshop plugin "TypeR" as far
as Krita's API allows:

  * Read translation scripts from Word (.docx), OpenOffice/LibreOffice (.odt)
    as well as .txt / .md
  * Split the text line by line, with one line active at a time
  * Navigate back / forward through the lines, preview the active line
  * Detect "Page" markers in the script so you always know which page you are
    on and can jump straight to a given page
  * Optionally skip empty lines
  * Insert the active line as a text layer in Krita (optionally centered on the
    current selection), with font, size and color

Important: the reader parses .docx / .odt correctly as ZIP-of-XML rather than
as plain text. That avoids any "character could not be read" error. Only
modules from the Python standard library are used (zipfile, xml.etree), so
nothing extra needs to be installed.
"""

import os
import html as _html
import math
import re
import json
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from ._qt import (Qt, pyqtSignal, QRectF, QEvent, QPoint, QPointF,
                          QMimeData, QTimer, QRect, QSize)
from ._qt import (QColor, QFont, QFontMetricsF, QImage, QPainter,
                         QPainterPath, QBrush, QPen, QPixmap, QTextCursor, QDrag,
                         QCursor, QKeySequence, QPolygonF, QIcon)
from ._qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QPlainTextEdit, QSpinBox, QCheckBox, QFileDialog, QColorDialog,
    QMessageBox, QSizePolicy, QFrame, QLineEdit, QListWidget, QListWidgetItem,
    QTextBrowser, QFontDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox,
    QInputDialog, QScrollArea, QTabBar, QTabWidget, QToolButton, QMenu,
    QDialog, QButtonGroup, QDialogButtonBox, QApplication,
    QShortcut, QLayout, QStackedWidget,
)

# Drag & drop mime type carrying a panel id while a PanelBox is dragged by
# its header (customize mode only).
PANEL_MIME = "application/x-typer-panel"

# How many generic host dockers are pre-registered so a panel can be detached
# into its own Krita-dockable window (kept in sync with layoutmodel).
MAX_DETACH_SLOTS = 3

# slot index -> live TyperExtraHost instance. Filled as Krita constructs the
# pre-registered host dockers; read by the main docker when detaching a panel.
_EXTRA_HOSTS = {}
from ._qt import font_families, binding_info

from krita import (DockWidget, DockWidgetFactory, DockWidgetFactoryBase,
                   Krita, Selection)

from . import layout as L
from . import imgfx as IMG
from . import xlsx as XLSX
from . import langpair as LP
from . import texttypes as TT
from . import fontmatch as FM
from . import gauth as GA
from . import gdocs as GD
from . import comments as CM
from . import bubbles as BB
from . import balloons as BAL
from . import ai_backend as AB


# Human-facing version number for this build (bump on releases).
# Version scheme: a real feature update bumps the minor (1.7 → 1.8 → 1.9 →
# 1.10 …); a pure bug-fix release bumps a third patch number (1.8 → 1.8.1 …).
VERSION = "1.11"

# BubblR (the AI bubble-detection tab) is still experimental and depends on the
# external BubblR-AI model. It is LOCKED OFF in public releases: the tab is
# hidden and its enable toggle is not shown. Set this to False to bring it back
# once the AI is ready (all the BubblR code stays in place, just dormant).
# Local/dev build: unlocked so the AI tab is available.
BUBBLR_LOCKED = False

# Build stamp = last-modified time of THIS installed file. copy/xcopy keep the
# source's timestamp, so this shows which code version Krita actually loaded -
# handy to confirm an update really took (compare it after running UPDATE.bat).
try:
    BUILD = time.strftime("%Y-%m-%d %H:%M",
                          time.localtime(os.path.getmtime(__file__)))
except Exception:
    BUILD = "?"


# ---------------------------------------------------------------------------
# Wheel-safe widgets
#
# A QComboBox/QSpinBox changes its value on a mouse-wheel tick even when it
# only happens to be under the cursor while the user scrolls the panel. That
# silently switches the manga/character/preset/etc. by accident. These
# subclasses only react to the wheel when they actually have keyboard focus
# (i.e. the user clicked into them first); otherwise the wheel event is passed
# on so the surrounding scroll area scrolls instead.
# ---------------------------------------------------------------------------
class NoScrollComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoScrollSpinBox(QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class ScriptTabBar(QTabBar):
    """Tab bar for the loaded scripts. Adds browser-style middle-click-to-close
    on top of the normal close button."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            idx = self.tabAt(event.pos())
            if idx >= 0:
                self.tabCloseRequested.emit(idx)
                return
        super().mousePressEvent(event)


class OldDocError(Exception):
    """Old binary format (.doc/.xls) that cannot be read directly."""

    def __init__(self, fmt=".doc"):
        super().__init__(fmt)
        self.fmt = fmt


# ---------------------------------------------------------------------------
# User-interface translations
# ---------------------------------------------------------------------------

LANG = {
    "en": {
        "title": "TypeR for Krita",
        "language": "Language:",
        "load_btn": "Load script (.docx / .odt / .txt / .gdoc)",
        "script_label": "Script (load a file or paste directly):",
        "editor_ph": "Paste the script here, or load a file above …",
        "skip_empty": "Skip empty lines",
        "analyze_btn": "Analyze · pair JP↔EN",
        "add_line_btn": "+ Add line",
        "add_line_dlg": "Add line",
        "add_line_prompt": "New line (translation text):",
        "save_script_btn": "Save to file",
        "save_script_dlg": "Save script",
        "save_script_confirm": "Overwrite the script file \"{name}\" with the current text?",
        "st_line_added": "Line added to the script.",
        "st_script_saved": "Script saved to {name}.",
        "st_save_script_fail": "Could not save the script: {err}",
        "align_label": "Japanese  ↔  Translation   (click to select a line)",
        "col_source": "Japanese (source)",
        "col_translation": "Translation",
        "prev": "◀ Back",
        "next": "Next ▶",
        "page_jump": "Jump to page:",
        "page_item": "Page {label}",
        "page_status": "Page {cur} / {n}",
        "page_status_intro": "before first page",
        "view_toggle": "⚙ Layout & sizes",
        "view_hint": "Show, resize or hide parts of this panel:",
        "view_preview": "Preview",
        "view_editor": "Script box",
        "view_table": "JP/EN table",
        "view_fonts": "Font list",
        "view_reset": "Reset layout",
        "font": "Font:",
        "font_search_ph": "Search font … (type to filter)",
        # --- text types ---
        "panel_text_type": "Text type",
        "text_type_label": "Kind of text:",
        "tt_apply": "Apply text type",
        "tt_none": "—",
        "tt_missing_font": "Wants “{font}” — not installed, using a stand-in.",
        "st_tt_pick": "Pick a kind of text first.",
        "st_tt_applied": "Text type “{name}” applied.",
        "panel_balloon": "Balloon",
        "balloon_tail": "Tail",
        "balloon_tail_tip": "Draw a tail hanging off the balloon. Move it to the speaker's mouth afterwards — TypeR can't know where that is.",
        "balloon_insert": "Insert balloon",
        "balloon_insert_tip": "Draw the balloon into the armed BubblR bubble, or into the selection. It becomes its own layer, so insert the balloon first and the text after it.",
        "balloon_hint": "The shape for: {kind}",
        "balloon_oval": "Oval (speech)",
        "balloon_cloud": "Cloud (thought)",
        "balloon_burst": "Burst (shout)",
        "balloon_radio": "Spiky (radio / phone)",
        "balloon_dashed": "Dashed (whisper)",
        "balloon_robot": "Cut corners (robot)",
        "balloon_wavy": "Wavy (weak voice)",
        "balloon_rough": "Rough (monster)",
        "st_balloon_no_box": "Select the area for the balloon first (or detect bubbles with BubblR).",
        "st_balloon_inserted": "Balloon “{shape}” inserted.",
        "st_balloon_fail": "Could not create the balloon layer: {exc}",
        "tt_dialogue": "Dialogue",
        "tt_emphasis": "Emphasis (bold-italic)",
        "tt_thought": "Thought",
        "tt_whisper": "Whisper",
        "tt_shout": "Shout / burst",
        "tt_weak": "Weak voice",
        "tt_radio": "Radio / phone / TV",
        "tt_robot": "Robot",
        "tt_telepathy": "Telepathy",
        "tt_monster": "Monster",
        "tt_song": "Song ♪",
        "tt_foreign": "Foreign language <>",
        "tt_distress": "Dying / unconscious",
        "tt_narration": "Narration / caption",
        "tt_monologue": "Inner monologue",
        "tt_offpanel": "Off-panel",
        "tt_aside": "Aside / handwritten",
        "tt_sfx": "SFX / sound word",
        "tt_signage": "Sign / label",
        "tt_display": "Title / display",
        "tt_tn": "Translator's note",
        "comic": "Comic lettering",
        "comic_tip": ("Comic-lettering grammar: keeps the double dash --\n"
                      "(comics do not use em dashes), an ellipsis is exactly\n"
                      "three dots and hugs the words, and a shouted question\n"
                      "is ?! with the question mark first."),
        "crossbar": "Crossbar-I",
        "crossbar_tip": ("Only the pronoun \u201cI\u201d and acronyms keep the barred I;\n"
                         "every other capital I is lowered so a comic font\n"
                         "renders the plain stroke. Needs a real comic font \u2014\n"
                         "with an ordinary font this looks like a typo."),
        "panel_google": "Google account (for .gdoc)",
        "g_client_label": "OAuth client ID (Desktop app):",
        "g_client_ph": "123-abc.apps.googleusercontent.com",
        "g_sign_in": "Sign in \u2026",
        "g_sign_out": "Sign out",
        "g_state_in": "Signed in.",
        "g_state_out": "Not signed in.",
        "g_hint": ("TypeR ships no Google credentials on purpose \u2014 this repository "
                   "is public. Create your own Cloud project, add an OAuth client of "
                   "type \u201cDesktop app\u201d and paste its ID here. Set the project to "
                   "\u201cIn production\u201d, otherwise Google drops the sign-in every 7 days."),
        "st_g_no_client": "Set your OAuth client ID in Setup first.",
        "st_g_not_signed_in": "Not signed in to Google yet (Setup \u2192 Google account).",
        "st_g_wait": "Finish the sign-in in your browser \u2026",
        "st_g_ok": "Signed in to Google.",
        "st_g_out": "Signed out.",
        "st_g_loading": "Fetching the document from Google \u2026",
        "st_g_loaded": "Loaded {name}: {n} lines, {c} comments.",
        "g_image_label": "Or: comments on a Drive image as the script",
        "g_image_ph": "paste the image's Drive share link",
        "g_image_btn": "Load image comments",
        "img_tab_label": "Image comments",
        "st_img_no_id": "Paste a Google Drive image link (or its file id) first.",
        "st_img_none": "That image has no comments (or none you can see).",
        "st_img_loaded": "Loaded {c} image comment(s) as a script.",
        "g_export_title": "Google Doc",
        "g_export_msg": ("A .gdoc is only a shortcut to Google Drive \u2014 the text lives "
                         "online.\n\nYour browser is already signed in, so it can export "
                         "the document without any setup. TypeR watches for the "
                         "download and loads it \u2014 comments included.\n\n(Signing in "
                         "under Setup \u2192 Google account skips this step.)"),
        "g_export_open": "Open export in browser",
        "st_g_waiting_dl": "Waiting for the download \u2026 save it and TypeR picks it up.",
        "st_g_dl_timeout": ("No download spotted. Open the saved .docx with "
                            "\u201cLoad script\u201d \u2014 it has the comments in it."),
        "g_export_cancel": "Cancel",
        "panel_comments": "Comments",
        "cm_line": "this line",
        "cm_page": "this page",
        "st_loaded_c": "Loaded {name}: {n} lines, {c} comments.",
        "panel_tt_fonts": "Fonts per text type",
        "ttf_open": "Choose fonts \u2026",
        "ttf_hint": ("Which font each kind of text uses. The defaults are the comic "
                     "faces the convention asks for \u2014 those are licensed, so if "
                     "one is not installed a stand-in is used until you pick your own."),
        "ttf_title": "Fonts per text type",
        "ttf_intro": ("Pick the font for each kind of text. Anything you do not set "
                      "keeps the catalogue default, which falls back to a font you "
                      "actually have installed."),
        "ttf_choose": "Choose \u2026",
        "ttf_reset_one": "Reset",
        "ttf_reset_one_tip": "Back to the default for this text type",
        "ttf_reset_all": "Reset all",
        "ttf_close": "Close",
        "ttf_default": "{font}  (default)",
        "ttf_pick_for": "Font for \u201c{name}\u201d",
        "ttf_add": "Add text type \u2026",
        "ttf_add_tip": "Create your own text type with a name and a font.",
        "ttf_add_name": "Name of the new text type:",
        "ttf_add_style_q": ("Give the new type the current style (font + size + "
                            "colours + effects), or the neutral default?"),
        "ttf_add_current": "Use current style",
        "ttf_add_default": "Default + pick font",
        "ttf_remove": "Remove",
        "ttf_remove_tip": "Delete this custom text type",
        "style": "Style:",
        "bold": "Bold",
        "italic": "Italic",
        "underline": "Underline",
        "ligatures": "Ligatures",
        "ligatures_tip": ("Keep OpenType ligatures. Turn OFF so pairs like "
                          "“fi”/“fl” don’t fuse in "
                          "hand-lettered fonts."),
        "align": "Alignment:",
        "align_left": "Left",
        "align_center": "Center",
        "align_right": "Right",
        "valign_label": "Vertical:",
        "valign_top": "Top",
        "valign_middle": "Middle",
        "valign_bottom": "Bottom",
        "active_ph": "Active line — edit the wording; press Enter for a manual line break.",
        "preview_label": "Live preview (font + settings):",
        "preview_empty": "Preview — the active line will appear here.",
        "preview_refresh_tip": "Refresh the live preview",
        "reset_btn": "Reset progress",
        "st_progress_reset": "Progress reset.",
        "case_label": "Case:",
        "case_none": "Normal",
        "case_upper": "UPPERCASE",
        "case_lower": "lowercase",
        "bold_sel": "Bold selection",
        "bold_sel_tip": "Make the selected words bold (wraps them in **…**). Select text first, then click. Click again on the same selection to remove bold.",
        "st_bold_no_sel": "Select some text in the active line first.",
        "tidy": "Smart punctuation",
        "tidy_tip": "Turn straight quotes into curly ones, ... into …, -- into —.",
        "round": "Round bubble (fit ellipse)",
        "round_tip": "Fit the text into the ellipse inside the selection so it doesn't overflow a round balloon. Only with auto-fit.",
        "vertical": "Vertical text (tategaki)",
        "vertical_tip": "Set the text in columns running top to bottom, right to left – for narrow bubbles and signs. Alignment places the block of columns, vertical alignment the text inside each column.",
        "shadow": "Shadow",
        "shadow_color_btn": "Shadow color …",
        "shadow_off": "Offset X / Y (px):",
        "shadow_tip": "Drop shadow drawn as an offset copy behind the text.",
        "preset": "Preset:",
        "preset_none": "(none)",
        "preset_save": "Save …",
        "preset_del": "Delete",
        "preset_import": "Import …",
        "preset_export": "Export …",
        "preset_name_dlg": "Save preset",
        "preset_name_prompt": "Preset name:",
        "preset_file_save": "Export presets",
        "preset_file_open": "Import presets",
        "preset_filter": "TypeR presets (*.json);;All files (*.*)",
        "preset_bundle_filter": "TypeR preset bundle (*.zip)",
        "preset_open_filter": "TypeR presets (*.zip *.json);;Preset bundle (*.zip);;"
                              "JSON (*.json);;All files (*.*)",
        "xlsx_filter": "Excel spreadsheet (*.xlsx)",
        "preset_export_fmt_title": "Export presets",
        "preset_export_fmt_prompt": "Export as:",
        "preset_fmt_bundle": "Presets + fonts (.zip) — installs itself elsewhere",
        "preset_fmt_json": "TypeR presets (JSON) — presets only, no fonts",
        "preset_fmt_xlsx": "Excel spreadsheet (.xlsx) — fonts of this manga",
        "st_preset_exported_bundle": "Exported {n} preset(s) with {fonts} font "
                                     "files ({missing} font(s) not installed "
                                     "here).",
        "st_preset_imported_bundle": "Imported {n} preset(s). Fonts: {inst} "
                                     "installed, {skip} already there, {fail} "
                                     "failed.",
        "font_scan": "Reading the installed fonts once — this can take a "
                     "moment with a large collection…",
        "st_preset_exported_xlsx": "Exported {n} fonts to an Excel table.",
        "xls_sheet_presets": "Fonts",
        "xls_default_char": "(default)",
        "col_character": "Character",
        "col_font": "Font",
        "col_purpose": "Used for",
        "st_preset_saved": "Preset ‘{name}’ saved.",
        "st_preset_applied": "Preset ‘{name}’ applied.",
        "st_preset_deleted": "Preset ‘{name}’ deleted.",
        "st_preset_none": "No preset selected.",
        "st_preset_name_empty": "Please enter a name.",
        "st_preset_exported": "Exported {n} preset(s).",
        "st_preset_imported": "Imported {n} preset(s).",
        "st_preset_import_fail": "Could not read the preset file.",
        "preset_import_excel": "Import fonts from Excel …",
        "preset_excel_open": "Open a font guide (.xlsx)",
        "preset_excel_filter": "Excel font guide (*.xlsx *.xlsm);;All files (*.*)",
        "st_preset_excel_no_header": "No 'Character' column found in the sheet.",
        "st_preset_excel_empty": "No fonts found in the sheet.",
        "st_preset_excel_imported": "Imported {n} font preset(s) for {c} character(s) into ‘{manga}’.",
        "group": "Manga:",
        "group_new": "New manga …",
        "group_del": "Delete manga",
        "group_default": "Manga 1",
        "group_new_dlg": "New manga",
        "group_name_prompt": "Manga name:",
        "char": "Character:",
        "char_new": "New character …",
        "char_del": "Delete character",
        "char_default": "Character 1",
        "auto_char": "Auto-pick character from “Name:”",
        "auto_char_tip": ("If a line starts with a speaker name like “Sakamoto: …” "
                          "and that name matches one of your characters, switch to "
                          "that character (and apply its first style preset). The "
                          "name is also removed from the inserted text."),
        "st_auto_char": "Auto-character: switched to ‘{name}’.",
        "auto_manga": "Auto-pick manga from the script",
        "auto_manga_tip": ("When loading a script, detect the manga from its file "
                           "name, a “Title:”/“Manga:” header or the first lines, and "
                           "switch to that saved manga automatically (if it matches "
                           "one). The character's default style preset is then "
                           "selected as well."),
        "st_auto_manga": "Auto-manga: switched to ‘{name}’.",
        "char_new_dlg": "New character",
        "char_name_prompt": "Character name:",
        "style_label": "Style preset:",
        "st_preset_saved_in": "Preset ‘{name}’ saved for ‘{char}’.",
        "st_group_saved": "Manga ‘{name}’ created.",
        "st_group_deleted": "Manga ‘{name}’ deleted.",
        "st_group_none": "No manga selected.",
        "st_group_name_empty": "Please enter a manga name.",
        "st_char_saved": "Character ‘{name}’ created.",
        "st_char_deleted": "Character ‘{name}’ deleted.",
        "st_char_none": "No character selected.",
        "st_char_name_empty": "Please enter a character name.",
        "size_max": "Max. size (px):",
        "size_fixed": "Size (px):",
        "size_tip": "With auto-fit on: the largest allowed size.\nOtherwise: a fixed size.",
        "color_btn": "Color …",
        "padding": "Inner padding (%):",
        "padding_tip": "Space between the text and the edge of the selection.",
        "spacing": "Line spacing (%):",
        "outline": "Outline",
        "outline_tip": "Outlines the text – e.g. a white outline so black text stays readable on a dark background.",
        "outline_color_btn": "Outline color …",
        "outline_width": "Width (px):",
        "outline2_color_btn": "2nd outline …",
        "outline2_width": "2nd width (0=off):",
        "outline2_color_dlg": "Choose 2nd outline color",
        "outline_pattern_label": "Outline pattern (texture fill, rasterized):",
        "outline_pattern_pick": "Choose pattern…",
        "outline_pattern_krita": "Krita pattern…",
        "outline_pattern_bad": "That image could not be loaded.",
        "outline_pattern_none": "No Krita patterns found.",
        "outline_pattern_target_label": "Pattern on:",
        "outline_pattern_t1": "1st outline",
        "outline_pattern_t2": "2nd outline",
        "outline_pattern_tboth": "Both outlines",
        "style_soft": "Soft outline",
        "style_soft_pattern": "Use pattern",
        "style_soft_w": "Width",
        "style_soft_blur": "Blur",
        "pattern_generate": "Generate…",
        "pattern_saved": "Saved…",
        "patlib_title": "Saved patterns",
        "patlib_name": "Pattern name:",
        "patlib_unnamed": "Pattern",
        "patlib_saved": "Saved pattern: {name}",
        "patlib_empty": "No saved patterns yet — make one with “Generate…”.",
        "patlib_delete": "Delete",
        "patgen_save": "★ Save to library…",
        "patgen_apply_sel": "▣ Fill the current selection",
        "patgen_gradient": "Gradient / screentone fade (dense → sparse)",
        "patgen_smooth": "Smooth colour",
        "panel_style_fill": "Pattern → selection",
        "fill_pattern_hint": "Pick or make a pattern, then select an area on the "
                             "canvas (e.g. your text) and click “Fill selection”.",
        "fill_pattern_pick": "Choose pattern…",
        "fill_apply_sel": "▣ Fill selection with this pattern",
        "sel_none": "Select an area on the canvas first (e.g. your text).",
        "sel_filled": "Filled the selection with the pattern.",
        "sel_pattern_layer": "Pattern fill",
        "auto": "Auto-fit to selection (size + wrap)",
        "auto_tip": "On: select a speech bubble, pick a font – the text wraps and scales to the largest size that fits.\nOff: fixed size, centered in the image/selection.",
        "hyphenate": "Hyphenate long words",
        "hyphenate_tip": "Split words that are too wide at correct syllable points (with a “-”). Lets the text reach a bigger size in narrow bubbles. Only with auto-fit.",
        "hyph_lang": "Hyphenation language:",
        "hyph_auto": "Auto",
        "hyph_en": "English",
        "hyph_de": "Deutsch",
        "hyph_es": "Español",
        "hyph_fr": "Français",
        "hyph_pt": "Português",
        "hyph_it": "Italiano",
        "insert_btn": "Insert translation  ⏎  (and go to next)",
        "color_dlg": "Choose text color",
        "outline_color_dlg": "Choose outline color",
        "file_dlg": "Choose a script file",
        "file_filter": "Scripts (*.docx *.xlsx *.xlsm *.odt *.txt *.md *.gdoc);;All files (*.*)",
        # status
        "st_no_doc": "No document is open.",
        "st_empty_line": "The active line is empty.",
        "st_create_fail": "Could not create the text layer: {exc}",
        "st_inserted_min": "Inserted at minimum size ({px}px) – the text is very long for the selection.",
        "st_inserted_fit": "Inserted: {px}px, {n} line(s).",
        "st_inserted": "Line inserted.",
        "st_not_found": "File not found.",
        "st_bad_zip": "The file is damaged or not a valid .docx/.xlsx/.odt.",
        "st_no_content": "No text content was found in the document.",
        "st_old_doc": "The old {fmt} format can't be read directly. Please open it and save as .docx/.xlsx or .txt.",
        "st_read_fail": "Could not read the file: {exc}",
        "st_loaded": "Loaded: {name}  ({n} units)",
        "st_already_open": "‘{name}’ is already open – switched to its tab.",
        "tab_untitled": "Untitled",
        "tab_rename_dlg": "Rename tab",
        "st_nothing": "Nothing loaded. Paste a script and click ‘Analyze’.",
        "st_no_font": "No font selected.",
        # main tabs
        "tab_type": "Type",
        "tab_style": "Style",
        "tab_presets": "Presets",
        "tab_setup": "Setup",
        "tab_shapr": "TextShapR",
        "tab_sfx": "SFX",
        "tab_fonts": "Fonts",
        "st_font_applied": "Font applied: {name}",
        "st_font_starred": "★ Added to favourites: {name}",
        "fav_star_current": "☆ Favourite",
        "fav_star_current_tip": "Add the selected font to the Fonts tab's "
                                "favourites.",
        "missing_btn": "Missing fonts",
        "missing_title": "Missing fonts",
        "missing_intro": "Which fonts used by the plugin aren't installed on "
                         "this computer? Pick a group:",
        "missing_fav": "Missing favourite fonts",
        "missing_sfx": "Missing SFX fonts",
        "missing_all": "All missing fonts",
        "missing_back": "← Back",
        "missing_head": "{have} fonts installed on this computer.\n"
                        "{title}: {missing} of {ref} used fonts are missing.",
        "missing_none_line": "None missing — all installed ✓",
        # Setup-tab section headings (group the flat settings list)
        "setup_h_general": "General",
        "setup_h_fonts": "Fonts",
        "setup_h_google": "Google account",
        "close": "Close",
        "preset_actions": "Preset actions (save, delete, import, export)",
        "outline_more": "Outline settings …",
        "shadow_more": "Shadow settings …",
        # TextShapR
        "shaper_btn": "TextShapR …",
        "shaper_btn_tip": ("Pick from several shapes for the current line: the "
                           "same text arranged into different line counts and "
                           "proportions, each auto-fitted to the selection."),
        "shaper_title": "TextShapR",
        "shaper_balanced": "Balanced",
        "shaper_round": "Round",
        "shaper_tall": "Tall",
        "shaper_wide": "Wide",
        "shaper_hyph": "Hyphenation",
        "shaper_dehyph": "De-hyphenate",
        "shaper_dehyph_tip": "Rejoin words the source split across a line (e.g. \"embar- rassing\") before reshaping",
        "shaper_hint": "Click a shape to test it. Shift+number applies and advances.",
        "shaper_break_label": "Edit line breaks:",
        "shaper_break_tip": "One line per line. Edit the breaks (or a word); the preview follows.",
        "shaper_auto": "Auto shape",
        "shaper_auto_tip": "Fit an ellipse when the selection is a round bubble",
        "shaper_live": "Live on canvas",
        "shaper_live_tip": "Insert the picked shape onto the page as you select (replacing)",
        "shaper_best": "\u2605 Best",
        "shaper_best_tip": "Jump to the recommended arrangement (best-scoring shape)",
        "shaper_match": "Match size",
        "shaper_match_tip": "Cap the size at the last inserted bubble, for a uniform page",
        "shaper_apply": "Apply",
        "shaper_apply_next": "Apply + next",
        "shaper_empty": ("No arrangements to show. Pick a font and make sure "
                         "the active line has text."),
        "shaper_no_doc": "No document open – previews use a default box.",
        # replace previously inserted layers on re-insert
        "replace_existing": "Replace previously inserted line",
        "replace_existing_tip": ("Inserting a line again first deletes the "
                                 "layer(s) TypeR created for it earlier – so "
                                 "trying several TextShapR shapes for the same "
                                 "bubble replaces the text instead of stacking "
                                 "copies. Off: every insert adds a new layer."),
        "st_replaced": "Replaced previous layer.",
        # optional character level for presets
        "presets_by_char": "Organize presets by character",
        "mainchar_btn": "Main characters …",
        "mainchar_hint": "Main characters sit at the top of the character and "
                         "preset dropdowns — handy once a series has more names "
                         "than fit on screen. Right-clicking the character "
                         "dropdown stars one straight away.",
        "mainchar_title": "Main characters",
        "mainchar_intro": "Star the characters you typeset most. They are "
                          "listed first (★) in the character dropdown and, in "
                          "simple mode, their presets head the preset list. "
                          "Nothing else changes — no preset is moved or lost.",
        "mainchar_manga": "Manga:",
        "mainchar_none": "This manga has no characters yet.",
        "mainchar_clear": "None of them",
        "mainchar_ctx_add": "★ Mark as main character",
        "mainchar_ctx_remove": "Remove from main characters",
        "st_mainchar_saved": "{n} main character(s) for “{manga}”.",
        "st_mainchar_on": "“{name}” is now a main character.",
        "st_mainchar_off": "“{name}” is no longer a main character.",
        "presets_by_char_tip": ("On: pick Manga → Character → preset – each "
                                "character can have its own font and style. "
                                "Off: pick Manga → preset – one flat list of "
                                "the manga's text presets (the character level "
                                "is hidden; new presets are stored under the "
                                "manga's default character)."),
        # BubblR tab (automatic bubble detection + per-bubble styles)
        "tab_bubblr": "BubblR",
        "bp_backend_heur": "Heuristic (built-in)",
        "bp_backend_ai": "AI (BubblR-AI)",
        "bp_backend_tip": ("How bubbles/free text are found: the built-in "
                           "heuristic or the learned model in the BubblR "
                           "'ai' folder (run ai\\setup.ps1 once)."),
        "bp_detect": "Detect bubbles",
        "bp_add_sel": "Add bubble from selection",
        "bp_reset": "Reset order",
        "bp_order": "Set order",
        "bp_order_tip": ("Click the bubbles in the order you want them "
                         "numbered (finish by clicking them all; click the "
                         "button again to cancel)."),
        "bp_sfxmark": "Mark SFX",
        "bp_sfxmark_tip": ("While active, click a box to switch it between "
                           "speech bubble and SFX / free text (blue). Click "
                           "the button again to leave the mode."),
        "bp_shapemark": "Toggle shape",
        "bp_shapemark_tip": ("While active, click a box to force its shape "
                             "round <-> rectangular (overrides the automatic "
                             "shape). Click the button again to leave."),
        "bp_edit": "Edit boxes",
        "bp_edit_tip": ("While active: drag on empty page to draw a new box, "
                        "drag a box to move it, drag a corner to resize. "
                        "Right-click removes. Shortcuts (click the image "
                        "first): E/Q next/prev, S = SFX, R = shape, Del = "
                        "remove."),
        "bp_panelorder": "Panel order",
        "bp_panelorder_tip": ("Detect comic panels (Magi AI) and renumber the "
                              "bubbles panel by panel — fixes wrong order "
                              "across side-by-side panels. First run downloads "
                              "the Magi model."),
        "bp_save_boxes": "Save boxes",
        "bp_save_boxes_tip": ("Save the current boxes to a .json file so you "
                              "can resume labelling this page later."),
        "bp_load_boxes": "Load boxes",
        "bp_load_boxes_tip": "Load boxes from a saved .json file.",
        "bp_model": "Model:",
        "bp_model_tip": ("Which detector weights to use. Auto uses your "
                         "fine-tuned model only if it beat the baseline in "
                         "eval; otherwise the baseline. Kitsumed = stronger "
                         "bubble model with real shape from a mask (bubbles "
                         "only); Hybrid = kitsumed bubbles + your model's SFX. "
                         "Both need the training setup and download on first "
                         "use."),
        "bp_model_auto": "Auto (best)",
        "bp_model_baseline": "Baseline",
        "bp_model_finetuned": "Fine-tuned",
        "bp_model_kitsumed": "kitsumed (bubbles + shape)",
        "bp_model_hybrid": "Hybrid (kitsumed + SFX)",
        "bp_conf": "Bubbles",
        "bp_conf_tip": ("Detection sensitivity: lower = more boxes (more "
                        "recall, more false ones), higher = fewer, surer "
                        "boxes."),
        "bp_sfxconf": "SFX",
        "bp_reset_tip": "Back to the automatic reading order.",
        "bp_chk_text": "Bubbles must contain text",
        "bp_chk_text_tip": ("Heuristic only: accept only white regions with "
                            "text inside (raw pages). Turn off for cleaned "
                            "pages."),
        "bp_chk_sfx": "Also detect free text (SFX)",
        "bp_chk_sfx_tip": ("Find handwritten SFX/mutterings without a bubble "
                           "and add them as blue boxes."),
        "bp_rtl": "Manga (right-to-left)",
        "bp_rtl_tip": ("Reading order: right-to-left for manga, unchecked = "
                       "left-to-right for western comics."),
        "bp_tile": "More accurate (slower)",
        "bp_tile_tip": ("Scan big pages in overlapping tiles so small SFX / "
                        "text are found at full resolution. Turn OFF on a "
                        "weak PC or laptop for a much faster (but coarser) "
                        "detection."),
        "bp_models": "Models…",
        "bp_models_tip": ("Show which detection models are installed and open "
                          "the folder they live in."),
        "bp_models_title": "BubblR models",
        "bp_models_none": ("No AI folder set yet — run a detection once and "
                           "point TypeR at your BubblR ai/ folder."),
        "bp_models_dir": "Models folder:",
        "bp_models_open": "Open folder",
        "bp_models_trainer": ("After training in BubblR Model Trainer the "
                              "weights land in runs\\<name>\\weights\\best.pt. "
                              "Export that to ONNX and copy it in here as "
                              "bubblr-finetuned.onnx to use it as 'finetuned'. "
                              "'auto' only uses it once eval.py promoted it."),
        "bp_overlay_tip": ("Click a box to make it the current bubble; "
                           "Ctrl+click boxes in the desired order to "
                           "renumber; right-click removes a box."),
        "bubble_of": "Bubble {cur} / {n}",
        "bubble_prev_tip": "Previous bubble (redo it — Insert replaces).",
        "bubble_next_tip": "Next bubble.",
        "panel_move_to": "Move to → {tab}",
        "panel_up": "Move up",
        "panel_down": "Move down",
        "panel_detach": "Detach into window",
        "panel_reattach": "Reattach into tab",
        "detach_host_hint": ("Detached TypeR panels appear here. "
                             "Use a panel's ⋮ menu → Reattach to send it back."),
        "panel_presets": "Presets",
        "panel_table": "Japanese / Translation",
        "panel_preview": "Preview",
        "panel_script": "Script",
        "panel_nav": "Navigation",
        "panel_active": "Text field",
        "panel_font": "Font & color",
        "panel_insert": "Insert",
        "panel_style_basic": "Style & alignment",
        "panel_style_size": "Size & fit",
        "panel_style_outline": "Outline",
        "panel_style_shadow": "Shadow",
        "panel_hyphenation": "Hyphenation",
        "panel_bubblr_detect": "Detection",
        "panel_bubblr_overlay": "Bubble preview",
        "panel_setup_general": "General",
        "panel_shapr": "TextShapR",
        "panel_sfx": "SFX Helper",
        "panel_layout_sizes": "Layout & sizes",
        "exp_section": "Experimental",
        "enable_bubblr": "Enable BubblR (automatic bubble detection)",
        "enable_shapr": "Enable TextShapR",
        "enable_sfx": "Enable SFX tab",
        "enable_fonts": "Enable Fonts tab",
        "enable_balloon": "Enable balloon tools (shape + Insert balloon)",
        "enable_patterns": "Enable pattern fills (experimental)",
        "enable_texttypes": "Enable text types / kinds (experimental)",
        "enable_balloon_tip": "Shows the Balloon panel on the Type tab: the "
                              "shape dropdown, the tail checkbox and “Insert "
                              "balloon”. Off by default — most pages already "
                              "have their balloons drawn.",
        "bp_hint": ("BubblR only marks the bubbles. Type the text on the "
                    "Type tab — Insert fills the current bubble and steps "
                    "to the next; ◀/▶ there redo a bubble."),
        "customize_layout": "Customize layout (rename && reorder tabs)",
        "customize_hint": ("Drag the tabs to reorder them; double-click a tab "
                           "to rename it. Panels can be moved between tabs in "
                           "a later update."),
        "layout_reset": "Reset layout",
        "layout_reset_done": "Layout reset to defaults.",
        "tab_rename_title": "Rename tab",
        "tab_rename_prompt": "Tab name (empty = default):",
        "bp_place_next": "Place && next",
        "bp_place_next_tip": ("Insert the current bubble's line and jump to "
                              "the next un-placed bubble — the Insert "
                              "rhythm of the Type tab."),
        "bp_selfollow": "Selection follows current bubble",
        "bp_selfollow_tip": ("The current bubble's rect becomes the Krita "
                             "selection, so Insert/TextShapR on the Type "
                             "tab work on it too. Off: your selection is "
                             "never touched."),
        "bp_sfx_db": "SFX words…",
        "bp_sfx_db_tip": ("Vocabulary used to recognize SFX lines in the "
                          "script (so they don't eat bubble slots while SFX "
                          "boxes are ignored). One word per line; "
                          "elongations like GOGOGOGO are matched "
                          "automatically."),
        "bp_sfx_dlg_hint": ("Your own SFX words, one per line (added to the "
                            "built-in list):"),
        "bp_src_sfx_suffix": ", {n} SFX skipped",
        "st_bp_all_done": "All mapped lines are placed.",
        "bp_src_page": "Lines: page {page} ({n} units)",
        "bp_src_all": "Lines: whole script ({n} units)",
        "bp_col_num": "#",
        "bp_col_text": "Text",
        "bp_col_style": "Style",
        "bp_up_tip": "Move the selected line up (previous box).",
        "bp_down_tip": "Move the selected line down (next box).",
        "bp_gap_add_tip": ("Insert a gap: this box gets no line; the lines "
                           "below shift down."),
        "bp_gap_rm_tip": ("Remove a gap: this box takes the next line; the "
                          "lines below shift up."),
        "bp_assign": "Assign current style",
        "bp_assign_tip": ("Store the current style (font, Style tab, preset) "
                          "on the selected row(s) – those bubbles keep it "
                          "when placing, others use the style active at "
                          "placement time."),
        "bp_unassign": "Use current style",
        "bp_unassign_tip": ("Remove the stored style from the selected "
                            "row(s); they follow the active style again "
                            "(auto-character styles are not re-applied)."),
        "bp_place": "Place all",
        "bp_place_sel": "Place selected",
        "bp_export": "Export training example",
        "bp_export_tip": ("Save this page + the corrected boxes as an AI "
                          "training sample into the ai folder's dataset."),
        "bp_pick_ai": "Select the BubblR 'ai' folder",
        "st_bp_no_script": "Load a script on the Type tab first.",
        "st_bp_unsupported": ("Unsupported image: {model}/{depth} – only "
                              "8-bit RGBA or grayscale documents work."),
        "st_bp_detected": "{n} box(es) detected.",
        "st_bp_none": "No bubbles detected.",
        "st_bp_mismatch": ("Warning: {b} boxes but {u} script lines – only "
                           "matching pairs will be placed."),
        "st_bp_no_sel": "No selection – select a bubble first.",
        "st_bp_added": "Box {n} added from the selection.",
        "st_bp_renumbered": "New order applied.",
        "st_bp_order_mode": ("Set order: click the bubbles in reading "
                             "order."),
        "st_bp_sfx_mode": ("Mark SFX: click a box to switch it between "
                           "bubble and SFX."),
        "st_bp_shape_mode": ("Toggle shape: click a box to flip it round / "
                             "rectangular."),
        "st_bp_edit_mode": ("Edit boxes: drag empty = new, drag box = move, "
                            "drag corner = resize, right-click = remove."),
        "st_bp_panels_wait": "Detecting panels (Magi)…",
        "st_bp_panels": "Reordered by {n} panel(s).",
        "st_bp_saved": "Boxes saved to {name}.",
        "st_bp_loaded": "Loaded {n} box(es).",
        "st_bp_style_set": "Style stored on {n} row(s).",
        "st_bp_style_cleared": "Stored style removed from {n} row(s).",
        "st_bp_no_rows": "Select row(s) in the table first.",
        "st_bp_placed": "{n} line(s) placed.",
        "st_bp_ai_missing": ("AI backend not found – run ai\\setup.ps1 once, "
                             "then select the 'ai' folder."),
        "st_bp_ai_error": "AI detection failed: {msg}",
        "st_bp_exported": "Training example saved: {name}",
        "st_bp_export_none": "Nothing to export – detect boxes first.",
        "view_bubblr": "BubblR preview",
        "view_bmap": "BubblR table",
    },
    "de": {
        "title": "TypeR für Krita",
        "language": "Sprache:",
        "load_btn": "Skript laden (.docx / .odt / .txt / .gdoc)",
        "script_label": "Skript (Datei laden oder direkt einfügen):",
        "editor_ph": "Hier das Skript einfügen oder oben eine Datei laden …",
        "skip_empty": "Leere Zeilen überspringen",
        "analyze_btn": "Analysieren · JP↔EN paaren",
        "add_line_btn": "+ Zeile",
        "add_line_dlg": "Zeile hinzufügen",
        "add_line_prompt": "Neue Zeile (Übersetzungstext):",
        "save_script_btn": "In Datei speichern",
        "save_script_dlg": "Skript speichern",
        "save_script_confirm": "Skriptdatei \"{name}\" mit dem aktuellen Text überschreiben?",
        "st_line_added": "Zeile zum Skript hinzugefügt.",
        "st_script_saved": "Skript gespeichert unter {name}.",
        "st_save_script_fail": "Skript konnte nicht gespeichert werden: {err}",
        "align_label": "Japanisch  ↔  Übersetzung   (Klick wählt die Zeile)",
        "col_source": "Japanisch (Quelle)",
        "col_translation": "Übersetzung",
        "prev": "◀ Zurück",
        "next": "Weiter ▶",
        "page_jump": "Zu Seite springen:",
        "page_item": "Seite {label}",
        "page_status": "Seite {cur} / {n}",
        "page_status_intro": "vor erster Seite",
        "view_toggle": "⚙ Layout & Größen",
        "view_hint": "Teile dieses Panels zeigen, vergrößern/verkleinern oder ausblenden:",
        "view_preview": "Vorschau",
        "view_editor": "Skript-Feld",
        "view_table": "JP/EN-Tabelle",
        "view_fonts": "Schriftliste",
        "view_reset": "Layout zurücksetzen",
        "font": "Schrift:",
        "font_search_ph": "Schrift suchen … (Tippen filtert)",
        # --- Textarten ---
        "panel_text_type": "Textart",
        "text_type_label": "Art des Textes:",
        "tt_apply": "Textart anwenden",
        "tt_none": "—",
        "tt_missing_font": "Braucht „{font}“ — nicht installiert, nutzt Ersatz.",
        "st_tt_pick": "Erst eine Textart wählen.",
        "st_tt_applied": "Textart „{name}“ angewendet.",
        "panel_balloon": "Sprechblase",
        "balloon_tail": "Schwanz",
        "balloon_tail_tip": "Zeichnet einen Schwanz an die Blase. Danach zum Mund der sprechenden Figur ziehen — wo der ist, kann TypeR nicht wissen.",
        "balloon_insert": "Blase einfügen",
        "balloon_insert_tip": "Zeichnet die Blase in die scharfgeschaltete BubblR-Blase oder in die Auswahl. Sie wird eine eigene Ebene — also erst die Blase einfügen, dann den Text.",
        "balloon_hint": "Die Form für: {kind}",
        "balloon_oval": "Oval (Sprache)",
        "balloon_cloud": "Wolke (Gedanke)",
        "balloon_burst": "Zacken (Schrei)",
        "balloon_radio": "Spitz (Funk / Telefon)",
        "balloon_dashed": "Gestrichelt (Flüstern)",
        "balloon_robot": "Gekappte Ecken (Roboter)",
        "balloon_wavy": "Wellig (schwache Stimme)",
        "balloon_rough": "Rau (Monster)",
        "st_balloon_no_box": "Erst den Bereich für die Blase auswählen (oder mit BubblR Blasen erkennen).",
        "st_balloon_inserted": "Blase „{shape}“ eingefügt.",
        "st_balloon_fail": "Konnte Blasenebene nicht erstellen: {exc}",
        "tt_dialogue": "Dialog",
        "tt_emphasis": "Betonung (fett-kursiv)",
        "tt_thought": "Gedanke",
        "tt_whisper": "Flüstern",
        "tt_shout": "Schreien / Burst",
        "tt_weak": "Schwache Stimme",
        "tt_radio": "Radio / Telefon / TV",
        "tt_robot": "Roboter",
        "tt_telepathy": "Telepathie",
        "tt_monster": "Monster",
        "tt_song": "Singen ♪",
        "tt_foreign": "Fremdsprache <>",
        "tt_distress": "Sterbend / bewusstlos",
        "tt_narration": "Erzählung / Caption",
        "tt_monologue": "Innerer Monolog",
        "tt_offpanel": "Off-Panel",
        "tt_aside": "Aside / Handschrift",
        "tt_sfx": "SFX / Soundwort",
        "tt_signage": "Schild / Label",
        "tt_display": "Titel / Display",
        "tt_tn": "Übersetzernotiz",
        "comic": "Comic-Lettering",
        "comic_tip": ("Comic-Lettering-Grammatik: beh\u00e4lt den Doppel-Dash --\n"
                      "(Comics nutzen keine Geviertstriche), Ellipse ist exakt\n"
                      "drei Punkte ohne Leerzeichen, und die geschriene Frage\n"
                      "ist ?! mit dem Fragezeichen zuerst."),
        "crossbar": "Crossbar-I",
        "crossbar_tip": ("Nur das Pronomen \u201eI\u201c und Akronyme behalten das I mit\n"
                         "Querbalken; jedes andere gro\u00dfe I wird gesenkt, damit ein\n"
                         "Comic-Font den glatten Strich zeigt. Braucht einen echten\n"
                         "Comic-Font \u2014 sonst sieht es wie ein Tippfehler aus."),
        "panel_google": "Google-Konto (f\u00fcr .gdoc)",
        "g_client_label": "OAuth-Client-ID (Desktop-App):",
        "g_client_ph": "123-abc.apps.googleusercontent.com",
        "g_sign_in": "Anmelden \u2026",
        "g_sign_out": "Abmelden",
        "g_state_in": "Angemeldet.",
        "g_state_out": "Nicht angemeldet.",
        "g_hint": ("TypeR liefert bewusst keine Google-Zugangsdaten mit \u2014 dieses "
                   "Repository ist \u00f6ffentlich. Leg ein eigenes Cloud-Projekt an, "
                   "erstelle einen OAuth-Client vom Typ \u201eDesktop-App\u201c und trag die "
                   "ID hier ein. Stell das Projekt auf \u201eIn production\u201c, sonst "
                   "verwirft Google die Anmeldung alle 7 Tage."),
        "st_g_no_client": "Erst die OAuth-Client-ID unter Einstellungen eintragen.",
        "st_g_not_signed_in": "Noch nicht bei Google angemeldet (Einstellungen \u2192 Google-Konto).",
        "st_g_wait": "Anmeldung im Browser abschlie\u00dfen \u2026",
        "st_g_ok": "Bei Google angemeldet.",
        "st_g_out": "Abgemeldet.",
        "st_g_loading": "Dokument wird von Google geholt \u2026",
        "st_g_loaded": "{name} geladen: {n} Zeilen, {c} Kommentare.",
        "g_image_label": "Oder: Kommentare auf einem Drive-Bild als Skript",
        "g_image_ph": "Freigabe-Link des Bildes einfügen",
        "g_image_btn": "Bild-Kommentare laden",
        "img_tab_label": "Bild-Kommentare",
        "st_img_no_id": "Erst einen Google-Drive-Bild-Link (oder die Datei-ID) einfügen.",
        "st_img_none": "Dieses Bild hat keine (sichtbaren) Kommentare.",
        "st_img_loaded": "{c} Bild-Kommentar(e) als Skript geladen.",
        "g_export_title": "Google-Doc",
        "g_export_msg": ("Eine .gdoc ist nur eine Verkn\u00fcpfung zu Google Drive \u2014 der "
                         "Text liegt online.\n\nDein Browser ist bereits angemeldet, "
                         "kann das Dokument also ohne jedes Setup exportieren. TypeR "
                         "wartet auf den Download und l\u00e4dt ihn \u2014 samt Kommentaren."
                         "\n\n(Anmelden unter Einstellungen \u2192 Google-Konto spart diesen "
                         "Schritt.)"),
        "g_export_open": "Export im Browser \u00f6ffnen",
        "st_g_waiting_dl": "Warte auf den Download \u2026 speichern, TypeR holt ihn ab.",
        "st_g_dl_timeout": ("Kein Download gefunden. \u00d6ffne die gespeicherte .docx "
                            "mit \u201eSkript laden\u201c \u2014 die Kommentare sind darin."),
        "g_export_cancel": "Abbrechen",
        "panel_comments": "Kommentare",
        "cm_line": "diese Zeile",
        "cm_page": "diese Seite",
        "st_loaded_c": "{name} geladen: {n} Zeilen, {c} Kommentare.",
        "panel_tt_fonts": "Schriften je Textart",
        "ttf_open": "Schriften w\u00e4hlen \u2026",
        "ttf_hint": ("Welche Schrift jede Textart benutzt. Die Vorgaben sind die "
                     "Comic-Schriften der Konvention \u2014 die sind lizenziert, also "
                     "nimmt TypeR einen Ersatz, bis du deine eigene w\u00e4hlst."),
        "ttf_title": "Schriften je Textart",
        "ttf_intro": ("W\u00e4hle die Schrift f\u00fcr jede Textart. Was du nicht setzt, "
                      "beh\u00e4lt die Katalog-Vorgabe \u2014 die f\u00e4llt auf eine Schrift "
                      "zur\u00fcck, die du tats\u00e4chlich installiert hast."),
        "ttf_choose": "W\u00e4hlen \u2026",
        "ttf_reset_one": "Zur\u00fccksetzen",
        "ttf_reset_one_tip": "Zur\u00fcck zur Vorgabe f\u00fcr diese Textart",
        "ttf_reset_all": "Alle zur\u00fccksetzen",
        "ttf_close": "Schlie\u00dfen",
        "ttf_default": "{font}  (Vorgabe)",
        "ttf_pick_for": "Schrift f\u00fcr \u201e{name}\u201c",
        "ttf_add": "Textart hinzuf\u00fcgen \u2026",
        "ttf_add_tip": "Eine eigene Textart mit Name und Schrift anlegen.",
        "ttf_add_name": "Name der neuen Textart:",
        "ttf_add_style_q": ("Der neuen Textart den aktuellen Stil geben (Schrift "
                            "+ Gr\u00f6\u00dfe + Farben + Effekte) oder den neutralen "
                            "Standard?"),
        "ttf_add_current": "Aktuellen Stil \u00fcbernehmen",
        "ttf_add_default": "Standard + Schrift w\u00e4hlen",
        "ttf_remove": "Entfernen",
        "ttf_remove_tip": "Diese eigene Textart l\u00f6schen",
        "style": "Stil:",
        "bold": "Fett",
        "italic": "Kursiv",
        "underline": "Unterstrichen",
        "ligatures": "Ligaturen",
        "ligatures_tip": ("OpenType-Ligaturen behalten. AUS, damit Paare wie "
                          "„fi“/„fl“ in handgeletterten Schriften nicht "
                          "verschmelzen."),
        "align": "Ausrichtung:",
        "align_left": "Links",
        "align_center": "Zentriert",
        "align_right": "Rechts",
        "valign_label": "Vertikal:",
        "valign_top": "Oben",
        "valign_middle": "Mitte",
        "valign_bottom": "Unten",
        "active_ph": "Aktive Zeile — Wortlaut anpassen; Enter setzt einen manuellen Umbruch.",
        "preview_label": "Live-Vorschau (Schrift + Einstellungen):",
        "preview_empty": "Vorschau — die aktive Zeile erscheint hier.",
        "preview_refresh_tip": "Live-Vorschau aktualisieren",
        "reset_btn": "Fortschritt zurücksetzen",
        "st_progress_reset": "Fortschritt zurückgesetzt.",
        "case_label": "Schreibung:",
        "case_none": "Normal",
        "case_upper": "GROSSBUCHSTABEN",
        "case_lower": "kleinbuchstaben",
        "bold_sel": "Auswahl fett",
        "bold_sel_tip": "Markierte Wörter fett machen (umschließt sie mit **…**). Erst Text markieren, dann klicken. Erneut auf dieselbe Auswahl klicken hebt Fett wieder auf.",
        "st_bold_no_sel": "Bitte zuerst Text in der aktiven Zeile markieren.",
        "tidy": "Typografie verbessern",
        "tidy_tip": "Gerade Anführungszeichen werden typografisch, ... wird …, -- wird —.",
        "round": "Runde Sprechblase (Ellipse)",
        "round_tip": "Text in die Ellipse innerhalb der Auswahl einpassen, damit er nicht über eine runde Blase hinausragt. Nur mit Auto-Anpassung.",
        "vertical": "Vertikaltext (Tategaki)",
        "vertical_tip": "Text in Spalten von oben nach unten setzen, rechts beginnend – für schmale Blasen und Schilder. Die Ausrichtung platziert dann den Spaltenblock, die vertikale Ausrichtung den Text in der Spalte.",
        "shadow": "Schatten",
        "shadow_color_btn": "Schattenfarbe …",
        "shadow_off": "Versatz X / Y (px):",
        "shadow_tip": "Schlagschatten als versetzte Kopie hinter dem Text.",
        "preset": "Preset:",
        "preset_none": "(keins)",
        "preset_save": "Speichern …",
        "preset_del": "Löschen",
        "preset_import": "Importieren …",
        "preset_export": "Exportieren …",
        "preset_name_dlg": "Preset speichern",
        "preset_name_prompt": "Preset-Name:",
        "preset_file_save": "Presets exportieren",
        "preset_file_open": "Presets importieren",
        "preset_filter": "TypeR-Presets (*.json);;Alle Dateien (*.*)",
        "preset_bundle_filter": "TypeR-Preset-Paket (*.zip)",
        "preset_open_filter": "TypeR-Presets (*.zip *.json);;Preset-Paket (*.zip);;"
                              "JSON (*.json);;Alle Dateien (*.*)",
        "xlsx_filter": "Excel-Tabelle (*.xlsx)",
        "preset_export_fmt_title": "Presets exportieren",
        "preset_export_fmt_prompt": "Exportieren als:",
        "preset_fmt_bundle": "Presets + Schriften (.zip) – installiert sich selbst",
        "preset_fmt_json": "TypeR-Presets (JSON) – nur Presets, ohne Schriften",
        "preset_fmt_xlsx": "Excel-Tabelle (.xlsx) – Schriften dieses Mangas",
        "st_preset_exported_bundle": "{n} Preset(s) mit {fonts} Schriftdateien "
                                     "exportiert ({missing} Schrift(en) hier "
                                     "nicht installiert).",
        "st_preset_imported_bundle": "{n} Preset(s) importiert. Schriften: "
                                     "{inst} installiert, {skip} schon "
                                     "vorhanden, {fail} fehlgeschlagen.",
        "font_scan": "Installierte Schriften werden einmalig eingelesen – bei "
                     "vielen Fonts dauert das einen Moment …",
        "st_preset_exported_xlsx": "{n} Schriften als Excel-Tabelle exportiert.",
        "xls_sheet_presets": "Schriften",
        "xls_default_char": "(Standard)",
        "col_character": "Charakter",
        "col_font": "Schrift",
        "col_purpose": "Wofür",
        "st_preset_saved": "Preset ‚{name}‘ gespeichert.",
        "st_preset_applied": "Preset ‚{name}‘ angewendet.",
        "st_preset_deleted": "Preset ‚{name}‘ gelöscht.",
        "st_preset_none": "Kein Preset gewählt.",
        "st_preset_name_empty": "Bitte einen Namen eingeben.",
        "st_preset_exported": "{n} Preset(s) exportiert.",
        "st_preset_imported": "{n} Preset(s) importiert.",
        "st_preset_import_fail": "Preset-Datei konnte nicht gelesen werden.",
        "preset_import_excel": "Fonts aus Excel importieren …",
        "preset_excel_open": "Font-Guide öffnen (.xlsx)",
        "preset_excel_filter": "Excel-Font-Guide (*.xlsx *.xlsm);;Alle Dateien (*.*)",
        "st_preset_excel_no_header": "Keine ‚Character‘-Spalte in der Tabelle gefunden.",
        "st_preset_excel_empty": "Keine Fonts in der Tabelle gefunden.",
        "st_preset_excel_imported": "{n} Font-Preset(s) für {c} Charakter(e) in ‚{manga}‘ importiert.",
        "group": "Manga:",
        "group_new": "Neues Manga …",
        "group_del": "Manga löschen",
        "group_default": "Manga 1",
        "group_new_dlg": "Neues Manga",
        "group_name_prompt": "Manga-Name:",
        "char": "Charakter:",
        "char_new": "Neuer Charakter …",
        "char_del": "Charakter löschen",
        "char_default": "Charakter 1",
        "auto_char": "Charakter aus „Name:“ automatisch wählen",
        "auto_char_tip": ("Beginnt eine Zeile mit einem Sprechernamen wie "
                          "„Sakamoto: …“ und passt der Name zu einem deiner "
                          "Charaktere, wird zu diesem Charakter gewechselt (und "
                          "sein erstes Stil-Preset angewendet). Der Name wird "
                          "außerdem aus dem eingefügten Text entfernt."),
        "st_auto_char": "Auto-Charakter: zu ‚{name}‘ gewechselt.",
        "auto_manga": "Manga aus dem Script automatisch wählen",
        "auto_manga_tip": ("Beim Laden eines Scripts den Manga am Dateinamen, an "
                           "einer „Title:“/„Manga:“-Kopfzeile oder den ersten "
                           "Zeilen erkennen und automatisch zu diesem gespeicherten "
                           "Manga wechseln (sofern einer passt). Danach wird auch "
                           "das Standard-Stil-Preset des Charakters gewählt."),
        "st_auto_manga": "Auto-Manga: zu ‚{name}‘ gewechselt.",
        "char_new_dlg": "Neuer Charakter",
        "char_name_prompt": "Charakter-Name:",
        "style_label": "Stil-Preset:",
        "st_preset_saved_in": "Preset ‚{name}‘ für ‚{char}‘ gespeichert.",
        "st_group_saved": "Manga ‚{name}‘ erstellt.",
        "st_group_deleted": "Manga ‚{name}‘ gelöscht.",
        "st_group_none": "Kein Manga gewählt.",
        "st_group_name_empty": "Bitte einen Manga-Namen eingeben.",
        "st_char_saved": "Charakter ‚{name}‘ erstellt.",
        "st_char_deleted": "Charakter ‚{name}‘ gelöscht.",
        "st_char_none": "Kein Charakter gewählt.",
        "st_char_name_empty": "Bitte einen Charakter-Namen eingeben.",
        "size_max": "Max. Größe (px):",
        "size_fixed": "Größe (px):",
        "size_tip": "Bei aktiver Auto-Anpassung: größte erlaubte Schriftgröße.\nSonst: feste Schriftgröße.",
        "color_btn": "Farbe …",
        "padding": "Innenabstand (%):",
        "padding_tip": "Luft zwischen Text und Rand der Auswahl.",
        "spacing": "Zeilenabstand (%):",
        "outline": "Kontur",
        "outline_tip": "Umrandet den Text – z. B. weiße Kontur, damit schwarzer Text auf dunklem Hintergrund lesbar bleibt.",
        "outline_color_btn": "Konturfarbe …",
        "outline_width": "Breite (px):",
        "outline2_color_btn": "2. Kontur …",
        "outline2_width": "2. Breite (0=aus):",
        "outline2_color_dlg": "2. Konturfarbe wählen",
        "outline_pattern_label": "Outline-Muster (Textur-Füllung, gerastert):",
        "outline_pattern_pick": "Muster wählen…",
        "outline_pattern_krita": "Krita-Muster…",
        "outline_pattern_bad": "Bild konnte nicht geladen werden.",
        "outline_pattern_none": "Keine Krita-Muster gefunden.",
        "outline_pattern_target_label": "Muster auf:",
        "outline_pattern_t1": "1. Outline",
        "outline_pattern_t2": "2. Outline",
        "outline_pattern_tboth": "Beide Outlines",
        "style_soft": "Weiche Outline",
        "style_soft_pattern": "Muster nutzen",
        "style_soft_w": "Breite",
        "style_soft_blur": "Weichzeichnen",
        "pattern_generate": "Erzeugen…",
        "pattern_saved": "Gespeicherte…",
        "patlib_title": "Gespeicherte Muster",
        "patlib_name": "Muster-Name:",
        "patlib_unnamed": "Muster",
        "patlib_saved": "Muster gespeichert: {name}",
        "patlib_empty": "Noch keine gespeicherten Muster — mit „Erzeugen…“ anlegen.",
        "patlib_delete": "Löschen",
        "patgen_save": "★ In Bibliothek speichern…",
        "patgen_apply_sel": "▣ Auf aktuelle Auswahl anwenden",
        "panel_style_fill": "Muster → Auswahl",
        "fill_pattern_hint": "Muster wählen/erzeugen, dann eine Fläche auf der "
                             "Leinwand markieren (z. B. deinen Text) und „Auswahl "
                             "füllen“ klicken.",
        "fill_pattern_pick": "Muster wählen…",
        "fill_apply_sel": "▣ Auswahl mit diesem Muster füllen",
        "sel_none": "Erst eine Fläche auf der Leinwand markieren (z. B. deinen Text).",
        "sel_filled": "Auswahl mit dem Muster gefüllt.",
        "sel_pattern_layer": "Muster-Füllung",
        # Muster-Generator (Dialog)
        "patgen_title": "Muster erstellen",
        "patgen_kind": "Muster:",
        "patgen_fg": "Tintenfarbe",
        "patgen_bg": "Hintergrund",
        "patgen_transparent": "Transparenter Hintergrund",
        "patgen_size": "Größe",
        "patgen_gap": "Abstand",
        "patgen_hstripes": "Waagerechte Streifen",
        "patgen_vstripes": "Senkrechte Streifen",
        "patgen_checker": "Schachbrett",
        "patgen_dots": "Punkte (Raster)",
        "patgen_grid": "Gitter",
        "patgen_crosshatch": "Kreuzschraffur",
        "patgen_diagonal": "Diagonale Linien",
        "patgen_noise": "Sand / Rauschen (Körnung)",
        "patgen_sparkle": "Funkeln (Sterne)",
        "patgen_gradient": "Verlauf / Raster-Verlauf (dicht → dünn)",
        "patgen_smooth": "Weicher Farbverlauf",
        "auto": "Automatisch in Auswahl einpassen (Größe + Umbruch)",
        "auto_tip": "An: Auswahl als Sprechblase markieren, Font wählen – der Text bricht um und wird auf die größte passende Größe skaliert.\nAus: feste Größe, in der Bild-/Auswahlmitte.",
        "hyphenate": "Lange Wörter trennen",
        "hyphenate_tip": "Zu breite Wörter an korrekten Silbengrenzen trennen (mit „-“). So passt der Text in schmale Blasen größer. Nur mit Auto-Anpassung.",
        "hyph_lang": "Trennsprache:",
        "hyph_auto": "Auto",
        "hyph_en": "English",
        "hyph_de": "Deutsch",
        "hyph_es": "Español",
        "hyph_fr": "Français",
        "hyph_pt": "Português",
        "hyph_it": "Italiano",
        "insert_btn": "Übersetzung einfügen  ⏎  (und zur nächsten)",
        "color_dlg": "Textfarbe wählen",
        "outline_color_dlg": "Konturfarbe wählen",
        "file_dlg": "Skript-Datei wählen",
        "file_filter": "Skripte (*.docx *.xlsx *.xlsm *.odt *.txt *.md *.gdoc);;Alle Dateien (*.*)",
        # status
        "st_no_doc": "Kein geöffnetes Dokument.",
        "st_empty_line": "Die aktive Zeile ist leer.",
        "st_create_fail": "Konnte Textebene nicht erstellen: {exc}",
        "st_inserted_min": "Eingefügt bei Minimalgröße ({px}px) – Text ist für die Auswahl sehr lang.",
        "st_inserted_fit": "Eingefügt: {px}px, {n} Zeile(n).",
        "st_inserted": "Zeile eingefügt.",
        "st_not_found": "Datei nicht gefunden.",
        "st_bad_zip": "Datei ist beschädigt oder keine gültige .docx/.xlsx/.odt.",
        "st_no_content": "Im Dokument wurde kein Textinhalt gefunden.",
        "st_old_doc": "Das alte {fmt}-Format kann nicht direkt gelesen werden. Bitte öffnen und als .docx/.xlsx oder .txt speichern.",
        "st_read_fail": "Konnte Datei nicht lesen: {exc}",
        "st_loaded": "Geladen: {name}  ({n} Einheiten)",
        "st_already_open": "‚{name}‘ ist schon offen – zum Tab gewechselt.",
        "tab_untitled": "Unbenannt",
        "tab_rename_dlg": "Tab umbenennen",
        "st_nothing": "Nichts geladen. Erst Skript einfügen und ‚Analysieren‘ klicken.",
        "st_no_font": "Keine Schrift gewählt.",
        # main tabs
        "tab_type": "Setzen",
        "tab_style": "Stil",
        "tab_presets": "Presets",
        "tab_setup": "Einstellungen",
        "tab_shapr": "TextShapR",
        "tab_sfx": "SFX",
        "tab_fonts": "Schriften",
        "st_font_applied": "Schrift übernommen: {name}",
        "st_font_starred": "★ Zu Favoriten hinzugefügt: {name}",
        "fav_star_current": "☆ Favorit",
        "fav_star_current_tip": "Die gewählte Schrift zu den Favoriten im "
                                "Schriften-Tab hinzufügen.",
        # Font-Favoriten (Fonts-Tab)
        "fav_intro": "Schriften mit ★ merken und in Kategorien einsortieren "
                     "(Dialog, SFX, …). Eine Schrift kann in mehreren Kategorien "
                     "liegen. Nach Kategorie filtern oder nach Namen suchen, dann "
                     "doppelklicken zum Übernehmen.",
        "fav_all": "Alle Favoriten",
        "fav_uncat": "(ohne Kategorie)",
        "fav_search_ph": "Schrift suchen…",
        "fav_add_current": "★ Aktuelle Schrift merken",
        "fav_add": "Schrift hinzufügen…",
        "fav_edit_cats": "Kategorien…",
        "fav_remove": "Entfernen",
        "fav_manage": "Kategorien verwalten…",
        "fav_apply": "Schrift übernehmen",
        "fav_none": "Noch keine Favoriten. Mit „★ Aktuelle Schrift merken“ "
                    "anlegen.",
        "fav_pick_font": "Favoriten-Schrift hinzufügen",
        "fav_choose_cats": "Kategorien für diese Schrift:",
        "fav_new_cat_ph": "Neue Kategorie…",
        "fav_new_cat_add": "Hinzufügen",
        "fav_manage_title": "Kategorien verwalten",
        "fav_rename": "Umbenennen",
        "fav_delete": "Löschen",
        "fav_delete_font_q": "„{name}“ aus den Favoriten entfernen?",
        "fav_count": "{n} Schriften",
        "fav_size": "Aa",
        "fav_size_tip": "Vorschaugröße – ziehen, um die Schriften größer zu sehen.",
        "fav_ctx_edit": "Kategorien bearbeiten…",
        "fav_ctx_delete": "Löschen…",
        "fav_import": "Importieren…",
        "fav_export": "Exportieren…",
        "fav_import_done": "{n} neue Favoriten-Schriften importiert.",
        "fav_export_done": "{n} Favoriten mit {fonts} Font-Dateien exportiert "
                           "({missing} auf diesem PC nicht gefunden).",
        "fav_import_bundle_done": "{n} Favoriten importiert.\nSchriften: {inst} "
                                  "installiert, {skip} schon vorhanden, {fail} "
                                  "fehlgeschlagen.\nStarte Krita neu, falls eine "
                                  "neu installierte Schrift noch nicht auftaucht.",
        "fav_export_filter": "TypeR-Font-Paket (*.zip)",
        "fav_import_filter": "TypeR-Font-Paket (*.zip);;JSON (*.json);;"
                             "Alle Dateien (*)",
        "fav_io_error": "Datei konnte nicht gelesen/geschrieben werden:\n{err}",
        "fav_missing_title": "Fehlende Schriften",
        "fav_missing_intro": "Diese Favoriten-Schriften sind auf diesem Rechner "
                             "nicht installiert. Installiere/lade sie herunter, "
                             "damit der Text in der gewünschten Schrift erscheint:",
        "fav_missing_none": "Alle Favoriten-Schriften sind installiert. ✓",
        "missing_btn": "Fehlende Schriften",
        "missing_title": "Fehlende Schriften",
        "missing_intro": "Welche vom Plugin genutzten Schriften sind auf diesem "
                         "Rechner nicht installiert? Gruppe wählen:",
        "missing_fav": "Fehlende Favoriten-Schriften",
        "missing_sfx": "Fehlende SFX-Schriften",
        "missing_all": "Alle fehlenden Schriften",
        "missing_back": "← Zurück",
        "missing_head": "{have} Schriften auf diesem Rechner installiert.\n"
                        "{title}: {missing} von {ref} genutzten Schriften fehlen.",
        "missing_none_line": "Keine fehlen — alle installiert ✓",
        # Überschriften im Einstellungen-Tab (gruppieren die flache Liste)
        "setup_h_general": "Allgemein",
        "setup_h_fonts": "Schriften",
        "setup_h_google": "Google-Konto",
        "close": "Schließen",
        "preset_actions": "Preset-Aktionen (speichern, löschen, importieren, exportieren)",
        "outline_more": "Kontur-Einstellungen …",
        "shadow_more": "Schatten-Einstellungen …",
        # TextShapR
        "shaper_btn": "TextShapR …",
        "shaper_btn_tip": ("Für die aktive Zeile aus mehreren Formen wählen: "
                           "derselbe Text in verschiedenen Zeilenzahlen und "
                           "Proportionen, jeweils automatisch in die Auswahl "
                           "eingepasst."),
        "shaper_title": "TextShapR",
        "shaper_balanced": "Ausgewogen",
        "shaper_round": "Rund",
        "shaper_tall": "Hoch",
        "shaper_wide": "Breit",
        "shaper_hyph": "Silbentrennung",
        "shaper_dehyph": "Ent-Trennen",
        "shaper_dehyph_tip": "Vom Quelltext getrennte Wörter (z. B. \"embar- rassing\") vor dem Umbrechen wieder zusammenfügen",
        "shaper_hint": "Klick testet eine Form. Umschalt+Zahl fügt ein und geht weiter.",
        "shaper_break_label": "Umbrüche bearbeiten:",
        "shaper_break_tip": "Eine Zeile pro Zeile. Umbrüche (oder ein Wort) ändern; Vorschau folgt.",
        "shaper_auto": "Form auto",
        "shaper_auto_tip": "Ellipse fitten, wenn die Auswahl eine runde Blase ist",
        "shaper_live": "Live auf Leinwand",
        "shaper_live_tip": "Gewählte Form beim Auswählen direkt auf die Seite einfügen (ersetzend)",
        "shaper_best": "\u2605 Bester",
        "shaper_best_tip": "Zur empfohlenen Anordnung springen (am besten bewertete Form)",
        "shaper_match": "Größe angleichen",
        "shaper_match_tip": "Größe auf die zuletzt eingefügte Blase deckeln (einheitliche Seite)",
        "shaper_apply": "Einfügen",
        "shaper_apply_next": "Einfügen + weiter",
        "shaper_empty": ("Keine Formen anzeigbar. Erst eine Schrift wählen und "
                         "sicherstellen, dass die aktive Zeile Text hat."),
        "shaper_no_doc": "Kein Dokument offen – Vorschau nutzt eine Standard-Box.",
        # replace previously inserted layers on re-insert
        "replace_existing": "Bereits eingefügte Zeile ersetzen",
        "replace_existing_tip": ("Beim erneuten Einfügen einer Zeile werden die "
                                 "zuvor von TypeR dafür erstellten Ebene(n) "
                                 "gelöscht – das Ausprobieren mehrerer "
                                 "TextShapR-Formen für dieselbe Blase ersetzt "
                                 "den Text also, statt Kopien zu stapeln. Aus: "
                                 "jedes Einfügen erzeugt eine neue Ebene."),
        "st_replaced": "Vorherige Ebene ersetzt.",
        # optional character level for presets
        "presets_by_char": "Presets nach Charakteren gliedern",
        "mainchar_btn": "Hauptcharaktere …",
        "mainchar_hint": "Hauptcharaktere stehen ganz oben in der Charakter- "
                         "und der Preset-Liste – praktisch, sobald eine Serie "
                         "mehr Namen hat, als auf den Schirm passen. Ein "
                         "Rechtsklick auf die Charakter-Liste markiert direkt.",
        "mainchar_title": "Hauptcharaktere",
        "mainchar_intro": "Markiere die Charaktere, die du am häufigsten "
                          "setzt. Sie stehen dann mit ★ ganz oben in der "
                          "Charakter-Liste, und im einfachen Modus stehen ihre "
                          "Presets oben in der Preset-Liste. Sonst ändert sich "
                          "nichts – kein Preset wird verschoben oder gelöscht.",
        "mainchar_manga": "Manga:",
        "mainchar_none": "Dieses Manga hat noch keine Charaktere.",
        "mainchar_clear": "Keiner davon",
        "mainchar_ctx_add": "★ Als Hauptcharakter markieren",
        "mainchar_ctx_remove": "Nicht mehr als Hauptcharakter",
        "st_mainchar_saved": "{n} Hauptcharakter(e) für „{manga}“.",
        "st_mainchar_on": "„{name}“ ist jetzt Hauptcharakter.",
        "st_mainchar_off": "„{name}“ ist kein Hauptcharakter mehr.",
        "presets_by_char_tip": ("An: Manga → Charakter → Preset wählen – jeder "
                                "Charakter kann eigene Schrift und eigenen Stil "
                                "haben. Aus: Manga → Preset wählen – eine "
                                "flache Liste aller Text-Presets des Mangas "
                                "(die Charakter-Ebene ist ausgeblendet; neue "
                                "Presets landen beim Standard-Charakter des "
                                "Mangas)."),
        # BubblR tab (automatic bubble detection + per-bubble styles)
        "tab_bubblr": "BubblR",
        "bp_backend_heur": "Heuristik (eingebaut)",
        "bp_backend_ai": "KI (BubblR-AI)",
        "bp_backend_tip": ("Wie Bubbles/freier Text gefunden werden: "
                           "eingebaute Heuristik oder das gelernte Modell im "
                           "BubblR-'ai'-Ordner (einmalig ai\\setup.ps1 "
                           "ausführen)."),
        "bp_detect": "Bubbles erkennen",
        "bp_add_sel": "Bubble aus Auswahl hinzufügen",
        "bp_reset": "Reihenfolge zurücksetzen",
        "bp_order": "Reihenfolge festlegen",
        "bp_order_tip": ("Die Bubbles in der gewünschten Reihenfolge "
                         "anklicken (fertig, wenn alle geklickt sind; nochmal "
                         "auf den Knopf = abbrechen)."),
        "bp_sfxmark": "SFX markieren",
        "bp_sfxmark_tip": ("Wenn aktiv, eine Box anklicken, um zwischen "
                           "Sprechblase und SFX / freier Text (blau) zu "
                           "wechseln. Nochmal auf den Knopf = beenden."),
        "bp_shapemark": "Form wechseln",
        "bp_shapemark_tip": ("Wenn aktiv, eine Box anklicken, um ihre Form "
                             "rund <-> eckig zu erzwingen (überschreibt die "
                             "automatische Form). Nochmal auf den Knopf = "
                             "beenden."),
        "bp_edit": "Boxen bearbeiten",
        "bp_edit_tip": ("Wenn aktiv: auf leerer Seite ziehen = neue Box, "
                        "Box ziehen = verschieben, Ecke ziehen = Größe. "
                        "Rechtsklick entfernt. Tasten (vorher aufs Bild "
                        "klicken): E/Q vor/zurück, S = SFX, R = Form, "
                        "Entf = löschen."),
        "bp_panelorder": "Panel-Reihenfolge",
        "bp_panelorder_tip": ("Comic-Panels erkennen (Magi-KI) und die Bubbles "
                              "panelweise neu nummerieren — behebt falsche "
                              "Reihenfolge bei nebeneinanderliegenden Panels. "
                              "Erster Aufruf lädt das Magi-Modell herunter."),
        "bp_save_boxes": "Boxen speichern",
        "bp_save_boxes_tip": ("Aktuelle Boxen als .json speichern, um das "
                              "Labeln dieser Seite später fortzusetzen."),
        "bp_load_boxes": "Boxen laden",
        "bp_load_boxes_tip": "Boxen aus einer gespeicherten .json-Datei laden.",
        "bp_model": "Modell:",
        "bp_model_tip": ("Welche Detektor-Gewichte. Auto nutzt dein "
                         "trainiertes Modell nur, wenn es im Test besser "
                         "war als das Basis-Modell; sonst das Basis-Modell. "
                         "Kitsumed = stärkeres Blasen-Modell mit echter Form "
                         "aus einer Maske (nur Blasen); Hybrid = kitsumed-"
                         "Blasen + SFX deines Modells. Beide brauchen das "
                         "Training-Setup und laden beim ersten Mal herunter."),
        "bp_model_auto": "Auto (bestes)",
        "bp_model_baseline": "Basis",
        "bp_model_finetuned": "Trainiert",
        "bp_model_kitsumed": "kitsumed (Blasen + Form)",
        "bp_model_hybrid": "Hybrid (kitsumed + SFX)",
        "bp_conf": "Bubbles",
        "bp_conf_tip": ("Empfindlichkeit: niedriger = mehr Boxen (mehr "
                        "Treffer, aber auch mehr falsche), höher = weniger, "
                        "sicherere Boxen."),
        "bp_sfxconf": "SFX",
        "bp_reset_tip": "Zurück zur automatischen Lesereihenfolge.",
        "bp_chk_text": "Bubbles müssen Text enthalten",
        "bp_chk_text_tip": ("Nur Heuristik: nur weiße Flächen mit Text darin "
                            "akzeptieren (Raw-Seiten). Für gecleante Seiten "
                            "ausschalten."),
        "bp_chk_sfx": "Auch freien Text finden (SFX)",
        "bp_chk_sfx_tip": ("Handgeschriebene SFX/Murmeln ohne Bubble finden "
                           "und als blaue Boxen hinzufügen."),
        "bp_rtl": "Manga (rechts-nach-links)",
        "bp_rtl_tip": ("Leserichtung: rechts-nach-links für Manga, ohne "
                       "Haken = links-nach-rechts für westliche Comics."),
        "bp_tile": "Genauer (langsamer)",
        "bp_tile_tip": ("Große Seiten in überlappenden Kacheln absuchen, "
                        "damit kleine SFX / Texte in voller Auflösung "
                        "gefunden werden. Auf schwachem PC oder Laptop "
                        "ausschalten für eine viel schnellere (aber gröbere) "
                        "Erkennung."),
        "bp_models": "Modelle…",
        "bp_models_tip": ("Zeigt, welche Erkennungs-Modelle installiert sind, "
                          "und öffnet den Ordner, in dem sie liegen."),
        "bp_models_title": "BubblR-Modelle",
        "bp_models_none": ("Noch kein AI-Ordner gesetzt — einmal eine "
                           "Erkennung starten und TypeR auf deinen "
                           "BubblR-ai/-Ordner zeigen lassen."),
        "bp_models_dir": "Modell-Ordner:",
        "bp_models_open": "Ordner öffnen",
        "bp_models_trainer": ("Nach dem Training im BubblR Model Trainer "
                              "liegen die Gewichte in "
                              "runs\\<name>\\weights\\best.pt. Diese nach "
                              "ONNX exportieren und hier als "
                              "bubblr-finetuned.onnx ablegen, um sie als "
                              "'finetuned' zu nutzen. 'auto' benutzt sie erst, "
                              "wenn eval.py sie promoted hat."),
        "bp_overlay_tip": ("Klick macht eine Box zur aktuellen Bubble; "
                           "Strg+Klick in gewünschter Reihenfolge "
                           "nummeriert neu; Rechtsklick entfernt eine "
                           "Box."),
        "bubble_of": "Bubble {cur} / {n}",
        "bubble_prev_tip": ("Vorherige Bubble (neu machen — Insert "
                            "ersetzt)."),
        "bubble_next_tip": "Nächste Bubble.",
        "panel_move_to": "Verschieben nach → {tab}",
        "panel_up": "Nach oben",
        "panel_down": "Nach unten",
        "panel_detach": "In Fenster lösen",
        "panel_reattach": "Zurück in Tab",
        "detach_host_hint": ("Abgelöste TypeR-Panels erscheinen hier. "
                             "Über ⋮ → Zurück in Tab zurückholen."),
        "panel_presets": "Presets",
        "panel_table": "Japanisch / Übersetzung",
        "panel_preview": "Vorschau",
        "panel_script": "Skript",
        "panel_nav": "Navigation",
        "panel_active": "Textfeld",
        "panel_font": "Schrift & Farbe",
        "panel_insert": "Einfügen",
        "panel_style_basic": "Stil & Ausrichtung",
        "panel_style_size": "Größe & Anpassung",
        "panel_style_outline": "Kontur",
        "panel_style_shadow": "Schatten",
        "panel_hyphenation": "Silbentrennung",
        "panel_bubblr_detect": "Erkennung",
        "panel_bubblr_overlay": "Bubble-Vorschau",
        "panel_setup_general": "Allgemein",
        "panel_shapr": "TextShapR",
        "panel_sfx": "SFX Helper",
        "panel_layout_sizes": "Layout & Größen",
        "exp_section": "Experimentell",
        "enable_bubblr": "BubblR aktivieren (automatische Bubble-Erkennung)",
        "enable_shapr": "TextShapR aktivieren",
        "enable_sfx": "SFX-Tab aktivieren",
        "enable_fonts": "Schriften-Tab aktivieren",
        "enable_balloon": "Blasen-Werkzeuge aktivieren (Form + Blase einfügen)",
        "enable_patterns": "Muster-Füllungen aktivieren (experimentell)",
        "enable_texttypes": "Textarten aktivieren (experimentell)",
        "enable_balloon_tip": "Zeigt das Panel „Sprechblase“ im Type-Tab: das "
                              "Formen-Dropdown, den Schwanz-Haken und „Blase "
                              "einfügen“. Standardmäßig aus — meist sind die "
                              "Blasen auf der Seite ja schon gezeichnet.",
        "bp_hint": ("BubblR markiert nur die Bubbles. Den Text schreibst du "
                    "im Type-Tab — Insert füllt die aktuelle Bubble und geht "
                    "weiter; ◀/▶ dort machen eine Bubble neu."),
        "customize_layout": "Layout anpassen (Tabs umbenennen && umordnen)",
        "customize_hint": ("Tabs ziehen zum Umordnen; Doppelklick auf einen "
                           "Tab zum Umbenennen. Panels lassen sich in einem "
                           "späteren Update zwischen Tabs verschieben."),
        "layout_reset": "Layout zurücksetzen",
        "layout_reset_done": "Layout auf Standard zurückgesetzt.",
        "tab_rename_title": "Tab umbenennen",
        "tab_rename_prompt": "Tab-Name (leer = Standard):",
        "bp_place_next": "Platzieren && weiter",
        "bp_place_next_tip": ("Zeile der aktuellen Bubble einfügen und zur "
                              "nächsten offenen Bubble springen — der "
                              "Insert-Rhythmus des Type-Tabs."),
        "bp_selfollow": "Auswahl folgt aktueller Bubble",
        "bp_selfollow_tip": ("Das Rechteck der aktuellen Bubble wird zur "
                             "Krita-Auswahl, damit auch Insert/TextShapR "
                             "vom Type-Tab darauf arbeiten. Aus: deine "
                             "Auswahl wird nie angefasst."),
        "bp_sfx_db": "SFX-Wörter…",
        "bp_sfx_db_tip": ("Wortschatz, mit dem SFX-Zeilen im Skript erkannt "
                          "werden (damit sie keine Bubbles verbrauchen, "
                          "solange SFX-Boxen ignoriert werden). Ein Wort "
                          "pro Zeile; Dehnungen wie GOGOGOGO werden "
                          "automatisch erkannt."),
        "bp_sfx_dlg_hint": ("Eigene SFX-Wörter, eins pro Zeile (ergänzt die "
                            "eingebaute Liste):"),
        "bp_src_sfx_suffix": ", {n} SFX übersprungen",
        "st_bp_all_done": "Alle zugeordneten Zeilen sind platziert.",
        "bp_src_page": "Zeilen: Seite {page} ({n} Einheiten)",
        "bp_src_all": "Zeilen: ganzes Skript ({n} Einheiten)",
        "bp_col_num": "#",
        "bp_col_text": "Text",
        "bp_col_style": "Stil",
        "bp_up_tip": "Markierte Zeile nach oben schieben (vorherige Box).",
        "bp_down_tip": "Markierte Zeile nach unten schieben (nächste Box).",
        "bp_gap_add_tip": ("Lücke einfügen: diese Box bekommt keine Zeile; "
                           "die folgenden Zeilen rutschen nach unten."),
        "bp_gap_rm_tip": ("Lücke entfernen: diese Box bekommt die nächste "
                          "Zeile; die folgenden rutschen nach oben."),
        "bp_assign": "Aktuellen Stil zuweisen",
        "bp_assign_tip": ("Speichert den aktuellen Stil (Schrift, Stil-Tab, "
                          "Preset) auf den markierten Zeilen – diese Bubbles "
                          "behalten ihn beim Platzieren, alle anderen nutzen "
                          "den dann aktiven Stil."),
        "bp_unassign": "Aktuellen Stil verwenden",
        "bp_unassign_tip": ("Entfernt den gespeicherten Stil von den "
                            "markierten Zeilen; sie folgen wieder dem "
                            "aktiven Stil (Auto-Charakter-Stile werden nicht "
                            "erneut gesetzt)."),
        "bp_place": "Alle platzieren",
        "bp_place_sel": "Markierte platzieren",
        "bp_export": "Trainingsbeispiel exportieren",
        "bp_export_tip": ("Diese Seite + die korrigierten Boxen als "
                          "KI-Trainingsbeispiel im dataset des ai-Ordners "
                          "speichern."),
        "bp_pick_ai": "BubblR-'ai'-Ordner auswählen",
        "st_bp_no_script": "Bitte zuerst ein Skript im Type-Tab laden.",
        "st_bp_unsupported": ("Nicht unterstütztes Bild: {model}/{depth} – "
                              "nur 8-Bit-RGBA- oder Graustufen-Dokumente "
                              "funktionieren."),
        "st_bp_detected": "{n} Box(en) erkannt.",
        "st_bp_none": "Keine Bubbles erkannt.",
        "st_bp_mismatch": ("Achtung: {b} Boxen, aber {u} Skriptzeilen – nur "
                           "passende Paare werden platziert."),
        "st_bp_no_sel": "Keine Auswahl – bitte zuerst eine Bubble auswählen.",
        "st_bp_added": "Box {n} aus der Auswahl hinzugefügt.",
        "st_bp_renumbered": "Neue Reihenfolge übernommen.",
        "st_bp_order_mode": ("Reihenfolge festlegen: Bubbles in Lesereihen"
                             "folge anklicken."),
        "st_bp_sfx_mode": ("SFX markieren: Box anklicken, um zwischen "
                           "Bubble und SFX zu wechseln."),
        "st_bp_shape_mode": ("Form wechseln: Box anklicken, um sie rund / "
                             "eckig zu schalten."),
        "st_bp_edit_mode": ("Boxen bearbeiten: leer ziehen = neu, Box "
                            "ziehen = verschieben, Ecke = Größe, Rechtsklick "
                            "= löschen."),
        "st_bp_panels_wait": "Panels werden erkannt (Magi)…",
        "st_bp_panels": "Nach {n} Panel(s) neu geordnet.",
        "st_bp_style_set": "Stil auf {n} Zeile(n) gespeichert.",
        "st_bp_style_cleared": "Gespeicherter Stil von {n} Zeile(n) entfernt.",
        "st_bp_no_rows": "Bitte zuerst Zeile(n) in der Tabelle markieren.",
        "st_bp_placed": "{n} Zeile(n) platziert.",
        "st_bp_ai_missing": ("KI-Backend nicht gefunden – einmalig "
                             "ai\\setup.ps1 ausführen und den 'ai'-Ordner "
                             "auswählen."),
        "st_bp_ai_error": "KI-Erkennung fehlgeschlagen: {msg}",
        "st_bp_exported": "Trainingsbeispiel gespeichert: {name}",
        "st_bp_export_none": "Nichts zu exportieren – erst Boxen erkennen.",
        "view_bubblr": "BubblR-Vorschau",
        "view_bmap": "BubblR-Tabelle",
    },
    # Core localization for additional UI languages; any key not listed here
    # falls back to English via _tr().
    "es": {
        "title": "TypeR para Krita",
        "language": "Idioma:",
        "load_btn": "Cargar guion (.docx / .xlsx / .odt / .txt)",
        "script_label": "Guion (carga un archivo o pega directamente):",
        "skip_empty": "Omitir líneas vacías",
        "analyze_btn": "Analizar · emparejar JP↔EN",
        "align_label": "Japonés  ↔  Traducción   (clic para elegir la línea)",
        "col_source": "Japonés (origen)",
        "col_translation": "Traducción",
        "prev": "◀ Atrás",
        "next": "Siguiente ▶",
        "reset_btn": "Reiniciar progreso",
        "font": "Fuente:",
        "style": "Estilo:",
        "bold": "Negrita",
        "italic": "Cursiva",
        "underline": "Subrayado",
        "align": "Alineación:",
        "align_left": "Izquierda",
        "align_center": "Centro",
        "align_right": "Derecha",
        "valign_label": "Vertical:",
        "valign_top": "Arriba",
        "valign_middle": "Centro",
        "valign_bottom": "Abajo",
        "case_label": "Mayúsculas:",
        "case_none": "Normal",
        "case_upper": "MAYÚSCULAS",
        "case_lower": "minúsculas",
        "tidy": "Tipografía",
        "round": "Globo redondo (elipse)",
        "vertical": "Texto vertical (tategaki)",
        "shadow": "Sombra",
        "outline": "Contorno",
        "auto": "Ajustar a la selección (tamaño + salto)",
        "hyphenate": "Dividir palabras largas",
        "hyph_lang": "Idioma de división:",
        "size_max": "Tamaño máx. (px):",
        "size_fixed": "Tamaño (px):",
        "color_btn": "Color …",
        "padding": "Margen interior (%):",
        "spacing": "Interlineado (%):",
        "page_jump": "Ir a la página:",
        "insert_btn": "Insertar traducción  ⏎  (y siguiente)",
    },
    "fr": {
        "title": "TypeR pour Krita",
        "language": "Langue :",
        "load_btn": "Charger le script (.docx / .xlsx / .odt / .txt)",
        "script_label": "Script (chargez un fichier ou collez directement) :",
        "skip_empty": "Ignorer les lignes vides",
        "analyze_btn": "Analyser · associer JP↔EN",
        "align_label": "Japonais  ↔  Traduction   (clic pour choisir la ligne)",
        "col_source": "Japonais (source)",
        "col_translation": "Traduction",
        "prev": "◀ Retour",
        "next": "Suivant ▶",
        "reset_btn": "Réinitialiser la progression",
        "font": "Police :",
        "style": "Style :",
        "bold": "Gras",
        "italic": "Italique",
        "underline": "Souligné",
        "align": "Alignement :",
        "align_left": "Gauche",
        "align_center": "Centré",
        "align_right": "Droite",
        "valign_label": "Vertical :",
        "valign_top": "Haut",
        "valign_middle": "Milieu",
        "valign_bottom": "Bas",
        "case_label": "Casse :",
        "case_none": "Normal",
        "case_upper": "MAJUSCULES",
        "case_lower": "minuscules",
        "tidy": "Typographie",
        "round": "Bulle ronde (ellipse)",
        "vertical": "Texte vertical (tategaki)",
        "shadow": "Ombre",
        "outline": "Contour",
        "auto": "Ajuster à la sélection (taille + retour)",
        "hyphenate": "Couper les mots longs",
        "hyph_lang": "Langue de césure :",
        "size_max": "Taille max. (px) :",
        "size_fixed": "Taille (px) :",
        "color_btn": "Couleur …",
        "padding": "Marge intérieure (%) :",
        "spacing": "Interligne (%) :",
        "page_jump": "Aller à la page :",
        "insert_btn": "Insérer la traduction  ⏎  (et suivant)",
    },
    "pt": {
        "title": "TypeR para Krita",
        "language": "Idioma:",
        "load_btn": "Carregar roteiro (.docx / .xlsx / .odt / .txt)",
        "script_label": "Roteiro (carregue um arquivo ou cole direto):",
        "skip_empty": "Ignorar linhas vazias",
        "analyze_btn": "Analisar · parear JP↔EN",
        "align_label": "Japonês  ↔  Tradução   (clique para escolher a linha)",
        "col_source": "Japonês (origem)",
        "col_translation": "Tradução",
        "prev": "◀ Voltar",
        "next": "Próximo ▶",
        "reset_btn": "Reiniciar progresso",
        "font": "Fonte:",
        "style": "Estilo:",
        "bold": "Negrito",
        "italic": "Itálico",
        "underline": "Sublinhado",
        "align": "Alinhamento:",
        "align_left": "Esquerda",
        "align_center": "Centro",
        "align_right": "Direita",
        "valign_label": "Vertical:",
        "valign_top": "Topo",
        "valign_middle": "Meio",
        "valign_bottom": "Base",
        "case_label": "Caixa:",
        "case_none": "Normal",
        "case_upper": "MAIÚSCULAS",
        "case_lower": "minúsculas",
        "tidy": "Tipografia",
        "round": "Balão redondo (elipse)",
        "vertical": "Texto vertical (tategaki)",
        "shadow": "Sombra",
        "outline": "Contorno",
        "auto": "Ajustar à seleção (tamanho + quebra)",
        "hyphenate": "Hifenizar palavras longas",
        "hyph_lang": "Idioma da hifenização:",
        "size_max": "Tamanho máx. (px):",
        "size_fixed": "Tamanho (px):",
        "color_btn": "Cor …",
        "padding": "Margem interna (%):",
        "spacing": "Entrelinha (%):",
        "page_jump": "Ir para a página:",
        "insert_btn": "Inserir tradução  ⏎  (e próximo)",
    },
    "it": {
        "title": "TypeR per Krita",
        "language": "Lingua:",
        "load_btn": "Carica script (.docx / .xlsx / .odt / .txt)",
        "script_label": "Script (carica un file o incolla direttamente):",
        "skip_empty": "Salta righe vuote",
        "analyze_btn": "Analizza · abbina JP↔EN",
        "align_label": "Giapponese  ↔  Traduzione   (clic per scegliere la riga)",
        "col_source": "Giapponese (origine)",
        "col_translation": "Traduzione",
        "prev": "◀ Indietro",
        "next": "Avanti ▶",
        "reset_btn": "Azzera avanzamento",
        "font": "Carattere:",
        "style": "Stile:",
        "bold": "Grassetto",
        "italic": "Corsivo",
        "underline": "Sottolineato",
        "align": "Allineamento:",
        "align_left": "Sinistra",
        "align_center": "Centro",
        "align_right": "Destra",
        "valign_label": "Verticale:",
        "valign_top": "Alto",
        "valign_middle": "Centro",
        "valign_bottom": "Basso",
        "case_label": "Maiuscole:",
        "case_none": "Normale",
        "case_upper": "MAIUSCOLO",
        "case_lower": "minuscolo",
        "tidy": "Tipografia",
        "round": "Nuvoletta tonda (ellisse)",
        "vertical": "Testo verticale (tategaki)",
        "shadow": "Ombra",
        "outline": "Contorno",
        "auto": "Adatta alla selezione (dimensione + a capo)",
        "hyphenate": "Sillaba le parole lunghe",
        "hyph_lang": "Lingua sillabazione:",
        "size_max": "Dimensione max (px):",
        "size_fixed": "Dimensione (px):",
        "color_btn": "Colore …",
        "padding": "Margine interno (%):",
        "spacing": "Interlinea (%):",
        "page_jump": "Vai alla pagina:",
        "insert_btn": "Inserisci traduzione  ⏎  (e avanti)",
    },
}

LANG_ORDER = [("en", "English"), ("de", "Deutsch"), ("es", "Español"),
              ("fr", "Français"), ("pt", "Português"), ("it", "Italiano")]


# ---------------------------------------------------------------------------
# File readers  (pure standard library, no dependencies)
# ---------------------------------------------------------------------------

def _local(tag):
    """Return a tag name without its XML namespace, e.g. '{...}p' -> 'p'."""
    return tag.rsplit('}', 1)[-1]


def _decode_bytes(data):
    """Decode bytes to text without ever failing.

    Order: UTF-8 (with/without BOM), then Windows-1252, finally latin-1.
    latin-1 can map every byte and therefore never raises an exception, so a
    "character not readable" error can never occur.
    """
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _read_plain(path):
    with open(path, "rb") as fh:
        return _decode_bytes(fh.read())


def _read_docx(path):
    """Extract text from a .docx file.

    A .docx is a ZIP; the body text lives in word/document.xml. Standalone
    paragraphs <w:p> become one line each (<w:tab> -> tab, <w:br>/<w:cr> -> line
    break, as before).

    A TABLE is read COLUMN-AWARE: every row becomes one line whose cells are
    separated by a TAB. That lets a two-column "source | translation" script be
    paired by column (see langpair.split_columns), which works for ANY source
    language – not only Japanese. Inside a cell, tabs/breaks become spaces so a
    real TAB only ever marks a column boundary.
    """
    with zipfile.ZipFile(path) as zf:
        raw = zf.read("word/document.xml")
    root = ET.fromstring(raw)

    def para_text(p, cell):
        buf = []
        for node in p.iter():
            name = _local(node.tag)
            if name == "t":
                if node.text:
                    buf.append(node.text)
            elif name == "tab":
                buf.append(" " if cell else "\t")
            elif name in ("br", "cr"):
                buf.append(" " if cell else "\n")
        return "".join(buf)

    def cell_text(tc):
        # a cell may hold several paragraphs; join them with a space and keep it
        # free of tabs/newlines so the row stays a clean TAB-separated record
        ps = [n for n in tc.iter() if _local(n.tag) == "p"]
        return " ".join(para_text(p, True).strip() for p in ps).strip()

    lines = []

    def walk(parent):
        for child in parent:
            name = _local(child.tag)
            if name == "tbl":
                for tr in child:
                    if _local(tr.tag) != "tr":
                        continue
                    cells = [cell_text(tc) for tc in tr
                             if _local(tc.tag) == "tc"]
                    if cells:
                        lines.append("\t".join(cells))
            elif name == "p":
                lines.append(para_text(child, False))
            else:
                walk(child)            # descend into <w:body>, content controls …

    walk(root)
    return "\n".join(lines)


def _read_odt(path):
    """Extract text from a .odt file (LibreOffice / OpenOffice).

    A .odt is also a ZIP; the content lives in content.xml. Paragraphs are
    <text:p> / <text:h>; line break <text:line-break>, tab <text:tab>,
    multiple spaces <text:s>.
    """
    with zipfile.ZipFile(path) as zf:
        raw = zf.read("content.xml")
    root = ET.fromstring(raw)

    def collect(elem, out):
        # text of this node
        if elem.text:
            out.append(elem.text)
        for child in elem:
            name = _local(child.tag)
            if name == "line-break":
                out.append("\n")
            elif name == "tab":
                out.append("\t")
            elif name == "s":
                count = 1
                for k, v in child.attrib.items():
                    if _local(k) == "c":
                        try:
                            count = int(v)
                        except ValueError:
                            count = 1
                out.append(" " * count)
            else:
                collect(child, out)
            if child.tail:
                out.append(child.tail)

    lines = []
    for para in root.iter():
        if _local(para.tag) in ("p", "h"):
            out = []
            collect(para, out)
            lines.append("".join(out))
    return "\n".join(lines)


def _col_index(ref):
    """Column number from a cell reference such as 'B2' -> 2."""
    idx = 0
    for ch in ref:
        if ch.isalpha():
            idx = idx * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return idx


def _read_xlsx(path):
    """Extract text from an Excel file (.xlsx).

    A .xlsx is a ZIP of XML. Text is usually stored in xl/sharedStrings.xml and
    referenced from the cells by an index. Every non-empty cell becomes its own
    line (row by row, left to right). If Japanese sits in one column and English
    in the next, that produces source/translation back to back - exactly what
    the later JP/EN pairing expects.
    """
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()

        shared = []
        if "xl/sharedStrings.xml" in names:
            sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sroot:
                if _local(si.tag) != "si":
                    continue
                parts = [t.text for t in si.iter()
                         if _local(t.tag) == "t" and t.text]
                shared.append("".join(parts))

        sheets = sorted(n for n in names
                        if n.startswith("xl/worksheets/") and n.endswith(".xml"))
        if not sheets:
            return ""
        wroot = ET.fromstring(zf.read(sheets[0]))

        lines = []
        for row in wroot.iter():
            if _local(row.tag) != "row":
                continue
            cells = []
            for c in row:
                if _local(c.tag) != "c":
                    continue
                col = _col_index(c.attrib.get("r", ""))
                ctype = c.attrib.get("t", "")
                val = ""
                if ctype == "s":
                    for ch in c:
                        if _local(ch.tag) == "v" and ch.text is not None:
                            try:
                                val = shared[int(ch.text)]
                            except (ValueError, IndexError):
                                val = ""
                            break
                elif ctype == "inlineStr":
                    val = "".join(t.text for t in c.iter()
                                  if _local(t.tag) == "t" and t.text)
                else:
                    for ch in c:
                        if _local(ch.tag) in ("v", "t") and ch.text is not None:
                            val = ch.text
                            break
                cells.append((col, val))
            cells.sort(key=lambda cv: cv[0])
            # one line per ROW, columns separated by a TAB, so a 2-column
            # source/translation sheet is paired by column (works for any source
            # language). Single-cell rows stay a plain line.
            vals = [("" if val is None else str(val)) for _col, val in cells]
            while vals and vals[-1].strip() == "":
                vals.pop()
            if not vals:
                continue
            lines.append("\t".join(vals) if len(vals) >= 2 else vals[0])
        return "\n".join(lines)


def _read_xlsx_grid(path):
    """Read an .xlsx as a list of rows, each a list of cell strings (missing
    cells filled with ""). Unlike `_read_xlsx` (which flattens to text for the
    script parser) this keeps the row/column layout, so a character/style
    font-guide sheet can be turned into presets."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sroot:
                if _local(si.tag) != "si":
                    continue
                parts = [t.text for t in si.iter()
                         if _local(t.tag) == "t" and t.text]
                shared.append("".join(parts))
        sheets = sorted(n for n in names
                        if n.startswith("xl/worksheets/") and n.endswith(".xml"))
        if not sheets:
            return []
        wroot = ET.fromstring(zf.read(sheets[0]))
        grid = []
        for row in wroot.iter():
            if _local(row.tag) != "row":
                continue
            cells, maxcol = {}, -1
            for c in row:
                if _local(c.tag) != "c":
                    continue
                col = _col_index(c.attrib.get("r", ""))
                ctype = c.attrib.get("t", "")
                val = ""
                if ctype == "s":
                    for ch in c:
                        if _local(ch.tag) == "v" and ch.text is not None:
                            try:
                                val = shared[int(ch.text)]
                            except (ValueError, IndexError):
                                val = ""
                            break
                elif ctype == "inlineStr":
                    val = "".join(t.text for t in c.iter()
                                  if _local(t.tag) == "t" and t.text)
                else:
                    for ch in c:
                        if _local(ch.tag) in ("v", "t") and ch.text is not None:
                            val = ch.text
                            break
                cells[col] = "" if val is None else str(val)
                maxcol = max(maxcol, col)
            grid.append([cells.get(i, "") for i in range(maxcol + 1)])
        return grid


def read_script(path):
    """Read a script file and return it as plain text (newline separated).

    Deliberately raises a clear, readable exception only on real problems
    (missing file, old .doc/.xls format), never because of individual
    characters.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return _read_docx(path)
    if ext == ".odt":
        return _read_odt(path)
    if ext in (".xlsx", ".xlsm"):
        return _read_xlsx(path)
    if ext == ".doc":
        raise OldDocError(".doc")
    if ext == ".xls":
        raise OldDocError(".xls")
    # treat .txt, .md and everything else as plain text
    return _read_plain(path)


# ---------------------------------------------------------------------------
# Line management
# ---------------------------------------------------------------------------

def split_lines(text, skip_empty):
    """Split text into lines. \r\n and \r are normalized."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if skip_empty:
        lines = [ln for ln in lines if ln.strip() != ""]
    return lines


# ---------------------------------------------------------------------------
# Insert a text layer into Krita
# ---------------------------------------------------------------------------

def _advance(fm, s):
    """Pixel width of a string (with a fallback for older Qt versions)."""
    try:
        return fm.horizontalAdvance(s)
    except AttributeError:
        return fm.width(s)


def _make_measurer(family, line_spacing, bold=False, italic=False):
    """measurer(px) -> (width_of, space_w, line_h, ascent, descent) via Qt.

    Bold/italic feed into the measurement so that auto-fit accounts for the
    actual (e.g. wider, bold) text width. width_of accepts a string OR a Word
    object (layout): for a Word the bold runs are measured individually with
    the matching (normal or bold) metric, so partially bold text wraps
    correctly."""
    def measurer(px):
        px = max(1, int(round(px)))
        fn = QFont(family)
        fn.setPixelSize(px)
        fn.setBold(bold)
        fn.setItalic(italic)
        fm = QFontMetricsF(fn)
        fb = QFont(family)
        fb.setPixelSize(px)
        fb.setBold(True)
        fb.setItalic(italic)
        fmb = QFontMetricsF(fb)
        space_w = _advance(fm, " ")
        line_h = fm.height() * line_spacing

        def width_of(x):
            runs = getattr(x, "runs", None)
            if runs is None:
                if isinstance(x, (list, tuple)):
                    runs = x          # a plain run list [(text, bold), ...]
                else:
                    return _advance(fm, x)   # a plain string
            tot = 0.0
            for (t, b) in runs:
                tot += _advance(fmb if (bold or b) else fm, t)
            return tot

        return width_of, space_w, line_h, fm.ascent(), fm.descent()
    return measurer


def _hex(color):
    return "#{:02x}{:02x}{:02x}".format(color.red(), color.green(), color.blue())


def _text_element(text_lines, line_pos, block_start, line_h, font_px, family,
                  fill_hex, stroke_hex=None, stroke_w=0.0,
                  bold=False, italic=False, underline=False, dx=0.0, dy=0.0,
                  vertical=False, ligatures=True):
    """text_lines: list of run lists ([(subtext, bold), ...] per line).

    Horizontal: `line_pos` is the absolute LEFT x of each line and `block_start`
    the baseline y of the first line; lines step downwards by line_h.
    Vertical (tategaki): the axes swap. `line_pos` is the absolute TOP y of each
    column and `block_start` the center x of the first column; columns step
    LEFTWARDS by line_h, because writing-mode 'vertical-rl' starts at the right.

    Lines are pre-centered/-aligned, so the element uses the default 'start'
    anchor – Krita's text tool keeps that absolute position when the shape is
    edited (a 'middle'/'end' anchor would be dropped and the text would snap to
    the corner). dx/dy shift the whole block (used for the offset shadow copy).
    Bold runs get font-weight='bold'."""
    tspans = []
    for i, runs in enumerate(text_lines):
        if not runs:
            continue
        if vertical:
            x = block_start - i * line_h + dx
            y = line_pos[i] + dy
        else:
            x = line_pos[i] + dx
            y = block_start + dy + i * line_h
        first = True
        for (txt, rb) in runs:
            weight = "bold" if (bold or rb) else "normal"
            if first:
                tspans.append(
                    '<tspan x="{x:.2f}" y="{y:.2f}" font-weight="{w}">'
                    "{txt}</tspan>".format(
                        x=x, y=y, w=weight, txt=xml_escape(txt)))
                first = False
            else:
                tspans.append(
                    '<tspan font-weight="{w}">{txt}</tspan>'.format(
                        w=weight, txt=xml_escape(txt)))
    attrs = (
        'text-anchor="start" fill="{fill}" '
        'font-family="{fam}" font-size="{size}"'
    ).format(fill=fill_hex, fam=xml_escape(family), size=int(round(font_px)))
    if vertical:
        # Krita parses both as plain presentation attributes
        # (KoSvgTextProperties::parseSvgTextAttribute); 'upright' is what stacks
        # Latin letters instead of rotating them onto their side.
        attrs += ' writing-mode="vertical-rl" text-orientation="upright"'
    if italic:
        attrs += ' font-style="italic"'
    if underline:
        attrs += ' text-decoration="underline"'
    if not ligatures:
        # Manga lettering usually wants ligatures OFF: "fi"/"fl" fusing looks
        # wrong in hand-lettered fonts. Krita's SVG text parses this
        # (KoSvgText::parseFontFeatureLigatures) and "none" disables all.
        attrs += ' font-variant-ligatures="none"'
    if stroke_hex is not None and stroke_w > 0:
        attrs += (
            ' stroke="{s}" stroke-width="{w:.2f}" '
            'stroke-linejoin="round" stroke-linecap="round"'
        ).format(s=stroke_hex, w=stroke_w)
    return "<text {attrs}>{spans}</text>".format(attrs=attrs, spans="".join(tspans))


def _build_svg(text_lines, line_pos, block_start, font_px, family, color, line_h,
               img_w, img_h,
               outline=False, outline_color=None, outline_px=0.0,
               bold=False, italic=False, underline=False,
               shadow=False, shadow_color=None, shadow_dx=0.0, shadow_dy=0.0,
               vertical=False, ligatures=True,
               outline2_color=None, outline2_px=0.0):
    """SVG with optional shadow, optional (double) outline and style (bold/
    italic/underline). Alignment is baked into `line_pos` (per-line absolute
    position along the line axis) and the text uses the default 'start' anchor,
    so the inserted shape keeps its position when edited with Krita's text tool.
    See _text_element for what line_pos/block_start mean per writing direction.

    Bottom-to-top order: shadow, 2nd (outer) outline, outline, fill.
    Everything is drawn as extra text copies so it works independently of the
    renderer (no filter/paint-order needed).
    """
    fill_hex = _hex(color)
    has_outline = bool(outline) and outline_color is not None and outline_px > 0
    # the 2nd outline is part of the outline feature: turning the outline off
    # turns it off too (it is not an independent effect).
    has_outline2 = (bool(outline) and outline2_color is not None
                    and outline2_px > 0)
    body = ""
    if shadow and shadow_color is not None and (shadow_dx or shadow_dy):
        sh = _hex(shadow_color)
        # the shadow takes the WIDEST outline so it keeps the full silhouette
        sw = max(outline_px if has_outline else 0.0,
                 outline2_px if has_outline2 else 0.0)
        body += _text_element(text_lines, line_pos, block_start, line_h, font_px,
                              family, fill_hex=sh,
                              stroke_hex=(sh if sw > 0 else None), stroke_w=sw,
                              bold=bold, italic=italic, underline=underline,
                              dx=shadow_dx, dy=shadow_dy, vertical=vertical,
                              ligatures=ligatures)
    if has_outline2:                       # outer outline, under the inner one
        o2 = _hex(outline2_color)
        body += _text_element(text_lines, line_pos, block_start, line_h, font_px,
                              family, fill_hex=o2, stroke_hex=o2,
                              stroke_w=outline2_px,
                              bold=bold, italic=italic, underline=underline,
                              vertical=vertical, ligatures=ligatures)
    if has_outline:
        ol = _hex(outline_color)
        body += _text_element(text_lines, line_pos, block_start, line_h, font_px,
                              family, fill_hex=ol, stroke_hex=ol,
                              stroke_w=outline_px,
                              bold=bold, italic=italic, underline=underline,
                              vertical=vertical, ligatures=ligatures)
    body += _text_element(text_lines, line_pos, block_start, line_h, font_px,
                          family, fill_hex=fill_hex,
                          bold=bold, italic=italic, underline=underline,
                          vertical=vertical, ligatures=ligatures)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="{w}" height="{h}">{body}</svg>'
    ).format(w=img_w, h=img_h, body=body)


def _text_path(text_lines, line_pos, block_start, font_px, family, line_h,
               bold, italic):
    """Build one QPainterPath covering the whole (multi-line, per-run bold)
    block, positioned in DOCUMENT coordinates exactly like _build_svg — so the
    raster render lands where the vector one would. Returns (path, underlines)
    with `underlines` a list of (x0, x1, y) baselines for optional underlining."""
    px = max(1, int(round(font_px)))
    path = QPainterPath()
    underlines = []
    for i, runs in enumerate(text_lines):
        x = float(line_pos[i])
        baseline = block_start + i * line_h
        x0 = x
        # a line is a run list [(text, bold), ...]; fall back to a plain string
        seq = runs if isinstance(runs, (list, tuple)) else [(str(runs), False)]
        for (t, b) in seq:
            f = QFont(family)
            f.setPixelSize(px)
            f.setItalic(italic)
            f.setBold(bool(bold or b))
            path.addText(x, baseline, f, t)
            x += _advance(QFontMetricsF(f), t)
        underlines.append((x0, x, baseline))
    return path, underlines


def _scaled_pattern_brush(pattern_img, scale):
    """A QBrush that tiles `pattern_img` (a QImage) scaled by `scale` percent."""
    s = max(0.05, float(scale) / 100.0)
    w = max(1, int(round(pattern_img.width() * s)))
    h = max(1, int(round(pattern_img.height() * s)))
    pm = QPixmap.fromImage(pattern_img).scaled(
        w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return QBrush(pm)


def presets_to_table(chars, header_of, default_char="(default)"):
    """Build a fonts MATRIX for ONE manga, like the user's own sheet: the first
    column is the character, then one column per purpose (preset name) used in
    the manga, and each cell holds the font that character uses for that purpose
    (blank if none). Purpose columns are ordered most-used first. Pure (no Qt),
    so it is unit-testable. Returns (headers, rows)."""
    counts = {}
    for presets in (chars or {}).values():
        for name in (presets or {}):
            counts[name] = counts.get(name, 0) + 1
    purposes = sorted(counts, key=lambda n: (-counts[n], str(n).lower()))
    headers = [header_of("col_character")] + purposes
    rows = []
    for char in sorted(chars or {}, key=lambda s: str(s).lower()):
        presets = chars[char] or {}
        row = [char if str(char).strip() else default_char]
        for p in purposes:
            cfg = presets.get(p)
            if cfg is None:
                row.append("")
            else:
                font = cfg.get("font", "") if isinstance(cfg, dict) else cfg
                row.append(font or "")
        rows.append(row)
    return headers, rows


def _render_text_raster(text_lines, line_pos, block_start, font_px, family,
                        line_h, color, bold, italic, underline,
                        outline, outline_color, outline_px,
                        outline2_color, outline2_px,
                        shadow, shadow_color, shadow_dx, shadow_dy,
                        pattern_img, pattern_scale,
                        soft, soft_color, soft_px, soft_blur, soft_pattern,
                        fill_pattern=None, fill_scale=100,
                        pattern_target="outline1"):
    """Render the text block to an ARGB QImage for the raster insert path (used
    when the text and/or outline is pattern-filled and/or has a soft/blurred
    halo — none of those can be a Krita vector paint). Returns (img, ox, oy)
    where (ox, oy) is the document-space top-left the image should be placed at.

    The primary outline is filled with the pattern when one is given; the second
    outline stays a solid colour; the text keeps its fill colour. Draw order
    (bottom→top): soft halo, shadow, 2nd outline, outline, fill — same as the
    vector path."""
    path, underlines = _text_path(text_lines, line_pos, block_start, font_px,
                                  family, line_h, bold, italic)
    if underline:
        uw = max(1.0, font_px * 0.06)
        for (x0, x1, base) in underlines:
            path.addRect(QRectF(x0, base + uw * 1.5, x1 - x0, uw))

    o1 = float(outline_px) if (outline and outline_color is not None) else 0.0
    o2 = float(outline2_px) if (outline and outline2_color is not None) else 0.0
    soft_w = float(soft_px) if soft else 0.0
    soft_bl = float(soft_blur) if soft else 0.0
    soft_ext = (soft_w + 2.0 * soft_bl) if soft else 0.0
    sdx = float(shadow_dx) if shadow else 0.0
    sdy = float(shadow_dy) if shadow else 0.0

    rect = path.boundingRect()
    if shadow and (sdx or sdy):
        rect = rect.united(path.boundingRect().translated(sdx, sdy))
    spread = max(o1, o2) / 2.0 + soft_ext + 3.0
    ox = int(math.floor(rect.left() - spread))
    oy = int(math.floor(rect.top() - spread))
    w = max(1, int(math.ceil(rect.right() + spread)) - ox)
    h = max(1, int(math.ceil(rect.bottom() + spread)) - oy)

    # the pattern fills the chosen outline(s); the other stays its solid colour
    _pat_brush = (_scaled_pattern_brush(pattern_img, pattern_scale)
                  if pattern_img is not None and not pattern_img.isNull()
                  else None)
    o1_brush = (_pat_brush if _pat_brush is not None
                and pattern_target in ("outline1", "both")
                else QBrush(outline_color if outline_color is not None
                            else QColor(0, 0, 0)))
    o2_brush = (_pat_brush if _pat_brush is not None
                and pattern_target in ("outline2", "both")
                else QBrush(QColor(outline2_color) if outline2_color is not None
                            else QColor(0, 0, 0)))

    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.translate(-ox, -oy)

    # soft halo: rendered isolated + blurred so the crisp text above stays sharp
    if soft and soft_bl > 0:
        if soft_pattern and pattern_img is not None and not pattern_img.isNull():
            sfill = pattern_img
        else:
            sfill = soft_color if soft_color is not None else QColor(0, 0, 0)
        halo = IMG.soft_outline_image(path.translated(-ox, -oy), img.size(),
                                      soft_bl, soft_w, sfill)
        p.drawImage(0, 0, halo)

    if shadow and (sdx or sdy):
        sp = QPainterPath(path)
        sp.translate(sdx, sdy)
        p.fillPath(sp, QBrush(shadow_color if shadow_color is not None
                              else QColor(0, 0, 0)))
    if o2 > 0:
        pen2 = QPen(o2_brush, o2)
        pen2.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.strokePath(path, pen2)
    if o1 > 0:
        pen = QPen(o1_brush, o1)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.strokePath(path, pen)
    if fill_pattern is not None and not fill_pattern.isNull():
        p.fillPath(path, _scaled_pattern_brush(fill_pattern, fill_scale))
    else:
        p.fillPath(path, QBrush(color))
    p.end()
    return img, ox, oy


def _paint_layer_from_image(doc, img, ox, oy, label):
    """Place `img` (ARGB) onto a NEW paint layer at document coords (ox, oy),
    clipped to the canvas. Returns the node, or None if nothing lands on-canvas.
    Uses the same TypeR layer label as the vector path so replace-mode still
    recognises and removes it."""
    img_w, img_h = doc.width(), doc.height()
    px, py = int(round(ox)), int(round(oy))
    cx0, cy0 = max(0, px), max(0, py)
    cx1 = min(img_w, px + img.width())
    cy1 = min(img_h, py + img.height())
    if cx1 <= cx0 or cy1 <= cy0:
        return None
    if (cx0, cy0, cx1, cy1) != (px, py, px + img.width(), py + img.height()):
        img = img.copy(cx0 - px, cy0 - py, cx1 - cx0, cy1 - cy0)
    img = img.convertToFormat(QImage.Format.Format_ARGB32)     # memory layout = BGRA
    node = doc.createNode(label, "paintlayer")
    root = doc.rootNode()
    kids = root.childNodes()
    root.addChildNode(node, kids[-1] if kids else None)
    try:
        doc.setActiveNode(node)
        doc.waitForDone()
    except Exception:                                   # noqa: BLE001
        pass
    nbytes = (img.sizeInBytes() if hasattr(img, "sizeInBytes")
              else img.byteCount())
    buf = img.constBits()
    buf.setsize(nbytes)
    node.setPixelData(bytes(buf), cx0, cy0, img.width(), img.height())
    doc.refreshProjection()
    try:
        doc.waitForDone()
    except Exception:                                   # noqa: BLE001
        pass
    return node


def _insert_vector_clip_pattern(doc, svg, label, text_lines, line_pos,
                                block_start, font_px, family, line_h,
                                bold, italic, fill_pattern, fill_scale):
    """Keep the text as an EDITABLE vector layer while still giving it a pattern
    fill: a group holds the vector text plus a raster pattern layer above it set
    to 'inherit alpha', so the pattern shows only over the letters. Returns the
    group node, or None if Krita's API can't do it (caller then falls back to a
    flat raster)."""
    if not hasattr(doc, "createGroupLayer"):
        return None
    path, _u = _text_path(text_lines, line_pos, block_start, font_px, family,
                          line_h, bold, italic)
    rect = path.boundingRect()
    m = 3.0
    ox = int(math.floor(rect.left() - m))
    oy = int(math.floor(rect.top() - m))
    w = max(1, int(math.ceil(rect.right() + m)) - ox)
    h = max(1, int(math.ceil(rect.bottom() + m)) - oy)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.fillRect(0, 0, w, h, _scaled_pattern_brush(fill_pattern, fill_scale))
    p.end()
    img_w, img_h = doc.width(), doc.height()
    cx0, cy0 = max(0, ox), max(0, oy)
    cx1 = min(img_w, ox + w)
    cy1 = min(img_h, oy + h)
    if cx1 <= cx0 or cy1 <= cy0:
        return None
    if (cx0, cy0, cx1, cy1) != (ox, oy, ox + w, oy + h):
        img = img.copy(cx0 - ox, cy0 - oy, cx1 - cx0, cy1 - cy0)
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    try:
        group = doc.createGroupLayer(label)
        vlayer = doc.createVectorLayer(label)
        group.addChildNode(vlayer, None)
        try:
            doc.setActiveNode(vlayer)
            doc.waitForDone()
        except Exception:                               # noqa: BLE001
            pass
        vlayer.addShapesFromSvg(svg)
        patlayer = doc.createNode(label, "paintlayer")
        if not hasattr(patlayer, "setInheritAlpha"):
            return None                                 # -> caller uses raster
        group.addChildNode(patlayer, vlayer)            # above the text
        nbytes = (img.sizeInBytes() if hasattr(img, "sizeInBytes")
                  else img.byteCount())
        buf = img.constBits()
        buf.setsize(nbytes)
        patlayer.setPixelData(bytes(buf), cx0, cy0, img.width(), img.height())
        patlayer.setInheritAlpha(True)                  # clip to the text alpha
        doc.rootNode().addChildNode(group, None)
        doc.refreshProjection()
        try:
            doc.waitForDone()
        except Exception:                               # noqa: BLE001
            pass
        return group
    except Exception:                                   # noqa: BLE001
        return None


_LINKIFY = re.compile(r"https?://[^\s<>\"']+")


def tidy_text(s, comic=False):
    """Typographic clean-up: straight quotes -> curly quotes, ... -> …,
    -- -> —, multiple spaces -> one. Makes text look more professional
    without changing its content."""
    s = s.replace("...", "\u2026")
    if not comic:
        # comics keep the double dash; em/en dashes are not used there
        s = re.sub(r"(?<!-)--(?!-)", "\u2014", s)
    # opening double quote after line start / whitespace / bracket
    s = re.sub(r'(^|[\s([{<\u2014])"', "\\1\u201c", s)
    s = s.replace('"', "\u201d")
    s = re.sub(r"(^|[\s([{<\u2014])'", "\\1\u2018", s)
    s = s.replace("'", "\u2019")
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s


_ACRONYM = re.compile(r"(?:\b[A-Za-z]\.){2,}")


def _fix_crossbar_i(s):
    """Give the crossbar "I" only to the pronoun and to acronyms.

    Comic fonts put the barred I on uppercase ``I`` and the plain vertical
    stroke on lowercase ``i`` (both render as a capital in an all-caps comic
    face). So lowering every other capital I is what actually selects the
    right glyph. Blambot calls using the barred I everywhere "probably the
    biggest mistake seen among amateur letterers".
    """
    spans = [m.span() for m in _ACRONYM.finditer(s)]

    def in_acronym(idx):
        return any(a <= idx < b for a, b in spans)

    out = []
    n = len(s)
    for i, ch in enumerate(s):
        if ch != "I" or in_acronym(i):
            out.append(ch)
            continue
        prev = s[i - 1] if i else ""
        nxt = s[i + 1] if i + 1 < n else ""
        starts_word = not (prev.isalpha() or prev == "'" or prev == "\u2019")
        # the pronoun: a standalone I, or I'm / I'll / I've / I'd
        if starts_word and (nxt in ("'", "\u2019") or not nxt.isalpha()):
            out.append("I")
        else:
            out.append("i")
    return "".join(out)


def comic_letter(s, crossbar_i=False):
    """Comic-lettering grammar (Blambot, "Comic Book Grammar & Tradition").

    Deliberately different from ordinary typography:

    * an ellipsis is exactly three dots and hugs the words around it
    * interrupted speech uses a double dash ``--``; em/en dashes are not used
    * a shouted question is ``?!`` \u2014 the question mark comes first
    * one space after punctuation, never two

    `crossbar_i` is off by default because it only makes sense with a real
    comic font: it lowers non-pronoun capital I's so the font renders the
    plain stroke. With an ordinary font that would just look like a typo.

    Must run *after* the letter-case transform, since the crossbar rule
    depends on the final case.
    """
    # an ellipsis is exactly three dots, and nothing breathes around it
    s = re.sub(r"\.{2,}", "\u2026", s)
    s = re.sub(r"[ \t]*\u2026[ \t]*", "\u2026", s)
    # interrupted speech: a double dash, never an em/en dash
    s = re.sub(r"[\u2014\u2013]", "--", s)
    s = re.sub(r"-{3,}", "--", s)
    s = re.sub(r"[ \t]*--[ \t]*", "--", s)
    # a shouted question puts the question mark first
    s = s.replace("!?", "?!")
    s = re.sub(r"[ \t]{2,}", " ", s)
    if crossbar_i:
        s = _fix_crossbar_i(s)
    return s


def parse_bold(text):
    """``**bold**`` marks bold sections. Returns (clean_text, mask); mask is a
    list of bool with the same length as clean_text (True = bold). A single
    ``*`` is kept as-is (not a marker)."""
    clean = []
    mask = []
    bold = False
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "*" and i + 1 < n and text[i + 1] == "*":
            bold = not bold
            i += 2
            continue
        clean.append(text[i])
        mask.append(bold)
        i += 1
    return "".join(clean), mask


def toggle_bold(text, start, end):
    """Add or remove bold markers (``**``) around the selection [start, end).
    Returns (new_text, new_start, new_end). Unchanged when there is no
    selection."""
    if start > end:
        start, end = end, start
    if start == end:
        return text, start, end
    sel = text[start:end]
    # markers directly outside the selection -> remove them (clear bold)
    if text[start - 2:start] == "**" and text[end:end + 2] == "**":
        new = text[:start - 2] + sel + text[end + 2:]
        return new, start - 2, end - 2
    # the selection itself is wrapped -> strip the markers
    if sel.startswith("**") and sel.endswith("**") and len(sel) >= 4:
        inner = sel[2:-2]
        new = text[:start] + inner + text[end:]
        return new, start, start + len(inner)
    # otherwise: wrap it
    new = text[:start] + "**" + sel + "**" + text[end:]
    return new, start + 2, end + 2


def prepare_text(line, case, tidy, comic=False, crossbar_i=False):
    """Prepare text before setting it (order: clean up, then letter case).

    case: "none" (unchanged), "upper" (UPPERCASE) or "lower" (lowercase).
    For backward compatibility case=True behaves like "upper", case=False like
    "none"."""
    out = line
    if tidy:
        out = tidy_text(out, comic=comic)
    if case is True or case == "upper":
        out = out.upper()
    elif case == "lower":
        out = out.lower()
    if comic:
        # last: the crossbar-I rule depends on the final letter case
        out = comic_letter(out, crossbar_i=crossbar_i)
    return out


ALIGN_ANCHOR = {"left": "start", "center": "middle", "right": "end"}


def _rects_overlap(a, b):
    """True if two (x, y, w, h) rectangles share any area."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _remove_existing_layers(doc, layer_index, box=None):
    """Remove earlier TypeR layers for the 1-based unit `layer_index` (matched
    by the exact 'TypeR NN — ' name prefix, so hand-made layers are never
    touched). Returns the number removed; never raises – a failed removal must
    not block the insert.

    With `box` (x, y, w, h) given, only a prior insert that OVERLAPS that box is
    dropped. That is what makes "Replace previously inserted line" behave when
    one script line is split across two bubbles: re-inserting into the same
    bubble replaces it, but placing the rest into a different bubble leaves the
    first piece alone. A layer whose bounds can't be read is treated as
    overlapping, so the old "replace all" behaviour is the safe fallback.
    Without `box`, every layer of the unit is removed (unchanged behaviour)."""
    removed = 0
    try:
        root = doc.rootNode()
        for node in list(root.childNodes()):
            try:
                if not L.is_typer_layer_name(node.name(), layer_index):
                    continue
                if box is not None:
                    b = node.bounds()
                    rect = (b.x(), b.y(), b.width(), b.height())
                    if rect[2] > 0 and rect[3] > 0 and not _rects_overlap(rect, box):
                        continue
                node.remove()
                removed += 1
            except Exception:
                pass
    except Exception:
        pass
    return removed


def insert_text_layer(line, font_family, font_px, color, auto_fit,
                      max_px, padding_frac, line_spacing,
                      outline=False, outline_color=None, outline_px=0.0,
                      bold=False, italic=False, underline=False,
                      align="center", case="none", tidy=False, shape="rect",
                      shadow=False, shadow_color=None, shadow_dx=0.0,
                      shadow_dy=0.0, valign="middle", layer_index=None,
                      hyphenate=False, hyph_lang="en", replace_existing=False,
                      box=None, comic=False, crossbar_i=False, vertical=False,
                      ligatures=True, outline2_color=None, outline2_px=0.0,
                      pattern_img=None, pattern_scale=100, soft=False,
                      soft_color=None, soft_px=0.0, soft_blur=0.0,
                      soft_pattern=False, fill_pattern=None, fill_scale=100,
                      vector_clip=False, pattern_target="outline1"):
    """Insert a single line of text as a text layer.

    auto_fit=True: the line is wrapped automatically, balanced and scaled to the
    largest size that fits the current selection (= "where to"). Without a
    selection the whole image is used as the box.

    box: optional (x, y, w, h) tuple that overrides the selection as the
    target box — used by the BubblR tab, which places into detected bubbles
    without touching the user's selection.

    auto_fit=False: fixed size font_px, only split at embedded line breaks.

    vertical=True: tategaki – the text runs top-to-bottom in columns that march
    right-to-left (for narrow bubbles and signs). `align` then places the block
    of columns horizontally and `valign` the text along each column.

    outline: optional outline in outline_color with width outline_px (pixels).
    bold/italic/underline: font style (variant of the chosen font).
    Individual words can be marked bold in the text with ``**...**``.

    replace_existing: with a layer_index, delete the layer(s) TypeR inserted
    earlier for the same unit before creating the new one, so re-inserting a
    line (e.g. trying several TextShapR shapes) replaces instead of stacking.

    Returns (ok, key, fmt); the caller translates key via LANG. fmt contains
    'replaced': the number of old layers that were removed.
    """
    app = Krita.instance()
    doc = app.activeDocument()
    if doc is None:
        return False, "st_no_doc", {}
    if line.strip() == "":
        return False, "st_empty_line", {}

    line = prepare_text(line, case, tidy, comic=comic, crossbar_i=crossbar_i)
    line = line.replace("\r\n", "\n").replace("\r", "\n")
    clean, mask = parse_bold(line)
    if clean.strip() == "":
        return False, "st_empty_line", {}

    img_w = doc.width()
    img_h = doc.height()

    # determine the box + its center (explicit box > selection > image)
    if box is not None:
        box_x, box_y, box_w, box_h = box
    else:
        sel = doc.selection()
        has_sel = sel is not None
        if has_sel:
            try:
                box_x, box_y = sel.x(), sel.y()
                box_w, box_h = sel.width(), sel.height()
            except Exception:
                has_sel = False
        if not has_sel:
            box_x, box_y, box_w, box_h = 0, 0, img_w, img_h
    cx = box_x + box_w / 2.0
    cy = box_y + box_h / 2.0

    if vertical:
        measurer = L.vertical_measurer(line_spacing)
    else:
        measurer = _make_measurer(font_family, line_spacing, bold, italic)

    # the fitter always works "along the line, then across the lines", so
    # vertical text hands it the box transposed. This is only correct together
    # with the vertical measurer above — transposing on its own measures the
    # wrong axis.
    fit_w, fit_h = (box_h, box_w) if vertical else (box_w, box_h)

    if auto_fit:
        result = L.fit_text(clean, measurer, fit_w, fit_h, max_px, 6,
                            padding_frac, shape, mask,
                            hyphenate=hyphenate, lang=hyph_lang)
        if result is None:
            return False, "st_empty_line", {}
        font_px, text_lines, line_h, ascent, descent, fitted = result
    else:
        # fixed size, split only at embedded line breaks (run lists per line)
        text_lines = [L.make_runs(pt, pm)
                      for (pt, pm) in L.split_paragraphs(clean, mask)]
        _wo, _sw, line_h, ascent, descent = measurer(font_px)
        fitted = True

    # alignment: each line gets its own absolute start position along its axis
    # (pre-centered/-aligned) so the SVG can use the default 'start' anchor –
    # this keeps the text in place when it's later edited with Krita's text tool
    # (text-anchor='middle' was getting dropped, snapping the shape into the
    # corner).
    width_of = measurer(font_px)[0]
    line_widths = [width_of(runs) for runs in text_lines]
    if vertical:
        # columns: position along y, block placed along x
        pad_y = box_h * padding_frac / 2.0
        line_pos = L.column_y_positions(
            line_widths, valign, box_y + pad_y, cy, box_y + box_h - pad_y)
        block_start = L.horizontal_start(align, box_x, box_w, padding_frac,
                                         len(text_lines), line_h)
    else:
        pad_x = box_w * padding_frac / 2.0
        line_pos = L.line_x_positions(
            line_widths, align, box_x + pad_x, cx, box_x + box_w - pad_x)
        # optical vertical centring: use the cap height (not the em ascent, which
        # carries empty ascender space) so all-caps lettering sits on the centre
        cap = None
        try:
            _capf = QFont(font_family)
            _capf.setPixelSize(int(font_px))
            _capf.setBold(bold)
            _capf.setItalic(italic)
            cap = QFontMetricsF(_capf).capHeight()
        except Exception:                       # noqa: BLE001
            cap = None
        block_start = L.vertical_start(valign, box_y, box_h, padding_frac,
                                       len(text_lines), line_h, ascent, descent,
                                       cap=cap)
    # A pattern-filled outline or a soft/blurred outline cannot be a Krita vector
    # paint, so those styles go onto a raster (paint) layer instead. Vertical
    # text keeps the vector path (the raster renderer is horizontal-only).
    has_pattern = (pattern_img is not None
                   and not (hasattr(pattern_img, "isNull") and pattern_img.isNull()))
    has_fill_pattern = (fill_pattern is not None
                        and not (hasattr(fill_pattern, "isNull")
                                 and fill_pattern.isNull()))
    use_raster = (not vertical) and (
        (outline and has_pattern)
        or has_fill_pattern
        or (soft and (soft_px > 0 or soft_blur > 0)))

    # replace mode: drop the layer(s) of an earlier insert of this unit first
    replaced = 0
    if replace_existing and layer_index is not None:
        replaced = _remove_existing_layers(doc, int(layer_index),
                                           (box_x, box_y, box_w, box_h))

    snippet = (L.runs_text(text_lines[0])[:24] if text_lines else "").strip()
    if layer_index is not None:
        label = L.typer_layer_prefix(int(layer_index)) + snippet
    else:
        label = "TypeR — " + snippet

    if use_raster:
        px = int(round(font_px))

        def _ok_result():
            if auto_fit and not fitted:
                return True, "st_inserted_min", {"px": px, "replaced": replaced}
            if auto_fit:
                return True, "st_inserted_fit", {"px": px, "n": len(text_lines),
                                                 "replaced": replaced}
            return True, "st_inserted", {"replaced": replaced}

        # 'Keep text as vector': the ONLY raster-forcing effect must be the text
        # fill pattern (a blurred/soft or pattern OUTLINE can't be vector). Then
        # the text stays an editable vector layer and the pattern rides on a
        # clip (inherit-alpha) layer above it. Falls back to flat raster if the
        # Krita build can't clip via the API.
        if (vector_clip and has_fill_pattern and not soft
                and not (outline and has_pattern)):
            svg_v = _build_svg(
                text_lines, line_pos, block_start, font_px, font_family, color,
                line_h, img_w, img_h, outline=outline,
                outline_color=outline_color, outline_px=outline_px,
                bold=bold, italic=italic, underline=underline,
                shadow=shadow, shadow_color=shadow_color, shadow_dx=shadow_dx,
                shadow_dy=shadow_dy, vertical=False, ligatures=ligatures,
                outline2_color=outline2_color, outline2_px=outline2_px)
            try:
                grp = _insert_vector_clip_pattern(
                    doc, svg_v, label, text_lines, line_pos, block_start,
                    font_px, font_family, line_h, bold, italic,
                    fill_pattern, fill_scale)
            except Exception:                           # noqa: BLE001
                grp = None
            if grp is not None:
                return _ok_result()
            # else: unsupported -> fall through to the flat raster below

        try:
            img, ox, oy = _render_text_raster(
                text_lines, line_pos, block_start, font_px, font_family, line_h,
                color, bold, italic, underline,
                outline, outline_color, outline_px, outline2_color, outline2_px,
                shadow, shadow_color, shadow_dx, shadow_dy,
                (pattern_img if (outline and has_pattern) else None),
                pattern_scale,
                soft, soft_color, soft_px, soft_blur,
                (soft_pattern and has_pattern),
                (fill_pattern if has_fill_pattern else None), fill_scale,
                pattern_target)
            node = _paint_layer_from_image(doc, img, ox, oy, label)
        except Exception as exc:  # pragma: no cover - Krita-version dependent
            return False, "st_create_fail", {"exc": exc}
        if node is None:
            return False, "st_create_fail", {"exc": "empty raster"}
        return _ok_result()

    svg = _build_svg(text_lines, line_pos, block_start, font_px, font_family,
                     color, line_h,
                     img_w, img_h, outline=outline, outline_color=outline_color,
                     outline_px=outline_px,
                     bold=bold, italic=italic, underline=underline,
                     shadow=shadow, shadow_color=shadow_color,
                     shadow_dx=shadow_dx, shadow_dy=shadow_dy,
                     vertical=vertical, ligatures=ligatures,
                     outline2_color=outline2_color, outline2_px=outline2_px)

    try:
        root = doc.rootNode()
        vlayer = doc.createVectorLayer(label)
        root.addChildNode(vlayer, None)
        # Let Krita finish registering the new vector layer BEFORE we push SVG
        # shapes into it. Adding shapes to a just-created layer while Krita's
        # shape/vector subsystem is still spinning up is what crashes the very
        # first insert of a session; setting it active + waiting for the pending
        # work settles it first.
        try:
            doc.setActiveNode(vlayer)
            doc.waitForDone()
        except Exception:      # noqa: BLE001 — older Krita may lack waitForDone
            pass
        vlayer.addShapesFromSvg(svg)
        doc.refreshProjection()
        try:
            doc.waitForDone()
        except Exception:      # noqa: BLE001
            pass
    except Exception as exc:  # pragma: no cover - depends on the Krita version
        return False, "st_create_fail", {"exc": exc}

    px = int(round(font_px))
    if auto_fit and not fitted:
        return True, "st_inserted_min", {"px": px, "replaced": replaced}
    if auto_fit:
        return True, "st_inserted_fit", {"px": px, "n": len(text_lines),
                                         "replaced": replaced}
    return True, "st_inserted", {"replaced": replaced}


# ---------------------------------------------------------------------------
# BubblR: pixel grab + overlay preview (detection logic lives in bubbles.py,
# the external AI detector is reached through ai_backend.py)
# ---------------------------------------------------------------------------

def grab_gray(doc):
    """Return (gray_bytes, w, h) of the flattened document, or
    (None, colorModel, colorDepth) when unsupported. 8-bit RGBA (BGRA byte
    order -> the green channel is a good luminance stand-in for B/W manga)
    and 8-bit grayscale are supported."""
    model = doc.colorModel()
    depth = doc.colorDepth()
    if depth != "U8" or model not in ("RGBA", "GRAYA"):
        return None, model, depth
    w, h = doc.width(), doc.height()
    data = bytes(doc.pixelData(0, 0, w, h))
    if model == "RGBA":
        gray = data[1::4]
    else:
        gray = data[0::2]
    return gray, w, h


class BubbleOverlay(QWidget):
    """Paints the page thumbnail with numbered bubble boxes on top.

    Plain left-click emits boxClicked(index, False) (select as current),
    Ctrl+left-click boxClicked(index, True) (renumber sequence), right-click
    boxRemoved(index); the docker owns the box list and the state. The
    current box is drawn with a thick border."""

    boxClicked = pyqtSignal(int, bool)
    boxRemoved = pyqtSignal(int)
    boxAdded = pyqtSignal(float, float, float, float)        # x, y, w, h (doc)
    boxChanged = pyqtSignal(int, float, float, float, float)  # idx + xywh

    _HANDLE = 9        # px radius around a corner that grabs it for resizing

    def __init__(self):
        super(BubbleOverlay, self).__init__()
        self._img = None
        self._doc_w = 1
        self._doc_h = 1
        self._boxes = []
        self._pending = {}
        self._current = -1
        self._edit = False        # draw/resize mode
        self._drag = None         # active draw/move/resize gesture
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_edit_mode(self, on):
        self._edit = bool(on)
        self._drag = None
        self.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)
        self.update()

    def set_page(self, img, doc_w, doc_h):
        self._img = img
        self._doc_w = max(1, doc_w)
        self._doc_h = max(1, doc_h)
        self.update()

    def set_boxes(self, boxes, pending=None, current=-1):
        self._boxes = boxes
        self._pending = pending or {}
        self._current = current
        self.update()

    def _target(self):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return QRectF(0, 0, 1, 1)
        scale = min(w / float(self._doc_w), h / float(self._doc_h))
        tw = self._doc_w * scale
        th = self._doc_h * scale
        return QRectF((w - tw) / 2.0, (h - th) / 2.0, tw, th)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(60, 60, 60))
        t = self._target()
        if self._img is not None and not self._img.isNull():
            p.drawImage(t, self._img,
                        QRectF(0, 0, self._img.width(), self._img.height()))
        scale = t.width() / float(self._doc_w)
        fnt = QFont()
        fnt.setBold(True)
        fnt.setPixelSize(14)
        p.setFont(fnt)
        for k, b in enumerate(self._boxes):
            r = QRectF(t.x() + b["x"] * scale, t.y() + b["y"] * scale,
                       b["w"] * scale, b["h"] * scale)
            pending = self._pending.get(k)
            if pending is not None:
                color = QColor(60, 200, 90)         # renumber in progress
            elif b.get("kind") == "sfx":
                color = QColor(70, 130, 230)        # free text / SFX
            else:
                color = QColor(230, 60, 60)         # bubble
            p.setPen(QPen(color, 4 if k == self._current else 2))
            p.setBrush(Qt.BrushStyle.NoBrush)      # outlines only — never fill the box
            # Always the plain detection rectangle: the preview shows exactly
            # the box the detector produced. Traced outlines/ellipses are still
            # used for fitting, but drawing them here only obscured what the AI
            # actually returned.
            p.drawRect(r)
            label = str(pending if pending is not None else k + 1)
            badge = QRectF(r.x(), r.y(), 22, 18)
            p.fillRect(badge, color)
            p.setPen(QPen(QColor(255, 255, 255)))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, label)
            # small corner handles while in draw/edit mode
            if self._edit:
                p.setBrush(QBrush(QColor(255, 255, 255)))
                p.setPen(QPen(QColor(30, 30, 30), 1))
                for hx, hy in ((r.left(), r.top()), (r.right(), r.top()),
                               (r.left(), r.bottom()), (r.right(), r.bottom())):
                    p.drawRect(QRectF(hx - 3, hy - 3, 6, 6))
        # the box currently being drawn / resized (dashed preview)
        rect = self._rect_of(self._drag) if self._drag else None
        if rect is not None:
            x, y, w, h = rect
            pr = QRectF(t.x() + x * scale, t.y() + y * scale,
                        w * scale, h * scale)
            pen = QPen(QColor(60, 200, 90), 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            p.drawRect(pr)
        p.end()

    def _hit(self, pos):
        t = self._target()
        if t.width() <= 0:
            return -1
        scale = t.width() / float(self._doc_w)
        x = (pos.x() - t.x()) / scale
        y = (pos.y() - t.y()) / scale
        best = -1
        best_area = None
        for k, b in enumerate(self._boxes):
            if b["x"] <= x <= b["x"] + b["w"] and \
               b["y"] <= y <= b["y"] + b["h"]:
                area = b["w"] * b["h"]
                if best_area is None or area < best_area:
                    best, best_area = k, area
        return best

    def _to_doc(self, pos):
        """Widget point -> document pixel coordinates."""
        t = self._target()
        if t.width() <= 0:
            return 0.0, 0.0
        scale = t.width() / float(self._doc_w)
        return (pos.x() - t.x()) / scale, (pos.y() - t.y()) / scale

    def _handle_at(self, pos):
        """What the press grabs in edit mode: (idx, 'nw'|'ne'|'sw'|'se') for a
        corner resize, (idx, 'move') inside a box, or None for empty canvas."""
        t = self._target()
        if t.width() <= 0:
            return None
        scale = t.width() / float(self._doc_w)
        best, best_area = None, None
        for k, b in enumerate(self._boxes):
            x0 = t.x() + b["x"] * scale
            y0 = t.y() + b["y"] * scale
            x1 = x0 + b["w"] * scale
            y1 = y0 + b["h"] * scale
            corners = {"nw": (x0, y0), "ne": (x1, y0),
                       "sw": (x0, y1), "se": (x1, y1)}
            for name, (cx, cy) in corners.items():
                if abs(pos.x() - cx) <= self._HANDLE \
                        and abs(pos.y() - cy) <= self._HANDLE:
                    return (k, name)
            if x0 <= pos.x() <= x1 and y0 <= pos.y() <= y1:
                area = b["w"] * b["h"]
                if best_area is None or area < best_area:
                    best, best_area = (k, "move"), area
        return best

    @staticmethod
    def _norm(ax, ay, bx, by):
        return (min(ax, bx), min(ay, by), abs(bx - ax), abs(by - ay))

    def _rect_of(self, d):
        """Current doc-space rect (x,y,w,h) of an in-progress gesture."""
        if not d:
            return None
        if d["mode"] == "new":
            return self._norm(d["x0"], d["y0"], d["cx"], d["cy"])
        if d["mode"] == "move":
            return (d["bx"] + (d["cx"] - d["px"]),
                    d["by"] + (d["cy"] - d["py"]), d["bw"], d["bh"])
        return self._norm(d["fx"], d["fy"], d["cx"], d["cy"])   # resize

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            idx = self._hit(event.pos())
            if idx >= 0:
                self.boxRemoved.emit(idx)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._edit:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._begin_edit(event.pos())
            return
        idx = self._hit(event.pos())
        if idx < 0:
            return
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self.boxClicked.emit(idx, ctrl)

    def _begin_edit(self, pos):
        dx, dy = self._to_doc(pos)
        hit = self._handle_at(pos)
        if hit is None:
            self._drag = {"mode": "new", "x0": dx, "y0": dy,
                          "cx": dx, "cy": dy}
        elif hit[1] == "move":
            b = self._boxes[hit[0]]
            self._drag = {"mode": "move", "idx": hit[0],
                          "bx": b["x"], "by": b["y"],
                          "bw": b["w"], "bh": b["h"],
                          "px": dx, "py": dy, "cx": dx, "cy": dy}
        else:
            idx, corner = hit
            b = self._boxes[idx]
            # fixed = the opposite corner
            fx = b["x"] + b["w"] if corner in ("nw", "sw") else b["x"]
            fy = b["y"] + b["h"] if corner in ("nw", "ne") else b["y"]
            self._drag = {"mode": "resize", "idx": idx,
                          "fx": fx, "fy": fy, "cx": dx, "cy": dy}
        self.update()

    def mouseMoveEvent(self, event):
        if not self._edit or self._drag is None:
            return
        self._drag["cx"], self._drag["cy"] = self._to_doc(event.pos())
        self.update()

    def mouseReleaseEvent(self, event):
        if not self._edit or self._drag is None:
            return
        d, self._drag = self._drag, None
        rect = self._rect_of(d)
        self.update()
        if rect is None:
            return
        x, y, w, h = rect
        if w < 8 or h < 8:          # ignore stray clicks / tiny boxes
            return
        # clamp into the page
        x = max(0.0, min(x, self._doc_w - 1))
        y = max(0.0, min(y, self._doc_h - 1))
        w = min(w, self._doc_w - x)
        h = min(h, self._doc_h - y)
        if d["mode"] == "new":
            self.boxAdded.emit(x, y, w, h)
        else:
            self.boxChanged.emit(d["idx"], x, y, w, h)


# ---------------------------------------------------------------------------
# Font picker  (scales to thousands of fonts)
# ---------------------------------------------------------------------------

def font_match(family, query):
    """True if the search term (case-insensitive) occurs in the family name."""
    q = query.strip().lower()
    return q == "" or q in family.lower()


def order_with_recents(families, recents):
    """Recently used fonts first, the rest in their original order."""
    seen = set()
    out = []
    for r in recents:
        if r in families and r not in seen:
            out.append(r)
            seen.add(r)
    for f in families:
        if f not in seen:
            out.append(f)
            seen.add(f)
    return out


class FontPicker(QWidget):
    """Fast, searchable font picker.

    Unlike QFontComboBox, NOT every entry is rendered in its own font (that is
    exactly what makes QFontComboBox slow with thousands of fonts). Instead: a
    plain text list + instant text filter, recently used fonts on top, and a
    preview only for the currently selected font.
    """

    familyChanged = pyqtSignal(str)

    def __init__(self, recents=None, search_placeholder=""):
        super().__init__()
        self._all = list(font_families())
        self._recents = [r for r in (recents or []) if r in self._all]
        self._current = None

        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.setLayout(lay)

        self.search = QLineEdit()
        self.search.setPlaceholderText(search_placeholder)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search)

        self.list = QListWidget()
        self.list.setUniformItemSizes(True)        # faster with many items
        self.list.setMinimumHeight(140)
        self.list.currentItemChanged.connect(self._on_select)
        lay.addWidget(self.list)

        self.preview = QLabel("")
        self.preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.preview.setMinimumHeight(40)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.preview)

        self._rebuild()

    # -- public API --

    def currentFamily(self):
        return self._current

    def setCurrentFamily(self, family):
        """Select a font programmatically (for presets). Matches
        case-insensitively (so a preset's 'Anime ace 2' still finds the installed
        'Anime Ace 2'); if the font is genuinely not installed, the NAME is
        adopted anyway so the preset's font is honoured instead of silently
        keeping the previous one (Krita substitutes a fallback but keeps the
        name, so it renders correctly once the font is installed)."""
        if not family:
            return
        family = family.strip()
        target = family
        if family not in self._all:
            low = family.lower()
            match = next((f for f in self._all if f.lower() == low), None)
            if match:
                target = match
        # clear any active filter so the row is reachable
        self.search.blockSignals(True)
        self.search.setText("")
        self.search.blockSignals(False)
        self._apply_filter("")
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == target:
                self.list.setCurrentRow(i)
                self.list.scrollToItem(self.list.item(i))
                return
        # not installed: adopt the name so inserts use the preset's font
        self._current = family
        self.preview.setText(family + "  –  (?)")
        f = QFont(family)
        f.setPixelSize(20)
        self.preview.setFont(f)
        self.list.blockSignals(True)
        self.list.setCurrentRow(-1)
        self.list.blockSignals(False)
        self.familyChanged.emit(family)

    def setRecents(self, recents):
        self._recents = [r for r in recents if r in self._all]

    def reloadFamilies(self):
        """Re-read the installed font list (e.g. after fonts were installed) and
        keep the current selection."""
        cur = self._current
        self._all = list(font_families())
        self._recents = [r for r in self._recents if r in self._all]
        self._rebuild()
        if cur:
            self.setCurrentFamily(cur)

    def noteUsed(self, family):
        """Mark a font as recently used (after inserting)."""
        if not family:
            return
        self._recents = [family] + [r for r in self._recents if r != family]
        self._recents = self._recents[:12]

    def recents(self):
        return list(self._recents)

    def set_search_placeholder(self, text):
        self.search.setPlaceholderText(text)

    # -- internal --

    def _rebuild(self):
        ordered = order_with_recents(self._all, self._recents)
        self.list.blockSignals(True)
        self.list.clear()
        recents_set = set(self._recents)
        for fam in ordered:
            label = ("★ " + fam) if fam in recents_set else fam
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, fam)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._apply_filter(self.search.text())
        # select the first visible row
        for i in range(self.list.count()):
            if not self.list.item(i).isHidden():
                self.list.setCurrentRow(i)
                break

    def _apply_filter(self, text):
        first_visible = None
        for i in range(self.list.count()):
            item = self.list.item(i)
            fam = item.data(Qt.ItemDataRole.UserRole)
            hide = not font_match(fam, text)
            item.setHidden(hide)
            if not hide and first_visible is None:
                first_visible = i
        cur = self.list.currentItem()
        if (cur is None or cur.isHidden()) and first_visible is not None:
            self.list.setCurrentRow(first_visible)

    def _on_select(self, current, _previous):
        if current is None:
            return
        fam = current.data(Qt.ItemDataRole.UserRole)
        self._current = fam
        self.preview.setText(fam + "  –  AaBb 123")
        f = QFont(fam)
        f.setPixelSize(20)
        self.preview.setFont(f)
        self.familyChanged.emit(fam)


# ---------------------------------------------------------------------------
# Live preview
# ---------------------------------------------------------------------------

class TextPreview(QWidget):
    """Shows a WYSIWYG preview of the active text with font, color, outline,
    shadow, alignment and letter case – rendered in the same order as the
    inserted layer (shadow -> outline -> fill). The font size is fitted to the
    preview area; outline and shadow widths stay proportional to the configured
    size so the effect matches the later result."""

    _MARGIN = 10

    def __init__(self, docker):
        super().__init__()
        self._docker = docker
        self._text = ""
        # em advance while measuring vertical text; 0 = horizontal (see _word_w)
        self._vem = 0.0
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_text(self, text):
        self._text = text or ""
        self.update()

    # -- pull the settings from the docker --
    def _opts(self):
        d = self._docker
        try:
            family = d.font_picker.currentFamily() or ""
        except Exception:
            family = ""
        align = d.align_combo.currentData() or "center"
        valign = d.valign_combo.currentData() or "middle"
        size_ref = max(1, d.size_spin.value())
        return {
            "family": family,
            "bold": d.bold_chk.isChecked(),
            "italic": d.italic_chk.isChecked(),
            "underline": d.underline_chk.isChecked(),
            "color": QColor(d._color),
            "align": align,
            "valign": valign,
            "case": d.case_combo.currentData() or "none",
            "tidy": d.tidy_chk.isChecked(),
            "comic": d.comic_chk.isChecked(),
            "crossbar_i": d.crossbar_chk.isChecked(),
            "vertical": d.vertical_chk.isChecked(),
            "spacing": d.spacing_spin.value() / 100.0,
            "size_ref": size_ref,
            "outline": d.outline_chk.isChecked(),
            "outline_color": QColor(d._outline_color),
            "outline_px": float(d.outline_spin.value()),
            "outline2_color": QColor(d._outline2_color),
            "outline2_px": float(d.outline2_spin.value()),
            "shadow": d.shadow_chk.isChecked(),
            "shadow_color": QColor(d._shadow_color),
            "shadow_dx": float(d.shadow_x_spin.value()),
            "shadow_dy": float(d.shadow_y_spin.value()),
            "hyphenate": d.hyph_chk.isChecked() and d.auto_chk.isChecked(),
            "hyph_lang": d._hyph_lang_for(self._text),
            **self._pattern_opts(d),
        }

    def _pattern_opts(self, d):
        """Pattern-fill / soft-outline data for the preview (guarded: these
        controls are built after the preview, so default to 'off' if missing)."""
        out = {"outline_pattern_img": None, "outline_pattern_scale": 100,
               "outline_pattern_target": "outline1",
               "soft": False, "soft_px": 0.0, "soft_blur": 0.0,
               "soft_color": QColor(0, 0, 0), "soft_pattern": False,
               "fill_pattern_img": None, "fill_scale": 100}
        if not (hasattr(d, "_patterns_on") and d._patterns_on()):
            return out                         # experiment off -> no pattern fx
        try:
            outline_on = d.outline_chk.isChecked()
            if outline_on:
                out["outline_pattern_img"] = d._ensure_outline_pattern_img()
                out["outline_pattern_scale"] = d.outline_pattern_scale_spin.value()
                out["outline_pattern_target"] = (
                    d.outline_pattern_target_combo.currentData() or "outline1")
                out["soft"] = d.style_soft_chk.isChecked()
                out["soft_px"] = float(d.style_soft_width_spin.value())
                out["soft_blur"] = float(d.style_soft_blur_spin.value())
                out["soft_color"] = QColor(d._style_soft_color)
                out["soft_pattern"] = d.style_soft_pattern_chk.isChecked()
            # the text itself is no longer auto pattern-filled (patterns apply
            # only to hand-made selections), so no fill_pattern in the preview.
        except Exception:                               # noqa: BLE001
            pass
        return out

    def _fonts(self, o, px):
        fn = QFont(o["family"]) if o["family"] else QFont()
        fn.setItalic(o["italic"])
        fn.setBold(o["bold"])
        fn.setPixelSize(px)
        fb = QFont(o["family"]) if o["family"] else QFont()
        fb.setItalic(o["italic"])
        fb.setBold(True)
        fb.setPixelSize(px)
        return fn, fb

    def _word_w(self, word, fmn, fmb, gbold):
        """Length of a word ALONG its line: the advance width horizontally, the
        stacked em height in vertical text (same reasoning as
        L.vertical_measurer — an upright glyph advances by one em whatever its
        width, so the font metrics are the wrong tape measure there)."""
        if self._vem:
            return sum(len(t) for (t, _b) in word.runs) * self._vem
        tot = 0.0
        for (t, b) in word.runs:
            tot += (fmb if (gbold or b) else fmn).horizontalAdvance(t)
        return tot

    def _line_w(self, words, fmn, fmb, gbold, space_w):
        if not words:
            return 0.0
        return (sum(self._word_w(w, fmn, fmb, gbold) for w in words)
                + space_w * (len(words) - 1))

    def _hyph_split(self, word, avail, fmn, fmb, gbold, lang):
        """Split `word` (preview) so the first part incl. hyphen fits `avail`;
        latest valid break wins. Returns (left, right) or None."""
        breaks = L.hyphenate(word.text, lang)
        if not breaks:
            return None
        best = None
        for b in breaks:
            left, right = L.split_word(word, b)
            if self._word_w(left, fmn, fmb, gbold) <= avail:
                best = (left, right)
            else:
                break
        return best

    def _wrap_words(self, paras, fmn, fmb, gbold, space_w, avail_w, hyph=None):
        """Greedily wrap words (with bold runs) to width, per paragraph. With
        `hyph` (a language code) an over-wide word is split at a syllable break,
        so the preview matches the inserted result — including the same
        typographic limits as L.wrap_greedy (hyphen ladder, splits per word)."""
        lines = []
        for words in paras:
            if not words:
                lines.append([])
                continue
            cur, cur_w = [], 0.0
            queue = list(words)
            guard = 0
            ladder = 0                # lines in a row ending with a hyphen
            splits = 0                # splits of the word in hand
            pending = None            # its tail, to keep the split count

            def may_split():
                return (bool(hyph)
                        and ladder < L.HYPH_MAX_LADDER
                        and splits < L.HYPH_MAX_WORD_SPLITS)

            while queue and guard < 100000:
                guard += 1
                wd = queue.pop(0)
                if wd is not pending:
                    splits = 0
                pending = None
                ww = self._word_w(wd, fmn, fmb, gbold)
                if not cur:
                    if ww <= avail_w:
                        cur, cur_w = [wd], ww
                        ladder = 0
                    else:
                        res = (self._hyph_split(wd, avail_w, fmn, fmb, gbold, hyph)
                               if may_split() else None)
                        if res:
                            left, right = res
                            lines.append([left])
                            queue.insert(0, right)
                            cur, cur_w = [], 0.0
                            ladder += 1
                            splits += 1
                            pending = right
                        else:
                            cur, cur_w = [wd], ww
                            ladder = 0
                elif cur_w + space_w + ww <= avail_w:
                    cur.append(wd)
                    cur_w += space_w + ww
                else:
                    avail = avail_w - cur_w - space_w
                    res = (self._hyph_split(wd, avail, fmn, fmb, gbold, hyph)
                           if may_split() else None)
                    if res:
                        left, right = res
                        cur.append(left)
                        lines.append(cur)
                        queue.insert(0, right)
                        cur, cur_w = [], 0.0
                        ladder += 1
                        splits += 1
                        pending = right
                    elif ww > avail_w and may_split():
                        # too wide for the rest AND for a whole line: close this
                        # line and retry the word against the full width
                        lines.append(cur)
                        cur, cur_w = [], 0.0
                        ladder = 0
                        queue.insert(0, wd)
                        pending = wd
                    else:
                        lines.append(cur)
                        cur, cur_w = [wd], ww
                        ladder = 0
            if cur:
                lines.append(cur)
        return lines

    def _metrics(self, o, px):
        """(fmn, fmb, space_w, line_h) for a size. In vertical text a glyph
        advances by the em down the column and the columns step by the em
        across, so neither comes from the horizontal font metrics."""
        fn, fb = self._fonts(o, px)
        fmn, fmb = QFontMetricsF(fn), QFontMetricsF(fb)
        if o.get("vertical"):
            return fmn, fmb, float(px), px * o["spacing"]
        return fmn, fmb, fmn.horizontalAdvance(" "), fmn.height() * o["spacing"]

    def _fit(self, o, paras, avail_w, avail_h):
        """Largest integer pixel size at which the wrapped words fit.
        Returns (px, lines); lines is a list of word lists.

        Vertical text runs the same search with the axes swapped: a line runs
        down `avail_h` and the block of columns spreads across `avail_w`."""
        lo, hi, best = 6, 160, 6
        best_lines = [[]]
        hyph = o["hyph_lang"] if o.get("hyphenate") else None
        along, across = ((avail_h, avail_w) if o.get("vertical")
                         else (avail_w, avail_h))
        while lo <= hi:
            mid = (lo + hi) // 2
            self._vem = float(mid) if o.get("vertical") else 0.0
            fmn, fmb, space_w, line_h = self._metrics(o, mid)
            lines = self._wrap_words(paras, fmn, fmb, o["bold"], space_w,
                                     along, hyph)
            total_across = line_h * len(lines)
            max_along = max((self._line_w(ws, fmn, fmb, o["bold"], space_w)
                             for ws in lines), default=0.0)
            if total_across <= across and max_along <= along:
                best, best_lines = mid, lines
                lo = mid + 1
            else:
                hi = mid - 1
        self._vem = float(best) if o.get("vertical") else 0.0
        return best, best_lines

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        w, h = self.width(), self.height()
        self._paint_background(p, w, h)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, w - 1, h - 1)

        o = self._opts()
        prepared = prepare_text(self._text, o["case"], o["tidy"],
                                comic=o.get("comic", False),
                                crossbar_i=o.get("crossbar_i", False))
        prepared = prepared.replace("\r\n", "\n").replace("\r", "\n")
        clean, mask = parse_bold(prepared)
        if not clean.strip():
            p.setPen(QColor(0, 0, 0, 110))
            f = QFont()
            f.setItalic(True)
            f.setPixelSize(13)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       self._docker._tr("preview_empty"))
            p.end()
            return

        paras = [L.make_words(pt, pm)
                 for (pt, pm) in L.split_paragraphs(clean, mask)]

        m = self._MARGIN
        avail_w = max(10, w - 2 * m)
        avail_h = max(10, h - 2 * m)
        fs, lines = self._fit(o, paras, avail_w, avail_h)
        fn, fb = self._fonts(o, fs)
        fmn, fmb, space_w, line_h = self._metrics(o, fs)
        scale = fs / float(o["size_ref"])

        if o.get("vertical"):
            self._paint_path(p, self._vertical_path(
                o, lines, fs, fn, fb, fmn, fmb, space_w, line_h,
                m, avail_w, avail_h), o, scale)
            return

        ascent = fmn.ascent()
        block_h = line_h * len(lines)

        if o["valign"] == "top":
            y0 = m + ascent
        elif o["valign"] == "bottom":
            y0 = m + (avail_h - block_h) + ascent
        else:
            y0 = m + (avail_h - block_h) / 2.0 + ascent

        underline_th = max(1.0, fs * 0.06)
        gbold = o["bold"]

        path = QPainterPath()
        for i, words in enumerate(lines):
            line_w = self._line_w(words, fmn, fmb, gbold, space_w)
            if o["align"] == "left":
                x = float(m)
            elif o["align"] == "right":
                x = m + (avail_w - line_w)
            else:
                x = m + (avail_w - line_w) / 2.0
            baseline = y0 + i * line_h
            x_start = x
            for wi, wd in enumerate(words):
                if wi > 0:
                    x += space_w
                for (txt, b) in wd.runs:
                    rf = fb if (gbold or b) else fn
                    if txt:
                        path.addText(x, baseline, rf, txt)
                        x += (fmb if (gbold or b) else fmn).horizontalAdvance(txt)
            if o["underline"] and words:
                uy = baseline + max(1.0, fs * 0.12)
                path.addRect(x_start, uy, x - x_start, underline_th)

        self._paint_path(p, path, o, scale)

    def _vertical_path(self, o, lines, fs, fn, fb, fmn, fmb, space_w, line_h,
                       m, avail_w, avail_h):
        """The text as columns running down, marching leftwards from the right
        (vertical-rl) — the preview twin of the SVG that insert_text_layer
        emits. Each glyph sits in an em-high cell, centered across the column.

        `align` places the block of columns horizontally and `valign` the text
        along each column, matching the insert path.
        """
        em = float(fs)
        block_w = line_h * len(lines)
        if o["align"] == "left":
            right = m + block_w
        elif o["align"] == "right":
            right = m + avail_w
        else:
            right = m + (avail_w + block_w) / 2.0
        gbold = o["bold"]
        # baseline inside an em cell: center the ascent/descent span in the cell
        cell_baseline = (em + fmn.ascent() - fmn.descent()) / 2.0

        path = QPainterPath()
        for i, words in enumerate(lines):
            col_len = self._line_w(words, fmn, fmb, gbold, space_w)
            if o["valign"] == "top":
                y = float(m)
            elif o["valign"] == "bottom":
                y = m + (avail_h - col_len)
            else:
                y = m + (avail_h - col_len) / 2.0
            cx = right - line_h / 2.0 - i * line_h
            for wi, wd in enumerate(words):
                if wi > 0:
                    y += space_w
                for (txt, b) in wd.runs:
                    rf = fb if (gbold or b) else fn
                    rfm = fmb if (gbold or b) else fmn
                    for ch in txt:
                        # upright: the glyph is centered in its column, not
                        # started at its left edge
                        path.addText(cx - rfm.horizontalAdvance(ch) / 2.0,
                                     y + cell_baseline, rf, ch)
                        y += em
        return path

    def _paint_path(self, p, path, o, scale):
        out_pat = o.get("outline_pattern_img")
        fill_pat = o.get("fill_pattern_img")
        # soft (blurred) outline / glow, under everything — rendered isolated so
        # the crisp text on top stays sharp (mirrors the raster insert path)
        if o.get("soft") and (o.get("soft_px", 0) > 0 or o.get("soft_blur", 0) > 0):
            dev = p.device()
            size = QSize(max(1, dev.width()), max(1, dev.height()))
            if o.get("soft_pattern") and out_pat is not None:
                sfill = out_pat
            else:
                sfill = o.get("soft_color") or QColor(0, 0, 0)
            try:
                halo = IMG.soft_outline_image(
                    path, size, o["soft_blur"] * scale, o["soft_px"] * scale,
                    sfill)
                p.drawImage(0, 0, halo)
            except Exception:                           # noqa: BLE001
                pass
        if o["shadow"]:
            sp = QPainterPath(path)
            sp.translate(o["shadow_dx"] * scale, o["shadow_dy"] * scale)
            p.fillPath(sp, QBrush(o["shadow_color"]))
        _tgt = o.get("outline_pattern_target", "outline1")
        _obr = (_scaled_pattern_brush(
                    out_pat, o.get("outline_pattern_scale", 100) * scale)
                if out_pat is not None else None)
        if o["outline"] and o.get("outline2_px", 0) > 0:   # outer, drawn first
            b2 = _obr if (_obr is not None and _tgt in ("outline2", "both")) \
                else QBrush(o["outline2_color"])
            pen2 = QPen(b2, max(0.5, o["outline2_px"] * scale))
            pen2.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.strokePath(path, pen2)
        if o["outline"] and o["outline_px"] > 0:
            b1 = _obr if (_obr is not None and _tgt in ("outline1", "both")) \
                else QBrush(o["outline_color"])
            pen = QPen(b1, max(0.5, o["outline_px"] * scale))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.strokePath(path, pen)
        if fill_pat is not None:
            p.fillPath(path, _scaled_pattern_brush(
                fill_pat, o.get("fill_scale", 100) * scale))
        else:
            p.fillPath(path, QBrush(o["color"]))
        p.end()

    def _paint_background(self, p, w, h):
        _paint_checker(p, w, h)


def _paint_checker(p, w, h):
    """Light-gray checkerboard (shows light and dark text colors well)."""
    p.fillRect(0, 0, w, h, QColor(0xEE, 0xEE, 0xEE))
    tile = 9
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0xDB, 0xDB, 0xDB))
    y = 0
    row = 0
    while y < h:
        x = (row % 2) * tile
        while x < w:
            p.fillRect(x, y, tile, tile, QColor(0xDB, 0xDB, 0xDB))
            x += 2 * tile
        y += tile
        row += 1


# ---------------------------------------------------------------------------
# TextShapR: visual picker for text-shape arrangements
# ---------------------------------------------------------------------------

# Auto-fit floor for the TextShapR candidate search: the smallest size a shape
# may shrink to before it is rejected. Not the docker's target size (size_spin),
# which is the *maximum*; there is no separate minimum-size setting to route to.
SHAPER_MIN_PX = 6


class ShapeCard(QFrame):
    """One numbered thumbnail in the TextShapR grid: a fixed arrangement of the
    text (run lists per line) painted with the docker's current font/color/
    effects, scaled by the shared factor `scale` so all cards are comparable."""

    clicked = pyqtSignal(int)
    W, H = 200, 120

    def __init__(self, index, cand, opts, scale, best=False, w=None, h=None,
                 custom=False):
        super().__init__()
        self._index = index
        self._cand = cand
        self._o = opts
        self._scale = scale
        self._selected = False
        self._best = best
        self._custom = custom
        self.setFixedSize(int(w or self.W), int(h or self.H))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_size(self, w, h, scale):
        self._scale = scale
        self.setFixedSize(int(w), int(h))
        self.update()

    def set_selected(self, on):
        if self._selected != bool(on):
            self._selected = bool(on)
            self.update()

    def set_custom(self, on):
        """Mark this card as a hand-edited arrangement (✎ instead of ★)."""
        if self._custom != bool(on):
            self._custom = bool(on)
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)
        super().mousePressEvent(event)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        w, h = self.width(), self.height()
        _paint_checker(p, w, h)

        o = self._o
        s = self._scale
        lines = self._cand["lines"]
        fpx = max(1, int(round(self._cand["px"] * s)))
        fn = QFont(o["family"]) if o["family"] else QFont()
        fn.setBold(o["bold"])
        fn.setItalic(o["italic"])
        fn.setPixelSize(fpx)
        fb = QFont(fn)
        fb.setBold(True)
        fmn, fmb = QFontMetricsF(fn), QFontMetricsF(fb)
        line_h = fmn.height() * o["spacing"]

        def run_w(runs):
            return sum((fmb if (o["bold"] or b) else fmn).horizontalAdvance(t)
                       for (t, b) in runs)

        block_h = line_h * len(lines)
        y0 = (h - block_h) / 2.0 + fmn.ascent()
        path = QPainterPath()
        underline_th = max(1.0, fpx * 0.06)
        # place each line with the SAME helper the insert path uses, so the
        # thumbnail's alignment matches the layer that Apply will produce.
        xs = L.line_x_positions([run_w(r) for r in lines],
                                o["align"], 6.0, w / 2.0, w - 6.0)
        for i, runs in enumerate(lines):
            x = xs[i]
            baseline = y0 + i * line_h
            x_start = x
            for (txt, b) in runs:
                rf = fb if (o["bold"] or b) else fn
                if txt:
                    path.addText(x, baseline, rf, txt)
                    x += (fmb if (o["bold"] or b) else fmn).horizontalAdvance(txt)
            if o["underline"] and runs:
                path.addRect(x_start, baseline + max(1.0, fpx * 0.12),
                             x - x_start, underline_th)

        # same bottom-to-top order as the inserted layer: shadow, 2nd outline,
        # outline, fill
        if o["shadow"]:
            sp = QPainterPath(path)
            sp.translate(o["shadow_dx"] * s, o["shadow_dy"] * s)
            p.fillPath(sp, QBrush(o["shadow_color"]))
        if o["outline"] and o.get("outline2_px", 0) > 0:   # outer, drawn first
            pen2 = QPen(o["outline2_color"])
            pen2.setWidthF(max(0.5, o["outline2_px"] * s))
            pen2.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.strokePath(path, pen2)
        if o["outline"] and o["outline_px"] > 0:
            pen = QPen(o["outline_color"])
            pen.setWidthF(max(0.5, o["outline_px"] * s))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.strokePath(path, pen)
        p.fillPath(path, QBrush(o["color"]))

        # number badge (top-right) + selection frame
        p.setPen(QColor(0, 0, 0, 130))
        bf = QFont()
        bf.setPixelSize(11)
        p.setFont(bf)
        p.drawText(self.rect().adjusted(0, 3, -6, 0),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, str(self._index + 1))
        if self._custom:                     # hand-edited arrangement
            p.setPen(QColor(0x2D, 0x8C, 0xEB))
            p.drawText(self.rect().adjusted(6, 3, 0, 0),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "\u270e")
        elif self._best:
            p.setPen(QColor(0x2E, 0x8B, 0x57))
            p.drawText(self.rect().adjusted(6, 3, 0, 0),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "\u2605")
        frame = QPen(QColor(0x2D, 0x8C, 0xEB), 2) if self._selected \
            else QPen(QColor(0, 0, 0, 70), 1)
        p.setPen(frame)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(1, 1, w - 2, h - 2)
        p.end()


class TextShapRWidget(QWidget):
    """TextShapR picker as its own docker tab: shows the current line wrapped
    into several candidate shapes (mode bar: Balanced / Round / Tall / Wide,
    plus a Hyphenation toggle) as numbered thumbnails that reflow to the docker
    width. Click selects; Apply inserts the chosen arrangement through the
    normal insert path; Apply + next also advances. Number keys select a card,
    Shift+number applies and advances."""

    _MODES = ("balanced", "round", "tall", "wide")

    def __init__(self, docker):
        super().__init__()
        self._docker = docker
        t = docker._tr

        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lay)

        bar = FlowLayout(margin=0, spacing=4)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for i, mode in enumerate(self._MODES):
            b = QPushButton(t("shaper_" + mode))
            b.setCheckable(True)
            if i == 0:
                b.setChecked(True)
            self._mode_group.addButton(b, i)
            bar.addWidget(b)
        self._mode_group.buttonClicked.connect(lambda *_a: self._reshuffle())
        # auto-pick the round shape when the selection is an ellipse
        self.auto_shape_btn = QPushButton(t("shaper_auto"))
        self.auto_shape_btn.setCheckable(True)
        self.auto_shape_btn.setChecked(True)
        self.auto_shape_btn.setToolTip(t("shaper_auto_tip"))
        self.auto_shape_btn.toggled.connect(lambda *_a: self._reshuffle())
        bar.addWidget(self.auto_shape_btn)
        # live: insert the selected candidate onto the canvas (replacing)
        # so you see it at the real page position; off by default.
        self.live_btn = QPushButton(t("shaper_live"))
        self.live_btn.setCheckable(True)
        self.live_btn.setToolTip(t("shaper_live_tip"))
        self.live_btn.toggled.connect(self._on_live_toggle)
        bar.addWidget(self.live_btn)
        # match: cap the size at the last inserted bubble for a uniform page
        self.match_btn = QPushButton(t("shaper_match"))
        self.match_btn.setCheckable(True)
        self.match_btn.setToolTip(t("shaper_match_tip"))
        self.match_btn.toggled.connect(lambda *_a: self._reshuffle())
        bar.addWidget(self.match_btn)
        # hyphenation is a toggle on top of the mode, not exclusive with it
        self.hyph_btn = QPushButton(t("shaper_hyph"))
        self.hyph_btn.setCheckable(True)
        self.hyph_btn.setChecked(docker.hyph_chk.isChecked())
        self.hyph_btn.toggled.connect(lambda *_a: self._reshuffle())
        bar.addWidget(self.hyph_btn)
        # de-hyphenation: rejoin words the source split across a line before
        # reshaping (the inverse of hyphenation; off by default).
        self.dehyph_btn = QPushButton(t("shaper_dehyph"))
        self.dehyph_btn.setCheckable(True)
        self.dehyph_btn.setToolTip(t("shaper_dehyph_tip"))
        self.dehyph_btn.toggled.connect(lambda *_a: self._reshuffle())
        bar.addWidget(self.dehyph_btn)
        lay.addLayout(bar)

        self._empty = QLabel(t("shaper_empty"))
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._empty)

        # The thumbnails reflow to the available width, so their rows follow the
        # docker size (a wider docker fits more cards per row).
        self._grid_host = QWidget()
        self._flow = FlowLayout(margin=0, spacing=8)
        self._grid_host.setLayout(self._flow)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.StyledPanel)
        scroll.setWidget(self._grid_host)
        lay.addWidget(scroll, 1)

        self._hint = QLabel(t("shaper_hint"))
        self._hint.setStyleSheet("color: gray;")
        self._hint.setWordWrap(True)
        lay.addWidget(self._hint)

        # Manual break editor: a plain text field showing the arrangement,
        # one line per line. Edit the breaks (or a word) directly; the
        # thumbnail follows and the canvas preview follows shortly after.
        self._brk_box = QWidget()
        _brk_lay = QVBoxLayout()
        _brk_lay.setContentsMargins(0, 0, 0, 0)
        _brk_lay.setSpacing(2)
        self._brk_box.setLayout(_brk_lay)
        self.lbl_break = QLabel(t("shaper_break_label"))
        self.lbl_break.setStyleSheet("color: gray;")
        _brk_lay.addWidget(self.lbl_break)
        self.break_edit = QPlainTextEdit()
        self.break_edit.setToolTip(t("shaper_break_tip"))
        self.break_edit.setMaximumHeight(90)
        self.break_edit.textChanged.connect(self._on_break_text_changed)
        _brk_lay.addWidget(self.break_edit)
        self._brk_box.setVisible(False)
        self._break_timer = QTimer(self)
        self._break_timer.setSingleShot(True)
        self._break_timer.setInterval(350)
        self._break_timer.timeout.connect(self._live_preview)
        lay.addWidget(self._brk_box)

        foot = QHBoxLayout()
        self.best_btn = QPushButton(t("shaper_best"))
        self.best_btn.setToolTip(t("shaper_best_tip"))
        self.best_btn.clicked.connect(self._select_best)
        foot.addWidget(self.best_btn)
        foot.addStretch(1)
        self.apply_btn = QPushButton(t("shaper_apply"))
        self.apply_btn.clicked.connect(lambda: self._apply(False))
        foot.addWidget(self.apply_btn)
        self.apply_next_btn = QPushButton(t("shaper_apply_next"))
        self.apply_next_btn.setDefault(True)
        self.apply_next_btn.clicked.connect(lambda: self._apply(True))
        foot.addWidget(self.apply_next_btn)
        lay.addLayout(foot)

        self._cards = []
        self._cands = []
        self._sel = -1
        # What the cards were built from, so a re-fit (size/style/mode change)
        # can put the selection back instead of jumping to card 1.
        self._text_key = None
        # The PINNED arrangement (markup lines). Once the user picks a card its
        # exact line breaks are pinned here and re-fitted on every style change,
        # so the selected shape NEVER silently turns into another one — only new
        # text or an explicit reshuffle (mode/hyphenation toggle) drops it.
        self._custom = None
        self._custom_index = 0         # the slot it was picked/edited in
        self._custom_hand = False      # True only for a hand-EDITED pin (badge)
        self._last_box = (1.0, 1.0)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._relayout_cards)
        self.refresh()

    def showEvent(self, ev):
        # Refresh when the tab becomes visible: the current line, selection or
        # style may have changed while another tab was in front.
        super().showEvent(ev)
        self.refresh()

    # -- data --

    def _box(self):
        """Box to fit into: the selection, else the whole image, else a
        default box (no document open). Returns (w, h, has_doc, shape, rows)
        where shape is 'round' for a roughly elliptical selection, else
        'rect'/None, and rows is its sampled outline (see `_sel_shape`) or
        None when there is no selection to sample."""
        try:
            doc = Krita.instance().activeDocument()
        except Exception:
            doc = None
        if doc is None:
            return 400.0, 300.0, False, None, None
        sel = doc.selection()
        if sel is not None:
            try:
                w, h = float(sel.width()), float(sel.height())
                if w > 0 and h > 0:
                    kind, rows = self._sel_shape(sel)
                    return w, h, True, kind, rows
            except Exception:
                pass
        return float(doc.width()), float(doc.height()), True, None, None

    #: How many rows of the selection are sampled for its outline profile.
    #: A speech balloon's silhouette is smooth, so a couple of dozen samples
    #: describe it as well as hundreds would.
    _SHAPE_ROWS = 20

    @classmethod
    def _sel_shape(cls, sel):
        """(kind, rows) for a selection: 'round' when it fills clearly less
        than its bounding box (an elliptical marquee is ~pi/4), else 'rect';
        `rows` is its outline sampled top to bottom as `_SHAPE_ROWS` width
        fractions normalised to the widest row — the shaper judges fill, rim
        clearance and silhouette against that instead of the bounding box.
        Returns ('rect', None) when the mask can't be read."""
        try:
            w, h = int(sel.width()), int(sel.height())
            if w <= 0 or h <= 0:
                return "rect", None
            data = sel.pixelData(sel.x(), sel.y(), w, h)
            if not data or len(data) < w * h:
                return "rect", None
            col_step = max(1, w // 160)         # bound the work on huge selections
            rows = []
            for i in range(cls._SHAPE_ROWS):
                y = min(h - 1, int((i + 0.5) / cls._SHAPE_ROWS * h))
                base = y * w
                marked = total = 0
                for x in range(0, w, col_step):
                    total += 1
                    if data[base + x]:
                        marked += 1
                rows.append(marked / float(total) if total else 0.0)
            widest = max(rows) if rows else 0.0
            if widest <= 0:
                return "rect", None
            profile = [r / widest for r in rows]
            frac = sum(rows) / len(rows)        # marked area / bounding box
            return ("round" if frac < 0.9 else "rect"), profile
        except Exception:
            return "rect", None

    def _opts(self):
        d = self._docker
        return {
            "family": d.font_picker.currentFamily() or "",
            "bold": d.bold_chk.isChecked(),
            "italic": d.italic_chk.isChecked(),
            "underline": d.underline_chk.isChecked(),
            "color": QColor(d._color),
            "align": d.align_combo.currentData() or "center",
            "spacing": d.spacing_spin.value() / 100.0,
            "outline": d.outline_chk.isChecked(),
            "outline_color": QColor(d._outline_color),
            "outline_px": float(d.outline_spin.value()),
            "outline2_color": QColor(d._outline2_color),
            "outline2_px": float(d.outline2_spin.value()),
            "shadow": d.shadow_chk.isChecked(),
            "shadow_color": QColor(d._shadow_color),
            "shadow_dx": float(d.shadow_x_spin.value()),
            "shadow_dy": float(d.shadow_y_spin.value()),
        }

    def _card_dims(self, box_w, box_h):
        """Card size from the current width: wider docker = bigger cards,
        and the height follows the bubble proportion so text is not cut."""
        avail = max(140, self.width() - 12)
        cols = max(1, int(avail // 210))
        cw = max(160, min(440, int(avail / cols) - 8))
        ratio = (box_h / float(box_w)) if box_w > 0 else 0.62
        ch = int(max(90, min(cw * 1.7, cw * ratio)))
        return cw, ch

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if hasattr(self, "_resize_timer"):
            self._resize_timer.start()

    def _relayout_cards(self):
        """Resize existing cards to the new docker width (no regeneration,
        so the selection is kept)."""
        if not self._cards:
            return
        box_w, box_h = self._last_box
        cw, ch = self._card_dims(box_w, box_h)
        scale = min((cw - 12) / box_w, (ch - 12) / box_h)
        for card in self._cards:
            card.set_size(cw, ch, scale)

    @staticmethod
    def _cand_key(cand):
        """Identity of an arrangement: its lines as markup. Only 'px' changes
        when the same arrangement is re-fitted at another size, so this key
        survives a size/style change and can restore the selection."""
        try:
            return tuple(L.runs_markup(r) for r in (cand.get("lines") or []))
        except Exception:
            return ()

    def refresh(self):
        """Regenerate the candidates for the current line and rebuild the
        cards. Never raises; with no font/text it shows a hint instead.

        As long as the text stays the same, the chosen card stays chosen: the
        arrangement is looked up again after the re-fit (and a hand-edited one
        is re-fitted and kept). Only new text starts over at the best card."""
        if not hasattr(self._docker, "font_picker"):
            return
        d = self._docker
        prev_key = self._cand_key(self._cands[self._sel]) \
            if 0 <= self._sel < len(self._cands) else None
        prev_index = self._sel
        for card in self._cards:
            self._flow.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        self._cands = []
        self._sel = -1

        family = d.font_picker.currentFamily()
        prepared = prepare_text(d._current_text(),
                                d.case_combo.currentData() or "none",
                                d.tidy_chk.isChecked(),
                                comic=d.comic_chk.isChecked(),
                                crossbar_i=d.crossbar_chk.isChecked())
        prepared = prepared.replace("\r\n", "\n").replace("\r", "\n")
        clean, mask = parse_bold(prepared)
        box_w, box_h, has_doc, sel_shape, sel_rows = self._box()
        same_text = (self._text_key == clean)
        self._text_key = clean
        if not same_text:                  # a new line starts over
            prev_key = None
            prev_index = -1
            self._custom = None
            self._custom_hand = False

        if family and clean.strip():
            measurer = _make_measurer(family,
                                      d.spacing_spin.value() / 100.0,
                                      d.bold_chk.isChecked(),
                                      d.italic_chk.isChecked())
            mode = self._MODES[max(0, self._mode_group.checkedId())]
            if self.auto_shape_btn.isChecked() and sel_shape == "round":
                mode = "round"      # elliptical selection -> fit an ellipse
            max_px = d.size_spin.value()
            last = getattr(d, "_last_insert_px", None)
            if self.match_btn.isChecked() and last:
                max_px = min(max_px, int(last))   # match neighbouring bubbles
            try:
                self._cands = L.shape_candidates(
                    clean, measurer, box_w, box_h,
                    max_px, SHAPER_MIN_PX, d.pad_spin.value() / 100.0,
                    mode=mode, hyphenate=self.hyph_btn.isChecked(),
                    lang=d._hyph_lang_for(clean), mask=mask, limit=10,
                    dehyphenate=self.dehyph_btn.isChecked(),
                    inset=self._outline_inset(),
                    shape_rows=sel_rows)
            except Exception:
                self._cands = []
            # a hand-edited arrangement survives the re-fit as its own card
            if self._custom:
                self._readd_custom(measurer, box_w, box_h,
                                   d.pad_spin.value() / 100.0, max_px)

        have = bool(self._cands)
        self._empty.setVisible(not have)
        self.apply_btn.setEnabled(have)
        self.apply_next_btn.setEnabled(have)
        self.best_btn.setEnabled(have)
        self._hint.setText(self._docker._tr(
            "shaper_hint" if has_doc else "shaper_no_doc"))
        if not have:
            self._brk_box.setVisible(False)
            return
        o = self._opts()
        self._last_box = (box_w, box_h)
        cw, ch = self._card_dims(box_w, box_h)
        # one shared scale so the size differences between shapes stay visible
        scale = min((cw - 12) / box_w, (ch - 12) / box_h)
        for i, cand in enumerate(self._cands):
            custom = bool(cand.get("custom"))
            card = ShapeCard(i, cand, o, scale, best=(i == 0 and not custom),
                             w=cw, h=ch, custom=custom)
            card.clicked.connect(lambda i: self._select(i, user=True))
            self._flow.addWidget(card)
            self._cards.append(card)
        self._select(self._restore_index(prev_key, prev_index))

    def _readd_custom(self, measurer, box_w, box_h, pad_frac, max_px):
        """Re-fit the hand-edited arrangement to the current style/box and put
        it back into the candidate list (at the slot it was picked from), so
        changing the size does not throw the manual line breaks away."""
        word_lines = []
        for ln in self._custom:
            c, m = parse_bold(ln)
            ws = L.make_words(c, list(m))
            if ws:
                word_lines.append(ws)
        if not word_lines:
            return
        _ins = 2.0 * self._outline_inset()
        try:
            res = L.fit_fixed_lines(word_lines, measurer,
                                    box_w * (1.0 - pad_frac) - _ins,
                                    box_h * (1.0 - pad_frac) - _ins, max_px, 6)
        except Exception:
            res = None
        if not res:
            self._custom = None
            self._custom_hand = False
            return
        px, wl = res
        runs = [L.line_runs(ws) for ws in wl]
        cand = {"px": px, "k": len(runs), "lines": runs,
                "words": [list(ws) for ws in wl],
                "custom": bool(self._custom_hand)}
        key = self._cand_key(cand)
        if any(self._cand_key(c) == key for c in self._cands):
            return                       # the edit matches a generated shape
        i = self._custom_index
        if not 0 <= i <= len(self._cands):
            i = len(self._cands)
        self._cands.insert(i, cand)      # back into the slot it was edited in

    def _outline_inset(self):
        """Per-side px to reserve for the outline so outlined text stays inside
        the bubble (the stroke extends ~half its width beyond the glyph; a soft
        outline spreads further)."""
        d = self._docker
        if not d.outline_chk.isChecked():
            return 0.0
        px = max(d.outline_spin.value(), d.outline2_spin.value()) / 2.0
        try:
            if d._patterns_on() and d.style_soft_chk.isChecked():
                px += (d.style_soft_width_spin.value()
                       + 2.0 * d.style_soft_blur_spin.value())
        except Exception:                               # noqa: BLE001
            pass
        return float(px)

    def _restore_index(self, key, index):
        """Card to select after a rebuild: the same arrangement if it is still
        there, else the same slot, else the recommended first card."""
        if key:
            for i, cand in enumerate(self._cands):
                if self._cand_key(cand) == key:
                    return i
        if 0 <= index < len(self._cands):
            return index
        return 0

    # -- interaction --

    def restyle(self):
        """Re-fit after a style change (font, size, spacing, alignment).

        Rebuilds the cards with the new style and, when 'live' is on, pushes
        the selection back onto the page — so changing the size shows the
        difference here AND on the canvas straight away."""
        self.refresh()
        self._live_preview()

    def _select(self, index, user=False):
        if not (0 <= index < len(self._cards)):
            return
        self._sel = index
        for i, card in enumerate(self._cards):
            card.set_selected(i == index)
        self._load_break_editor(index)
        if user:
            # PIN the chosen arrangement: its exact line breaks are re-fitted on
            # every later style change (size/font/colour/outline/pattern), so the
            # selection never silently morphs into a different shape.
            cand = self._cands[index]
            self._custom = tuple(L.runs_markup(r) for r in cand.get("lines", []))
            self._custom_index = index
            self._custom_hand = bool(cand.get("custom"))
            self._live_preview()

    def _reshuffle(self):
        """Explicit 'give me different shapes' (mode / auto-shape / match /
        hyphenation toggle): drop the pinned selection so the fresh best for the
        new setting is shown."""
        self._custom = None
        self._custom_hand = False
        self.refresh()

    def _live_preview(self):
        """When 'live' is on, insert the selected candidate onto the
        canvas (replacing the line's previous layer) so it shows at the
        real page position."""
        if not (hasattr(self, "live_btn") and self.live_btn.isChecked()):
            return
        if 0 <= self._sel < len(self._cands):
            try:
                self._docker.insert_arrangement(
                    self._cands[self._sel], False, replace=True)
            except Exception:
                pass

    def _on_live_toggle(self, on):
        if on:
            self._live_preview()

    def _load_break_editor(self, index):
        """Show the selected candidate's arrangement in the editable text
        field (one line per line, bold as **...**)."""
        cand = self._cands[index] if 0 <= index < len(self._cands) else None
        lines = cand.get("lines") if cand else None
        if not lines:
            self._brk_box.setVisible(False)
            return
        text = "\n".join(L.runs_markup(runs) for runs in lines)
        self.break_edit.blockSignals(True)
        self.break_edit.setPlainText(text)
        self.break_edit.blockSignals(False)
        self._brk_box.setVisible(True)

    def _on_break_text_changed(self):
        """Rebuild the selected candidate from the edited text (one line
        per line); update the thumbnail now, the canvas preview shortly."""
        if not (0 <= self._sel < len(self._cands)):
            return
        lines = [ln for ln in self.break_edit.toPlainText().split("\n")
                 if ln.strip()]
        if not lines:
            return
        runs = []
        for ln in lines:
            clean, mask = parse_bold(ln)
            runs.append(L.make_runs(clean, mask))
        cand = self._cands[self._sel]
        cand["lines"] = runs
        cand["k"] = len(runs)
        cand["custom"] = True
        cand.pop("words", None)
        # remember the edit so a later re-fit (size, style, mode) keeps it
        self._custom = tuple(L.runs_markup(r) for r in runs)
        self._custom_index = self._sel
        self._custom_hand = True                 # hand-edited -> show the badge
        self._cards[self._sel].set_custom(True)
        self._cards[self._sel].update()
        self._break_timer.start()

    def _select_best(self):
        """Pick the recommended candidate (the first, biggest-fitting)."""
        if self._cards:
            self._select(0, user=True)
            self._cards[0].setFocus()

    def _apply(self, advance):
        if not (0 <= self._sel < len(self._cands)):
            return
        ok = self._docker.insert_arrangement(self._cands[self._sel], advance)
        if ok and advance:
            self.refresh()        # show the shapes for the next line

    @staticmethod
    def _digit(event):
        """Digit 0-9 of a key event, robust against Shift (which turns the key
        into a symbol on most layouts). None if not a digit key."""
        vk = event.nativeVirtualKey()      # Windows/X11: VK stays '0'..'9'
        if 0x30 <= vk <= 0x39:
            return vk - 0x30
        k = event.key()
        if Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
            return k - Qt.Key.Key_0
        return None

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Right, Qt.Key.Key_Down) \
                and self._cards:
            step = -1 if key in (Qt.Key.Key_Left, Qt.Key.Key_Up) else 1
            cur = self._sel if self._sel >= 0 else 0
            self._select(max(0, min(cur + step, len(self._cards) - 1)),
                         user=True)
            return
        digit = self._digit(event)
        if digit is not None:
            index = 9 if digit == 0 else digit - 1       # key 0 = card 10
            if 0 <= index < len(self._cards):
                self._select(index, user=True)
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._apply(True)
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Movable panel wrapper (customizable layout, step 2a)
# ---------------------------------------------------------------------------

class FlowLayout(QLayout):
    """A layout that lays widgets out left-to-right and wraps to the next line
    when they don't fit the available width (Qt's classic flow-layout example).

    Used for the BubblR control rows so the buttons/fields reflow to the
    docker width instead of overflowing off the right edge."""

    def __init__(self, margin=0, spacing=4):
        super(FlowLayout, self).__init__()
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        # empty flags = don't expand. Qt 6 dropped the Qt.Orientations flags
        # wrapper and Orientation is itself a flag, so Qt.Orientation(0) is the
        # one spelling that means "no directions" on both PyQt5 and PyQt6.
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        right = rect.right() - m.right()
        line_h = 0
        space = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            w, h = hint.width(), hint.height()
            if x + w > right and line_h > 0:      # wrap to next line
                x = rect.x() + m.left()
                y = y + line_h + space
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += w + space
            line_h = max(line_h, h)
        return y + line_h - rect.y() + m.bottom()


class PanelBox(QFrame):
    """A relocatable panel: a small header bar (title + a ⋮ menu that moves
    the panel to another tab) above its content. The header only shows in
    "Customize layout" mode, so in normal use the panel looks like plain
    content. The docker owns the actual move logic (`_move_panel_to_tab`)."""

    def __init__(self, pid, docker):
        super(PanelBox, self).__init__()
        self._pid = pid
        self._docker = docker
        self._edit = False
        self._locked = False           # pinned: excluded from dragging
        self._drag_pos = None          # press point on the header (drag start)
        self._drop_zone = None         # "top"/"bottom" while a panel hovers
        # declared early: event filters below can fire during construction
        self._resize_grip = None
        self._resize_ref = None
        self._user_height = 0
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)      # a panel can be dropped onto this one
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        self._header = QWidget()
        h = QHBoxLayout(self._header)
        h.setContentsMargins(4, 0, 2, 0)
        h.setSpacing(2)
        # A grip glyph hints the header is a drag handle in customize mode.
        self._grip = QLabel("⠿")
        self._grip.setStyleSheet("color: palette(mid);")
        h.addWidget(self._grip)
        self._title = QLabel()
        self._title.setStyleSheet("color: palette(mid); font-weight: bold;")
        h.addWidget(self._title, 1)
        # padlock: pin a panel so it can't be dragged even in customize mode
        self._lock_btn = QToolButton()
        self._lock_btn.setAutoRaise(True)
        self._lock_btn.setCheckable(True)
        self._lock_btn.setText("🔓")
        self._lock_btn.toggled.connect(
            lambda on: self._docker._set_panel_locked(self._pid, on))
        h.addWidget(self._lock_btn)
        self._menu_btn = QToolButton()
        self._menu_btn.setText("⋮")
        self._menu_btn.setAutoRaise(True)
        self._menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self._menu_btn)
        menu.aboutToShow.connect(self._build_menu)
        self._menu = menu
        self._menu_btn.setMenu(menu)
        h.addWidget(self._menu_btn)
        v.addWidget(self._header)
        # The header (title + grip) is the drag handle. Watch its mouse events.
        self._header.installEventFilter(self)
        self._title.installEventFilter(self)
        self._grip.installEventFilter(self)
        self._header.setCursor(Qt.CursorShape.OpenHandCursor)
        self.body = QWidget()
        self._body_lay = QVBoxLayout(self.body)
        self._body_lay.setContentsMargins(0, 0, 0, 0)
        self._body_lay.setSpacing(6)
        v.addWidget(self.body, 1)
        # resize handle along the bottom edge, shown only in Customize mode;
        # drag it to set the panel's height (persisted by the docker).
        self._resize_grip = QWidget()
        self._resize_grip.setFixedHeight(7)
        self._resize_grip.setCursor(Qt.CursorShape.SizeVerCursor)
        self._resize_grip.setStyleSheet(
            "background: palette(mid); border-radius: 2px;")
        self._resize_grip.setVisible(False)
        self._resize_grip.installEventFilter(self)
        v.addWidget(self._resize_grip)
        self._user_height = 0          # 0 = natural size, >0 = fixed height
        self._resize_ref = None
        self._header.setVisible(False)

    def body_layout(self):
        return self._body_lay

    def set_title(self, text):
        self._title.setText(text)

    def set_edit(self, on):
        self._edit = bool(on)
        self._header.setVisible(self._edit)
        self._resize_grip.setVisible(self._edit)
        self._apply_frame()

    def set_user_height(self, h):
        """Fix the panel height to `h` px (0 = back to natural sizing)."""
        self._user_height = int(h) if h and h > 0 else 0
        if self._user_height > 0:
            self.setMinimumHeight(self._user_height)
            self.setMaximumHeight(self._user_height)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)

    def set_locked(self, on):
        """Pin/unpin the panel (reflects docker state; does not re-save)."""
        self._locked = bool(on)
        self._lock_btn.blockSignals(True)
        self._lock_btn.setChecked(self._locked)
        self._lock_btn.setText("🔒" if self._locked else "🔓")
        self._lock_btn.blockSignals(False)
        self._header.setCursor(
            Qt.CursorShape.ForbiddenCursor if self._locked else Qt.CursorShape.OpenHandCursor)

    def _apply_frame(self):
        self.setFrameShape(QFrame.Shape.StyledPanel if self._edit else QFrame.Shape.NoFrame)
        if self._edit and self._drop_zone == "top":
            self.setStyleSheet("PanelBox { border-top: 2px solid palette(highlight); }")
        elif self._edit and self._drop_zone == "bottom":
            self.setStyleSheet("PanelBox { border-bottom: 2px solid palette(highlight); }")
        else:
            self.setStyleSheet("")

    def _build_menu(self):
        self._menu.clear()
        self._docker._fill_panel_menu(self._menu, self._pid)

    # -- drag source (drag the header to relocate the panel) ----------------

    def eventFilter(self, obj, ev):
        if obj is self._resize_grip and self._edit:
            et = ev.type()
            if et == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                self._resize_ref = (ev.globalPos().y(), self.height())
                return True
            if et == QEvent.Type.MouseMove and self._resize_ref is not None:
                dy = ev.globalPos().y() - self._resize_ref[0]
                self.set_user_height(max(80, self._resize_ref[1] + dy))
                return True
            if et == QEvent.Type.MouseButtonRelease and self._resize_ref is not None:
                self._resize_ref = None
                self._docker._save_panel_heights()
                return True
        if (obj in (self._header, self._title, self._grip)
                and self._edit and not self._locked):
            et = ev.type()
            if et == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = ev.pos()
            elif et == QEvent.Type.MouseMove and self._drag_pos is not None:
                if ((ev.pos() - self._drag_pos).manhattanLength()
                        >= QApplication.startDragDistance()):
                    self._drag_pos = None
                    self._start_drag()
                    return True
            elif et == QEvent.Type.MouseButtonRelease:
                self._drag_pos = None
        return super(PanelBox, self).eventFilter(obj, ev)

    def _start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(PANEL_MIME, self._pid.encode("utf-8"))
        drag.setMimeData(mime)
        pm = self.grab()
        if pm.width() > 320:
            pm = pm.scaledToWidth(320, Qt.TransformationMode.SmoothTransformation)
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(20, 10))
        self._docker._panel_drag_started()
        drag.exec(Qt.DropAction.MoveAction)
        self._docker._panel_drag_finished()

    # -- drop target (another panel dropped onto this one) ------------------

    def dragEnterEvent(self, ev):
        if self._edit and ev.mimeData().hasFormat(PANEL_MIME):
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        if not (self._edit and ev.mimeData().hasFormat(PANEL_MIME)):
            ev.ignore()
            return
        zone = "top" if ev.pos().y() < self.height() / 2 else "bottom"
        if zone != self._drop_zone:
            self._drop_zone = zone
            self._apply_frame()
        ev.acceptProposedAction()

    def dragLeaveEvent(self, ev):
        if self._drop_zone is not None:
            self._drop_zone = None
            self._apply_frame()

    def dropEvent(self, ev):
        after = self._drop_zone == "bottom"
        self._drop_zone = None
        self._apply_frame()
        if not (self._edit and ev.mimeData().hasFormat(PANEL_MIME)):
            ev.ignore()
            return
        src = bytes(ev.mimeData().data(PANEL_MIME)).decode("utf-8")
        self._docker._drop_panel_rel(src, self._pid, after)
        ev.acceptProposedAction()


# ---------------------------------------------------------------------------
# Detach host dockers
# ---------------------------------------------------------------------------

class TyperExtraHost(DockWidget):
    """A generic host docker for a *detached* TypeR panel. Krita only shows
    dockers registered at startup, so a small pool of these is pre-registered
    (see :func:`register`). They stay empty until the user detaches a panel
    into one; each registers itself in ``_EXTRA_HOSTS`` by its slot so the
    main docker can find a free host."""

    _SLOT = 0     # overridden per registered subclass

    def __init__(self):
        super(TyperExtraHost, self).__init__()
        slot = self.__class__._SLOT
        self._slot = slot
        self.setWindowTitle("TypeR panel %d" % (slot + 1))
        host = QWidget()
        self._lay = QVBoxLayout(host)
        self._lay.setContentsMargins(4, 4, 4, 4)
        self._lay.setSpacing(4)
        self._placeholder = QLabel("")
        self._placeholder.setStyleSheet("color: gray;")
        self._placeholder.setWordWrap(True)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lay.addWidget(self._placeholder)
        self._lay.addStretch(1)
        self.setWidget(host)
        _EXTRA_HOSTS[slot] = self

    def host_layout(self):
        return self._lay

    def set_hint(self, text):
        self._placeholder.setText(text)

    def show_placeholder(self, on):
        self._placeholder.setVisible(bool(on))

    def canvasChanged(self, canvas):
        pass


# ---------------------------------------------------------------------------
# Docker UI
# ---------------------------------------------------------------------------

class MainCharsDialog(QDialog):
    """Mark a manga's main characters.

    In a long series the character list grows to dozens of names while three or
    four of them speak on nearly every page. Starring those keeps them at the
    top of the character dropdown — and of the flat preset list in simple mode,
    where every character's styles share one combo. Purely a view: no preset
    data is touched, so unstarring never loses anything.
    """

    def __init__(self, parent, tr, groups, main_map, current_manga):
        QDialog.__init__(self, parent)
        self._tr = tr
        self._groups = groups or {}
        # working copy — only written back when the dialog is accepted
        self._map = {str(m): [str(c) for c in (names or [])]
                     for m, names in (main_map or {}).items()}
        self._boxes = {}

        self.setWindowTitle(tr("mainchar_title"))
        self.setMinimumWidth(360)
        outer = QVBoxLayout(self)

        intro = QLabel(tr("mainchar_intro"))
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#999;")
        outer.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("mainchar_manga")))
        self.manga_combo = QComboBox()
        for g in sorted(self._groups.keys(), key=lambda s: s.lower()):
            self.manga_combo.addItem(g, g)
        idx = self.manga_combo.findData(current_manga)
        if idx >= 0:
            self.manga_combo.setCurrentIndex(idx)
        self.manga_combo.currentIndexChanged.connect(self._on_manga)
        row.addWidget(self.manga_combo, 1)
        outer.addLayout(row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setMinimumHeight(220)
        outer.addWidget(self._scroll, 1)

        self.clear_btn = QPushButton(tr("mainchar_clear"))
        self.clear_btn.clicked.connect(self._clear)
        btns = QHBoxLayout()
        btns.addWidget(self.clear_btn)
        btns.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        btns.addWidget(box)
        outer.addLayout(btns)

        self._build_list()

    # -- internals ---------------------------------------------------------
    def _manga(self):
        return self.manga_combo.currentData() or ""

    def _build_list(self):
        """One checkbox per character of the selected manga."""
        manga = self._manga()
        chars = self._groups.get(manga) or {}
        body = QWidget()
        lay = QVBoxLayout(body)
        self._boxes = {}
        starred = set(c.lower() for c in self._map.get(manga, []))
        names = sorted((str(c) for c in chars.keys()), key=lambda s: s.lower())
        if not names:
            empty = QLabel(self._tr("mainchar_none"))
            empty.setStyleSheet("color:#999;")
            lay.addWidget(empty)
        for name in names:
            cb = QCheckBox("%s  (%d)" % (name, len(chars.get(name) or {})))
            cb.setChecked(name.lower() in starred)
            cb.toggled.connect(lambda _c=False, n=name: self._on_toggle(n))
            self._boxes[name] = cb
            lay.addWidget(cb)
        lay.addStretch(1)
        self._scroll.setWidget(body)

    def _collect(self):
        """Store the current checkbox state for the selected manga."""
        manga = self._manga()
        if not manga or not self._boxes:
            return
        chosen = [n for n, cb in self._boxes.items() if cb.isChecked()]
        chosen.sort(key=lambda s: s.lower())
        if chosen:
            self._map[manga] = chosen
        else:
            self._map.pop(manga, None)

    def _on_toggle(self, _name):
        self._collect()

    def _on_manga(self):
        self._build_list()

    def _clear(self):
        for cb in self._boxes.values():
            cb.setChecked(False)
        self._collect()

    # -- API ---------------------------------------------------------------
    def result_map(self):
        """{manga: [main characters]} as the user left it."""
        self._collect()
        return {m: list(v) for m, v in self._map.items() if v}


class TextTypeFontsDialog(QDialog):
    """Pick the font for each kind of text.

    The catalogue names a font per type, but those are the comic faces the
    convention asks for — licensed, and often not installed. So the defaults are
    only ever a suggestion: this is where someone says what their dialogue
    actually looks like. Every row can go back to the default on its own, and
    the whole set can go back at once.
    """

    def __init__(self, parent, tr, installed, overrides, docker):
        QDialog.__init__(self, parent)
        self._tr = tr
        self._installed = installed
        self._ov = dict(overrides or {})
        self._docker = docker          # for labels + add/remove of custom types
        self._rows = {}

        self.setWindowTitle(tr("ttf_title"))
        self.setMinimumWidth(520)
        outer = QVBoxLayout(self)

        intro = QLabel(tr("ttf_intro"))
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#999;")
        outer.addWidget(intro)

        # more rows than fit a screen comfortably; the grid rebuilds itself when
        # the user adds or removes a custom type.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._body = QWidget()
        self._grid = QGridLayout(self._body)
        self._grid.setColumnStretch(1, 1)
        scroll.setWidget(self._body)
        outer.addWidget(scroll, 1)
        self._build_rows()

        btns = QHBoxLayout()
        self.add_btn = QPushButton(tr("ttf_add"))
        self.add_btn.setToolTip(tr("ttf_add_tip"))
        self.add_btn.clicked.connect(self._add_type)
        btns.addWidget(self.add_btn)
        self.reset_all_btn = QPushButton(tr("ttf_reset_all"))
        self.reset_all_btn.clicked.connect(self._reset_all)
        btns.addWidget(self.reset_all_btn)
        btns.addStretch(1)
        close = QPushButton(tr("ttf_close"))
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        outer.addLayout(btns)

        self._refresh()

    def _clear_grid(self):
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()

    def _build_rows(self):
        """(Re)build one row per text type. Built-in rows offer Reset; custom
        rows offer Remove."""
        self._clear_grid()
        self._rows = {}
        for r, tid in enumerate(TT.ids()):
            self._grid.addWidget(QLabel(self._docker._tt_label(tid)), r, 0)
            val = QLabel()
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._grid.addWidget(val, r, 1)
            pick = QPushButton(self._tr("ttf_choose"))
            pick.clicked.connect(lambda _c=False, t=tid: self._choose(t))
            self._grid.addWidget(pick, r, 2)
            if TT.is_custom(tid):
                rm = QPushButton(self._tr("ttf_remove"))
                rm.setToolTip(self._tr("ttf_remove_tip"))
                rm.clicked.connect(lambda _c=False, t=tid: self._remove(t))
                self._grid.addWidget(rm, r, 3)
                self._rows[tid] = (val, None)
            else:
                rst = QPushButton(self._tr("ttf_reset_one"))
                rst.setToolTip(self._tr("ttf_reset_one_tip"))
                rst.clicked.connect(lambda _c=False, t=tid: self._reset_one(t))
                self._grid.addWidget(rst, r, 3)
                self._rows[tid] = (val, rst)

    def overrides(self):
        """What the user chose; only real choices, never the defaults."""
        return {k: v for k, v in self._ov.items() if v}

    def _refresh(self):
        for tid, (val, rst) in self._rows.items():
            own = self._ov.get(tid)
            fam = TT.effective_font(tid, self._installed, self._ov)
            if own:
                val.setText(fam)
                val.setStyleSheet("")
            else:
                # say it is a default, so "why is this not my font" never comes up
                val.setText(self._tr("ttf_default").format(font=fam))
                val.setStyleSheet("color:#888;")
            if rst is not None:
                rst.setEnabled(bool(own))
        self.reset_all_btn.setEnabled(any(self._ov.values()))

    def _choose(self, tid):
        cur = QFont(TT.effective_font(tid, self._installed, self._ov))
        font, ok = QFontDialog.getFont(cur, self, self._tr("ttf_pick_for").format(
            name=self._docker._tt_label(tid)))
        if ok:
            self._ov[tid] = font.family()
            self._refresh()

    def _reset_one(self, tid):
        self._ov.pop(tid, None)
        self._refresh()

    def _reset_all(self):
        self._ov = {}
        self._refresh()

    def _add_type(self):
        """Create a user text type: ask for a name, then let the user decide
        between snapshotting the current style or the neutral default (only when
        they explicitly pick "current style"), then register it via the docker."""
        name, ok = QInputDialog.getText(
            self, self._tr("ttf_add"), self._tr("ttf_add_name"))
        if not ok or not name.strip():
            return
        name = name.strip()
        box = QMessageBox(self)
        box.setWindowTitle(self._tr("ttf_add"))
        box.setText(self._tr("ttf_add_style_q"))
        b_current = box.addButton(self._tr("ttf_add_current"),
                                  QMessageBox.ButtonRole.AcceptRole)
        b_default = box.addButton(self._tr("ttf_add_default"),
                                  QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(b_default)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_current:
            # snapshot the docker's current look (font + style)
            style = self._docker._collect_preset()
            font = style.pop("font", "") or ""
            self._docker._add_custom_type(name, font, style)
        elif clicked is b_default:
            cur = QFont(self._installed[0] if self._installed else "")
            font, ok2 = QFontDialog.getFont(cur, self, self._tr("ttf_add"))
            self._docker._add_custom_type(name, font.family() if ok2 else "")
        else:
            return                              # cancelled
        self._build_rows()
        self._refresh()

    def _remove(self, tid):
        self._docker._remove_custom_type(tid)
        self._ov.pop(tid, None)         # keep the working copy consistent
        self._build_rows()
        self._refresh()


class TyperDocker(DockWidget):

    def __init__(self):
        super().__init__()

        self._pairs = []
        self._pair_pages = []        # page label per unit (parallel to _pairs)
        self._pages = []             # ordered (label, first_unit_index)
        self._index = 0
        self._done = set()
        self._color = QColor(0, 0, 0)
        self._outline_color = QColor(255, 255, 255)
        self._outline2_color = QColor(0, 0, 0)   # 2nd (outer) outline colour
        self._shadow_color = QColor(0, 0, 0)
        # pattern-filled + soft (blurred) outline (raster insert path). Source is
        # a file OR a Krita pattern resource, resolved lazily to a QImage (cache).
        self._style_soft_color = QColor(0, 0, 0)
        self._outline_pattern_path = ""
        self._outline_pattern_krita_name = ""
        self._outline_pattern_img = None
        # pattern/gradient used to fill a hand-made SELECTION (Style tab)
        self._fill_pattern_path = ""
        self._fill_pattern_krita_name = ""
        self._fill_pattern_img = None
        self._fill_pattern_stretch = False   # True for a gradient (fit, no tile)
        self._fill_pattern_grad_spec = None  # gradient params, re-rendered at size
        self._lang = self._load_lang()
        self._groups = self._load_groups()
        # Reopen on the manga (and character) worked on last time; _ensure_levels
        # falls back to the first one if it was since renamed or deleted.
        _last = self._load_last_manga()
        self._group = _last.get("group", "")
        self._char = _last.get("char", "")
        self._script_path = ""             # file name of the active script
        # The active script's comments. Must exist from the start: the docker
        # opens an empty "Untitled" session before anything is ever loaded, and
        # snapshotting that session already reads this.
        self._script_comments = []
        self._preset_usage = self._load_preset_usage()
        # Who the main characters are, per manga: they head the character and
        # preset dropdowns instead of being buried in a long alphabetical list.
        self._main_chars_map = self._load_main_chars()
        # Multiple loaded scripts ("tabs"). Each session is a dict with a unique
        # id; the QTabBar stores that id as tab data, so tab order and the
        # session list stay decoupled (reordering tabs is harmless). The live
        # self._pairs/_index/_done/… always mirror the ACTIVE session and are
        # snapshotted back into it on every tab switch/close.
        self._sessions = []
        self._active_sid = None
        self._next_sid = 1

        # Load user-defined text types before any text-type list is built, so
        # they appear everywhere the built-ins do (Style combo, Fonts dialog).
        # Stored in kritarc, so they and the font choices survive plugin updates.
        # Defensive: a bad stored value must never abort the whole docker.
        try:
            TT.register_custom(self._load_custom_types())
        except Exception:
            pass

        # The docker is organized into four top-level tabs so the everyday
        # workflow (Type: script -> line -> bubble -> font -> insert) stays
        # uncluttered; styling, presets and setup are one click away. Each
        # page scrolls on its own so nothing ever squishes or clips.
        main = QWidget()
        outer = QVBoxLayout()
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)
        main.setLayout(outer)

        self.main_tabs = QTabWidget()
        outer.addWidget(self.main_tabs, 1)

        def _page():
            page = QWidget()
            lay = QVBoxLayout()
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(6)
            page.setLayout(lay)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(page)
            self.main_tabs.addTab(scroll, "")
            return lay

        lay_type = _page()       # everyday insert loop
        lay_style = _page()      # font variants, alignment, effects, fitting
        lay_setup = _page()      # language + panel layout
        lay_bubblr = _page()     # auto-detect bubbles + per-bubble styles
        lay_shapr = _page()      # TextShapR: pick a shape arrangement
        lay_sfx = _page()        # SFX Helper (embedded MangaSFX docker)
        lay_fonts = _page()      # Font favourites (starred fonts + categories)

        # Presets are no longer their own tab: they live inside the Type
        # tab as a self-contained panel container. Building them into this
        # container's layout keeps every `lay_presets.addWidget(...)` call
        # below unchanged; the container is inserted into the Type tab.
        self.presets_panel = QWidget()
        lay_presets = QVBoxLayout()
        lay_presets.setContentsMargins(0, 0, 0, 0)
        lay_presets.setSpacing(6)
        self.presets_panel.setLayout(lay_presets)

        # movable-panel registry (customizable layout, step 2a)
        self._tab_layouts = {"type": lay_type, "style": lay_style,
                             "setup": lay_setup, "bubblr": lay_bubblr,
                             "shapr": lay_shapr, "sfx": lay_sfx,
                             "fonts": lay_fonts}
        self._panels = {}          # panel id -> PanelBox
        self._panel_tab = {}       # panel id -> current tab id
        self._panel_home = {}      # panel id -> default (home) tab id
        self._detached = {}        # panel id -> slot int, or "float"
        self._float_dialogs = {}   # panel id -> floating QDialog (fallback)

        # BubblR tab state. BubblR only DETECTS and orders the bubbles; the
        # text is typed/placed from the Type tab (Insert fills the current
        # bubble and steps to the next). So there is no script mapping here.
        self._bp_boxes = []        # ordered detected box dicts (x/y/w/h/shape)
        self._bp_click_seq = []    # box indices Ctrl-clicked for renumbering
        self._bp_current = -1      # current bubble (Insert target / step ptr)
        self._bp_placed = set()    # bubble indices already filled with text

        # Make a Setup section collapsible under a checkable button, exactly
        # like the "Layout & sizes" / "Experimental" sections: the button shows/
        # hides a content box and remembers its open/closed state across
        # restarts. Returns (button, inner_layout); callers add content to the
        # inner layout so it lives inside the collapsible box (and travels with
        # the panel when the layout is customized).
        def _collapsible(body_lay, setting_key, default_open=True):
            app = Krita.instance()
            btn = QPushButton()
            btn.setCheckable(True)
            is_open = app.readSetting(
                "typer_kr", setting_key,
                "true" if default_open else "false") == "true"
            btn.setChecked(is_open)
            body_lay.addWidget(btn)
            box = QWidget()
            inner = QVBoxLayout()
            inner.setContentsMargins(6, 2, 6, 2)
            inner.setSpacing(4)
            box.setLayout(inner)
            body_lay.addWidget(box)
            box.setVisible(is_open)
            btn.toggled.connect(
                lambda on, b=box, k=setting_key: (
                    b.setVisible(bool(on)),
                    Krita.instance().writeSetting(
                        "typer_kr", k, "true" if on else "false")))
            return btn, inner

        # --- general settings panel (language + insert/preset options) ---
        _sg_pb = self._new_panel("setup_general", "setup")
        self.setup_general_toggle, _sgl = _collapsible(
            _sg_pb.body_layout(), "setupGeneralOpen")
        lang_row = QHBoxLayout()
        self.lang_label = QLabel()
        self.lang_combo = NoScrollComboBox()
        for code, name in LANG_ORDER:
            self.lang_combo.addItem(name, code)
        start = 0
        for i, (code, _name) in enumerate(LANG_ORDER):
            if code == self._lang:
                start = i
        self.lang_combo.setCurrentIndex(start)
        self.lang_combo.currentIndexChanged.connect(self._on_lang_change)
        lang_row.addWidget(self.lang_label)
        lang_row.addWidget(self.lang_combo, 1)
        _sgl.addLayout(lang_row)
        # replace the layer(s) of an earlier insert when a line is re-inserted
        self.replace_chk = QCheckBox()
        self.replace_chk.setChecked(self._load_replace_existing())
        self.replace_chk.toggled.connect(self._on_replace_toggle)
        _sgl.addWidget(self.replace_chk)
        # presets: with a character level (default) or one flat list per manga
        self.by_char_chk = QCheckBox()
        self.by_char_chk.setChecked(self._load_by_char())
        self.by_char_chk.toggled.connect(self._on_by_char_toggle)
        _sgl.addWidget(self.by_char_chk)
        # which characters head the preset dropdowns
        self.main_chars_btn = QPushButton()
        self.main_chars_btn.clicked.connect(self.on_main_chars)
        _sgl.addWidget(self.main_chars_btn)
        self.main_chars_hint = QLabel()
        self.main_chars_hint.setWordWrap(True)
        self.main_chars_hint.setStyleSheet("color:#999;")
        _sgl.addWidget(self.main_chars_hint)
        lay_setup.addWidget(_sg_pb)

        # --- collapsible "Layout & sizes" panel ---
        # Lets the user resize or hide the big parts of the docker (preview,
        # script box, JP/EN table, font list) and remembers it across restarts.
        # --- fonts per text type ---
        _ttf_pb = self._new_panel("tt_fonts", "setup")
        self.setup_fonts_toggle, _ttfl = _collapsible(
            _ttf_pb.body_layout(), "setupFontsOpen")
        self.tt_fonts_hint = QLabel()
        self.tt_fonts_hint.setWordWrap(True)
        self.tt_fonts_hint.setStyleSheet("color:#999;")
        _ttfl.addWidget(self.tt_fonts_hint)
        self.tt_fonts_btn = QPushButton()
        self.tt_fonts_btn.clicked.connect(self.on_tt_fonts)
        _ttfl.addWidget(self.tt_fonts_btn)
        # Which starred (Fonts-tab) fonts aren't installed on this machine?
        self.fav_missing_btn = QPushButton(self._tr("missing_btn"))
        self.fav_missing_btn.clicked.connect(self._show_missing_fonts)
        _ttfl.addWidget(self.fav_missing_btn)
        lay_setup.addWidget(_ttf_pb)

        # --- Google account: the user brings their own client ID, because a
        # public plugin cannot ship credentials (see gauth.py) ---
        _g_pb = self._new_panel("google", "setup")
        self.setup_google_toggle, _gl = _collapsible(
            _g_pb.body_layout(), "setupGoogleOpen", default_open=False)
        self.lbl_g_client = QLabel()
        _gl.addWidget(self.lbl_g_client)
        self.g_client_edit = QLineEdit()
        self.g_client_edit.setText(self._g_client_id())
        self.g_client_edit.editingFinished.connect(self._on_g_client_edited)
        _gl.addWidget(self.g_client_edit)
        _grow = QHBoxLayout()
        self.g_sign_in_btn = QPushButton()
        self.g_sign_in_btn.clicked.connect(self.on_g_sign_in)
        _grow.addWidget(self.g_sign_in_btn)
        self.g_sign_out_btn = QPushButton()
        self.g_sign_out_btn.clicked.connect(self.on_g_sign_out)
        _grow.addWidget(self.g_sign_out_btn)
        _gl.addLayout(_grow)
        self.g_status = QLabel()
        _gl.addWidget(self.g_status)
        self.g_hint = QLabel()
        self.g_hint.setWordWrap(True)
        self.g_hint.setStyleSheet("color:#999;")
        _gl.addWidget(self.g_hint)

        # --- #21: a Drive image's comments AS the script -------------------
        # When the translation arrives as comments on the raw image (not a
        # Doc), the comments are the script. Paste the image's share link and
        # each comment becomes a line to typeset. Needs sign-in above — no
        # download carries an image's comments, so this path is OAuth-only.
        self.lbl_g_image = QLabel()
        _gl.addWidget(self.lbl_g_image)
        self.g_image_edit = QLineEdit()
        _gl.addWidget(self.g_image_edit)
        self.g_image_btn = QPushButton()
        self.g_image_btn.clicked.connect(self.on_load_image_comments)
        _gl.addWidget(self.g_image_btn)
        lay_setup.addWidget(_g_pb)

        _lz_pb = self._new_panel("layout_sizes", "setup")
        _lzl = _lz_pb.body_layout()
        v = self._load_view()
        defaults = self._view_defaults()
        for k, dv in defaults.items():
            v.setdefault(k, dv)

        self.view_toggle = QPushButton()
        self.view_toggle.setCheckable(True)
        self.view_toggle.setChecked(bool(v["open"]))
        _lzl.addWidget(self.view_toggle)

        self.view_box = QWidget()
        view_lay = QVBoxLayout()
        view_lay.setContentsMargins(6, 2, 6, 2)
        view_lay.setSpacing(4)
        self.view_box.setLayout(view_lay)
        self.view_hint = QLabel()
        self.view_hint.setStyleSheet("color: gray;")
        self.view_hint.setWordWrap(True)
        view_lay.addWidget(self.view_hint)
        view_grid = QGridLayout()
        view_grid.setHorizontalSpacing(8)

        def _view_row(r, chk_attr, spin_attr, lo, hi, val, show):
            chk = QCheckBox()
            chk.setChecked(bool(show))
            spin = NoScrollSpinBox()
            spin.setRange(lo, hi)
            spin.setSingleStep(10)
            spin.setValue(int(val))
            spin.setSuffix(" px")
            setattr(self, chk_attr, chk)
            setattr(self, spin_attr, spin)
            view_grid.addWidget(chk, r, 0)
            view_grid.addWidget(spin, r, 1)

        _view_row(0, "v_preview_chk", "v_preview_h", 40, 1200,
                  v["preview_h"], v["preview_show"])
        _view_row(1, "v_editor_chk", "v_editor_h", 40, 1200,
                  v["editor_h"], v["editor_show"])
        _view_row(2, "v_table_chk", "v_table_h", 60, 1600,
                  v["table_h"], v["table_show"])
        _view_row(3, "v_fonts_chk", "v_fonts_h", 40, 1200,
                  v["fonts_h"], v["fonts_show"])
        _view_row(4, "v_bubblr_chk", "v_bubblr_h", 80, 1600,
                  v["bubblr_h"], v["bubblr_show"])
        _view_row(5, "v_bmap_chk", "v_bmap_h", 60, 1600,
                  v["bmap_h"], v["bmap_show"])
        view_grid.setColumnStretch(0, 1)
        view_lay.addLayout(view_grid)
        self.view_reset_btn = QPushButton()
        self.view_reset_btn.clicked.connect(self._on_view_reset)
        view_lay.addWidget(self.view_reset_btn)
        _lzl.addWidget(self.view_box)
        lay_setup.addWidget(_lz_pb)

        # --- collapsible "Experimental" section ---
        # Groups the not-yet-final features: enabling/disabling BubblR and
        # TextShapR, and the customizable layout (rename/reorder tabs; panel
        # drag/detach follows in a later phase).
        app = Krita.instance()
        self.exp_toggle = QPushButton()
        self.exp_toggle.setCheckable(True)
        self.exp_toggle.setChecked(
            app.readSetting("typer_kr", "expOpen", "false") == "true")
        self.exp_toggle.toggled.connect(self._on_exp_toggle)
        lay_setup.addWidget(self.exp_toggle)

        self.exp_box = QWidget()
        exp_lay = QVBoxLayout()
        exp_lay.setContentsMargins(6, 2, 6, 2)
        exp_lay.setSpacing(4)
        self.exp_box.setLayout(exp_lay)

        # enable/disable the BubblR tab and the TextShapR button
        self.enable_bubblr_chk = QCheckBox()
        self.enable_bubblr_chk.setChecked(
            (not BUBBLR_LOCKED)
            and app.readSetting("typer_kr", "enableBubblr", "true") == "true")
        self.enable_bubblr_chk.toggled.connect(self._on_enable_bubblr)
        exp_lay.addWidget(self.enable_bubblr_chk)
        # locked off in public releases → hide the toggle so it can't be enabled
        self.enable_bubblr_chk.setVisible(not BUBBLR_LOCKED)
        self.enable_shapr_chk = QCheckBox()
        self.enable_shapr_chk.setChecked(
            app.readSetting("typer_kr", "enableShapr", "true") == "true")
        self.enable_shapr_chk.toggled.connect(self._on_enable_shapr)
        exp_lay.addWidget(self.enable_shapr_chk)
        self.enable_sfx_chk = QCheckBox()
        self.enable_sfx_chk.setChecked(
            app.readSetting("typer_kr", "enableSfx", "true") == "true")
        self.enable_sfx_chk.toggled.connect(self._on_enable_sfx)
        exp_lay.addWidget(self.enable_sfx_chk)
        self.enable_fonts_chk = QCheckBox()
        self.enable_fonts_chk.setChecked(
            app.readSetting("typer_kr", "enableFonts", "true") == "true")
        self.enable_fonts_chk.toggled.connect(self._on_enable_fonts)
        exp_lay.addWidget(self.enable_fonts_chk)
        # balloon tools are off by default: most pages come with their balloons
        self.enable_balloon_chk = QCheckBox()
        self.enable_balloon_chk.setChecked(
            app.readSetting("typer_kr", "enableBalloon", "false") == "true")
        self.enable_balloon_chk.toggled.connect(self._on_enable_balloon)
        exp_lay.addWidget(self.enable_balloon_chk)
        # pattern fills (outline/soft/text pattern + generator) — experimental,
        # off by default so the Style tab stays simple until it's opted in.
        self.enable_patterns_chk = QCheckBox()
        self.enable_patterns_chk.setChecked(
            app.readSetting("typer_kr", "enablePatterns", "false") == "true")
        self.enable_patterns_chk.toggled.connect(self._on_enable_patterns)
        exp_lay.addWidget(self.enable_patterns_chk)
        # 'kind of text' (text types + per-type fonts) — experimental, off by
        # default.
        self.enable_texttypes_chk = QCheckBox()
        self.enable_texttypes_chk.setChecked(
            app.readSetting("typer_kr", "enableTextTypes", "false") == "true")
        self.enable_texttypes_chk.toggled.connect(self._on_enable_texttypes)
        exp_lay.addWidget(self.enable_texttypes_chk)

        exp_lay.addWidget(self._hline())
        self.customize_chk = QCheckBox()
        self.customize_chk.setChecked(
            app.readSetting("typer_kr", "customize", "false") == "true")
        self.customize_chk.toggled.connect(self._on_customize_toggle)
        exp_lay.addWidget(self.customize_chk)
        self.customize_hint = QLabel()
        self.customize_hint.setWordWrap(True)
        self.customize_hint.setStyleSheet("color: gray;")
        self.customize_hint.setVisible(self.customize_chk.isChecked())
        exp_lay.addWidget(self.customize_hint)
        self.layout_reset_btn = QPushButton()
        self.layout_reset_btn.clicked.connect(self.on_layout_reset)
        exp_lay.addWidget(self.layout_reset_btn)

        lay_setup.addWidget(self.exp_box)
        self.exp_box.setVisible(self.exp_toggle.isChecked())
        lay_setup.addStretch(1)
        self.view_box.setVisible(self.view_toggle.isChecked())

        # wire up after the initial values are set, so nothing fires early
        self.view_toggle.toggled.connect(self._on_view_toggle)
        for _w in (self.v_preview_chk, self.v_editor_chk, self.v_table_chk,
                   self.v_fonts_chk, self.v_bubblr_chk, self.v_bmap_chk):
            _w.toggled.connect(self._on_view_changed)
        for _w in (self.v_preview_h, self.v_editor_h, self.v_table_h,
                   self.v_fonts_h, self.v_bubblr_h, self.v_bmap_h):
            _w.valueChanged.connect(self._on_view_changed)

        # --- presets (Presets tab) ---
        self.lbl_preset = QLabel()
        lay_presets.addWidget(self.lbl_preset)
        group_row = QHBoxLayout()
        self.lbl_group = QLabel()
        group_row.addWidget(self.lbl_group)
        self.group_combo = NoScrollComboBox()
        self.group_combo.currentIndexChanged.connect(self._on_group_selected)
        group_row.addWidget(self.group_combo, 1)
        self.group_new_btn = QPushButton()
        self.group_new_btn.clicked.connect(self.on_group_new)
        self.group_del_btn = QPushButton()
        self.group_del_btn.clicked.connect(self.on_group_delete)
        group_row.addWidget(self.group_new_btn)
        group_row.addWidget(self.group_del_btn)
        lay_presets.addLayout(group_row)
        char_row = QHBoxLayout()
        self.lbl_char = QLabel()
        char_row.addWidget(self.lbl_char)
        self.char_combo = NoScrollComboBox()
        self.char_combo.currentIndexChanged.connect(self._on_char_selected)
        # right-click stars a character without a trip to the Setup tab
        self.char_combo.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.char_combo.customContextMenuRequested.connect(
            self._char_context_menu)
        char_row.addWidget(self.char_combo, 1)
        self.char_new_btn = QPushButton()
        self.char_new_btn.clicked.connect(self.on_char_new)
        self.char_del_btn = QPushButton()
        self.char_del_btn.clicked.connect(self.on_char_delete)
        char_row.addWidget(self.char_new_btn)
        char_row.addWidget(self.char_del_btn)
        lay_presets.addLayout(char_row)
        # Auto-pick character from a "Name:" speaker prefix (optional)
        self.auto_char_chk = QCheckBox()
        self.auto_char_chk.setChecked(self._load_auto_char())
        self.auto_char_chk.toggled.connect(self._on_auto_char_toggle)
        lay_presets.addWidget(self.auto_char_chk)
        # Auto-pick manga from the script's file name / header / first lines
        self.auto_manga_chk = QCheckBox()
        self.auto_manga_chk.setChecked(self._load_auto_manga())
        self.auto_manga_chk.toggled.connect(self._on_auto_manga_toggle)
        lay_presets.addWidget(self.auto_manga_chk)
        preset_row = QHBoxLayout()
        self.preset_combo = NoScrollComboBox()
        # `activated` (not currentIndexChanged) so re-picking the SAME preset
        # re-applies it: after tweaking the font/size you can click the preset
        # again to get its values back, without hopping to another one and back.
        self.preset_combo.activated.connect(self._on_preset_selected)
        preset_row.addWidget(self.preset_combo, 1)
        # the rarely-used preset actions live in one compact "⋯" menu instead
        # of two full button rows
        self.preset_menu_btn = QToolButton()
        self.preset_menu_btn.setText("⋯")
        self.preset_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        preset_menu = QMenu(self.preset_menu_btn)
        self.preset_save_act = preset_menu.addAction("")
        self.preset_save_act.triggered.connect(self.on_preset_save)
        self.preset_del_act = preset_menu.addAction("")
        self.preset_del_act.triggered.connect(self.on_preset_delete)
        preset_menu.addSeparator()
        self.preset_import_act = preset_menu.addAction("")
        self.preset_import_act.triggered.connect(self.on_preset_import)
        self.preset_import_excel_act = preset_menu.addAction("")
        self.preset_import_excel_act.triggered.connect(self.on_preset_import_excel)
        self.preset_export_act = preset_menu.addAction("")
        self.preset_export_act.triggered.connect(self.on_preset_export)
        self.preset_menu_btn.setMenu(preset_menu)
        preset_row.addWidget(self.preset_menu_btn)
        lay_presets.addLayout(preset_row)
        # (no trailing stretch: this is a compact panel inside the Type tab)

        # --- load a file + script input (Type tab) ---
        # Wrapped as one movable "script" panel (load button, script tabs,
        # the parsed-text editor and the analyze row) so it can be reordered
        # relative to the presets / preview / table panels.
        _script_pb = self._new_panel("script_box", "type")
        _slay = _script_pb.body_layout()
        self.load_btn = QPushButton()
        self.load_btn.clicked.connect(self.on_load)
        _slay.addWidget(self.load_btn)

        # Generously sized so the parsed/pasted script is easy to read and edit.
        self.lbl_script = QLabel()
        _slay.addWidget(self.lbl_script)
        # Tabs for several loaded scripts (browser-style: closable + middle-click,
        # reorderable, eliding long names, with scroll buttons in a narrow dock).
        self.script_tabs = ScriptTabBar()
        self.script_tabs.setTabsClosable(True)
        self.script_tabs.setMovable(True)
        self.script_tabs.setExpanding(False)
        self.script_tabs.setDrawBase(False)
        self.script_tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.script_tabs.setUsesScrollButtons(True)
        self.script_tabs.currentChanged.connect(self._on_tab_changed)
        self.script_tabs.tabCloseRequested.connect(self._close_tab)
        self.script_tabs.tabBarDoubleClicked.connect(self._rename_tab)
        # remember the tab ORDER when the user drags tabs around
        self.script_tabs.tabMoved.connect(
            lambda *_a: self._schedule_session_save())
        _slay.addWidget(self.script_tabs)
        self.editor = QPlainTextEdit()
        self.editor.setMinimumHeight(170)
        self.editor.setMaximumHeight(320)
        # remember edits to the script text too (debounced)
        self.editor.textChanged.connect(self._schedule_session_save)
        _slay.addWidget(self.editor)

        opt_row = QHBoxLayout()
        self.skip_empty = QCheckBox()
        self.skip_empty.setChecked(True)
        self.skip_empty.stateChanged.connect(self.analyze)
        opt_row.addWidget(self.skip_empty)
        self.analyze_btn = QPushButton()
        self.analyze_btn.clicked.connect(self.analyze)
        opt_row.addWidget(self.analyze_btn)
        _slay.addLayout(opt_row)

        # Add a line to the script and write the script back to its file.
        edit_row = QHBoxLayout()
        self.add_line_btn = QPushButton()
        self.add_line_btn.clicked.connect(self.on_add_line)
        edit_row.addWidget(self.add_line_btn)
        self.save_script_btn = QPushButton()
        self.save_script_btn.clicked.connect(self.on_save_script)
        edit_row.addWidget(self.save_script_btn)
        _slay.addLayout(edit_row)
        lay_type.addWidget(_script_pb)

        lay_type.addWidget(self._hline())

        # --- two-column JP/EN view ---
        self.lbl_align = QLabel()
        lay_type.addWidget(self.lbl_align)
        self.table = QTableWidget(0, 2)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.itemSelectionChanged.connect(self._on_table_select)
        self.table.cellDoubleClicked.connect(self._on_table_double)
        _pb = self._new_panel("jp_en_table", "type")
        _pb.body_layout().addWidget(self.table)
        lay_type.addWidget(_pb, 1)

        # --- navigation panel (line nav + bubble stepper + page jump) ---
        _nav_pb = self._new_panel("nav_line", "type")
        _navl = _nav_pb.body_layout()
        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton()
        self.prev_btn.clicked.connect(self.on_prev)
        self.next_btn = QPushButton()
        self.next_btn.clicked.connect(self.on_next)
        self.reset_btn = QPushButton()
        self.reset_btn.clicked.connect(self.on_reset_progress)
        self.counter = QLabel("0 / 0")
        self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self.prev_btn)
        nav_row.addWidget(self.counter, 1)
        nav_row.addWidget(self.next_btn)
        nav_row.addWidget(self.reset_btn)
        _navl.addLayout(nav_row)

        # --- BubblR bubble stepper (only useful once bubbles are detected) ---
        # Lets Insert on the Type tab fill the current bubble; ◀/▶ step the
        # bubble pointer so a bubble can be redone. Hidden until Detect runs.
        bnav_row = QHBoxLayout()
        self.bubble_prev_btn = QToolButton()
        self.bubble_prev_btn.setText("◀")
        self.bubble_prev_btn.clicked.connect(lambda: self._bp_step(-1))
        self.bubble_lbl = QLabel("")
        self.bubble_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble_next_btn = QToolButton()
        self.bubble_next_btn.setText("▶")
        self.bubble_next_btn.clicked.connect(lambda: self._bp_step(1))
        bnav_row.addWidget(self.bubble_prev_btn)
        bnav_row.addWidget(self.bubble_lbl, 1)
        bnav_row.addWidget(self.bubble_next_btn)
        self.bubble_nav_widget = QWidget()
        self.bubble_nav_widget.setLayout(bnav_row)
        self.bubble_nav_widget.setVisible(False)
        _navl.addWidget(self.bubble_nav_widget)

        # --- page indicator + jump (only shown when the script has "Page" markers) ---
        page_row = QHBoxLayout()
        self.lbl_page = QLabel()
        self.page_combo = NoScrollComboBox()
        # 'activated' fires only on user interaction, so syncing the combo to the
        # current page while navigating does not trigger another jump.
        self.page_combo.activated.connect(self.on_jump_page)
        self.page_status = QLabel("")
        self.page_status.setStyleSheet("color: gray;")
        page_row.addWidget(self.lbl_page)
        page_row.addWidget(self.page_combo, 1)
        page_row.addWidget(self.page_status)
        _navl.addLayout(page_row)
        lay_type.addWidget(_nav_pb)

        # --- active text field panel (edit + bold + JP reference) ---
        _act_pb = self._new_panel("active_field", "type")
        _actl = _act_pb.body_layout()
        self.active_edit = QPlainTextEdit()
        self.active_edit.setMinimumHeight(42)
        self.active_edit.setMaximumHeight(70)
        self.active_edit.textChanged.connect(self._update_text_preview)
        _actl.addWidget(self.active_edit)
        bold_row = QHBoxLayout()
        self.bold_sel_btn = QPushButton()
        self.bold_sel_btn.clicked.connect(self.on_bold_selection)
        bold_row.addWidget(self.bold_sel_btn)
        bold_row.addStretch(1)
        _actl.addLayout(bold_row)
        self.jp_ref = QLabel("")
        self.jp_ref.setWordWrap(True)
        self.jp_ref.setStyleSheet("color: gray;")
        _actl.addWidget(self.jp_ref)
        lay_type.addWidget(_act_pb)

        # --- live preview panel ---
        self.lbl_preview = QLabel("")
        self.lbl_preview.setStyleSheet("color: gray; margin-top: 2px;")
        self.preview = TextPreview(self)
        # --- script comments: the translator's notes for the line/page in
        # front of you. Hidden entirely when there is nothing to say. ---
        _cm_pb = self._new_panel("comments", "type")
        _cml = _cm_pb.body_layout()
        self.comments_view = QTextBrowser()
        self.comments_view.setOpenExternalLinks(True)
        self.comments_view.setMinimumHeight(80)
        _cml.addWidget(self.comments_view)
        self._comments_panel = _cm_pb
        _cm_pb.setVisible(False)
        lay_type.addWidget(_cm_pb)

        _pb = self._new_panel("live_preview", "type")
        _prev_head = QHBoxLayout()
        _prev_head.addWidget(self.lbl_preview)
        _prev_head.addStretch(1)
        self.preview_refresh_btn = QToolButton()
        self.preview_refresh_btn.setText("↻")
        self.preview_refresh_btn.setToolTip(self._tr("preview_refresh_tip"))
        self.preview_refresh_btn.clicked.connect(self._update_text_preview)
        _prev_head.addWidget(self.preview_refresh_btn)
        _pb.body_layout().addLayout(_prev_head)
        _pb.body_layout().addWidget(self.preview)
        lay_type.addWidget(_pb)

        # --- presets panel (Manga -> Character -> style preset) ---
        _pb = self._new_panel("presets", "type")
        _pb.body_layout().addWidget(self.presets_panel)
        lay_type.addWidget(_pb)

        # --- font picker + text color panel ---
        _font_pb = self._new_panel("font_picker", "type")
        _fontl = _font_pb.body_layout()
        self.lbl_font = QLabel()
        _fontl.addWidget(self.lbl_font)
        self.font_picker = FontPicker(self._load_recents(),
                                      self._tr("font_search_ph"))
        _fontl.addWidget(self.font_picker)
        # Right-click a font row: star it / drop it straight into a category,
        # without switching to the Fonts tab.
        self.font_picker.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.font_picker.list.customContextMenuRequested.connect(
            self._font_context_menu)
        # One-click star: drop the picked font into the Fonts tab's favourites
        # without leaving the insert loop.
        fav_row = QHBoxLayout()
        self.fav_add_btn = QPushButton(self._tr("fav_star_current"))
        self.fav_add_btn.setToolTip(self._tr("fav_star_current_tip"))
        self.fav_add_btn.clicked.connect(self._star_current_font)
        fav_row.addWidget(self.fav_add_btn)
        fav_row.addStretch(1)
        _fontl.addLayout(fav_row)
        color_row = QHBoxLayout()
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self.on_pick_color)
        color_row.addWidget(self.color_btn, 1)
        _fontl.addLayout(color_row)
        self._update_color_btn()
        lay_type.addWidget(_font_pb)

        # --- insert + TextShapR panel ---
        _ins_pb = self._new_panel("insert", "type")
        _insl = _ins_pb.body_layout()
        insert_row = QHBoxLayout()
        self.insert_btn = QPushButton()
        self.insert_btn.clicked.connect(self.on_insert)
        insert_row.addWidget(self.insert_btn, 1)
        _insl.addLayout(insert_row)
        lay_type.addWidget(_ins_pb)

        # --- balloon panel: draw the bubble itself, not just the text in it ---
        _bal_pb = self._new_panel("balloon", "type")
        _ball = _bal_pb.body_layout()
        bal_row = QHBoxLayout()
        self.balloon_combo = NoScrollComboBox()
        for _sid in BAL.SHAPE_ORDER:
            self.balloon_combo.addItem("", _sid)
        bal_row.addWidget(self.balloon_combo, 1)
        self.balloon_tail_chk = QCheckBox()
        self.balloon_tail_chk.setChecked(True)
        bal_row.addWidget(self.balloon_tail_chk)
        _ball.addLayout(bal_row)
        self.balloon_btn = QPushButton()
        self.balloon_btn.clicked.connect(self.on_insert_balloon)
        _ball.addWidget(self.balloon_btn)
        self.balloon_hint = QLabel()
        self.balloon_hint.setWordWrap(True)
        self.balloon_hint.setStyleSheet("color:#999;")
        _ball.addWidget(self.balloon_hint)
        self.balloon_combo.currentIndexChanged.connect(self._on_balloon_changed)
        lay_type.addWidget(_bal_pb)

        # --- text type panel: one click sets the whole look for a kind of text ---
        _tt_pb = self._new_panel("text_type", "style")
        _ttl = _tt_pb.body_layout()
        tt_row = QHBoxLayout()
        self.lbl_text_type = QLabel()
        tt_row.addWidget(self.lbl_text_type)
        self.text_type_combo = NoScrollComboBox()
        self.text_type_combo.addItem("", "")          # "-" = don't touch the style
        for _tid in TT.ids():
            self.text_type_combo.addItem("", _tid)
        tt_row.addWidget(self.text_type_combo, 1)
        _ttl.addLayout(tt_row)
        self.text_type_apply_btn = QPushButton()
        self.text_type_apply_btn.clicked.connect(self.on_text_type_apply)
        _ttl.addWidget(self.text_type_apply_btn)
        self.text_type_hint = QLabel()
        self.text_type_hint.setWordWrap(True)
        self.text_type_hint.setStyleSheet("color:#999;")
        _ttl.addWidget(self.text_type_hint)
        self.text_type_combo.currentIndexChanged.connect(self._on_text_type_changed)
        lay_style.addWidget(_tt_pb)
        self._texttype_panel = _tt_pb        # gated by the 'text types' experiment

        # --- basic style panel: variant + alignment + text processing ---
        _sb_pb = self._new_panel("style_basic", "style")
        _sbl = _sb_pb.body_layout()
        style_row = QHBoxLayout()
        self.lbl_style = QLabel()
        style_row.addWidget(self.lbl_style)
        self.bold_chk = QCheckBox()
        self.italic_chk = QCheckBox()
        self.underline_chk = QCheckBox()
        # Ligatures on/off (like sakushi's TypeR). Default ON = unchanged
        # behaviour; a letterer usually turns it OFF so "fi"/"fl" don't fuse in
        # hand-lettered fonts. Persisted with the other style toggles.
        self.liga_chk = QCheckBox()
        self.liga_chk.setChecked(True)
        style_row.addWidget(self.bold_chk)
        style_row.addWidget(self.italic_chk)
        style_row.addWidget(self.underline_chk)
        style_row.addWidget(self.liga_chk)
        style_row.addStretch(1)
        _sbl.addLayout(style_row)

        align_row = QHBoxLayout()
        self.lbl_alignment = QLabel()
        align_row.addWidget(self.lbl_alignment)
        self.align_combo = NoScrollComboBox()
        for code in ("left", "center", "right"):
            self.align_combo.addItem("", code)
        self.align_combo.setCurrentIndex(1)  # center
        align_row.addWidget(self.align_combo, 1)
        _sbl.addLayout(align_row)

        valign_row = QHBoxLayout()
        self.lbl_valign = QLabel()
        valign_row.addWidget(self.lbl_valign)
        self.valign_combo = NoScrollComboBox()
        for code in ("top", "middle", "bottom"):
            self.valign_combo.addItem("", code)
        self.valign_combo.setCurrentIndex(1)  # middle
        valign_row.addWidget(self.valign_combo, 1)
        _sbl.addLayout(valign_row)

        text_row = QHBoxLayout()
        self.case_label = QLabel()
        self.case_combo = NoScrollComboBox()
        for code in ("none", "upper", "lower"):
            self.case_combo.addItem("", code)
        self.case_combo.setCurrentIndex(0)
        text_row.addWidget(self.case_label)
        text_row.addWidget(self.case_combo)
        self.tidy_chk = QCheckBox()
        text_row.addWidget(self.tidy_chk)
        text_row.addStretch(1)
        _sbl.addLayout(text_row)

        # own row: the case combo plus three toggles overflow a narrow docker
        comic_row = QHBoxLayout()
        self.comic_chk = QCheckBox()
        comic_row.addWidget(self.comic_chk)
        self.crossbar_chk = QCheckBox()
        comic_row.addWidget(self.crossbar_chk)
        self.comic_chk.toggled.connect(
            lambda on: self.crossbar_chk.setEnabled(on))
        self.crossbar_chk.setEnabled(False)
        comic_row.addStretch(1)
        _sbl.addLayout(comic_row)
        lay_style.addWidget(_sb_pb)

        # --- size / spacing / auto-fit panel ---
        _ss_pb = self._new_panel("style_size", "style")
        _ssl = _ss_pb.body_layout()
        grid = QGridLayout()
        self.size_label = QLabel()
        grid.addWidget(self.size_label, 0, 0)
        self.size_spin = NoScrollSpinBox()
        self.size_spin.setRange(4, 2000)
        self.size_spin.setValue(72)
        grid.addWidget(self.size_spin, 0, 1)

        self.lbl_pad = QLabel()
        grid.addWidget(self.lbl_pad, 1, 0)
        self.pad_spin = NoScrollSpinBox()
        self.pad_spin.setRange(0, 45)
        self.pad_spin.setValue(12)
        grid.addWidget(self.pad_spin, 1, 1)

        self.lbl_spacing = QLabel()
        grid.addWidget(self.lbl_spacing, 2, 0)
        self.spacing_spin = NoScrollSpinBox()
        # Line spacing as a percentage of the font's line height. Unclamped on
        # purpose: 0 collapses the lines onto one baseline, and values well past
        # 100 spread them as far apart as wanted.
        self.spacing_spin.setRange(0, 1000)
        self.spacing_spin.setValue(105)
        grid.addWidget(self.spacing_spin, 2, 1)
        _ssl.addLayout(grid)

        self.auto_chk = QCheckBox()
        self.auto_chk.setChecked(True)
        self.auto_chk.stateChanged.connect(self._on_auto_toggle)
        _ssl.addWidget(self.auto_chk)

        self.round_chk = QCheckBox()
        self.round_chk.stateChanged.connect(self._on_auto_toggle)
        _ssl.addWidget(self.round_chk)

        self.vertical_chk = QCheckBox()
        _ssl.addWidget(self.vertical_chk)
        lay_style.addWidget(_ss_pb)

        # --- outline panel: checkbox on the tab, color + width in a popup ---
        self.outline_dlg = QDialog(main)
        out_dlg_lay = QVBoxLayout()
        self.outline_dlg.setLayout(out_dlg_lay)
        out_opts = QHBoxLayout()
        self.outline_color_btn = QPushButton()
        self.outline_color_btn.clicked.connect(self.on_pick_outline_color)
        out_opts.addWidget(self.outline_color_btn)
        self.lbl_outline_width = QLabel()
        out_opts.addWidget(self.lbl_outline_width)
        self.outline_spin = NoScrollSpinBox()
        self.outline_spin.setRange(1, 200)
        self.outline_spin.setValue(4)
        out_opts.addWidget(self.outline_spin)
        out_dlg_lay.addLayout(out_opts)
        # second (outer) outline for a double rim (width 0 = off), e.g. white
        # outer + black inner + white text.
        out2_opts = QHBoxLayout()
        self.outline2_color_btn = QPushButton()
        self.outline2_color_btn.clicked.connect(self.on_pick_outline2_color)
        out2_opts.addWidget(self.outline2_color_btn)
        self.lbl_outline2_width = QLabel()
        out2_opts.addWidget(self.lbl_outline2_width)
        self.outline2_spin = NoScrollSpinBox()
        self.outline2_spin.setRange(0, 200)
        self.outline2_spin.setValue(0)
        out2_opts.addWidget(self.outline2_spin)
        out_dlg_lay.addLayout(out2_opts)

        # pattern/texture fill for the (primary) outline — an image tiled into
        # the outline stroke instead of a flat colour. Needs the raster insert
        # path (Krita vector text can't take a pattern), so choosing one routes
        # the insert through pixels. File OR a pattern from Krita's resources.
        # pattern + soft-outline controls, wrapped in one box so the whole thing
        # can be hidden when the experimental 'pattern fills' feature is off.
        self._style_pattern_box = QWidget()
        pbl = QVBoxLayout(self._style_pattern_box)
        pbl.setContentsMargins(0, 0, 0, 0)
        self.lbl_outline_pattern = QLabel()
        pbl.addWidget(self.lbl_outline_pattern)
        pat_row = QHBoxLayout()
        self.outline_pattern_btn = QPushButton()
        self.outline_pattern_btn.clicked.connect(self._pick_outline_pattern_file)
        pat_row.addWidget(self.outline_pattern_btn, 1)
        self.outline_pattern_krita_btn = QPushButton()
        self.outline_pattern_krita_btn.clicked.connect(
            self._pick_outline_pattern_krita)
        pat_row.addWidget(self.outline_pattern_krita_btn)
        self.outline_pattern_gen_btn = QPushButton()
        self.outline_pattern_gen_btn.clicked.connect(
            self._generate_outline_pattern)
        pat_row.addWidget(self.outline_pattern_gen_btn)
        self.outline_pattern_saved_btn = QPushButton()
        self.outline_pattern_saved_btn.clicked.connect(self._pick_outline_saved)
        pat_row.addWidget(self.outline_pattern_saved_btn)
        self.outline_pattern_clear_btn = QPushButton("✕")
        self.outline_pattern_clear_btn.setFixedWidth(28)
        self.outline_pattern_clear_btn.clicked.connect(self._clear_outline_pattern)
        pat_row.addWidget(self.outline_pattern_clear_btn)
        pbl.addLayout(pat_row)
        self.outline_pattern_scale_spin = NoScrollSpinBox()
        self.outline_pattern_scale_spin.setRange(10, 400)
        self.outline_pattern_scale_spin.setValue(100)
        self.outline_pattern_scale_spin.setSuffix(" %")
        self.outline_pattern_scale_spin.valueChanged.connect(
            lambda _v: self._update_text_preview())
        pbl.addWidget(self.outline_pattern_scale_spin)
        # which outline the pattern fills: the 1st (inner), 2nd (outer) or both
        tgt_row = QHBoxLayout()
        self.lbl_outline_pattern_target = QLabel()
        tgt_row.addWidget(self.lbl_outline_pattern_target)
        self.outline_pattern_target_combo = NoScrollComboBox()
        for _key in ("outline1", "outline2", "both"):
            self.outline_pattern_target_combo.addItem("", _key)
        self.outline_pattern_target_combo.currentIndexChanged.connect(
            lambda _i: self._update_text_preview())
        tgt_row.addWidget(self.outline_pattern_target_combo, 1)
        pbl.addLayout(tgt_row)

        # soft (blurred) outline / glow: solid colour OR the pattern above
        soft_row = QHBoxLayout()
        self.style_soft_chk = QCheckBox()
        self.style_soft_chk.toggled.connect(
            lambda _v: (self._update_soft_enabled(), self._update_text_preview()))
        soft_row.addWidget(self.style_soft_chk)
        self.style_soft_pattern_chk = QCheckBox()
        self.style_soft_pattern_chk.toggled.connect(
            lambda _v: self._update_text_preview())
        soft_row.addWidget(self.style_soft_pattern_chk)
        self.style_soft_color_btn = QPushButton()
        self.style_soft_color_btn.clicked.connect(self.on_pick_style_soft_color)
        soft_row.addWidget(self.style_soft_color_btn, 1)
        pbl.addLayout(soft_row)
        soft_w_row = QHBoxLayout()
        self.lbl_style_soft_w = QLabel()
        soft_w_row.addWidget(self.lbl_style_soft_w)
        self.style_soft_width_spin = NoScrollSpinBox()
        self.style_soft_width_spin.setRange(0, 40)
        self.style_soft_width_spin.setValue(3)
        self.style_soft_width_spin.valueChanged.connect(
            lambda _v: self._update_text_preview())
        soft_w_row.addWidget(self.style_soft_width_spin)
        self.lbl_style_soft_blur = QLabel()
        soft_w_row.addWidget(self.lbl_style_soft_blur)
        self.style_soft_blur_spin = NoScrollSpinBox()
        self.style_soft_blur_spin.setRange(1, 60)
        self.style_soft_blur_spin.setValue(8)
        self.style_soft_blur_spin.valueChanged.connect(
            lambda _v: self._update_text_preview())
        soft_w_row.addWidget(self.style_soft_blur_spin)
        pbl.addLayout(soft_w_row)
        out_dlg_lay.addWidget(self._style_pattern_box)

        self.outline_close_btn = QPushButton()
        self.outline_close_btn.clicked.connect(self.outline_dlg.accept)
        out_dlg_lay.addWidget(self.outline_close_btn)
        self._update_style_soft_btn()
        self._update_outline_pattern_btn()
        self._update_soft_enabled()

        _out_pb = self._new_panel("style_outline", "style")
        out_row = QHBoxLayout()
        self.outline_chk = QCheckBox()
        self.outline_chk.stateChanged.connect(self._on_outline_toggle)
        out_row.addWidget(self.outline_chk)
        self.outline_more_btn = QPushButton()
        self.outline_more_btn.clicked.connect(self.outline_dlg.show)
        out_row.addWidget(self.outline_more_btn)
        out_row.addStretch(1)
        _out_pb.body_layout().addLayout(out_row)
        lay_style.addWidget(_out_pb)
        self._update_outline_btn()
        self._update_outline2_btn()

        # --- pattern fill for a SELECTION: pick/generate a pattern, then drop
        # it into a hand-made canvas selection (the text itself is never auto
        # pattern-filled — you mark the area yourself). ---
        _fill_pb = self._new_panel("style_fill", "style")
        _fl = _fill_pb.body_layout()
        self.fill_pattern_hint = QLabel()
        self.fill_pattern_hint.setWordWrap(True)
        self.fill_pattern_hint.setStyleSheet("color: gray;")
        _fl.addWidget(self.fill_pattern_hint)
        fillp_row = QHBoxLayout()
        self.fill_pattern_btn = QPushButton()
        self.fill_pattern_btn.clicked.connect(self._pick_fill_pattern_file)
        fillp_row.addWidget(self.fill_pattern_btn, 1)
        self.fill_pattern_krita_btn = QPushButton()
        self.fill_pattern_krita_btn.clicked.connect(self._pick_fill_pattern_krita)
        fillp_row.addWidget(self.fill_pattern_krita_btn)
        self.fill_pattern_gen_btn = QPushButton()
        self.fill_pattern_gen_btn.clicked.connect(self._generate_fill_pattern)
        fillp_row.addWidget(self.fill_pattern_gen_btn)
        self.fill_pattern_saved_btn = QPushButton()
        self.fill_pattern_saved_btn.clicked.connect(self._pick_fill_saved)
        fillp_row.addWidget(self.fill_pattern_saved_btn)
        self.fill_pattern_clear_btn = QPushButton("✕")
        self.fill_pattern_clear_btn.setFixedWidth(28)
        self.fill_pattern_clear_btn.clicked.connect(self._clear_fill_pattern)
        fillp_row.addWidget(self.fill_pattern_clear_btn)
        _fl.addLayout(fillp_row)
        self.fill_pattern_scale_spin = NoScrollSpinBox()
        self.fill_pattern_scale_spin.setRange(10, 400)
        self.fill_pattern_scale_spin.setValue(100)
        self.fill_pattern_scale_spin.setSuffix(" %")
        _fl.addWidget(self.fill_pattern_scale_spin)
        # fill a hand-made canvas SELECTION with the current pattern
        self.fill_sel_btn = QPushButton()
        self.fill_sel_btn.clicked.connect(self._fill_selection_current)
        _fl.addWidget(self.fill_sel_btn)
        lay_style.addWidget(_fill_pb)
        self._fill_panel = _fill_pb          # gated by the 'patterns' experiment
        self._update_fill_pattern_btn()

        # --- shadow panel: checkbox on the tab, color + offset in a popup ---
        self.shadow_dlg = QDialog(main)
        sh_dlg_lay = QVBoxLayout()
        self.shadow_dlg.setLayout(sh_dlg_lay)
        sh_opts = QHBoxLayout()
        self.shadow_color_btn = QPushButton()
        self.shadow_color_btn.clicked.connect(self.on_pick_shadow_color)
        sh_opts.addWidget(self.shadow_color_btn)
        self.lbl_shadow_off = QLabel()
        sh_opts.addWidget(self.lbl_shadow_off)
        self.shadow_x_spin = NoScrollSpinBox()
        self.shadow_x_spin.setRange(-100, 100)
        self.shadow_x_spin.setValue(3)
        self.shadow_y_spin = NoScrollSpinBox()
        self.shadow_y_spin.setRange(-100, 100)
        self.shadow_y_spin.setValue(3)
        sh_opts.addWidget(self.shadow_x_spin)
        sh_opts.addWidget(self.shadow_y_spin)
        sh_dlg_lay.addLayout(sh_opts)
        self.shadow_close_btn = QPushButton()
        self.shadow_close_btn.clicked.connect(self.shadow_dlg.accept)
        sh_dlg_lay.addWidget(self.shadow_close_btn)

        _sh_pb = self._new_panel("style_shadow", "style")
        sh_row = QHBoxLayout()
        self.shadow_chk = QCheckBox()
        self.shadow_chk.stateChanged.connect(self._on_shadow_toggle)
        sh_row.addWidget(self.shadow_chk)
        self.shadow_more_btn = QPushButton()
        self.shadow_more_btn.clicked.connect(self.shadow_dlg.show)
        sh_row.addWidget(self.shadow_more_btn)
        sh_row.addStretch(1)
        _sh_pb.body_layout().addLayout(sh_row)
        lay_style.addWidget(_sh_pb)
        self._update_shadow_btn()

        # --- hyphenation panel (split long words at syllable points) ---
        _hy_pb = self._new_panel("hyphenation", "style")
        _hyl = _hy_pb.body_layout()
        self.hyph_chk = QCheckBox()
        self.hyph_chk.stateChanged.connect(self._on_hyph_toggle)
        _hyl.addWidget(self.hyph_chk)
        hyph_row = QHBoxLayout()
        self.lbl_hyph_lang = QLabel()
        hyph_row.addWidget(self.lbl_hyph_lang)
        self.hyph_lang_combo = NoScrollComboBox()
        # only offer languages whose hyphenation patterns are bundled
        for code in ("auto",) + L.HYPH_LANGS:
            self.hyph_lang_combo.addItem("", code)
        self.hyph_lang_combo.currentIndexChanged.connect(
            lambda *_a: self._update_text_preview())
        hyph_row.addWidget(self.hyph_lang_combo, 1)
        _hyl.addLayout(hyph_row)
        lay_style.addWidget(_hy_pb)
        lay_style.addStretch(1)

        # --- BubblR tab (auto-detect bubbles + per-bubble styles) ---
        self._build_bubblr_tab(lay_bubblr)

        # --- TextShapR tab (a movable panel, so it joins the custom layout) ---
        self.shapr_widget = TextShapRWidget(self)
        _shapr_pb = self._new_panel("shapr_panel", "shapr")
        _shapr_pb.body_layout().addWidget(self.shapr_widget)
        lay_shapr.addWidget(_shapr_pb)

        # TextShapR reads the style from these controls, so a change to any of
        # them has to re-fit the arrangements (and the live preview) right away
        # — otherwise the cards keep showing the previous size/font/effects.
        # Outline and shadow (enable + size) are included so the cards repaint
        # with the effect as soon as it is switched on or resized.
        for _w in (self.size_spin, self.pad_spin, self.spacing_spin,
                   self.outline_spin, self.outline2_spin,
                   self.shadow_x_spin, self.shadow_y_spin):
            _w.valueChanged.connect(self._on_style_changed)
        for _w in (self.bold_chk, self.italic_chk, self.vertical_chk,
                   self.liga_chk, self.outline_chk, self.shadow_chk):
            _w.toggled.connect(self._on_style_changed)
        for _w in (self.align_combo, self.valign_combo):
            _w.currentIndexChanged.connect(self._on_style_changed)
        self.font_picker.familyChanged.connect(self._on_style_changed)
        self.preset_combo.currentIndexChanged.connect(self._on_style_changed)

        # --- SFX tab (embed the MangaSFX docker in a movable panel) ---
        # Defensive: a failure to build the SFX panel must never take TypeR down.
        self._sfx_docker = None
        _sfx_pb = self._new_panel("sfx_panel", "sfx")
        # Let the SFX panel grow to fill the tab instead of sitting at its
        # natural height at the top.
        _sfx_pb.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        try:
            from .sfx.sfx_docker import MangaSFXDocker
            self._sfx_docker = MangaSFXDocker()
            _sfx_root = self._sfx_docker.widget()
            # The docker wraps its content in a QScrollArea. takeWidget() cleanly
            # DETACHES the inner content so OUR layout owns its size — plain
            # .widget() leaves the old scroll area still managing it, which is why
            # it kept a fixed size and ignored the docker resizing (too small when
            # narrow, empty space when wide, no vertical fill). Never host a second
            # resizable QScrollArea here: nesting two loops the layout and crashes
            # Krita. The tab's own single scroll handles overflow.
            _inner = None
            if hasattr(_sfx_root, "takeWidget"):
                _inner = _sfx_root.takeWidget()
            elif hasattr(_sfx_root, "widget"):
                _inner = _sfx_root.widget()
            _sfx_content = _inner if _inner is not None else _sfx_root
            _sfx_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            _sfx_pb.body_layout().addWidget(_sfx_content)
        except Exception as _sfx_exc:      # noqa: BLE001
            _lbl = QLabel("SFX Helper could not load:\n%s" % _sfx_exc)
            _lbl.setWordWrap(True)
            _lbl.setStyleSheet("color: gray;")
            _sfx_pb.body_layout().addWidget(_lbl)
        # Stretch so the panel takes the full tab height (the tab's own single
        # scroll handles any overflow — no second scroll area here).
        lay_sfx.addWidget(_sfx_pb, 1)

        # --- Fonts tab (starred fonts sorted into categories) ---------
        # Decoupled panel: it only talks to us through callbacks, so a failure
        # to build it must never take TypeR down.
        self.fonts_panel = None
        try:
            from .fontfav_ui import FontFavoritesPanel
            from . import fontfiles as _FF
            self.fonts_panel = FontFavoritesPanel(
                families_fn=lambda: sorted(font_families()),
                apply_fn=self._apply_favorite_font,
                load_fn=self._load_font_favorites,
                save_fn=self._save_font_favorites,
                tr=self._tr,
                current_font_fn=lambda: (self.font_picker.currentFamily() or ""),
                # ALL files of each family (Regular/Bold/Italic/…), so an
                # exported bundle needs no manual installing on the other side
                find_fonts_fn=lambda fams: _FF.collect_font_files(
                    fams, parent=self.widget(), label=self._tr("font_scan"))[0],
                install_fonts_fn=self._install_fonts_and_refresh)
            lay_fonts.addWidget(self.fonts_panel, 1)
        except Exception as _ff_exc:      # noqa: BLE001
            _lbl = QLabel("Font favourites could not load:\n%s" % _ff_exc)
            _lbl.setWordWrap(True)
            _lbl.setStyleSheet("color: gray;")
            lay_fonts.addWidget(_lbl)

        # status line below the tabs, always visible
        self.status = QLabel("")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        # build stamp so you can see at a glance which version Krita loaded
        # the detected Qt binding (auto-chosen at import: PyQt6 on Krita 6,
        # PyQt5 on Krita 5) — shown for transparency / bug reports
        self.build_lbl = QLabel("TypeR v" + VERSION + " · Build " + BUILD
                                + " · " + binding_info())
        self.build_lbl.setStyleSheet("color: gray; font-size: 10px;")
        self.build_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        outer.addWidget(self.build_lbl)

        self.setWidget(main)

        # --- tab customization (rename / reorder / reset) ---
        # Each tab carries a stable id in its tabData, so text and order stay
        # correct even after the user drags tabs around. Custom names and the
        # order are persisted; the panel-level drag/detach comes in a later
        # phase and builds on layoutmodel.py.
        self._tab_defaults = [("type", "tab_type"), ("style", "tab_style"),
                              ("setup", "tab_setup"), ("bubblr", "tab_bubblr"),
                              ("shapr", "tab_shapr"), ("sfx", "tab_sfx"),
                              ("fonts", "tab_fonts")]
        self._tab_pages = {}          # id -> tab page widget (kept when hidden)
        for i, (tid, _nk) in enumerate(self._tab_defaults):
            self.main_tabs.tabBar().setTabData(i, tid)
            self._tab_pages[tid] = self.main_tabs.widget(i)
        self._tab_names = self._load_tab_names()      # id -> custom name
        # apply the BubblR-tab / TextShapR-button enable state now that both
        # the tabs and the toggles exist
        self._on_enable_bubblr(self.enable_bubblr_chk.isChecked(), save=False)
        self._on_enable_shapr(self.enable_shapr_chk.isChecked(), save=False)
        self._on_enable_sfx(self.enable_sfx_chk.isChecked(), save=False)
        self._on_enable_fonts(self.enable_fonts_chk.isChecked(), save=False)
        self._on_enable_balloon(self.enable_balloon_chk.isChecked(), save=False)
        self._on_enable_patterns(self.enable_patterns_chk.isChecked(), save=False)
        self._on_enable_texttypes(
            self.enable_texttypes_chk.isChecked(), save=False)
        # One-time repair: an earlier build could persist a corrupted main-tab
        # order (a symptom of the old label/content desync). Clear the saved
        # order ONCE so everyone lands back on the clean default; the robust
        # _apply_tab_order keeps any future customization correct from here on.
        self._repair_tab_order_once()
        self._apply_tab_order(self._load_tab_order())
        self._retranslate_tabs()
        self.main_tabs.tabBar().setMovable(self.customize_chk.isChecked())
        self.main_tabs.tabBar().tabMoved.connect(self._on_tab_moved)
        self.main_tabs.tabBarDoubleClicked.connect(self._on_tab_rename)
        # restore saved panel placements (tab) + within-tab order + header
        self._apply_panel_positions()
        self._normalize_setup_order_once()
        self._apply_panel_order()
        # re-detach panels into their host windows once those dockers exist
        # (deferred: the host dockers are constructed by Krita separately)
        QTimer.singleShot(0, self._apply_detached)

        # remember the last-used main tab across restarts
        self.main_tabs.setCurrentIndex(self._load_ui_tab())
        self.main_tabs.currentChanged.connect(self._save_ui_tab)

        self._apply_settings(self._load_settings())
        self._on_outline_toggle()
        self._on_shadow_toggle()
        self._on_auto_toggle()
        self._refresh_groups_combo()
        self._refresh_chars_combo()
        self._refresh_presets_combo()
        self._refresh_pages_combo()
        self._wire_preview()
        self._retranslate()
        self._refresh_view()
        self._apply_view()
        self._apply_preset_mode()          # show/hide the character level
        self._update_text_preview()
        self._init_first_session()         # start with one empty "Untitled" tab

    # -- language --

    def _tr(self, key):
        table = LANG.get(self._lang, LANG["en"])
        return table.get(key, LANG["en"].get(key, key))

    def _load_lang(self):
        try:
            v = Krita.instance().readSetting("typer_kr", "uiLang", "")
            return v if v in LANG else "en"
        except Exception:
            return "en"

    def _save_lang(self):
        try:
            Krita.instance().writeSetting("typer_kr", "uiLang", self._lang)
        except Exception:
            pass

    # -- font favourites (fonts tab) ---------------------------------------
    def _apply_favorite_font(self, family):
        """Route a font picked in the Fonts tab into the live picker so the next
        insert (and the preview) use it — WITHOUT leaving the Fonts tab, so you
        can keep browsing/trying fonts."""
        if not family:
            return
        try:
            self.font_picker.setCurrentFamily(family)
        except Exception:
            pass
        try:
            self.status.setText(self._tr("st_font_applied").format(name=family))
        except Exception:
            pass

    def _star_current_font(self):
        """★ button next to the picker: add the current font to the Fonts tab's
        favourites (idempotent), then confirm in the status line."""
        self._star_font(self.font_picker.currentFamily())

    def _star_font(self, family, category=None):
        """Add *family* to favourites (optionally tagged with *category*) and
        confirm in the status line."""
        if not family:
            return
        panel = getattr(self, "fonts_panel", None)
        if panel is None:
            return
        panel.add_favorite(family, [category] if category else None)
        try:
            self.status.setText(self._tr("st_font_starred").format(name=family))
        except Exception:
            pass

    # -- 'Missing fonts' report (Setup tab) --------------------------------
    def _favorite_fonts(self):
        panel = getattr(self, "fonts_panel", None)
        if panel is None:
            return []
        try:
            return list(panel._store.fonts())
        except Exception:                               # noqa: BLE001
            return []

    def _sfx_fonts(self):
        d = getattr(self, "_sfx_docker", None)
        if d is None or not hasattr(d, "referenced_fonts"):
            return []
        try:
            return list(d.referenced_fonts())
        except Exception:                               # noqa: BLE001
            return []

    def _main_preset_fonts(self):
        out = []
        for manga in getattr(self, "_groups", {}).values():
            for char in (manga or {}).values():
                for cfg in (char or {}).values():
                    if isinstance(cfg, dict):
                        f = (cfg.get("font") or "").strip()
                        if f:
                            out.append(f)
        return out

    def _all_referenced_fonts(self):
        return (self._favorite_fonts() + self._sfx_fonts()
                + self._main_preset_fonts())

    def _dedup_ci(self, fonts):
        seen, out = set(), []
        for f in fonts:
            fl = (f or "").strip().lower()
            if fl and fl not in seen:
                seen.add(fl)
                out.append(f.strip())
        return out

    def _font_index(self):
        """Tolerant matcher over the installed families.

        The font names in rules, presets and favourites are hand-written and
        travel between machines, so they drift from what the system reports:
        "CC Wild Words" here, "CCWildWords" there; a Fonts.com kit registering
        as "ImaginaryFriendBBW00-Rg"; a repack that baked the cut into the
        family name. Matching through the index means a mere spelling
        difference stops counting as a missing font. See typer_kr.fontmatch for
        the tiers -- and for the near misses it deliberately refuses to bridge,
        because "BadaBoom Pro BB" really is not "BadaBoom BB"."""
        return FM.FontIndex(self._installed_families())

    def _missing_of(self, fonts):
        """Referenced fonts that resolve to nothing installed at all."""
        idx = self._font_index()
        return sorted(idx.missing(self._dedup_ci(fonts)),
                      key=lambda s: s.lower())

    def _show_missing_fonts(self):
        """Setup-tab 'Missing fonts' report: one window that switches between a
        menu (favourite / SFX / all) and the result list, with a Back button and
        a header showing how many fonts are installed vs. missing."""
        dlg = QDialog(self.widget())
        dlg.setWindowTitle(self._tr("missing_title"))
        dlg.resize(380, 440)
        outer = QVBoxLayout(dlg)
        stack = QStackedWidget()
        outer.addWidget(stack)

        menu = QWidget()
        mlay = QVBoxLayout(menu)
        intro = QLabel(self._tr("missing_intro"))
        intro.setWordWrap(True)
        mlay.addWidget(intro)
        b_fav = QPushButton(self._tr("missing_fav"))
        b_sfx = QPushButton(self._tr("missing_sfx"))
        b_all = QPushButton(self._tr("missing_all"))
        for b in (b_fav, b_sfx, b_all):
            b.setMinimumHeight(34)
            mlay.addWidget(b)
        mlay.addStretch(1)
        stack.addWidget(menu)

        page = QWidget()
        play = QVBoxLayout(page)
        head = QLabel()
        head.setWordWrap(True)
        play.addWidget(head)
        lst = QListWidget()
        play.addWidget(lst, 1)
        back = QPushButton(self._tr("missing_back"))
        play.addWidget(back)
        stack.addWidget(page)

        def _add(text, family):
            it = QListWidgetItem(text)
            ff = QFont(family)
            ff.setPixelSize(14)
            it.setFont(ff)
            lst.addItem(it)

        def _show(title, fonts):
            ref = self._dedup_ci(fonts)
            _, renamed, missing = self._font_index().report(ref)
            head.setText(self._tr("missing_head").format(
                title=title, have=len(self._installed_families()),
                ref=len(ref), missing=len(missing)))
            lst.clear()
            # Names that only differ in spelling are not missing. Listing them
            # first, rendered in the face they actually resolve to, turns the
            # report into something actionable: these are the entries whose
            # spelling the user may want to correct, and the preview proves the
            # match is the right face. The arrow needs no translation.
            for wanted, m in sorted(renamed, key=lambda p: p[0].lower()):
                _add("%s  →  %s" % (wanted, m.family), m.family)
            if missing:
                for f in missing:
                    _add(f, f)
            elif not renamed:
                lst.addItem(self._tr("missing_none_line"))
            stack.setCurrentWidget(page)

        b_fav.clicked.connect(
            lambda: _show(self._tr("missing_fav"), self._favorite_fonts()))
        b_sfx.clicked.connect(
            lambda: _show(self._tr("missing_sfx"), self._sfx_fonts()))
        b_all.clicked.connect(
            lambda: _show(self._tr("missing_all"), self._all_referenced_fonts()))
        back.clicked.connect(lambda: stack.setCurrentWidget(menu))
        dlg.exec()

    def _font_context_menu(self, pos):
        """Right-click menu on the font picker: star the font under the cursor,
        or add it directly to one of the existing categories."""
        lst = self.font_picker.list
        it = lst.itemAt(pos)
        fam = (it.data(Qt.ItemDataRole.UserRole) if it is not None
               else self.font_picker.currentFamily())
        if not fam:
            return
        panel = getattr(self, "fonts_panel", None)
        menu = QMenu(lst)
        act_fav = menu.addAction(self._tr("fav_star_current"))
        cat_actions = {}
        if panel is not None:
            cats = panel.category_names()
            if cats:
                menu.addSeparator()
                for c in cats:
                    cat_actions[menu.addAction("→ " + c)] = c
        chosen = menu.exec(lst.mapToGlobal(pos))
        if chosen is None or panel is None:
            return
        if chosen is act_fav:
            self._star_font(fam)
        elif chosen in cat_actions:
            self._star_font(fam, cat_actions[chosen])

    def _install_fonts_and_refresh(self, paths):
        """Install bundled fonts (per-user, Windows) and refresh the picker so
        they show up right away."""
        from . import fontfiles as _FF
        res = _FF.install_fonts(paths)
        try:
            self.font_picker.reloadFamilies()
        except Exception:                               # noqa: BLE001
            pass
        return res

    def _load_font_favorites(self):
        try:
            return Krita.instance().readSetting("typer_kr", "fontFavorites", "")
        except Exception:
            return ""

    def _save_font_favorites(self, text):
        try:
            Krita.instance().writeSetting("typer_kr", "fontFavorites", text)
        except Exception:
            pass

    def _load_auto_char(self):
        try:
            return Krita.instance().readSetting(
                "typer_kr", "autoChar", "true") != "false"
        except Exception:
            return True

    def _on_auto_char_toggle(self, checked):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "autoChar", "true" if checked else "false")
        except Exception:
            pass
        if checked:
            self._show_current()      # auf die aktuelle Zeile sofort anwenden

    def _load_auto_manga(self):
        try:
            return Krita.instance().readSetting(
                "typer_kr", "autoManga", "true") != "false"
        except Exception:
            return True

    def _load_replace_existing(self):
        try:
            return Krita.instance().readSetting(
                "typer_kr", "replaceExisting", "true") != "false"
        except Exception:
            return True

    def _on_replace_toggle(self, checked):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "replaceExisting", "true" if checked else "false")
        except Exception:
            pass

    # ---- preset mode: with a character level, or one flat list per manga ----

    def _load_by_char(self):
        try:
            return Krita.instance().readSetting(
                "typer_kr", "presetsByCharacter", "true") != "false"
        except Exception:
            return True

    def _by_char(self):
        """True = Manga -> Character -> preset (default); False = simple mode
        (Manga -> preset, character level hidden)."""
        chk = getattr(self, "by_char_chk", None)
        return True if chk is None else chk.isChecked()

    def _on_by_char_toggle(self, checked):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "presetsByCharacter", "true" if checked else "false")
        except Exception:
            pass
        self._apply_preset_mode()

    def _apply_preset_mode(self):
        """Show/hide the character level and rebuild the preset dropdown for
        the active mode. Simple mode is only a view – the stored 3-level
        preset data is never migrated or renamed."""
        by_char = self._by_char()
        for w in (self.lbl_char, self.char_combo, self.char_new_btn,
                  self.char_del_btn):
            w.setVisible(by_char)
        self.auto_char_chk.setVisible(by_char)
        self._refresh_presets_combo()

    # ---- main characters (the ones pinned to the top of the dropdowns) ----
    def _load_main_chars(self):
        """{manga: [character, …]} — who is a main character, per manga."""
        try:
            raw = Krita.instance().readSetting("typer_kr", "mainChars", "")
            data = json.loads(raw) if raw else {}
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        out = {}
        for manga, names in data.items():
            if isinstance(names, list):
                out[str(manga)] = [str(n) for n in names if str(n).strip()]
        return out

    def _save_main_chars(self):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "mainChars", json.dumps(self._main_chars_map))
        except Exception:
            pass

    def _main_chars(self, manga=None):
        """The main characters of a manga (the current one by default)."""
        return list(self._main_chars_map.get(manga or self._group, []))

    def _is_main_char(self, char, manga=None):
        low = (char or "").strip().lower()
        return any(c.lower() == low for c in self._main_chars(manga))

    def _toggle_main_char(self, char, manga=None):
        """Star/unstar a character. Returns True when it is a main character
        afterwards."""
        char = (char or "").strip()
        if not char:
            return False
        manga = manga or self._group
        names = [c for c in self._main_chars_map.get(manga, [])]
        low = char.lower()
        hit = [c for c in names if c.lower() == low]
        if hit:
            names = [c for c in names if c.lower() != low]
            now_main = False
        else:
            names.append(char)
            now_main = True
        if names:
            self._main_chars_map[manga] = names
        else:
            self._main_chars_map.pop(manga, None)
        self._save_main_chars()
        return now_main

    def _forget_main_char(self, char, manga=None):
        """Drop a character from the main list (used when it is deleted)."""
        manga = manga or self._group
        names = self._main_chars_map.get(manga)
        if not names:
            return
        low = (char or "").strip().lower()
        rest = [c for c in names if c.lower() != low]
        if rest:
            self._main_chars_map[manga] = rest
        else:
            self._main_chars_map.pop(manga, None)
        self._save_main_chars()

    def on_main_chars(self):
        """Setup button: pick each manga's main characters."""
        dlg = MainCharsDialog(self.widget(), self._tr, self._groups,
                              self._main_chars_map, self._group)
        if dlg.exec():
            self._main_chars_map = dlg.result_map()
            self._save_main_chars()
            self._refresh_chars_combo(select=self._char)
            self._refresh_presets_combo()
            self._set_status(self._tr("st_mainchar_saved").format(
                n=len(self._main_chars()), manga=self._group))

    def _char_context_menu(self, pos):
        """Right-click the character dropdown: star/unstar without leaving the
        page you are working on."""
        ch = self.char_combo.currentData()
        if not ch:
            return
        menu = QMenu(self.char_combo)
        is_main = self._is_main_char(ch)
        act = menu.addAction(self._tr(
            "mainchar_ctx_remove" if is_main else "mainchar_ctx_add"))
        menu.addSeparator()
        act_manage = menu.addAction(self._tr("mainchar_btn"))
        chosen = menu.exec(self.char_combo.mapToGlobal(pos))
        if chosen is act:
            now = self._toggle_main_char(ch)
            self._refresh_chars_combo(select=ch)
            self._refresh_presets_combo()
            self._set_status(self._tr(
                "st_mainchar_on" if now else "st_mainchar_off").format(name=ch))
        elif chosen is act_manage:
            self.on_main_chars()

    def _preset_ref(self, data):
        """(owning character, preset name) for a preset-combo item's data.
        Character mode stores just the name (owner = current character);
        simple mode stores the (character, name) tuple. ('', '') for none."""
        if isinstance(data, (tuple, list)) and len(data) == 2:
            return str(data[0]), str(data[1])
        if data:
            return self._char, str(data)
        return "", ""

    def _bucket_char(self):
        """Character that receives newly saved presets in simple mode: the
        localized default character if the manga has one, else its first
        character (created on demand by _ensure_levels)."""
        self._ensure_levels()
        chars = self._groups[self._group]
        cd = self._tr("char_default")
        if cd in chars:
            return cd
        return sorted(chars.keys(), key=lambda s: s.lower())[0]

    def _on_auto_manga_toggle(self, checked):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "autoManga", "true" if checked else "false")
        except Exception:
            pass

    def _maybe_auto_manga(self, text, filename=""):
        """If 'auto manga' is on, detect which saved manga this script belongs
        to (file name / header / first lines) and switch to it. Does nothing
        when the feature is off or no manga matches."""
        chk = getattr(self, "auto_manga_chk", None)
        if chk is None or not chk.isChecked():
            return
        match = LP.detect_manga(list(self._groups.keys()), text, filename)
        if not match or match == self._group:
            return
        self._group = match
        self._char = ""
        self._refresh_groups_combo(select=match)
        self._refresh_chars_combo()
        self._refresh_presets_combo()
        self._apply_default_preset()      # default style for the new character
        self._save_last_manga()
        self._set_status(self._tr("st_auto_manga").format(name=match))

    def _maybe_auto_character(self, text):
        """If 'auto character' is on and the line starts with a speaker name
        ('Name: …') that matches a character in the current manga, switch to
        that character (and apply its default style preset). Returns the text
        without the speaker prefix so the bubble stays clean; otherwise the
        text unchanged."""
        if not self._by_char():
            return text        # simple mode: characters are not in the workflow
        chk = getattr(self, "auto_char_chk", None)
        if chk is None or not chk.isChecked():
            return text
        name, rest = LP.split_speaker(text)
        if not name:
            return text
        match = None
        for ch in self._cur_chars():
            if ch.lower() == name.lower():
                match = ch
                break
        if not match:
            return text
        if match != self._char:
            self._char = match
            self._refresh_chars_combo(select=match)
            self._apply_default_preset()
            self._set_status(self._tr("st_auto_char").format(name=match))
        return rest

    # ---- preset usage learning (per manga/character) ----
    def _load_preset_usage(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "presetUsage", "")
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_preset_usage(self):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "presetUsage", json.dumps(self._preset_usage))
        except Exception:
            pass

    def _record_preset_usage(self, manga, char, preset):
        """Count that `preset` was used for (manga, char) so the default-preset
        picker can learn the most-used style over time."""
        if not (manga and char and preset):
            return
        by_manga = self._preset_usage.setdefault(manga, {})
        by_char = by_manga.setdefault(char, {})
        by_char[preset] = int(by_char.get(preset, 0)) + 1
        self._save_preset_usage()

    def _apply_default_preset(self):
        """Auto-select the current character's default preset (normal/talking,
        else most-used, else first non-none). Does nothing if the character has
        no real preset. In simple mode the default is picked from ALL presets
        of the manga (usage counts merged across characters)."""
        if not self._by_char():
            entries = LP.flatten_presets(self._cur_chars())
            usage_by_char = self._preset_usage.get(self._group, {})
            usage = {}
            for _label, ch, name in entries:
                n = int(usage_by_char.get(ch, {}).get(name, 0))
                if n:
                    usage[name] = usage.get(name, 0) + n
            name = LP.default_preset_for([e[2] for e in entries], usage)
            for _label, ch, nm in entries:
                if name and nm == name:
                    self._apply_preset(self._cur_chars()[ch][nm])
                    self._refresh_presets_combo(select=(ch, nm))
                    return
            self._refresh_presets_combo()
            return
        presets = self._cur_presets()
        usage = self._preset_usage.get(self._group, {}).get(self._char, {})
        name = LP.default_preset_for(list(presets.keys()), usage)
        if name and name in presets:
            self._apply_preset(presets[name])
            self._refresh_presets_combo(select=name)
        else:
            self._refresh_presets_combo()

    def _on_lang_change(self):
        self._lang = self.lang_combo.currentData() or "en"
        self._save_lang()
        self._retranslate()
        self._refresh_view()

    def _retranslate(self):
        t = self._tr
        self.setWindowTitle(t("title"))
        self._retranslate_tabs()
        self.lang_label.setText(t("language"))
        self.setup_general_toggle.setText("⚙ " + t("setup_h_general"))
        self.setup_fonts_toggle.setText("🅰 " + t("setup_h_fonts"))
        self.setup_google_toggle.setText("🔑 " + t("setup_h_google"))
        self.view_toggle.setText(t("view_toggle"))
        self.view_hint.setText(t("view_hint"))
        self.v_preview_chk.setText(t("view_preview"))
        self.v_editor_chk.setText(t("view_editor"))
        self.v_table_chk.setText(t("view_table"))
        self.v_fonts_chk.setText(t("view_fonts"))
        self.v_bubblr_chk.setText(t("view_bubblr"))
        self.v_bmap_chk.setText(t("view_bmap"))
        self.view_reset_btn.setText(t("view_reset"))
        self.load_btn.setText(t("load_btn"))
        self.lbl_script.setText(t("script_label"))
        self.editor.setPlaceholderText(t("editor_ph"))
        self.skip_empty.setText(t("skip_empty"))
        self.analyze_btn.setText(t("analyze_btn"))
        self.add_line_btn.setText(t("add_line_btn"))
        self.save_script_btn.setText(t("save_script_btn"))
        if hasattr(self, "fav_add_btn"):
            self.fav_add_btn.setText(t("fav_star_current"))
            self.fav_add_btn.setToolTip(t("fav_star_current_tip"))
        self.lbl_align.setText(t("align_label"))
        self.table.setHorizontalHeaderLabels([t("col_source"), t("col_translation")])
        self.prev_btn.setText(t("prev"))
        self.next_btn.setText(t("next"))
        self.bubble_prev_btn.setToolTip(t("bubble_prev_tip"))
        self.bubble_next_btn.setToolTip(t("bubble_next_tip"))
        self.reset_btn.setText(t("reset_btn"))
        self.lbl_page.setText(t("page_jump"))
        self.active_edit.setPlaceholderText(t("active_ph"))
        self.lbl_preview.setText(t("preview_label"))
        if hasattr(self, "preview_refresh_btn"):
            self.preview_refresh_btn.setToolTip(t("preview_refresh_tip"))
        self._update_text_preview()
        self.lbl_font.setText(t("font"))
        self.font_picker.set_search_placeholder(t("font_search_ph"))
        self.lbl_text_type.setText(t("text_type_label"))
        self.tt_fonts_btn.setText(t("ttf_open"))
        if hasattr(self, "fav_missing_btn"):
            self.fav_missing_btn.setText(t("missing_btn"))
        self.tt_fonts_hint.setText(t("ttf_hint"))
        self.lbl_g_client.setText(t("g_client_label"))
        self.g_client_edit.setPlaceholderText(t("g_client_ph"))
        self.g_sign_in_btn.setText(t("g_sign_in"))
        self.g_sign_out_btn.setText(t("g_sign_out"))
        self.g_hint.setText(t("g_hint"))
        self.lbl_g_image.setText(t("g_image_label"))
        self.g_image_edit.setPlaceholderText(t("g_image_ph"))
        self.g_image_btn.setText(t("g_image_btn"))
        self._refresh_g_status()
        self.text_type_apply_btn.setText(t("tt_apply"))
        self.text_type_combo.setItemText(0, t("tt_none"))
        for _i, _tid in enumerate(TT.ids()):
            self.text_type_combo.setItemText(_i + 1, self._tt_label(_tid))
        self._on_text_type_changed()
        for _i, _sid in enumerate(BAL.SHAPE_ORDER):
            self.balloon_combo.setItemText(_i, t("balloon_" + _sid))
        self.balloon_tail_chk.setText(t("balloon_tail"))
        self.balloon_tail_chk.setToolTip(t("balloon_tail_tip"))
        self.balloon_btn.setText(t("balloon_insert"))
        self.balloon_btn.setToolTip(t("balloon_insert_tip"))
        self._on_balloon_changed()
        self.lbl_style.setText(t("style"))
        self.bold_chk.setText(t("bold"))
        self.italic_chk.setText(t("italic"))
        self.underline_chk.setText(t("underline"))
        self.liga_chk.setText(t("ligatures"))
        self.liga_chk.setToolTip(t("ligatures_tip"))
        self.lbl_alignment.setText(t("align"))
        self.align_combo.setItemText(0, t("align_left"))
        self.align_combo.setItemText(1, t("align_center"))
        self.align_combo.setItemText(2, t("align_right"))
        self.lbl_valign.setText(t("valign_label"))
        self.valign_combo.setItemText(0, t("valign_top"))
        self.valign_combo.setItemText(1, t("valign_middle"))
        self.valign_combo.setItemText(2, t("valign_bottom"))
        self.case_label.setText(t("case_label"))
        self.case_combo.setItemText(0, t("case_none"))
        self.case_combo.setItemText(1, t("case_upper"))
        self.case_combo.setItemText(2, t("case_lower"))
        self.bold_sel_btn.setText(t("bold_sel"))
        self.bold_sel_btn.setToolTip(t("bold_sel_tip"))
        self.tidy_chk.setText(t("tidy"))
        self.comic_chk.setText(t("comic"))
        self.comic_chk.setToolTip(t("comic_tip"))
        self.crossbar_chk.setText(t("crossbar"))
        self.crossbar_chk.setToolTip(t("crossbar_tip"))
        self.tidy_chk.setToolTip(t("tidy_tip"))
        self.round_chk.setText(t("round"))
        self.round_chk.setToolTip(t("round_tip"))
        self.vertical_chk.setText(t("vertical"))
        self.vertical_chk.setToolTip(t("vertical_tip"))
        self.shadow_chk.setText(t("shadow"))
        self.shadow_chk.setToolTip(t("shadow_tip"))
        self.shadow_color_btn.setText(t("shadow_color_btn"))
        self.lbl_shadow_off.setText(t("shadow_off"))
        self.lbl_preset.setText(t("style_label"))
        self.lbl_group.setText(t("group"))
        self.group_new_btn.setText(t("group_new"))
        self.group_del_btn.setText(t("group_del"))
        self.lbl_char.setText(t("char"))
        self.char_new_btn.setText(t("char_new"))
        self.char_del_btn.setText(t("char_del"))
        self.auto_char_chk.setText(t("auto_char"))
        self.auto_char_chk.setToolTip(t("auto_char_tip"))
        self.auto_manga_chk.setText(t("auto_manga"))
        self.auto_manga_chk.setToolTip(t("auto_manga_tip"))
        self.preset_menu_btn.setToolTip(t("preset_actions"))
        self.preset_save_act.setText(t("preset_save"))
        self.preset_del_act.setText(t("preset_del"))
        self.preset_import_act.setText(t("preset_import"))
        self.preset_import_excel_act.setText(t("preset_import_excel"))
        self.preset_export_act.setText(t("preset_export"))
        # relabel the first combo entry (no preset)
        if self.preset_combo.count() > 0:
            self.preset_combo.blockSignals(True)
            self.preset_combo.setItemText(0, t("preset_none"))
            self.preset_combo.blockSignals(False)
        self.size_label.setText(
            t("size_max") if self.auto_chk.isChecked() else t("size_fixed"))
        self.size_spin.setToolTip(t("size_tip"))
        self.color_btn.setText(t("color_btn"))
        self.lbl_pad.setText(t("padding"))
        self.pad_spin.setToolTip(t("padding_tip"))
        self.lbl_spacing.setText(t("spacing"))
        self.outline_chk.setText(t("outline"))
        self.outline_chk.setToolTip(t("outline_tip"))
        self.outline_color_btn.setText(t("outline_color_btn"))
        self.lbl_outline_width.setText(t("outline_width"))
        self.outline2_color_btn.setText(t("outline2_color_btn"))
        self.lbl_outline2_width.setText(t("outline2_width"))
        self.outline_more_btn.setText(t("outline_more"))
        self.outline_dlg.setWindowTitle(t("outline"))
        self.lbl_outline_pattern.setText(t("outline_pattern_label"))
        self.outline_pattern_krita_btn.setText(t("outline_pattern_krita"))
        self.outline_pattern_gen_btn.setText(t("pattern_generate"))
        self.outline_pattern_saved_btn.setText(t("pattern_saved"))
        self.lbl_outline_pattern_target.setText(t("outline_pattern_target_label"))
        for _i, _k in enumerate(("outline_pattern_t1", "outline_pattern_t2",
                                 "outline_pattern_tboth")):
            self.outline_pattern_target_combo.setItemText(_i, t(_k))
        self._update_outline_pattern_btn()
        self.fill_pattern_hint.setText(t("fill_pattern_hint"))
        self.fill_pattern_krita_btn.setText(t("outline_pattern_krita"))
        self.fill_pattern_gen_btn.setText(t("pattern_generate"))
        self.fill_pattern_saved_btn.setText(t("pattern_saved"))
        self.fill_sel_btn.setText(t("fill_apply_sel"))
        self._update_fill_pattern_btn()
        self.style_soft_chk.setText(t("style_soft"))
        self.style_soft_pattern_chk.setText(t("style_soft_pattern"))
        self.lbl_style_soft_w.setText(t("style_soft_w"))
        self.lbl_style_soft_blur.setText(t("style_soft_blur"))
        self.outline_close_btn.setText(t("close"))
        self.shadow_more_btn.setText(t("shadow_more"))
        self.shadow_dlg.setWindowTitle(t("shadow"))
        self.shadow_close_btn.setText(t("close"))
        self.auto_chk.setText(t("auto"))
        self.auto_chk.setToolTip(t("auto_tip"))
        self.hyph_chk.setText(t("hyphenate"))
        self.hyph_chk.setToolTip(t("hyphenate_tip"))
        self.lbl_hyph_lang.setText(t("hyph_lang"))
        for i in range(self.hyph_lang_combo.count()):
            code = self.hyph_lang_combo.itemData(i)
            self.hyph_lang_combo.setItemText(
                i, t("hyph_auto" if code == "auto" else "hyph_" + str(code)))
        self.insert_btn.setText(t("insert_btn"))
        self.replace_chk.setText(t("replace_existing"))
        self.replace_chk.setToolTip(t("replace_existing_tip"))
        self.by_char_chk.setText(t("presets_by_char"))
        self.main_chars_btn.setText(t("mainchar_btn"))
        self.main_chars_hint.setText(t("mainchar_hint"))
        self.by_char_chk.setToolTip(t("presets_by_char_tip"))
        self._retranslate_panels()
        self.exp_toggle.setText("⚗ " + t("exp_section"))
        self.enable_bubblr_chk.setText(t("enable_bubblr"))
        self.enable_shapr_chk.setText(t("enable_shapr"))
        self.enable_sfx_chk.setText(t("enable_sfx"))
        self.enable_fonts_chk.setText(t("enable_fonts"))
        self.enable_balloon_chk.setText(t("enable_balloon"))
        self.enable_patterns_chk.setText(t("enable_patterns"))
        self.enable_texttypes_chk.setText(t("enable_texttypes"))
        self.enable_balloon_chk.setToolTip(t("enable_balloon_tip"))
        self.customize_chk.setText(t("customize_layout"))
        self.customize_hint.setText(t("customize_hint"))
        self.layout_reset_btn.setText(t("layout_reset"))
        # BubblR tab
        self.bp_backend_combo.setItemText(0, t("bp_backend_heur"))
        self.bp_backend_combo.setItemText(1, t("bp_backend_ai"))
        self.bp_backend_combo.setToolTip(t("bp_backend_tip"))
        self.bp_detect_btn.setText(t("bp_detect"))
        self.bp_add_sel_btn.setText(t("bp_add_sel"))
        self.bp_reset_btn.setText(t("bp_reset"))
        self.bp_order_btn.setText(t("bp_order"))
        self.bp_order_btn.setToolTip(t("bp_order_tip"))
        self.bp_sfxmark_btn.setText(t("bp_sfxmark"))
        self.bp_sfxmark_btn.setToolTip(t("bp_sfxmark_tip"))
        self.bp_shape_btn.setText(t("bp_shapemark"))
        self.bp_shape_btn.setToolTip(t("bp_shapemark_tip"))
        self.bp_edit_btn.setText(t("bp_edit"))
        self.bp_edit_btn.setToolTip(t("bp_edit_tip"))
        self.bp_panelorder_btn.setText(t("bp_panelorder"))
        self.bp_panelorder_btn.setToolTip(t("bp_panelorder_tip"))
        self.bp_save_btn.setText(t("bp_save_boxes"))
        self.bp_save_btn.setToolTip(t("bp_save_boxes_tip"))
        self.bp_load_btn.setText(t("bp_load_boxes"))
        self.bp_load_btn.setToolTip(t("bp_load_boxes_tip"))
        self.bp_model_lbl.setText(t("bp_model"))
        self.bp_model_combo.setItemText(0, t("bp_model_auto"))
        self.bp_model_combo.setItemText(1, t("bp_model_baseline"))
        self.bp_model_combo.setItemText(2, t("bp_model_finetuned"))
        self.bp_model_combo.setItemText(3, t("bp_model_kitsumed"))
        self.bp_model_combo.setItemText(4, t("bp_model_hybrid"))
        self.bp_model_combo.setToolTip(t("bp_model_tip"))
        self.bp_models_btn.setText(t("bp_models"))
        self.bp_models_btn.setToolTip(t("bp_models_tip"))
        self.bp_conf_lbl.setText(t("bp_conf"))
        self.bp_conf_spin.setToolTip(t("bp_conf_tip"))
        self.bp_sfxconf_lbl.setText(t("bp_sfxconf"))
        self.bp_sfxconf_spin.setToolTip(t("bp_conf_tip"))
        self.bp_reset_btn.setToolTip(t("bp_reset_tip"))
        self.bp_text_chk.setText(t("bp_chk_text"))
        self.bp_text_chk.setToolTip(t("bp_chk_text_tip"))
        self.bp_sfx_chk.setText(t("bp_chk_sfx"))
        self.bp_sfx_chk.setToolTip(t("bp_chk_sfx_tip"))
        self.bp_rtl_chk.setText(t("bp_rtl"))
        self.bp_rtl_chk.setToolTip(t("bp_rtl_tip"))
        self.bp_tile_chk.setText(t("bp_tile"))
        self.bp_tile_chk.setToolTip(t("bp_tile_tip"))
        self.bp_overlay.setToolTip(t("bp_overlay_tip"))
        self.bp_hint_lbl.setText(t("bp_hint"))
        self.bp_selfollow_chk.setText(t("bp_selfollow"))
        self.bp_selfollow_chk.setToolTip(t("bp_selfollow_tip"))
        self.bp_sfx_db_btn.setText(t("bp_sfx_db"))
        self.bp_sfx_db_btn.setToolTip(t("bp_sfx_db_tip"))
        self.bp_export_btn.setText(t("bp_export"))
        self.bp_export_btn.setToolTip(t("bp_export_tip"))
        # re-label the page combo / status in the new language
        self._refresh_pages_combo()

    # -- UI helpers --

    def _hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _update_color_btn(self):
        self.color_btn.setStyleSheet(
            "QPushButton {{ background-color: {}; }}".format(self._color.name())
        )
        self._update_text_preview()

    def _update_outline_btn(self):
        self.outline_color_btn.setStyleSheet(
            "QPushButton {{ background-color: {}; }}".format(
                self._outline_color.name())
        )
        self._update_text_preview()

    def _update_outline2_btn(self):
        self.outline2_color_btn.setStyleSheet(
            "QPushButton {{ background-color: {}; }}".format(
                self._outline2_color.name())
        )
        self._update_text_preview()

    # -- pattern-filled + soft (blurred) outline ---------------------------
    def _update_style_soft_btn(self):
        self.style_soft_color_btn.setStyleSheet(
            "QPushButton {{ background-color: {}; }}".format(
                self._style_soft_color.name()))

    def on_pick_style_soft_color(self):
        prev = QColor(self._style_soft_color)

        def _apply(col):
            if col.isValid():
                self._style_soft_color = QColor(col)
                self._update_style_soft_btn()
                self._update_text_preview()

        dlg = QColorDialog(self._style_soft_color, self.widget())
        dlg.currentColorChanged.connect(_apply)
        if dlg.exec():
            _apply(dlg.selectedColor())
        else:
            _apply(prev)

    def _update_soft_enabled(self):
        """Soft-outline sub-controls follow the enable checkbox; the solid-colour
        button is disabled when the halo is set to use the pattern instead."""
        on = self.style_soft_chk.isChecked()
        for w in (self.style_soft_pattern_chk, self.style_soft_width_spin,
                  self.style_soft_blur_spin):
            w.setEnabled(on)
        self.style_soft_color_btn.setEnabled(
            on and not self.style_soft_pattern_chk.isChecked())

    def _update_outline_pattern_btn(self):
        """Show the chosen pattern's name on the button (or the 'choose' hint)."""
        name = ""
        if self._outline_pattern_path:
            name = os.path.basename(self._outline_pattern_path)
        elif self._outline_pattern_krita_name:
            name = self._outline_pattern_krita_name
        self.outline_pattern_btn.setText(name or self._tr("outline_pattern_pick"))

    def _krita_pattern_image(self, name):
        """QImage of a Krita-stored pattern resource, or None."""
        try:
            res = Krita.instance().resources("pattern")
            r = res.get(name) if res else None
            img = r.image() if r is not None else None
            if img is not None and not img.isNull():
                return img
        except Exception:                               # noqa: BLE001
            pass
        return None

    def _ensure_outline_pattern_img(self):
        """Lazily resolve + cache the outline pattern QImage (file OR Krita
        resource); None when nothing valid is chosen."""
        if (self._outline_pattern_img is not None
                and not self._outline_pattern_img.isNull()):
            return self._outline_pattern_img
        if self._outline_pattern_path and os.path.exists(self._outline_pattern_path):
            img = QImage(self._outline_pattern_path)
            if not img.isNull():
                self._outline_pattern_img = img
                return img
        if self._outline_pattern_krita_name:
            img = self._krita_pattern_image(self._outline_pattern_krita_name)
            if img is not None:
                self._outline_pattern_img = QImage(img)
                return self._outline_pattern_img
        return None

    def _pick_outline_pattern_file(self):
        path, _f = QFileDialog.getOpenFileName(
            self.widget(), self._tr("outline_pattern_pick"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            self._set_status(self._tr("outline_pattern_bad"), error=True)
            return
        self._outline_pattern_path = path
        self._outline_pattern_krita_name = ""
        self._outline_pattern_img = img
        self._update_outline_pattern_btn()
        self._update_text_preview()

    def _pick_outline_pattern_krita(self):
        nm, img = self._choose_krita_pattern()
        if not nm or img is None:
            return
        self._outline_pattern_krita_name = nm
        self._outline_pattern_path = ""
        self._outline_pattern_img = QImage(img)
        self._update_outline_pattern_btn()
        self._update_text_preview()

    def _clear_outline_pattern(self):
        self._outline_pattern_path = ""
        self._outline_pattern_krita_name = ""
        self._outline_pattern_img = None
        self._update_outline_pattern_btn()
        self._update_text_preview()

    def _outline_pattern_active(self):
        return self._ensure_outline_pattern_img() is not None

    # -- shared pattern helpers (used by both outline + text fill) ----------
    def _choose_krita_pattern(self):
        """Modal picker over Krita's stored patterns. Returns (name, QImage) or
        (None, None)."""
        try:
            res = Krita.instance().resources("pattern")
        except Exception:                               # noqa: BLE001
            res = None
        if not res:
            self._set_status(self._tr("outline_pattern_none"), error=True)
            return None, None
        dlg = QDialog(self.widget())
        dlg.setWindowTitle(self._tr("outline_pattern_krita"))
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        lst.setViewMode(QListWidget.ViewMode.IconMode)
        lst.setIconSize(QSize(64, 64))
        lst.setResizeMode(QListWidget.ResizeMode.Adjust)
        lst.setMovement(QListWidget.Movement.Static)
        lst.setMinimumSize(430, 340)
        for nm in sorted(res.keys(), key=lambda s: s.lower()):
            img = self._krita_pattern_image(nm)
            if img is None:
                continue
            it = QListWidgetItem(nm[:22])
            it.setData(Qt.ItemDataRole.UserRole, nm)
            it.setToolTip(nm)
            it.setIcon(QIcon(QPixmap.fromImage(img).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            lst.addItem(it)
        if lst.count() == 0:
            self._set_status(self._tr("outline_pattern_none"), error=True)
            return None, None
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        lay.addWidget(lst)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None, None
        it = lst.currentItem()
        if it is None:
            return None, None
        nm = it.data(Qt.ItemDataRole.UserRole)
        return nm, self._krita_pattern_image(nm)

    def _patterns_dir(self):
        """Stable folder for generated pattern PNGs (persisted by path)."""
        base = os.path.join(os.path.expanduser("~"), "TypeR-Patterns")
        try:
            os.makedirs(base, exist_ok=True)
        except Exception:                               # noqa: BLE001
            base = tempfile.gettempdir()
        return base

    def _save_generated_pattern(self, img):
        """Write a generated tile to a PNG so it survives restarts; return the
        path (or '' on failure)."""
        try:
            path = os.path.join(self._patterns_dir(),
                                "pattern_%d.png" % int(time.time() * 1000))
            return path if img.save(path, "PNG") else ""
        except Exception:                               # noqa: BLE001
            return ""

    # -- saved-pattern library (make a pattern, keep it, reuse it) ----------
    def _load_pattern_library(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "patternLibrary", "")
            data = json.loads(raw) if raw else []
            return [e for e in data
                    if isinstance(e, dict) and e.get("path")]
        except Exception:                               # noqa: BLE001
            return []

    def _save_pattern_library(self, lib):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "patternLibrary", json.dumps(lib))
        except Exception:                               # noqa: BLE001
            pass

    def _save_pattern_to_library(self, img):
        """Prompt for a name and store the tile (as a PNG) in the reusable
        pattern library."""
        if img is None or img.isNull():
            return
        name, ok = QInputDialog.getText(
            self.widget(), self._tr("patlib_title"), self._tr("patlib_name"))
        if not ok:
            return
        name = (name or "").strip() or self._tr("patlib_unnamed")
        path = self._save_generated_pattern(img)
        if not path:
            return
        lib = self._load_pattern_library()
        lib.append({"name": name, "path": path})
        self._save_pattern_library(lib)
        self._set_status(self._tr("patlib_saved").format(name=name))

    def _fill_selection_with_pattern(self, tile, stretch=False, grad_spec=None):
        """Fill the document's current selection with `tile`, clipped to the
        selection shape, on a NEW paint layer. Lets the user pick the area (e.g.
        their own text) by hand and drop a pattern into it. `stretch` fits the
        image once across the whole selection (for a gradient) instead of tiling
        it (for a repeating pattern). `grad_spec`, when given, re-renders the
        gradient at the exact selection size — so screentone dots stay round
        instead of being stretched into ovals."""
        doc = Krita.instance().activeDocument()
        if doc is None:
            self._set_status(self._tr("st_no_doc"), error=True)
            return
        if grad_spec is None and (tile is None or tile.isNull()):
            return
        sel = doc.selection()
        if sel is None:
            self._set_status(self._tr("sel_none"), error=True)
            return
        sx, sy, sw, sh = sel.x(), sel.y(), sel.width(), sel.height()
        if sw <= 0 or sh <= 0:
            self._set_status(self._tr("sel_none"), error=True)
            return
        img = QImage(sw, sh, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        if grad_spec is not None:     # re-render the fade at the real size
            fresh = IMG.make_pattern_gradient(width=sw, height=sh, **grad_spec)
            p.drawImage(0, 0, fresh)
        elif stretch:                 # one span across the whole selection
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(QRectF(0, 0, sw, sh), tile, QRectF(tile.rect()))
        else:
            p.fillRect(0, 0, sw, sh, _scaled_pattern_brush(tile, 100))
        try:                          # clip to the selection's actual shape
            mbytes = bytes(sel.pixelData(sx, sy, sw, sh))
            if len(mbytes) >= sw * sh:
                mask = QImage(mbytes, sw, sh, sw,
                              QImage.Format.Format_Alpha8).copy()
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                p.drawImage(0, 0, mask)
        except Exception:             # noqa: BLE001 — fall back to the bbox fill
            pass
        p.end()
        img = img.convertToFormat(QImage.Format.Format_ARGB32)
        node = _paint_layer_from_image(doc, img, sx, sy,
                                       self._tr("sel_pattern_layer"))
        if node is not None:
            self._set_status(self._tr("sel_filled"))
        else:
            self._set_status(self._tr("sel_none"), error=True)

    def _fill_selection_current(self):
        """Fill-panel button: use the currently chosen selection-fill pattern."""
        img = self._ensure_fill_pattern_img()
        if img is None:
            self._set_status(self._tr("fill_pattern_pick"), error=True)
            return
        self._fill_selection_with_pattern(
            img, getattr(self, "_fill_pattern_stretch", False),
            getattr(self, "_fill_pattern_grad_spec", None))

    def _pick_saved_pattern(self):
        """Modal picker over the saved-pattern library (with delete). Returns
        (QImage, path) or (None, None)."""
        lib = self._load_pattern_library()
        if not lib:
            self._set_status(self._tr("patlib_empty"), error=True)
            return None, None
        dlg = QDialog(self.widget())
        dlg.setWindowTitle(self._tr("patlib_title"))
        dlg.resize(430, 380)
        lay = QVBoxLayout(dlg)
        lst = QListWidget()
        lst.setViewMode(QListWidget.ViewMode.IconMode)
        lst.setIconSize(QSize(72, 72))
        lst.setResizeMode(QListWidget.ResizeMode.Adjust)
        lst.setMovement(QListWidget.Movement.Static)

        def _fill():
            lst.clear()
            for e in self._load_pattern_library():
                img = QImage(e["path"])
                if img.isNull():
                    continue
                it = QListWidgetItem(e.get("name", ""))
                it.setData(Qt.ItemDataRole.UserRole, e["path"])
                it.setToolTip(e.get("name", ""))
                it.setIcon(QIcon(QPixmap.fromImage(img).scaled(
                    72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)))
                it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
                lst.addItem(it)
        _fill()
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        lay.addWidget(lst)
        row = QHBoxLayout()
        del_btn = QPushButton(self._tr("patlib_delete"))

        def _delete():
            it = lst.currentItem()
            if it is None:
                return
            p = it.data(Qt.ItemDataRole.UserRole)
            self._save_pattern_library(
                [e for e in self._load_pattern_library() if e.get("path") != p])
            _fill()
        del_btn.clicked.connect(_delete)
        row.addWidget(del_btn)
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        row.addWidget(bb)
        lay.addLayout(row)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None, None
        it = lst.currentItem()
        if it is None:
            return None, None
        path = it.data(Qt.ItemDataRole.UserRole)
        img = QImage(path)
        return (img if not img.isNull() else None), path

    def _pick_outline_saved(self):
        img, path = self._pick_saved_pattern()
        if img is None:
            return
        self._outline_pattern_path = path
        self._outline_pattern_krita_name = ""
        self._outline_pattern_img = img
        self._update_outline_pattern_btn()
        self._update_text_preview()

    def _pick_fill_saved(self):
        img, path = self._pick_saved_pattern()
        if img is None:
            return
        self._fill_pattern_path = path
        self._fill_pattern_krita_name = ""
        self._fill_pattern_img = img
        self._fill_pattern_stretch = False
        self._fill_pattern_grad_spec = None
        self._update_fill_pattern_btn()
        self._update_text_preview()

    def _run_pattern_generator(self, fg, target):
        """Open the 'make a pattern' dialog and LIVE-apply every change to the
        text preview (better workflow: you see the pattern on the real text as
        you tweak it). `target` is 'fill' or 'outline'. Cancelling restores the
        previous pattern; OK commits it (saved to disk for persistence)."""
        try:
            from .patterngen import PatternGeneratorDialog
        except Exception:                               # noqa: BLE001
            return
        if target == "fill":
            prev = (self._fill_pattern_path, self._fill_pattern_krita_name,
                    self._fill_pattern_img)
        else:
            prev = (self._outline_pattern_path,
                    self._outline_pattern_krita_name, self._outline_pattern_img)

        def _live(tile):
            if target == "fill":
                self._fill_pattern_img = tile
            else:
                self._outline_pattern_img = tile
            self._update_text_preview()

        # NON-modal on purpose: with the generator open you can keep working on
        # the style (outlines, colours, size …) and the live preview reflects
        # BOTH the pattern-in-progress and your other edits — no need to close
        # it or detour through TextShapR to force a refresh.
        old = getattr(self, "_patgen_dlg", None)
        if old is not None:
            try:
                old.close()
            except Exception:                           # noqa: BLE001
                pass
        dlg = PatternGeneratorDialog(self.widget(), self._tr, fg=fg)
        dlg.setModal(False)
        dlg.previewChanged.connect(_live)
        dlg.saveRequested.connect(self._save_pattern_to_library)
        dlg.applyToSelectionRequested.connect(
            lambda t: self._fill_selection_with_pattern(
                t, dlg.is_gradient(), dlg.gradient_spec()))

        def _finish(result):
            if result == QDialog.DialogCode.Accepted:
                img = dlg._current_tile()
                path = self._save_generated_pattern(img)
                if target == "fill":
                    self._fill_pattern_img = img
                    self._fill_pattern_path = path
                    self._fill_pattern_krita_name = ""
                    self._fill_pattern_stretch = dlg.is_gradient()
                    self._fill_pattern_grad_spec = dlg.gradient_spec()
                    self._update_fill_pattern_btn()
                else:
                    self._outline_pattern_img = img
                    self._outline_pattern_path = path
                    self._outline_pattern_krita_name = ""
                    self._update_outline_pattern_btn()
            else:                                       # restore the old pattern
                if target == "fill":
                    (self._fill_pattern_path, self._fill_pattern_krita_name,
                     self._fill_pattern_img) = prev
                    self._update_fill_pattern_btn()
                else:
                    (self._outline_pattern_path,
                     self._outline_pattern_krita_name,
                     self._outline_pattern_img) = prev
                    self._update_outline_pattern_btn()
            self._update_text_preview()
            self._patgen_dlg = None

        dlg.finished.connect(_finish)
        self._patgen_dlg = dlg              # keep a reference (non-modal)
        _live(dlg._current_tile())          # apply immediately on open
        dlg.show()
        dlg.raise_()

    # -- text fill pattern (Style tab) -------------------------------------
    def _update_fill_pattern_btn(self):
        name = ""
        if self._fill_pattern_path:
            name = os.path.basename(self._fill_pattern_path)
        elif self._fill_pattern_krita_name:
            name = self._fill_pattern_krita_name
        self.fill_pattern_btn.setText(name or self._tr("fill_pattern_pick"))

    def _ensure_fill_pattern_img(self):
        if (self._fill_pattern_img is not None
                and not self._fill_pattern_img.isNull()):
            return self._fill_pattern_img
        if self._fill_pattern_path and os.path.exists(self._fill_pattern_path):
            img = QImage(self._fill_pattern_path)
            if not img.isNull():
                self._fill_pattern_img = img
                return img
        if self._fill_pattern_krita_name:
            img = self._krita_pattern_image(self._fill_pattern_krita_name)
            if img is not None:
                self._fill_pattern_img = QImage(img)
                return self._fill_pattern_img
        return None

    def _fill_pattern_active(self):
        return self._ensure_fill_pattern_img() is not None

    def _pick_fill_pattern_file(self):
        path, _f = QFileDialog.getOpenFileName(
            self.widget(), self._tr("fill_pattern_pick"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            self._set_status(self._tr("outline_pattern_bad"), error=True)
            return
        self._fill_pattern_path = path
        self._fill_pattern_krita_name = ""
        self._fill_pattern_img = img
        self._fill_pattern_stretch = False
        self._fill_pattern_grad_spec = None
        self._update_fill_pattern_btn()
        self._update_text_preview()

    def _pick_fill_pattern_krita(self):
        nm, img = self._choose_krita_pattern()
        if not nm or img is None:
            return
        self._fill_pattern_krita_name = nm
        self._fill_pattern_path = ""
        self._fill_pattern_img = QImage(img)
        self._fill_pattern_stretch = False
        self._fill_pattern_grad_spec = None
        self._update_fill_pattern_btn()
        self._update_text_preview()

    def _generate_fill_pattern(self):
        self._run_pattern_generator(self._color, "fill")

    def _generate_outline_pattern(self):
        self._run_pattern_generator(self._outline_color, "outline")

    def _clear_fill_pattern(self):
        self._fill_pattern_path = ""
        self._fill_pattern_krita_name = ""
        self._fill_pattern_img = None
        self._fill_pattern_stretch = False
        self._fill_pattern_grad_spec = None
        self._update_fill_pattern_btn()
        self._update_text_preview()

    def _on_outline_toggle(self):
        on = self.outline_chk.isChecked()
        self.outline_color_btn.setEnabled(on)
        self.outline_spin.setEnabled(on)
        # the 2nd outline is coupled to the outline switch
        if hasattr(self, "outline2_spin"):
            self.outline2_color_btn.setEnabled(on)
            self.outline2_spin.setEnabled(on)
        if hasattr(self, "outline_more_btn"):
            self.outline_more_btn.setEnabled(on)

    def _update_shadow_btn(self):
        self.shadow_color_btn.setStyleSheet(
            "QPushButton {{ background-color: {}; }}".format(
                self._shadow_color.name())
        )
        self._update_text_preview()

    def _on_shadow_toggle(self):
        on = self.shadow_chk.isChecked()
        self.shadow_color_btn.setEnabled(on)
        self.shadow_x_spin.setEnabled(on)
        self.shadow_y_spin.setEnabled(on)
        if hasattr(self, "shadow_more_btn"):
            self.shadow_more_btn.setEnabled(on)

    def on_pick_shadow_color(self):
        # Live shadow-colour picking (see on_pick_color): applies while dragging.
        prev = QColor(self._shadow_color)

        def _apply(col):
            if col.isValid():
                self._shadow_color = QColor(col)
                self._update_shadow_btn()
                self._on_style_changed()

        dlg = QColorDialog(self._shadow_color, self.widget())
        dlg.setWindowTitle(self._tr("shadow_color_btn"))
        dlg.currentColorChanged.connect(_apply)
        if dlg.exec():
            _apply(dlg.selectedColor())
        else:
            _apply(prev)                  # cancelled -> restore the old colour

    def _set_status(self, msg, error=False):
        self.status.setStyleSheet("color: #c0392b;" if error else "color: gray;")
        self.status.setText(msg)

    # -- main tabs (remember the last-used one) --

    # -- tab customization (rename / reorder / reset) ----------------------

    def _tab_namekey(self, tid):
        for t, nk in self._tab_defaults:
            if t == tid:
                return nk
        return None

    def _tab_label(self, tid):
        """Display name of a tab: the user's custom name if set, else the
        localized default."""
        custom = self._tab_names.get(tid)
        if custom:
            return custom
        nk = self._tab_namekey(tid)
        return self._tr(nk) if nk else (tid or "")

    def _retranslate_tabs(self):
        bar = self.main_tabs.tabBar()
        for i in range(self.main_tabs.count()):
            self.main_tabs.setTabText(i, self._tab_label(bar.tabData(i)))

    def _current_tab_order(self):
        bar = self.main_tabs.tabBar()
        return [bar.tabData(i) for i in range(self.main_tabs.count())]

    def _apply_tab_order(self, order):
        """Reorder the tab bar so its tab ids follow `order` (unknown/missing
        ids are ignored / left in place). Done by moving tabs into position.

        IMPORTANT: we must NOT block the tab bar's signals here. QTabWidget keeps
        its page stack in sync with the tab bar *through* the tabMoved signal;
        blocking it moves only the labels+data while the pages stay put, so every
        tab ends up showing another tab's content (labels look 'scrambled' and
        e.g. the real Setup page hides under a different label). Instead we guard
        our own save handler with a flag so a programmatic reorder does not
        churn the setting."""
        if not order:
            return
        bar = self.main_tabs.tabBar()
        # Build a clean permutation of the tabs that are ACTUALLY present:
        #  - drop ids from the saved order that have no tab right now (e.g. a
        #    hidden BubblR tab) — otherwise their target slot is wasted and every
        #    following tab lands one place off;
        #  - append any present tab the saved order doesn't mention (e.g. a newly
        #    added Fonts tab) so it goes to the end instead of being shuffled in.
        present = self._current_tab_order()
        present_set = set(present)
        wanted = [t for t in order if t in present_set]
        seen = set(wanted)
        wanted += [t for t in present if t not in seen]
        self._reordering = True
        try:
            for target, tid in enumerate(wanted):
                cur = next((i for i in range(self.main_tabs.count())
                            if bar.tabData(i) == tid), None)
                if cur is not None and cur != target:
                    bar.moveTab(cur, target)
        except Exception:
            pass
        finally:
            self._reordering = False

    def _on_tab_moved(self, *_a):
        if getattr(self, "_reordering", False):
            return
        Krita.instance().writeSetting(
            "typer_kr", "tabOrder", ",".join(self._current_tab_order()))

    def _on_tab_rename(self, index):
        if not self.customize_chk.isChecked():
            return
        if not (0 <= index < self.main_tabs.count()):
            return
        tid = self.main_tabs.tabBar().tabData(index)
        cur = self._tab_label(tid)
        name, ok = QInputDialog.getText(
            self.widget(), self._tr("tab_rename_title"),
            self._tr("tab_rename_prompt"), text=cur)
        if not ok:
            return
        name = name.strip()
        if name and name != self._tr(self._tab_namekey(tid) or ""):
            self._tab_names[tid] = name
        else:
            self._tab_names.pop(tid, None)      # empty / default -> reset name
        self._save_tab_names()
        self._retranslate_tabs()

    def _on_customize_toggle(self, on):
        self.main_tabs.tabBar().setMovable(bool(on))
        if hasattr(self, "customize_hint"):
            self.customize_hint.setVisible(bool(on))
        for pid, box in getattr(self, "_panels", {}).items():
            box.set_edit(on or pid in self._detached)
        Krita.instance().writeSetting(
            "typer_kr", "customize", "true" if on else "false")

    def _on_exp_toggle(self, on):
        if hasattr(self, "exp_box"):
            self.exp_box.setVisible(bool(on))
        Krita.instance().writeSetting(
            "typer_kr", "expOpen", "true" if on else "false")

    # -- movable panels (customizable layout, step 2a) ---------------------

    _PANEL_TITLES = {"presets": "panel_presets",
                     "jp_en_table": "panel_table",
                     "live_preview": "panel_preview",
                     "script_box": "panel_script",
                     "nav_line": "panel_nav",
                     "active_field": "panel_active",
                     "font_picker": "panel_font",
                     "insert": "panel_insert",
                     "text_type": "panel_text_type",
                     "comments": "panel_comments",
                     "google": "panel_google",
                     "tt_fonts": "panel_tt_fonts",
                     "style_basic": "panel_style_basic",
                     "style_size": "panel_style_size",
                     "style_outline": "panel_style_outline",
                     "style_fill": "panel_style_fill",
                     "style_shadow": "panel_style_shadow",
                     "hyphenation": "panel_hyphenation",
                     "bubblr_detect": "panel_bubblr_detect",
                     "bubblr_overlay": "panel_bubblr_overlay",
                     "setup_general": "panel_setup_general",
                     "layout_sizes": "panel_layout_sizes",
                     "shapr_panel": "panel_shapr",
                     "balloon": "panel_balloon",
                     "sfx_panel": "panel_sfx"}

    def _new_panel(self, pid, tab_id):
        """Create a PanelBox for panel `pid`, initially living in `tab_id`.
        Called during UI build; the caller adds the box to that tab's
        layout."""
        box = PanelBox(pid, self)
        self._panels[pid] = box
        self._panel_tab[pid] = tab_id
        self._panel_home[pid] = tab_id     # default tab, used by layout reset
        return box

    def _panel_title(self, pid):
        return self._tr(self._PANEL_TITLES.get(pid, pid))

    def _retranslate_panels(self):
        for pid, box in self._panels.items():
            box.set_title(self._panel_title(pid))

    def _fill_panel_menu(self, menu, pid):
        """Populate a panel's ⋮ menu: reorder within the tab (up/down), move
        to another tab, and detach into / reattach from a separate window."""
        if pid in self._detached:
            act = menu.addAction("⧉  " + self._tr("panel_reattach"))
            act.triggered.connect(
                lambda _c=False, p=pid: self._reattach_panel(p))
            return
        up = menu.addAction("▲  " + self._tr("panel_up"))
        up.triggered.connect(lambda _c=False, p=pid: self._reorder_panel(p, -1))
        down = menu.addAction("▼  " + self._tr("panel_down"))
        down.triggered.connect(
            lambda _c=False, p=pid: self._reorder_panel(p, 1))
        menu.addSeparator()
        cur = self._panel_tab.get(pid)
        for i in range(self.main_tabs.count()):
            tid = self.main_tabs.tabBar().tabData(i)
            if tid == cur or tid not in self._tab_layouts:
                continue
            act = menu.addAction(self._tr("panel_move_to").format(
                tab=self.main_tabs.tabText(i)))
            act.triggered.connect(
                lambda _c=False, t=tid, p=pid: self._move_panel_to_tab(p, t))
        menu.addSeparator()
        det = menu.addAction("⧉  " + self._tr("panel_detach"))
        det.triggered.connect(lambda _c=False, p=pid: self._detach_panel(p))

    def _panel_layout_index(self, lay, box):
        for i in range(lay.count()):
            if lay.itemAt(i).widget() is box:
                return i
        return None

    def _reorder_panel(self, pid, delta):
        """Move the panel up/down by one position within its current tab.
        Swaps past whatever widget is adjacent (panel or inline section)."""
        box = self._panels.get(pid)
        lay = self._tab_layouts.get(self._panel_tab.get(pid))
        if box is None or lay is None:
            return
        idx = self._panel_layout_index(lay, box)
        if idx is None:
            return
        lay.removeWidget(box)
        target = idx + delta
        # after removal the max insert index is lay.count(); clamp, but skip a
        # trailing stretch so the panel never ends up below it
        maxpos = lay.count()
        if maxpos > 0 and lay.itemAt(maxpos - 1).spacerItem() is not None:
            maxpos -= 1
        target = max(0, min(target, maxpos))
        lay.insertWidget(target, box)
        box.show()
        self._sync_gated_panels()
        self._save_panel_order()

    def _save_panel_order(self):
        """Persist the per-tab panel order (list of panel ids per tab), so
        reordering survives a restart."""
        order = {}
        for tid, lay in self._tab_layouts.items():
            ids = []
            for i in range(lay.count()):
                w = lay.itemAt(i).widget()
                if isinstance(w, PanelBox):
                    ids.append(w._pid)
            order[tid] = ids
        try:
            Krita.instance().writeSetting(
                "typer_kr", "panelOrder", json.dumps(order))
        except Exception:
            pass

    def _panels_in_tab(self, lay):
        """List of (pid, layout_index) for the PanelBoxes in a tab layout,
        in layout order."""
        out = []
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if isinstance(w, PanelBox):
                out.append((w._pid, i))
        return out

    def _normalize_setup_order_once(self):
        """One-time: make the General section sit above Layout & sizes in the
        Setup tab — that is the default (code) order, but a saved layout from
        earlier dragging may have them swapped. Fix that saved order once,
        leaving every other panel where the user put it, then never touch it
        again (the user can still reorder freely)."""
        app = Krita.instance()
        if app.readSetting("typer_kr", "setupOrderFix", "") == "done":
            return
        try:
            raw = app.readSetting("typer_kr", "panelOrder", "")
            order = json.loads(raw) if raw else {}
        except Exception:
            order = {}
        ids = order.get("setup")
        if (isinstance(ids, list) and "setup_general" in ids
                and "layout_sizes" in ids
                and ids.index("setup_general") > ids.index("layout_sizes")):
            ids.remove("setup_general")
            ids.insert(ids.index("layout_sizes"), "setup_general")
            order["setup"] = ids
            try:
                app.writeSetting("typer_kr", "panelOrder", json.dumps(order))
            except Exception:
                pass
        try:
            app.writeSetting("typer_kr", "setupOrderFix", "done")
        except Exception:
            pass

    def _apply_panel_order(self):
        """Restore the saved within-tab panel order. Panels are reordered
        RELATIVE to each other only; inline (non-panel) sections keep their
        place. Best effort — a bubble pass swaps out-of-order neighbours."""
        try:
            raw = Krita.instance().readSetting("typer_kr", "panelOrder", "")
            order = json.loads(raw) if raw else {}
        except Exception:
            return
        for tid, ids in order.items():
            lay = self._tab_layouts.get(tid)
            if lay is None:
                continue
            present = [pid for pid, _i in self._panels_in_tab(lay)]
            desired = [p for p in ids if p in present]
            desired += [p for p in present if p not in desired]
            for _ in range(len(desired) * len(desired) + 1):
                pos = dict(self._panels_in_tab(lay))
                swapped = False
                for a, b in zip(desired, desired[1:]):
                    if pos.get(a, -1) > pos.get(b, 1 << 30):
                        box = self._panels[a]
                        lay.removeWidget(box)
                        bi = self._panel_layout_index(
                            lay, self._panels[b])
                        lay.insertWidget(bi if bi is not None
                                         else lay.count(), box)
                        box.show()
                        swapped = True
                        break
                if not swapped:
                    break
        self._sync_gated_panels()

    def _move_panel_to_tab(self, pid, tab_id, save=True):
        box = self._panels.get(pid)
        if box is None or tab_id not in self._tab_layouts:
            return
        src = self._panel_tab.get(pid)
        if src in self._tab_layouts:
            self._tab_layouts[src].removeWidget(box)
        lay = self._tab_layouts[tab_id]
        # insert before a trailing stretch so the panel stays visible
        pos = lay.count()
        if pos > 0 and lay.itemAt(pos - 1).spacerItem() is not None:
            pos -= 1
        lay.insertWidget(pos, box)
        box.show()
        self._sync_gated_panels()
        self._panel_tab[pid] = tab_id
        if save:
            self._save_panel_tabs()
            self._save_panel_order()

    def _drop_panel_rel(self, dragged, target, after):
        """Drop `dragged` next to `target` (before it, or after it when
        `after`). Handles both within-tab reordering and moving into the
        target's tab. Called by PanelBox.dropEvent."""
        if dragged == target:
            return
        box = self._panels.get(dragged)
        tgt = self._panels.get(target)
        if box is None or tgt is None:
            return
        tab_id = self._panel_tab.get(target)
        lay = self._tab_layouts.get(tab_id)
        if lay is None:
            return
        src = self._panel_tab.get(dragged)
        if src in self._tab_layouts:
            self._tab_layouts[src].removeWidget(box)
        # recompute the target index after a possible same-tab removal
        ti = self._panel_layout_index(lay, tgt)
        if ti is None:
            pos = lay.count()
            if pos > 0 and lay.itemAt(pos - 1).spacerItem() is not None:
                pos -= 1
            lay.insertWidget(pos, box)
        else:
            lay.insertWidget(ti + (1 if after else 0), box)
        box.show()
        self._sync_gated_panels()
        self._panel_tab[dragged] = tab_id
        self._save_panel_tabs()
        self._save_panel_order()

    def _panel_drag_started(self):
        self._panel_dragging = True
        if getattr(self, "_drag_scroll_timer", None) is None:
            self._drag_scroll_timer = QTimer(self)
            self._drag_scroll_timer.setInterval(30)
            self._drag_scroll_timer.timeout.connect(self._drag_scroll_tick)
        self._drag_scroll_timer.start()

    def _panel_drag_finished(self):
        self._panel_dragging = False
        if getattr(self, "_drag_scroll_timer", None) is not None:
            self._drag_scroll_timer.stop()

    def _drag_scroll_tick(self):
        """While a panel is being dragged, auto-scroll the current tab's
        scroll area when the cursor nears its top/bottom edge, so a panel can
        be dropped past the visible region."""
        sa = self.main_tabs.currentWidget()
        if not isinstance(sa, QScrollArea):
            return
        vp = sa.viewport()
        pos = vp.mapFromGlobal(QCursor.pos())
        if not (0 <= pos.x() <= vp.width()):
            return                       # cursor is outside this list
        margin, step = 34, 26
        bar = sa.verticalScrollBar()
        if pos.y() < margin:
            bar.setValue(bar.value() - step)
        elif pos.y() > vp.height() - margin:
            bar.setValue(bar.value() + step)

    def _ensure_tabbar_dnd(self):
        """One-time: let the top tab bar accept panel drops (drop a panel on
        a tab to move it into that tab)."""
        if getattr(self, "_tabbar_dnd_ready", False):
            return
        bar = self.main_tabs.tabBar()
        bar.setAcceptDrops(True)
        bar.installEventFilter(self)
        self._tabbar_dnd_ready = True

    def eventFilter(self, obj, ev):
        """Handle panel drops onto the top tab bar (cross-tab move)."""
        bar = self.main_tabs.tabBar()
        if obj is bar:
            et = ev.type()
            if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if ev.mimeData().hasFormat(PANEL_MIME):
                    i = bar.tabAt(ev.pos())
                    if i >= 0:
                        # preview the destination tab so a following body drop
                        # lands where the user expects
                        self.main_tabs.setCurrentIndex(i)
                    ev.acceptProposedAction()
                    return True
                ev.ignore()
                return True
            if et == QEvent.Type.Drop:
                if ev.mimeData().hasFormat(PANEL_MIME):
                    pid = bytes(ev.mimeData().data(PANEL_MIME)).decode("utf-8")
                    i = bar.tabAt(ev.pos())
                    tid = bar.tabData(i) if i >= 0 else None
                    if tid in self._tab_layouts:
                        self._move_panel_to_tab(pid, tid)
                    ev.acceptProposedAction()
                    return True
                ev.ignore()
                return True
        return super(TyperDocker, self).eventFilter(obj, ev)

    def _set_panel_locked(self, pid, on):
        """Pin/unpin a panel (called by its padlock button) and persist it."""
        box = self._panels.get(pid)
        if box is None:
            return
        box.set_locked(on)
        self._save_panel_locked()

    def _save_panel_locked(self):
        locked = [pid for pid, box in self._panels.items()
                  if getattr(box, "_locked", False)]
        try:
            Krita.instance().writeSetting(
                "typer_kr", "panelLocked", json.dumps(locked))
        except Exception:
            pass

    def _load_panel_locked(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "panelLocked", "")
            return json.loads(raw) if raw else []
        except Exception:
            return []

    def _save_panel_heights(self):
        heights = {pid: box._user_height
                   for pid, box in self._panels.items()
                   if getattr(box, "_user_height", 0) > 0}
        try:
            Krita.instance().writeSetting(
                "typer_kr", "panelHeights", json.dumps(heights))
        except Exception:
            pass

    def _load_panel_heights(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "panelHeights", "")
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    # -- detach into a separate window (customizable layout, step 2c) -------

    def _free_detach_slot(self):
        """Lowest host-docker slot that exists and holds no panel yet."""
        used = {s for s in self._detached.values() if isinstance(s, int)}
        for s in range(MAX_DETACH_SLOTS):
            if s in _EXTRA_HOSTS and s not in used:
                return s
        return None

    def _detach_panel(self, pid, prefer=None):
        """Move a panel out of its tab into its own window: a pre-registered
        host docker when one is free, otherwise a floating tool dialog."""
        box = self._panels.get(pid)
        if box is None or pid in self._detached:
            return
        src = self._panel_tab.get(pid)
        if src in self._tab_layouts:
            self._tab_layouts[src].removeWidget(box)
        slot = prefer if (isinstance(prefer, int)
                          and prefer in _EXTRA_HOSTS
                          and prefer not in
                          {s for s in self._detached.values()
                           if isinstance(s, int)}) else None
        if slot is None and prefer != "float":
            slot = self._free_detach_slot()
        if slot is not None:
            host = _EXTRA_HOSTS[slot]
            host.show_placeholder(False)
            host.host_layout().insertWidget(0, box)
            host.setVisible(True)
            host.raise_()
            self._detached[pid] = slot
        else:
            dlg = QDialog(self, Qt.WindowType.Tool)
            dlg.setWindowTitle(self._panel_title(pid))
            dl = QVBoxLayout(dlg)
            dl.setContentsMargins(4, 4, 4, 4)
            dl.addWidget(box)
            dlg.resize(320, 420)
            dlg.finished.connect(
                lambda _r=0, p=pid: self._reattach_panel(p))
            self._float_dialogs[pid] = dlg
            self._detached[pid] = "float"
            dlg.show()
        box.show()
        self._sync_gated_panels()
        box.set_edit(True)   # keep the header (⋮ Reattach) reachable
        self._save_detached()

    def _reattach_panel(self, pid):
        """Bring a detached panel back into its home tab."""
        box = self._panels.get(pid)
        if box is None or pid not in self._detached:
            return
        slot = self._detached.pop(pid)
        if slot == "float":
            dlg = self._float_dialogs.pop(pid, None)
            box.setParent(None)
            if dlg is not None:
                dlg.deleteLater()
        else:
            host = _EXTRA_HOSTS.get(slot)
            if host is not None:
                host.host_layout().removeWidget(box)
                box.setParent(None)
                # show the placeholder again if the host is now empty
                if not any(s == slot for s in self._detached.values()):
                    host.show_placeholder(True)
        home = self._panel_home.get(pid, "type")
        self._panel_tab[pid] = None
        self._move_panel_to_tab(pid, home)
        box.set_edit(self.customize_chk.isChecked())
        self._save_detached()

    def _save_detached(self):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "panelDetached", json.dumps(self._detached))
        except Exception:
            pass

    def _load_detached(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "panelDetached", "")
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _apply_detached(self):
        """Re-detach panels that were detached last session. Runs deferred so
        the pre-registered host dockers are already constructed."""
        saved = self._load_detached()
        for pid, slot in saved.items():
            if pid == "balloon" and not self.enable_balloon_chk.isChecked():
                continue          # switched off: no empty window for it
            if pid in self._panels and pid not in self._detached:
                self._detach_panel(
                    pid, prefer=slot if isinstance(slot, int) else "float")
        for host in _EXTRA_HOSTS.values():
            host.set_hint(self._tr("detach_host_hint"))

    def _save_panel_tabs(self):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "panelTabs", json.dumps(self._panel_tab))
        except Exception:
            pass

    def _load_panel_tabs(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "panelTabs", "")
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _apply_panel_positions(self):
        """Restore saved panel->tab placements, and reflect the current
        customize-mode state on every panel header."""
        self._ensure_tabbar_dnd()
        saved = self._load_panel_tabs()
        for pid, tid in saved.items():
            if (pid in self._panels and tid in self._tab_layouts
                    and tid != self._panel_tab.get(pid)):
                self._move_panel_to_tab(pid, tid)
        locked = set(self._load_panel_locked())
        for pid, box in self._panels.items():
            box.set_locked(pid in locked)
        heights = self._load_panel_heights()
        for pid, box in self._panels.items():
            box.set_user_height(heights.get(pid, 0))
        edit = self.customize_chk.isChecked()
        for box in self._panels.values():
            box.set_edit(edit)

    def _tab_index_of(self, tid):
        bar = self.main_tabs.tabBar()
        for i in range(self.main_tabs.count()):
            if bar.tabData(i) == tid:
                return i
        return None

    def _on_enable_bubblr(self, on, save=True):
        """Show or hide the BubblR tab. The page widget is kept alive when
        hidden so its state (detected boxes, mapping) survives re-enabling."""
        idx = self._tab_index_of("bubblr")
        if on and idx is None:
            page = self._tab_pages.get("bubblr")
            if page is not None:
                i = self.main_tabs.addTab(page, self._tab_label("bubblr"))
                self.main_tabs.tabBar().setTabData(i, "bubblr")
        elif not on and idx is not None:
            self.main_tabs.removeTab(idx)
        if save:
            Krita.instance().writeSetting(
                "typer_kr", "enableBubblr", "true" if on else "false")

    def _on_enable_shapr(self, on, save=True):
        """Show or hide the TextShapR tab. The page widget is kept alive when
        hidden so its state survives re-enabling."""
        idx = self._tab_index_of("shapr")
        if on and idx is None:
            page = self._tab_pages.get("shapr")
            if page is not None:
                i = self.main_tabs.addTab(page, self._tab_label("shapr"))
                self.main_tabs.tabBar().setTabData(i, "shapr")
        elif not on and idx is not None:
            self.main_tabs.removeTab(idx)
        if save:
            Krita.instance().writeSetting(
                "typer_kr", "enableShapr", "true" if on else "false")

    def _on_enable_sfx(self, on, save=True):
        """Show or hide the SFX tab (kept alive when hidden)."""
        idx = self._tab_index_of("sfx")
        if on and idx is None:
            page = self._tab_pages.get("sfx")
            if page is not None:
                i = self.main_tabs.addTab(page, self._tab_label("sfx"))
                self.main_tabs.tabBar().setTabData(i, "sfx")
        elif not on and idx is not None:
            self.main_tabs.removeTab(idx)
        if save:
            Krita.instance().writeSetting(
                "typer_kr", "enableSfx", "true" if on else "false")

    def _on_enable_fonts(self, on, save=True):
        """Show or hide the Fonts (favourites) tab (kept alive when hidden)."""
        idx = self._tab_index_of("fonts")
        if on and idx is None:
            page = self._tab_pages.get("fonts")
            if page is not None:
                i = self.main_tabs.addTab(page, self._tab_label("fonts"))
                self.main_tabs.tabBar().setTabData(i, "fonts")
        elif not on and idx is not None:
            self.main_tabs.removeTab(idx)
        if save:
            Krita.instance().writeSetting(
                "typer_kr", "enableFonts", "true" if on else "false")

    def _sync_gated_panels(self):
        """Re-apply the switches that hide a whole panel. Every layout move
        ends in box.show(), so this has to run after those, too."""
        chk = getattr(self, "enable_balloon_chk", None)
        box = getattr(self, "_panels", {}).get("balloon")
        if chk is not None and box is not None:
            box.setVisible(chk.isChecked())

    def _on_enable_balloon(self, on, save=True):
        """Show or hide the Balloon panel (shape dropdown + tail + Insert
        balloon). The panel is only hidden, never destroyed, so its settings
        survive. A detached panel comes home first, so switching it off cannot
        leave an empty window behind."""
        if not on and "balloon" in getattr(self, "_detached", {}):
            self._reattach_panel("balloon")
        self._sync_gated_panels()
        if save:
            Krita.instance().writeSetting(
                "typer_kr", "enableBalloon", "true" if on else "false")

    def _on_enable_patterns(self, on, save=True):
        """Show/hide the experimental pattern-fill controls (outline pattern +
        soft outline in the outline popup, and the text-fill pattern panel)."""
        if hasattr(self, "_style_pattern_box"):
            self._style_pattern_box.setVisible(on)
        if hasattr(self, "_fill_panel"):
            self._fill_panel.setVisible(on)
        if save:
            Krita.instance().writeSetting(
                "typer_kr", "enablePatterns", "true" if on else "false")
        if hasattr(self, "preview"):
            self._update_text_preview()

    def _patterns_on(self):
        chk = getattr(self, "enable_patterns_chk", None)
        return bool(chk and chk.isChecked())

    def _on_enable_texttypes(self, on, save=True):
        """Show/hide the experimental 'kind of text' (text-type) panel."""
        if hasattr(self, "_texttype_panel"):
            self._texttype_panel.setVisible(on)
        if save:
            Krita.instance().writeSetting(
                "typer_kr", "enableTextTypes", "true" if on else "false")

    def on_layout_reset(self):
        """Back to the built-in tab names/order AND panel homes (unpin
        everything, drop custom panel order + placement)."""
        self._tab_names = {}
        self._save_tab_names()
        self._apply_tab_order([t for t, _nk in self._tab_defaults])
        self._on_tab_moved()
        self._retranslate_tabs()
        # panels: reattach any detached, unpin, clear saved state, send home
        for pid in list(self._detached.keys()):
            self._reattach_panel(pid)
        for box in self._panels.values():
            box.set_locked(False)
            box.set_user_height(0)
        for pid, home in self._panel_home.items():
            self._move_panel_to_tab(pid, home, save=False)
        try:
            app = Krita.instance()
            app.writeSetting("typer_kr", "panelOrder", "")
            app.writeSetting("typer_kr", "panelTabs", "")
            app.writeSetting("typer_kr", "panelLocked", "")
            app.writeSetting("typer_kr", "panelDetached", "")
            app.writeSetting("typer_kr", "panelHeights", "")
        except Exception:
            pass
        self._set_status(self._tr("layout_reset_done"))

    def _load_tab_names(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "tabNames", "")
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _save_tab_names(self):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "tabNames", json.dumps(self._tab_names))
        except Exception:
            pass

    def _repair_tab_order_once(self):
        """Clear a possibly-corrupted saved tab order exactly once (guarded by a
        flag), so users hit by the old desync bug land on the default order
        again. Tab names are left untouched — they were never corrupted."""
        try:
            app = Krita.instance()
            if app.readSetting("typer_kr", "tabOrderRepairV2", "") != "done":
                app.writeSetting("typer_kr", "tabOrder", "")
                app.writeSetting("typer_kr", "tabOrderRepairV2", "done")
        except Exception:
            pass

    def _load_tab_order(self):
        raw = Krita.instance().readSetting("typer_kr", "tabOrder", "")
        return [t for t in raw.split(",") if t] if raw else []

    def _load_ui_tab(self):
        try:
            return max(0, min(3, int(
                Krita.instance().readSetting("typer_kr", "uiTab", "0"))))
        except Exception:
            return 0

    def _save_ui_tab(self, index):
        try:
            Krita.instance().writeSetting("typer_kr", "uiTab", str(int(index)))
        except Exception:
            pass

    # -- layout / view (sizes + show/hide of docker parts) --

    _QWIDGET_MAX = 16777215  # Qt's QWIDGETSIZE_MAX (no height cap)

    def _view_defaults(self):
        return {
            "open": False,
            "preview_show": True, "preview_h": 120,
            "editor_show": True, "editor_h": 200,
            "table_show": True, "table_h": 240,
            "fonts_show": True, "fonts_h": 160,
            "bubblr_show": True, "bubblr_h": 280,
            "bmap_show": True, "bmap_h": 160,
        }

    def _load_view(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "view", "")
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_view(self):
        try:
            Krita.instance().writeSetting("typer_kr", "view", json.dumps({
                "open": self.view_toggle.isChecked(),
                "preview_show": self.v_preview_chk.isChecked(),
                "preview_h": self.v_preview_h.value(),
                "editor_show": self.v_editor_chk.isChecked(),
                "editor_h": self.v_editor_h.value(),
                "table_show": self.v_table_chk.isChecked(),
                "table_h": self.v_table_h.value(),
                "fonts_show": self.v_fonts_chk.isChecked(),
                "fonts_h": self.v_fonts_h.value(),
                "bubblr_show": self.v_bubblr_chk.isChecked(),
                "bubblr_h": self.v_bubblr_h.value(),
                "bmap_show": self.v_bmap_chk.isChecked(),
                "bmap_h": self.v_bmap_h.value(),
            }))
        except Exception:
            pass

    def _apply_view(self):
        """Apply the chosen visibility + heights to the docker widgets.

        Fixed-height parts (preview, script box, font list) are pinned to their
        value; the JP/EN table uses the value as a minimum and still expands to
        fill spare space. A widget's label is hidden together with it."""
        if not hasattr(self, "preview"):
            return

        def fixed(w, h):
            w.setMinimumHeight(h)
            w.setMaximumHeight(h)

        pv = self.v_preview_chk.isChecked()
        self.lbl_preview.setVisible(pv)
        self.preview.setVisible(pv)
        fixed(self.preview, self.v_preview_h.value())
        self.v_preview_h.setEnabled(pv)

        ev = self.v_editor_chk.isChecked()
        self.lbl_script.setVisible(ev)
        self.editor.setVisible(ev)
        fixed(self.editor, self.v_editor_h.value())
        self.v_editor_h.setEnabled(ev)

        tv = self.v_table_chk.isChecked()
        self.lbl_align.setVisible(tv)
        self.table.setVisible(tv)
        self.table.setMinimumHeight(self.v_table_h.value())
        self.table.setMaximumHeight(self._QWIDGET_MAX)
        self.v_table_h.setEnabled(tv)

        fv = self.v_fonts_chk.isChecked()
        self.lbl_font.setVisible(fv)
        self.font_picker.setVisible(fv)
        fixed(self.font_picker.list, self.v_fonts_h.value())
        self.v_fonts_h.setEnabled(fv)

        if hasattr(self, "bp_overlay"):
            # The overlay always FILLS its panel: a small floor so it can never
            # collapse to nothing, no upper cap, and it expands via its stretch
            # in the panel. Its size now follows the panel size (drag the
            # panel's bottom edge in Customize mode to resize it); the old
            # height slider no longer fights the layout.
            self.bp_overlay.setVisible(self.v_bubblr_chk.isChecked())
            self.bp_overlay.setMinimumHeight(140)
            self.bp_overlay.setMaximumHeight(self._QWIDGET_MAX)
            self.v_bubblr_h.setEnabled(False)
            self.v_bmap_h.setEnabled(False)

    def _on_view_toggle(self, checked):
        self.view_box.setVisible(checked)
        self._save_view()

    def _on_view_changed(self, *_a):
        self._apply_view()
        self._save_view()

    def _on_view_reset(self):
        d = self._view_defaults()
        widgets = (self.v_preview_chk, self.v_editor_chk, self.v_table_chk,
                   self.v_fonts_chk, self.v_preview_h, self.v_editor_h,
                   self.v_table_h, self.v_fonts_h,
                   self.v_bubblr_chk, self.v_bubblr_h,
                   self.v_bmap_chk, self.v_bmap_h)
        for w in widgets:
            w.blockSignals(True)
        self.v_preview_chk.setChecked(d["preview_show"])
        self.v_preview_h.setValue(d["preview_h"])
        self.v_editor_chk.setChecked(d["editor_show"])
        self.v_editor_h.setValue(d["editor_h"])
        self.v_table_chk.setChecked(d["table_show"])
        self.v_table_h.setValue(d["table_h"])
        self.v_fonts_chk.setChecked(d["fonts_show"])
        self.v_fonts_h.setValue(d["fonts_h"])
        self.v_bubblr_chk.setChecked(d["bubblr_show"])
        self.v_bubblr_h.setValue(d["bubblr_h"])
        self.v_bmap_chk.setChecked(d["bmap_show"])
        self.v_bmap_h.setValue(d["bmap_h"])
        for w in widgets:
            w.blockSignals(False)
        self._apply_view()
        self._save_view()

    # -- actions --

    def _load_recents(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "recentFonts", "")
            return json.loads(raw) if raw else []
        except Exception:
            return []

    def _save_recents(self):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "recentFonts",
                json.dumps(self.font_picker.recents()),
            )
        except Exception:
            pass

    def _load_settings(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "settings", "")
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _collect_settings(self):
        return {
            "size": self.size_spin.value(),
            "pad": self.pad_spin.value(),
            "spacing": self.spacing_spin.value(),
            "auto": self.auto_chk.isChecked(),
            "round": self.round_chk.isChecked(),
            "vertical": self.vertical_chk.isChecked(),
            "outline": self.outline_chk.isChecked(),
            "outline_w": self.outline_spin.value(),
            "outline2_w": self.outline2_spin.value(),
            "bold": self.bold_chk.isChecked(),
            "italic": self.italic_chk.isChecked(),
            "underline": self.underline_chk.isChecked(),
            "ligatures": self.liga_chk.isChecked(),
            "align": self.align_combo.currentData() or "center",
            "valign": self.valign_combo.currentData() or "middle",
            "case": self.case_combo.currentData() or "none",
            "tidy": self.tidy_chk.isChecked(),
            "comic": self.comic_chk.isChecked(),
            "crossbar_i": self.crossbar_chk.isChecked(),
            "color": self._color.name(),
            "outline_color": self._outline_color.name(),
            "outline2_color": self._outline2_color.name(),
            "shadow": self.shadow_chk.isChecked(),
            "shadow_x": self.shadow_x_spin.value(),
            "shadow_y": self.shadow_y_spin.value(),
            "shadow_color": self._shadow_color.name(),
            "hyphenate": self.hyph_chk.isChecked(),
            "hyph_lang": self.hyph_lang_combo.currentData() or "auto",
            # pattern-filled + soft (blurred) outline
            "outline_pattern_path": self._outline_pattern_path,
            "outline_pattern_krita": self._outline_pattern_krita_name,
            "outline_pattern_scale": self.outline_pattern_scale_spin.value(),
            "outline_pattern_target": (
                self.outline_pattern_target_combo.currentData() or "outline1"),
            "soft_outline": self.style_soft_chk.isChecked(),
            "soft_outline_pattern": self.style_soft_pattern_chk.isChecked(),
            "soft_outline_color": self._style_soft_color.name(),
            "soft_outline_w": self.style_soft_width_spin.value(),
            "soft_outline_blur": self.style_soft_blur_spin.value(),
            # the current selection-fill pattern (chosen, applied by hand)
            "fill_pattern_path": self._fill_pattern_path,
            "fill_pattern_krita": self._fill_pattern_krita_name,
            "fill_pattern_scale": self.fill_pattern_scale_spin.value(),
        }

    def _save_settings(self):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "settings", json.dumps(self._collect_settings()))
        except Exception:
            pass

    def _apply_settings(self, d):
        if not isinstance(d, dict) or not d:
            return
        try:
            if "size" in d:
                self.size_spin.setValue(int(d["size"]))
            if "pad" in d:
                self.pad_spin.setValue(int(d["pad"]))
            if "spacing" in d:
                self.spacing_spin.setValue(int(d["spacing"]))
            if "auto" in d:
                self.auto_chk.setChecked(bool(d["auto"]))
            if "round" in d:
                self.round_chk.setChecked(bool(d["round"]))
            if "vertical" in d:
                self.vertical_chk.setChecked(bool(d["vertical"]))
            if "outline" in d:
                self.outline_chk.setChecked(bool(d["outline"]))
            if "outline_w" in d:
                self.outline_spin.setValue(int(d["outline_w"]))
            if "outline2_w" in d:
                self.outline2_spin.setValue(int(d["outline2_w"]))
            if "bold" in d:
                self.bold_chk.setChecked(bool(d["bold"]))
            if "italic" in d:
                self.italic_chk.setChecked(bool(d["italic"]))
            if "underline" in d:
                self.underline_chk.setChecked(bool(d["underline"]))
            if "ligatures" in d:
                self.liga_chk.setChecked(bool(d["ligatures"]))
            if d.get("case") in ("none", "upper", "lower"):
                self.case_combo.setCurrentIndex(
                    {"none": 0, "upper": 1, "lower": 2}[d["case"]])
            elif "caps" in d:                       # old presets/settings
                self.case_combo.setCurrentIndex(1 if d["caps"] else 0)
            if "tidy" in d:
                self.tidy_chk.setChecked(bool(d["tidy"]))
            if "comic" in d:
                self.comic_chk.setChecked(bool(d["comic"]))
            if "crossbar_i" in d:
                self.crossbar_chk.setChecked(bool(d["crossbar_i"]))
            self.crossbar_chk.setEnabled(self.comic_chk.isChecked())
            if d.get("align") in ("left", "center", "right"):
                idx = {"left": 0, "center": 1, "right": 2}[d["align"]]
                self.align_combo.setCurrentIndex(idx)
            if d.get("valign") in ("top", "middle", "bottom"):
                vidx = {"top": 0, "middle": 1, "bottom": 2}[d["valign"]]
                self.valign_combo.setCurrentIndex(vidx)
            if "color" in d:
                self._color = QColor(d["color"])
                self._update_color_btn()
            if "outline_color" in d:
                self._outline_color = QColor(d["outline_color"])
                self._update_outline_btn()
            if "outline2_color" in d:
                self._outline2_color = QColor(d["outline2_color"])
                self._update_outline2_btn()
            # pattern-filled + soft (blurred) outline
            if "outline_pattern_path" in d or "outline_pattern_krita" in d:
                self._outline_pattern_path = d.get("outline_pattern_path", "") or ""
                self._outline_pattern_krita_name = \
                    d.get("outline_pattern_krita", "") or ""
                self._outline_pattern_img = None
                self._update_outline_pattern_btn()
            if "outline_pattern_scale" in d:
                self.outline_pattern_scale_spin.setValue(
                    int(d["outline_pattern_scale"]))
            if "outline_pattern_target" in d:
                _ti = self.outline_pattern_target_combo.findData(
                    d["outline_pattern_target"])
                if _ti >= 0:
                    self.outline_pattern_target_combo.setCurrentIndex(_ti)
            if "soft_outline_color" in d:
                self._style_soft_color = QColor(d["soft_outline_color"])
                self._update_style_soft_btn()
            if "soft_outline_w" in d:
                self.style_soft_width_spin.setValue(int(d["soft_outline_w"]))
            if "soft_outline_blur" in d:
                self.style_soft_blur_spin.setValue(int(d["soft_outline_blur"]))
            if "soft_outline_pattern" in d:
                self.style_soft_pattern_chk.setChecked(
                    bool(d["soft_outline_pattern"]))
            if "soft_outline" in d:
                self.style_soft_chk.setChecked(bool(d["soft_outline"]))
            self._update_soft_enabled()
            # the chosen selection-fill pattern
            if "fill_pattern_path" in d or "fill_pattern_krita" in d:
                self._fill_pattern_path = d.get("fill_pattern_path", "") or ""
                self._fill_pattern_krita_name = d.get("fill_pattern_krita", "") or ""
                self._fill_pattern_img = None
                self._update_fill_pattern_btn()
            if "fill_pattern_scale" in d:
                self.fill_pattern_scale_spin.setValue(int(d["fill_pattern_scale"]))
            if "shadow" in d:
                self.shadow_chk.setChecked(bool(d["shadow"]))
            if "shadow_x" in d:
                self.shadow_x_spin.setValue(int(d["shadow_x"]))
            if "shadow_y" in d:
                self.shadow_y_spin.setValue(int(d["shadow_y"]))
            if "shadow_color" in d:
                self._shadow_color = QColor(d["shadow_color"])
                self._update_shadow_btn()
            if "hyphenate" in d:
                self.hyph_chk.setChecked(bool(d["hyphenate"]))
            if d.get("hyph_lang") in ("auto", "en", "de"):
                hidx = {"auto": 0, "en": 1, "de": 2}[d["hyph_lang"]]
                self.hyph_lang_combo.setCurrentIndex(hidx)
        except Exception:
            pass

    # -- presets: three levels (Manga -> Character -> style preset) --

    _CFG_KEYS = ("size", "font", "color", "align", "valign", "case",
                 "caps", "outline", "shadow", "spacing", "pad")

    def _is_cfg(self, d):
        return isinstance(d, dict) and any(k in d for k in self._CFG_KEYS)

    def _normalize(self, data):
        """Convert any old format into the 3-level structure
        {Manga: {Character: {Name: config}}}.
        - flat     {Name: config}                       -> default Manga/Character
        - 2-level  {Group: {Name: config}}              -> Group as Manga, default Character
        - 3-level  {Manga: {Character: {Name: config}}} -> unchanged
        """
        if not isinstance(data, dict) or not data:
            return {}
        md = self._tr("group_default")
        cd = self._tr("char_default")
        if any(self._is_cfg(v) for v in data.values()):
            return {md: {cd: {str(n): c for n, c in data.items()
                              if isinstance(c, dict)}}}
        two = False
        for v in data.values():
            if isinstance(v, dict) and any(self._is_cfg(vv) for vv in v.values()):
                two = True
                break
        if two:
            out = {}
            for g, presets in data.items():
                if isinstance(presets, dict):
                    out[str(g)] = {cd: {str(n): c for n, c in presets.items()
                                        if isinstance(c, dict)}}
            return out
        out = {}
        for m, chars in data.items():
            if not isinstance(chars, dict):
                continue
            out[str(m)] = {}
            for ch, presets in chars.items():
                if isinstance(presets, dict):
                    out[str(m)][str(ch)] = {str(n): c for n, c in presets.items()
                                            if isinstance(c, dict)}
        return out

    def _load_groups(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "presets", "")
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
        return self._normalize(data)

    def _save_groups(self):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "presets", json.dumps(self._groups))
        except Exception:
            pass

    def _load_last_manga(self):
        """The manga/character worked on last session, so we reopen on it."""
        try:
            raw = Krita.instance().readSetting("typer_kr", "lastManga", "")
            d = json.loads(raw) if raw else {}
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save_last_manga(self):
        """Remember the current manga/character as the one worked on last."""
        try:
            Krita.instance().writeSetting(
                "typer_kr", "lastManga",
                json.dumps({"group": self._group, "char": self._char}))
        except Exception:
            pass

    def _ensure_levels(self):
        """Ensure at least one Manga + one Character, and keep the selection valid."""
        if not self._groups:
            self._groups = {self._tr("group_default"): {}}
        if self._group not in self._groups:
            self._group = sorted(self._groups.keys(), key=lambda s: s.lower())[0]
        chars = self._groups[self._group]
        if not chars:
            chars[self._tr("char_default")] = {}
        if self._char not in chars:
            self._char = sorted(chars.keys(), key=lambda s: s.lower())[0]

    def _cur_chars(self):
        return self._groups.get(self._group, {})

    # ---- Text types ----
    def _tt_overrides(self):
        """The user's font per text type, if they picked one."""
        try:
            raw = Krita.instance().readSetting("typer_kr", "ttFonts", "")
            d = json.loads(raw) if raw else {}
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save_tt_overrides(self, d):
        try:
            Krita.instance().writeSetting("typer_kr", "ttFonts",
                                          json.dumps(d or {}))
        except Exception:
            pass

    # --- user-defined text types (persist in kritarc, survive updates) -----
    def _load_custom_types(self):
        """The user's own text types: [{id, label, font}, ...]. Empty on error."""
        try:
            raw = Krita.instance().readSetting("typer_kr", "ttCustom", "")
            d = json.loads(raw) if raw else []
            return d if isinstance(d, list) else []
        except Exception:
            return []

    def _save_custom_types(self, types):
        try:
            Krita.instance().writeSetting("typer_kr", "ttCustom",
                                          json.dumps(types or []))
        except Exception:
            pass

    def _tt_label(self, tid):
        """Display name for a text type: the stored label for a custom type,
        else the built-in's translated name."""
        return TT.label(tid) or self._tr("tt_" + tid)

    def _rebuild_text_type_combo(self):
        """Repopulate the Style-tab text-type combo from the current catalogue
        (built-ins + custom), keeping the current selection if it still exists."""
        combo = self.text_type_combo
        prev = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self._tr("tt_none"), "")
        for tid in TT.ids():
            combo.addItem(self._tt_label(tid), tid)
        idx = combo.findData(prev)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _add_custom_type(self, label, font, style=None):
        """Create a user text type, persist it, and make it appear everywhere at
        once. Returns its new id (or None if the name was empty).

        `style` is optional: pass a captured style dict (from _collect_preset,
        minus its font) to snapshot the current look; omit it for the neutral
        default look."""
        label = (label or "").strip()
        if not label:
            return None
        types = self._load_custom_types()
        entry = {"label": label, "font": (font or "").strip()}
        if isinstance(style, dict) and style:
            entry["style"] = style
        types.append(entry)
        # register_custom assigns the final (unique) ids; store those back so the
        # id stays stable across restarts and the font override can key on it.
        registered = TT.register_custom(types)
        self._save_custom_types(registered)
        self._rebuild_text_type_combo()
        return registered[-1]["id"] if registered else None

    def _remove_custom_type(self, tid):
        """Delete a user text type (and any font override keyed on it)."""
        types = [e for e in self._load_custom_types() if e.get("id") != tid]
        registered = TT.register_custom(types)
        self._save_custom_types(registered)
        ov = self._tt_overrides()
        if tid in ov:
            ov.pop(tid, None)
            self._save_tt_overrides(ov)
        self._rebuild_text_type_combo()

    def on_tt_fonts(self):
        dlg = TextTypeFontsDialog(self.widget(), self._tr,
                                  self._installed_families(),
                                  self._tt_overrides(), self)
        dlg.exec()
        self._save_tt_overrides(dlg.overrides())
        self._on_text_type_changed()          # the stand-in hint may be stale now

    def _installed_families(self):
        try:
            return list(font_families())
        except Exception:
            return []

    def _on_text_type_changed(self):
        """Show which face the chosen kind of text really wants."""
        tid = self.text_type_combo.currentData() or ""
        if not tid:
            self.text_type_hint.setText("")
            return
        want = TT.missing_font(tid, self._installed_families(),
                               self._tt_overrides())
        self.text_type_hint.setText(
            self._tr("tt_missing_font").format(font=want) if want else "")

    def on_text_type_apply(self):
        """Apply a whole kind of text (font + style) in one step."""
        tid = self.text_type_combo.currentData() or ""
        if not tid:
            self._set_status(self._tr("st_tt_pick"), error=True)
            return
        style = TT.style_for(tid, self._installed_families(),
                             self._tt_overrides())
        if not style:
            return
        self._apply_preset(style)
        self._set_status(self._tr("st_tt_applied").format(
            name=self._tt_label(tid)))

    def _on_g_client_edited(self):
        try:
            Krita.instance().writeSetting(
                "typer_kr", "gClientId", self.g_client_edit.text().strip())
        except Exception:
            pass

    def _cur_presets(self):
        return self._cur_chars().get(self._char, {})

    def _collect_preset(self):
        p = self._collect_settings()
        p["font"] = self.font_picker.currentFamily() or ""
        return p

    def _apply_preset(self, p):
        if not isinstance(p, dict):
            return
        self._apply_settings(p)
        fam = p.get("font")
        if fam:
            self.font_picker.setCurrentFamily(fam)
        self._on_outline_toggle()
        self._on_shadow_toggle()
        self._on_auto_toggle()

    # ---- Manga level ----
    def _refresh_groups_combo(self, select=None):
        self._ensure_levels()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        for g in sorted(self._groups.keys(), key=lambda s: s.lower()):
            self.group_combo.addItem(g, g)
        target = select or self._group
        idx = self.group_combo.findData(target)
        if idx >= 0:
            self.group_combo.setCurrentIndex(idx)
            self._group = target
        self.group_combo.blockSignals(False)

    def _on_group_selected(self):
        g = self.group_combo.currentData()
        if g is not None and g in self._groups:
            self._group = g
            self._char = ""
            self._refresh_chars_combo()
            self._refresh_presets_combo()
            self._save_last_manga()

    def on_group_new(self):
        name, ok = QInputDialog.getText(
            self.widget(), self._tr("group_new_dlg"),
            self._tr("group_name_prompt"))
        if not ok:
            return
        name = name.strip()
        if not name:
            self._set_status(self._tr("st_group_name_empty"), error=True)
            return
        if name not in self._groups:
            self._groups[name] = {self._tr("char_default"): {}}
        self._group = name
        self._char = ""
        self._save_groups()
        self._save_last_manga()
        self._refresh_groups_combo(select=name)
        self._refresh_chars_combo()
        self._refresh_presets_combo()
        self._set_status(self._tr("st_group_saved").format(name=name))

    def on_group_delete(self):
        g = self.group_combo.currentData()
        if g is None or g not in self._groups:
            self._set_status(self._tr("st_group_none"), error=True)
            return
        del self._groups[g]
        if self._main_chars_map.pop(g, None) is not None:
            self._save_main_chars()
        self._char = ""
        self._ensure_levels()
        self._save_groups()
        self._refresh_groups_combo()
        self._refresh_chars_combo()
        self._refresh_presets_combo()
        self._set_status(self._tr("st_group_deleted").format(name=g))

    # ---- Character level ----
    def _refresh_chars_combo(self, select=None):
        """Rebuild the character dropdown: main characters on top (starred),
        a separator, then the rest. Item data stays the plain name, so
        everything that looks a character up is unaffected."""
        self._ensure_levels()
        self.char_combo.blockSignals(True)
        self.char_combo.clear()
        main, rest = LP.sort_characters(self._cur_chars().keys(),
                                        self._main_chars())
        for ch in main:
            self.char_combo.addItem("★ " + ch, ch)
        if main and rest:
            self.char_combo.insertSeparator(self.char_combo.count())
        for ch in rest:
            self.char_combo.addItem(ch, ch)
        target = select or self._char
        idx = self.char_combo.findData(target)
        if idx >= 0:
            self.char_combo.setCurrentIndex(idx)
            self._char = target
        self.char_combo.blockSignals(False)

    def _on_char_selected(self):
        ch = self.char_combo.currentData()
        if ch is not None and ch in self._cur_chars():
            self._char = ch
            self._apply_default_preset()   # auto-select the default style
            self._save_last_manga()

    def on_char_new(self):
        name, ok = QInputDialog.getText(
            self.widget(), self._tr("char_new_dlg"),
            self._tr("char_name_prompt"))
        if not ok:
            return
        name = name.strip()
        if not name:
            self._set_status(self._tr("st_char_name_empty"), error=True)
            return
        self._ensure_levels()
        if name not in self._groups[self._group]:
            self._groups[self._group][name] = {}
        self._char = name
        self._save_groups()
        self._save_last_manga()
        self._refresh_chars_combo(select=name)
        self._refresh_presets_combo()
        self._set_status(self._tr("st_char_saved").format(name=name))

    def on_char_delete(self):
        ch = self.char_combo.currentData()
        if ch is None or ch not in self._cur_chars():
            self._set_status(self._tr("st_char_none"), error=True)
            return
        del self._groups[self._group][ch]
        self._forget_main_char(ch)
        self._char = ""
        self._ensure_levels()
        self._save_groups()
        self._refresh_chars_combo()
        self._refresh_presets_combo()
        self._set_status(self._tr("st_char_deleted").format(name=ch))

    # ---- style preset level ----
    def _refresh_presets_combo(self, select=None):
        """Rebuild the preset dropdown. Character mode lists the current
        character's presets (item data = name); simple mode lists every preset
        of the manga (item data = (character, name), duplicate names get a
        '(Character)' suffix)."""
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem(self._tr("preset_none"), None)
        if self._by_char():
            for name in sorted(self._cur_presets().keys(),
                               key=lambda s: s.lower()):
                self.preset_combo.addItem(name, name)
        else:
            # simple mode lists every character's presets in one dropdown, so
            # the main characters' styles go to the top of it
            mains = self._main_chars()
            prev_main = None
            for label, ch, name in LP.flatten_presets(self._cur_chars(), mains):
                is_main = self._is_main_char(ch)
                if prev_main and not is_main:
                    self.preset_combo.insertSeparator(self.preset_combo.count())
                prev_main = is_main
                self.preset_combo.addItem("★ " + label if is_main else label,
                                          (ch, name))
        if select is not None:
            # manual match: findData compares QVariants, which is unreliable
            # for python tuples
            for i in range(self.preset_combo.count()):
                if self.preset_combo.itemData(i) == select:
                    self.preset_combo.setCurrentIndex(i)
                    break
        self.preset_combo.blockSignals(False)

    def _on_preset_selected(self):
        ch, name = self._preset_ref(self.preset_combo.currentData())
        presets = self._cur_chars().get(ch, {})
        if name and name in presets:
            self._apply_preset(presets[name])
            self._record_preset_usage(self._group, ch, name)
            self._save_last_manga()
            self._set_status(self._tr("st_preset_applied").format(name=name))

    def on_preset_save(self):
        _ch, current = self._preset_ref(self.preset_combo.currentData())
        name, ok = QInputDialog.getText(
            self.widget(), self._tr("preset_name_dlg"),
            self._tr("preset_name_prompt"), text=current)
        if not ok:
            return
        name = name.strip()
        if not name:
            self._set_status(self._tr("st_preset_name_empty"), error=True)
            return
        self._ensure_levels()
        # simple mode saves into the manga's default bucket character
        target = self._char if self._by_char() else self._bucket_char()
        self._groups[self._group].setdefault(target, {})[name] = \
            self._collect_preset()
        self._save_groups()
        self._refresh_presets_combo(
            select=name if self._by_char() else (target, name))
        self._set_status(self._tr("st_preset_saved_in").format(
            name=name, char=target))

    def on_preset_delete(self):
        ch, name = self._preset_ref(self.preset_combo.currentData())
        presets = self._cur_chars().get(ch, {})
        if not name or name not in presets:
            self._set_status(self._tr("st_preset_none"), error=True)
            return
        del self._groups[self._group][ch][name]
        self._save_groups()
        self._refresh_presets_combo()
        self._set_status(self._tr("st_preset_deleted").format(name=name))

    def on_preset_export(self):
        # ask what to export as: the self-contained bundle (presets + the fonts
        # they name, so the other machine has nothing left to install), the bare
        # JSON, or a readable Excel table for sharing / spreadsheet editing
        fmts = [self._tr("preset_fmt_bundle"), self._tr("preset_fmt_json"),
                self._tr("preset_fmt_xlsx")]
        choice, ok = QInputDialog.getItem(
            self.widget(), self._tr("preset_export_fmt_title"),
            self._tr("preset_export_fmt_prompt"), fmts, 0, False)
        if not ok:
            return
        if choice == fmts[0]:
            manga = self._group or ""
            default = "TypeR presets (%s).zip" % manga if manga \
                else "typer_presets.zip"
            path, _ = QFileDialog.getSaveFileName(
                self.widget(), self._tr("preset_file_save"),
                default, self._tr("preset_bundle_filter"))
            if not path:
                return
            if not path.lower().endswith(".zip"):
                path += ".zip"
            self._export_presets_bundle(path)
            return
        if choice == fmts[2]:
            manga = self._group or ""
            default = "Fonts (%s).xlsx" % manga if manga else "Fonts.xlsx"
            path, _ = QFileDialog.getSaveFileName(
                self.widget(), self._tr("preset_file_save"),
                default, self._tr("xlsx_filter"))
            if not path:
                return
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            self._export_presets_xlsx(path)
            return
        path, _ = QFileDialog.getSaveFileName(
            self.widget(), self._tr("preset_file_save"),
            "typer_presets.json", self._tr("preset_filter"))
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._groups, fh, ensure_ascii=False, indent=2)
            n = sum(len(pr) for chars in self._groups.values()
                    for pr in chars.values())
            self._set_status(self._tr("st_preset_exported").format(n=n))
        except Exception as exc:
            self._set_status(self._tr("st_read_fail").format(exc=exc), error=True)

    def preset_font_names(self):
        """Every font family named by a saved preset, once each, order kept."""
        return self._dedup_ci(self._main_preset_fonts())

    def _export_presets_bundle(self, path):
        """Write presets.json PLUS every font file the presets name into a .zip.

        Presets are useless without their fonts — importing them on another
        machine used to mean hunting down and installing most of the families by
        hand. The bundle carries every cut of every family found here, and the
        import side installs them.
        """
        from . import fontfiles as _FF
        fams = self.preset_font_names()
        app = QApplication.instance()
        if app is not None:
            app.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            files, missing = _FF.collect_font_files(
                fams, parent=self.widget(), label=self._tr("font_scan"))
        except Exception:                               # noqa: BLE001
            files, missing = {}, list(fams)
        finally:
            if app is not None:
                app.restoreOverrideCursor()
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("presets.json",
                           json.dumps(self._groups, ensure_ascii=False, indent=2))
                n_files = _FF.add_fonts_to_zip(z, files)
        except Exception as exc:                        # noqa: BLE001
            self._set_status(self._tr("st_read_fail").format(exc=exc), error=True)
            return
        n = sum(len(pr) for chars in self._groups.values()
                for pr in chars.values())
        self._set_status(self._tr("st_preset_exported_bundle").format(
            n=n, fonts=n_files, missing=len(missing)))
        if missing:
            self._warn_preset_fonts_missing(missing)

    def _warn_preset_fonts_missing(self, missing):
        """Say which preset fonts couldn't be bundled — they aren't installed
        here, so the other machine will still be short of them."""
        QMessageBox.information(
            self.widget(), self._tr("fav_missing_title"),
            self._tr("fav_missing_intro") + "\n\n• " + "\n• ".join(missing[:40])
            + ("\n…" if len(missing) > 40 else ""))

    def _export_presets_xlsx(self, path):
        """Write a fonts matrix for the CURRENT manga only (characters as rows,
        purposes as columns, fonts in the cells) — the style of the user's own
        sheet. Dependency-free writer; character column + header row frozen."""
        chars = self._groups.get(self._group, {})
        headers, rows = presets_to_table(
            chars, self._tr, default_char=self._tr("xls_default_char"))
        sheet = self._group or self._tr("xls_sheet_presets")
        widths = [24] + [20] * (len(headers) - 1)
        try:
            XLSX.write_xlsx(path, sheet, headers, rows, widths=widths,
                            freeze_rows=1, freeze_cols=1)
            self._set_status(
                self._tr("st_preset_exported_xlsx").format(n=len(rows)))
        except Exception as exc:
            self._set_status(self._tr("st_read_fail").format(exc=exc), error=True)

    def on_preset_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self.widget(), self._tr("preset_file_open"),
            "", self._tr("preset_open_filter"))
        if not path:
            return
        fonts = []
        try:
            if zipfile.is_zipfile(path):
                data, fonts = self._read_preset_bundle(path)
            else:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("not a preset object")
        except Exception:
            self._set_status(self._tr("st_preset_import_fail"), error=True)
            return
        incoming = self._normalize(data)
        count = 0
        for m, chars in incoming.items():
            dst_m = self._groups.setdefault(str(m), {})
            for ch, presets in chars.items():
                dst_c = dst_m.setdefault(str(ch), {})
                for name, cfg in presets.items():
                    dst_c[str(name)] = cfg
                    count += 1
        self._save_groups()
        self._refresh_groups_combo()
        self._refresh_chars_combo()
        self._refresh_presets_combo()
        if fonts:
            res = self._install_fonts_and_refresh(fonts) or {}
            self._set_status(self._tr("st_preset_imported_bundle").format(
                n=count, inst=len(res.get("installed", [])),
                skip=len(res.get("skipped", [])),
                fail=len(res.get("failed", []))))
        else:
            self._set_status(self._tr("st_preset_imported").format(n=count))

    def _read_preset_bundle(self, path):
        """(preset data, [extracted font file paths]) from an exported .zip."""
        data = {}
        fonts = []
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            member = "presets.json" if "presets.json" in names else next(
                (n for n in names if n.lower().endswith(".json")), "")
            if member:
                data = json.loads(z.read(member).decode("utf-8"))
            wanted = [n for n in names
                      if n.startswith("fonts/") and not n.endswith("/")]
            if wanted:
                tmp = tempfile.mkdtemp(prefix="typer_presets_fonts_")
                for nm in wanted:
                    dest = os.path.join(tmp, os.path.basename(nm))
                    with open(dest, "wb") as fh:
                        fh.write(z.read(nm))
                    fonts.append(dest)
        return data, fonts

    def on_preset_import_excel(self):
        """Import a character/style font-guide sheet (.xlsx) as presets: a row
        per character, a column per style (a cell = the font for that style).
        Each non-empty cell becomes a preset named after the style column, under
        the character, in a manga named after the sheet's folder."""
        path, _ = QFileDialog.getOpenFileName(
            self.widget(), self._tr("preset_excel_open"), "",
            self._tr("preset_excel_filter"))
        if not path:
            return
        try:
            rows = _read_xlsx_grid(path)
        except Exception:
            self._set_status(self._tr("st_preset_import_fail"), error=True)
            return
        # find the header row: the one carrying a "Character" column
        hdr_i = char_col = -1
        for i, row in enumerate(rows):
            for j, cell in enumerate(row):
                if cell.strip().lower() == "character":
                    hdr_i, char_col = i, j
                    break
            if hdr_i >= 0:
                break
        if hdr_i < 0:
            self._set_status(self._tr("st_preset_excel_no_header"), error=True)
            return
        header = rows[hdr_i]
        style_cols = [(j, header[j].strip())
                      for j in range(char_col + 1, len(header))
                      if header[j].strip()]
        # the manga is named after the sheet's folder ("…/<Manga>/Fonts.xlsx"),
        # else the file itself
        manga = (os.path.basename(os.path.dirname(path))
                 or os.path.splitext(os.path.basename(path))[0])
        dst_m = self._groups.setdefault(manga, {})
        n_presets = n_chars = 0
        for row in rows[hdr_i + 1:]:
            if char_col >= len(row):
                continue
            ch = row[char_col].strip()
            if not ch:
                continue
            dst_c = dst_m.setdefault(ch, {})
            made = 0
            for j, style in style_cols:
                font = row[j].strip() if j < len(row) else ""
                if font:
                    dst_c[style] = {"font": font}
                    made += 1
            if made:
                n_chars += 1
                n_presets += made
            elif not dst_c:
                dst_m.pop(ch, None)          # character with no fonts: drop it
        if n_presets == 0:
            self._set_status(self._tr("st_preset_excel_empty"), error=True)
            return
        self._group, self._char = manga, ""
        self._save_groups()
        self._save_last_manga()
        self._refresh_groups_combo(select=manga)
        self._refresh_chars_combo()
        self._refresh_presets_combo()
        self._set_status(self._tr("st_preset_excel_imported").format(
            n=n_presets, c=n_chars, manga=manga))

    # ==================================================================
    #  Script tabs (several loaded scripts at once)
    # ==================================================================
    def _session_index(self, sid):
        """Index of the session with id `sid` in self._sessions, or -1."""
        for i, s in enumerate(self._sessions):
            if s["id"] == sid:
                return i
        return -1

    def _tab_index(self, sid):
        """Index of the tab carrying session id `sid`, or -1."""
        for i in range(self.script_tabs.count()):
            if self.script_tabs.tabData(i) == sid:
                return i
        return -1

    def _snapshot_active(self):
        """Save the live editor text + parse state into the active session."""
        i = self._session_index(self._active_sid)
        if i < 0:
            return
        s = self._sessions[i]
        s["text"] = self.editor.toPlainText()
        s["pairs"] = self._pairs
        s["pair_pages"] = self._pair_pages
        s["pages"] = self._pages
        s["index"] = self._index
        s["done"] = self._done
        s["path"] = self._script_path
        s["comments"] = self._script_comments

    def _restore_by_sid(self, sid):
        """Load the session with id `sid` into the live view (no re-parsing)."""
        i = self._session_index(sid)
        if i < 0:
            return
        s = self._sessions[i]
        self._active_sid = sid
        self._script_path = s["path"]
        self._pairs = s["pairs"]
        self._pair_pages = s["pair_pages"]
        self._script_comments = s.get("comments") or []
        self._pages = s["pages"]
        self._index = s["index"]
        self._done = s["done"]
        self.editor.blockSignals(True)
        self.editor.setPlainText(s["text"])
        self.editor.blockSignals(False)
        self._populate_table()
        self._repaint_done()
        self._refresh_pages_combo()
        self._refresh_view()

    def _add_session(self, name, path, text, do_analyze):
        """Create a new session + tab and make it active."""
        self._snapshot_active()
        sid = self._next_sid
        self._next_sid += 1
        self._sessions.append({
            "id": sid, "name": name, "path": path, "text": text,
            "pairs": [], "pair_pages": [], "pages": [], "index": 0, "done": set(),
            "comments": [],
        })
        self._active_sid = sid
        self._script_path = path
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        if do_analyze:
            self.analyze()                 # fills the live state from the text
        else:
            self._pairs, self._pair_pages, self._pages = [], [], []
            self._index = 0
            self._done = set()
            self._populate_table()
            self._refresh_pages_combo()
            self._refresh_view()
        self._snapshot_active()            # store the parsed state in the session
        self.script_tabs.blockSignals(True)
        idx = self.script_tabs.addTab(name)
        self.script_tabs.setTabData(idx, sid)
        self.script_tabs.setTabToolTip(idx, path or name)
        self.script_tabs.setCurrentIndex(idx)
        self.script_tabs.blockSignals(False)
        self._schedule_session_save()

    def _new_untitled(self):
        """Add an empty, unnamed script tab."""
        name = LP.unique_untitled([s["name"] for s in self._sessions],
                                  base=self._tr("tab_untitled"))
        self._add_session(name, "", "", do_analyze=False)

    def _init_first_session(self):
        """At startup: reopen the scripts that were open last time (with their
        progress); if there were none, start with one empty tab."""
        if self._sessions:
            return
        if self._restore_sessions():
            return
        self._new_untitled()

    # --- persist the open script tabs (order + text + progress) --------------
    def _schedule_session_save(self):
        """Debounced save so rapid edits/navigation coalesce into one write."""
        t = getattr(self, "_sessions_save_timer", None)
        if t is None:
            t = QTimer(self.widget())
            t.setSingleShot(True)
            t.setInterval(800)
            t.timeout.connect(self._save_sessions)
            self._sessions_save_timer = t
        t.start()

    def _save_sessions(self):
        """Write every open tab (in tab-bar order) — its text, parsed units,
        current line and green 'done' marks — so a restart reopens them exactly.
        Empty untitled tabs are skipped. Never raises."""
        try:
            self._snapshot_active()
            out = {"active": self._active_sid, "sessions": []}
            for i in range(self.script_tabs.count()):
                sid = self.script_tabs.tabData(i)
                j = self._session_index(sid) if sid is not None else -1
                if j < 0:
                    continue
                s = self._sessions[j]
                if not (s.get("text") or "").strip() and not s.get("pairs"):
                    continue                       # nothing worth remembering
                out["sessions"].append({
                    "sid": sid,
                    "name": s.get("name") or "",
                    "path": s.get("path") or "",
                    "text": s.get("text") or "",
                    "pairs": [list(p) for p in s.get("pairs", [])],
                    "pair_pages": list(s.get("pair_pages", [])),
                    "pages": list(s.get("pages", [])),
                    "index": int(s.get("index", 0)),
                    "done": sorted(int(x) for x in s.get("done", set())),
                })
            blob = json.dumps(out)
            if len(blob) > 4_000_000:              # keep kritarc sane
                return
            Krita.instance().writeSetting("typer_kr", "sessions", blob)
        except Exception:
            pass

    def _restore_sessions(self):
        """Rebuild the saved script tabs (no file re-read, so progress is kept).
        Returns True if at least one tab was restored."""
        try:
            raw = Krita.instance().readSetting("typer_kr", "sessions", "")
            data = json.loads(raw) if raw else {}
        except Exception:
            return False
        saved = data.get("sessions") if isinstance(data, dict) else None
        if not saved:
            return False
        want_active = data.get("active")
        active_tab = 0
        self.script_tabs.blockSignals(True)
        for sd in saved:
            sid = self._next_sid
            self._next_sid += 1
            sess = {
                "id": sid,
                "name": sd.get("name") or self._tr("tab_untitled"),
                "path": sd.get("path") or "",
                "text": sd.get("text") or "",
                "pairs": [tuple(p) if isinstance(p, list) else p
                          for p in sd.get("pairs", [])],
                "pair_pages": list(sd.get("pair_pages", [])),
                "pages": list(sd.get("pages", [])),
                "index": int(sd.get("index", 0)),
                "done": set(int(x) for x in sd.get("done", [])),
                "comments": [],
            }
            self._sessions.append(sess)
            idx = self.script_tabs.addTab(sess["name"])
            self.script_tabs.setTabData(idx, sid)
            self.script_tabs.setTabToolTip(idx, sess["path"] or sess["name"])
            if sd.get("sid") == want_active:
                active_tab = idx
        self.script_tabs.setCurrentIndex(active_tab)
        self.script_tabs.blockSignals(False)
        self._active_sid = None                    # force a full restore
        cur = self.script_tabs.tabData(active_tab)
        if cur is not None:
            self._restore_by_sid(cur)
        return True

    def _on_tab_changed(self, tab_i):
        if tab_i < 0:
            return
        sid = self.script_tabs.tabData(tab_i)
        if sid is None or sid == self._active_sid:
            return
        self._snapshot_active()
        self._restore_by_sid(sid)
        self._schedule_session_save()

    def _close_tab(self, tab_i):
        sid = self.script_tabs.tabData(tab_i)
        if sid is None:
            return
        self._snapshot_active()
        i = self._session_index(sid)
        if i >= 0:
            del self._sessions[i]
        self.script_tabs.blockSignals(True)
        self.script_tabs.removeTab(tab_i)
        self.script_tabs.blockSignals(False)
        if not self._sessions:
            self._active_sid = None
            self._new_untitled()           # never leave zero tabs
            self._schedule_session_save()
            return
        # activate whatever tab Qt now shows as current
        cur = self.script_tabs.currentIndex()
        self._active_sid = None            # force a full restore
        self._restore_by_sid(self.script_tabs.tabData(cur))
        self._schedule_session_save()

    def _rename_tab(self, tab_i):
        if tab_i < 0:
            return
        sid = self.script_tabs.tabData(tab_i)
        i = self._session_index(sid)
        if i < 0:
            return
        name, ok = QInputDialog.getText(
            self.widget(), self._tr("tab_rename_dlg"),
            self._tr("tab_rename_prompt"), text=self._sessions[i]["name"])
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        self._sessions[i]["name"] = name
        self.script_tabs.setTabText(tab_i, name)
        self._schedule_session_save()

    def on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self.widget(),
            self._tr("file_dlg"),
            "",
            self._tr("file_filter"),
        )
        if not path:
            return
        # already open? -> just switch to its tab instead of opening twice
        existing = LP.find_session_by_path(self._sessions, path)
        if existing >= 0:
            self.script_tabs.setCurrentIndex(
                self._tab_index(self._sessions[existing]["id"]))
            self._set_status(self._tr("st_already_open").format(
                name=os.path.basename(path)))
            return
        if GD.is_gdoc(path):
            self._load_gdoc(path)
            return
        try:
            text = read_script(path)
        except FileNotFoundError:
            self._set_status(self._tr("st_not_found"), error=True)
            return
        except zipfile.BadZipFile:
            self._set_status(self._tr("st_bad_zip"), error=True)
            return
        except KeyError:
            self._set_status(self._tr("st_no_content"), error=True)
            return
        except OldDocError as exc:
            self._set_status(self._tr("st_old_doc").format(fmt=exc.fmt),
                             error=True)
            return
        except Exception as exc:
            self._set_status(self._tr("st_read_fail").format(exc=exc), error=True)
            return

        self._script_comments = CM.from_docx(path)
        self._add_session(LP.default_tab_label(path), path, text, do_analyze=True)
        if self._script_comments:
            self._set_status(self._tr("st_loaded_c").format(
                name=os.path.basename(path), n=len(self._pairs),
                c=len(self._script_comments)))
        else:
            self._set_status(self._tr("st_loaded").format(
                name=os.path.basename(path), n=len(self._pairs)))

    # ---- Google Docs ----
    def _g_client_id(self):
        try:
            return Krita.instance().readSetting("typer_kr", "gClientId", "").strip()
        except Exception:
            return ""

    def _g_token(self):
        try:
            raw = Krita.instance().readSetting("typer_kr", "gToken", "")
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _g_store_token(self, tok):
        try:
            Krita.instance().writeSetting("typer_kr", "gToken",
                                          json.dumps(tok or {}))
        except Exception:
            pass

    def on_g_sign_in(self):
        """Run the browser sign-in. The client ID stays the user's own."""
        cid = self._g_client_id()
        if not cid:
            self._set_status(self._tr("st_g_no_client"), error=True)
            return
        self._set_status(self._tr("st_g_wait"))
        try:
            tok = GA.sign_in(cid)
        except GA.AuthError as e:
            self._set_status(str(e), error=True)
            return
        self._g_store_token(tok)
        self._refresh_g_status()
        self._set_status(self._tr("st_g_ok"))

    def on_g_sign_out(self):
        self._g_store_token({})
        self._refresh_g_status()
        self._set_status(self._tr("st_g_out"))

    def _refresh_g_status(self):
        tok = self._g_token()
        self.g_status.setText(self._tr("g_state_in") if tok.get("refresh_token")
                              else self._tr("g_state_out"))

    def _g_ready_token(self):
        """A usable access token, or None (with the reason already shown)."""
        cid = self._g_client_id()
        if not cid:
            self._set_status(self._tr("st_g_no_client"), error=True)
            return None
        tok = self._g_token()
        if not tok.get("refresh_token"):
            self._set_status(self._tr("st_g_not_signed_in"), error=True)
            return None
        try:
            tok = GA.ensure(tok, cid)
        except GA.AuthError as e:
            self._set_status(str(e), error=True)
            return None
        self._g_store_token(tok)
        return tok

    def _download_dirs(self):
        """Where a browser is likely to drop the export.

        ~/Downloads is only the default: Windows lets the folder be moved
        (onto another drive, into a cloud folder), and then the registry is
        the only place that knows where it went.
        """
        home = os.path.expanduser("~")
        dirs = [os.path.join(home, "Downloads"), os.path.join(home, "Download")]
        try:
            import winreg
            key = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                   r"\Shell Folders")
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                # FOLDERID_Downloads
                val, _ = winreg.QueryValueEx(
                    k, "{374DE290-123F-4565-9164-39C4925E467B}")
                if val:
                    dirs.insert(0, os.path.expandvars(val))
        except Exception:
            pass                       # not Windows, or the value is absent
        seen = []
        for d in dirs:
            if os.path.isdir(d) and d not in seen:
                seen.append(d)
        return seen

    def _docx_snapshot(self):
        seen = {}
        for d in self._download_dirs():
            try:
                for n in os.listdir(d):
                    if n.lower().endswith((".docx", ".odt")):
                        p = os.path.join(d, n)
                        try:
                            seen[p] = os.path.getmtime(p)
                        except OSError:
                            pass
            except OSError:
                pass
        return seen

    def _offer_export(self, doc_id):
        """No sign-in needed: let the browser export it, then pick it up.

        The browser is already signed in to Google, so this needs no
        credentials, no consent screen and no API quota — and the .docx export
        carries the comments along, which is the whole point.
        """
        box = QMessageBox(self.widget())
        box.setWindowTitle(self._tr("g_export_title"))
        box.setText(self._tr("g_export_msg"))
        openb = box.addButton(self._tr("g_export_open"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self._tr("g_export_cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not openb:
            return
        import webbrowser
        self._exp_before = self._docx_snapshot()
        self._exp_deadline = time.time() + 120
        webbrowser.open(GD.export_url(doc_id))
        self._set_status(self._tr("st_g_waiting_dl"))
        self._exp_timer = QTimer(self.widget())
        self._exp_timer.setInterval(700)
        self._exp_timer.timeout.connect(self._check_export)
        self._exp_timer.start()

    def _stop_export_watch(self):
        t = getattr(self, "_exp_timer", None)
        if t is not None:
            t.stop()
            self._exp_timer = None

    def _check_export(self):
        """Poll for a freshly downloaded export; give up politely."""
        now = self._docx_snapshot()
        before = getattr(self, "_exp_before", {})
        fresh = [p for p, m in now.items()
                 if p not in before or m > before.get(p, 0)]
        if fresh:
            newest = max(fresh, key=lambda p: now[p])
            # a browser writes the file in chunks; wait until it stops growing
            try:
                size = os.path.getsize(newest)
            except OSError:
                return
            if getattr(self, "_exp_last_size", None) != size:
                self._exp_last_size = size
                return                          # still downloading
            self._stop_export_watch()
            self._exp_last_size = None
            self._load_exported(newest)
            return
        if time.time() > getattr(self, "_exp_deadline", 0):
            self._stop_export_watch()
            self._set_status(self._tr("st_g_dl_timeout"), error=True)

    def _load_exported(self, path):
        """Load a downloaded export exactly like any other script."""
        try:
            text = read_script(path)
        except Exception as exc:
            self._set_status(self._tr("st_read_fail").format(exc=exc),
                             error=True)
            return
        cs = CM.from_docx(path)
        self._script_comments = cs
        self._add_session(LP.default_tab_label(path), path, text,
                          do_analyze=True)
        self._script_comments = cs
        self._set_status(self._tr("st_g_loaded").format(
            name=os.path.basename(path), n=len(self._pairs), c=len(cs)))

    def _load_gdoc(self, path):
        """Fetch a Google Doc script (and its comments) into a new tab."""
        try:
            doc_id = GD.read_stub(path)
        except ValueError as e:
            self._set_status(str(e), error=True)
            return
        tok = self._g_ready_token()
        if tok is None:
            self._offer_export(doc_id)
            return
        self._set_status(self._tr("st_g_loading"))
        try:
            lines, cs = GD.load(doc_id, tok)
        except GA.AuthError as e:
            self._set_status(str(e), error=True)
            return
        except Exception as e:
            self._set_status(self._tr("st_read_fail").format(exc=e), error=True)
            return
        self._script_comments = cs
        self._add_session(LP.default_tab_label(path), path, "\n".join(lines),
                          do_analyze=True)
        self._script_comments = cs
        self._set_status(self._tr("st_g_loaded").format(
            name=os.path.basename(path), n=len(self._pairs), c=len(cs)))

    def on_load_image_comments(self):
        """#21: load a Drive image's comments as a new script.

        The comment threads on a raw image are, for this group, a way the
        translation arrives — so turn them into a session where each comment is
        a line to place. No image format carries its comments in a download, so
        this is OAuth-only by nature; the export fallback that the Doc path has
        does not exist here.
        """
        raw = self.g_image_edit.text().strip()
        file_id = LP.drive_file_id(raw)
        if not file_id:
            self._set_status(self._tr("st_img_no_id"), error=True)
            return
        tok = self._g_ready_token()
        if tok is None:
            # _g_ready_token already said why (no client id / not signed in).
            return
        self._set_status(self._tr("st_g_loading"))
        try:
            cs = GD.fetch_comments(file_id, tok)
        except GA.AuthError as e:
            self._set_status(str(e), error=True)
            return
        except Exception as e:                      # noqa: BLE001
            self._set_status(self._tr("st_read_fail").format(exc=e), error=True)
            return
        if not cs:
            self._set_status(self._tr("st_img_none"), error=True)
            return
        # createdTime order ≈ reading order on a page; the typesetter re-steps
        # if not.
        cs.sort(key=lambda c: (c.date, c.id))
        text = LP.image_comments_to_script(cs)
        label = self._tr("img_tab_label")
        self._add_session(label, None, text, do_analyze=True)
        # Note: the comments are the SCRIPT now (each text became a line), not
        # notes-on-lines — so they are deliberately NOT set as _script_comments.
        # analyze() anchors notes by quoted text, which an image comment lacks,
        # so keeping them would just be a dead assignment. Showing author/reply
        # threads beside each derived line would be a separate follow-up (it
        # needs the comment→unit mapping, which the empty-skip breaks 1:1).
        n_placed = len([c for c in cs if (c.text or "").strip()])
        self._set_status(self._tr("st_img_loaded").format(c=n_placed))

    def analyze(self):
        lines = split_lines(self.editor.toPlainText(), self.skip_empty.isChecked())
        # pair_lines_paged also pulls out the "Page N" markers and tells us which
        # page every unit belongs to (so we can show it and jump between pages).
        self._pairs, self._pair_pages, self._pages = LP.pair_lines_paged(lines)
        self._index = 0
        self._done = set()
        # auto-switch the manga before the first line is shown (auto-character
        # then runs against the right character set)
        self._maybe_auto_manga(self.editor.toPlainText(), self._script_path)
        if self._script_comments:
            CM.anchor_to_units(self._script_comments,
                               [LP.unit_text(p) + " " + (p[0] or "")
                                for p in self._pairs])
        self._populate_table()
        self._refresh_pages_combo()
        self._refresh_view()
        self._schedule_session_save()

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._pairs))
        for r, (ja, en) in enumerate(self._pairs):
            self.table.setItem(r, 0, QTableWidgetItem(ja))
            self.table.setItem(r, 1, QTableWidgetItem(en))
        self.table.blockSignals(False)
        self.table.resizeRowsToContents()

    def on_add_line(self):
        """Add a line to the script: append it to the editor (the script's own
        text, so it is kept and can be written back to the file) AND to the
        parsed units, then select it. Existing done-marks/indices are untouched
        because the new unit goes at the end."""
        text, ok = QInputDialog.getMultiLineText(
            self.widget(), self._tr("add_line_dlg"), self._tr("add_line_prompt"))
        if not ok:
            return
        text = text.strip()
        if not text:
            return
        cur = self.editor.toPlainText()
        if cur and not cur.endswith("\n"):
            cur += "\n"
        self.editor.blockSignals(True)
        self.editor.setPlainText(cur + text + "\n")
        self.editor.blockSignals(False)
        self._pairs.append(("", text))                 # a new EN-only unit
        pp = getattr(self, "_pair_pages", None)
        if pp is not None:
            pp.append(pp[-1] if pp else 0)             # same page as the last unit
        self._index = len(self._pairs) - 1
        self._populate_table()
        self._refresh_pages_combo()
        self._refresh_view()
        self._snapshot_active()
        self._set_status(self._tr("st_line_added"))

    def on_save_script(self):
        """Write the current script text back to a file: overwrite the loaded
        .txt/.md in place, or (for a pasted script or a binary format like
        .docx/.xlsx that can't be rewritten) save a new .txt via a dialog."""
        text = self.editor.toPlainText()
        path = self._script_path
        is_text = bool(path) and path.lower().endswith((".txt", ".md"))
        if is_text:
            if QMessageBox.question(
                    self.widget(), self._tr("save_script_dlg"),
                    self._tr("save_script_confirm").format(
                        name=os.path.basename(path))) != QMessageBox.StandardButton.Yes:
                return
            target = path
        else:
            default = (os.path.splitext(path)[0] + ".txt") if path else "script.txt"
            target, _ = QFileDialog.getSaveFileName(
                self.widget(), self._tr("save_script_dlg"), default,
                "Text (*.txt);;Markdown (*.md)")
            if not target:
                return
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:                         # noqa: BLE001
            self._set_status(
                self._tr("st_save_script_fail").format(err=str(e)), error=True)
            return
        # point the active session/tab at the saved file
        self._script_path = target
        base = os.path.basename(target)
        i = self._session_index(self._active_sid)
        if i >= 0:
            self._sessions[i]["path"] = target
            self._sessions[i]["name"] = base
            ti = self.script_tabs.currentIndex()
            if ti >= 0:
                self.script_tabs.setTabText(ti, base)
                self.script_tabs.setTabToolTip(ti, target)
        self._snapshot_active()
        self._set_status(self._tr("st_script_saved").format(name=base))

    def _on_table_select(self):
        model = self.table.selectionModel()
        if model is None:
            return
        rows = model.selectedRows()
        if rows:
            self._index = rows[0].row()
            self._show_current()

    def _on_table_double(self, *args):
        # double-click on a row = insert immediately
        self.on_insert()

    def on_prev(self):
        if self._pairs:
            self._index = (self._index - 1) % len(self._pairs)
        self._refresh_view()

    def on_next(self):
        if self._pairs:
            self._index = (self._index + 1) % len(self._pairs)
        self._refresh_view()

    def on_reset_progress(self):
        self._done = set()
        self._repaint_done()
        self._show_current()
        self._set_status(self._tr("st_progress_reset"))

    # -- pages ("Page N" markers in the script) --

    def _page_labels(self):
        """Ordered list of the non-empty page labels found in the script."""
        return [label for label, _first in self._pages if label]

    def _current_page_label(self):
        """Page label of the currently active unit ('' if before page 1)."""
        if 0 <= self._index < len(self._pair_pages):
            return self._pair_pages[self._index]
        return ""

    def _refresh_pages_combo(self):
        """Rebuild the jump-to-page combo and show/hide the whole page row
        depending on whether the script actually contains "Page" markers."""
        labels = self._page_labels()
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        for label, first in self._pages:
            if not label:
                continue
            self.page_combo.addItem(
                self._tr("page_item").format(label=label), first)
        self.page_combo.blockSignals(False)
        has_pages = bool(labels)
        self.lbl_page.setVisible(has_pages)
        self.page_combo.setVisible(has_pages)
        self.page_status.setVisible(has_pages)
        self._sync_page_indicator()

    def on_jump_page(self, combo_index):
        """Jump to the first unit of the selected page."""
        first = self.page_combo.itemData(combo_index)
        if first is None:
            return
        self._index = int(first)
        self._refresh_view()

    def _sync_page_indicator(self):
        """Update the "Page X / N" label and keep the combo in sync with the
        page of the current unit (without triggering a jump)."""
        labels = self._page_labels()
        if not labels:
            self.page_status.setText("")
            return
        cur = self._current_page_label()
        if cur in labels:
            self.page_status.setText(self._tr("page_status").format(
                cur=cur, n=len(labels)))
            self.page_combo.blockSignals(True)
            self.page_combo.setCurrentIndex(labels.index(cur))
            self.page_combo.blockSignals(False)
        else:
            self.page_status.setText(self._tr("page_status_intro"))

    def _done_brush(self):
        # subtle green that works in both the light and dark Krita theme
        c = QColor(70, 160, 90)
        c.setAlpha(60)
        return c

    def _mark_done_row(self, row):
        if not (0 <= row < self.table.rowCount()):
            return
        brush = self._done_brush()
        for col in range(self.table.columnCount()):
            it = self.table.item(row, col)
            if it is not None:
                it.setBackground(brush)

    def _repaint_done(self):
        empty = QColor(0, 0, 0, 0)
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                it = self.table.item(row, col)
                if it is not None:
                    it.setBackground(self._done_brush() if row in self._done else empty)

    def on_pick_color(self):
        # Live text-colour picking: as the colour is dragged in the dialog, apply
        # it right away so the TextShapR cards, the live preview AND the canvas
        # layer (when "Live on canvas" is on) follow in real time. Cancel reverts.
        prev = QColor(self._color)

        def _apply(col):
            if col.isValid():
                self._color = QColor(col)
                self._update_color_btn()
                self._on_style_changed()

        dlg = QColorDialog(self._color, self.widget())
        dlg.setWindowTitle(self._tr("color_dlg"))
        dlg.currentColorChanged.connect(_apply)
        if dlg.exec():
            _apply(dlg.selectedColor())
        else:
            _apply(prev)                  # cancelled -> restore the old colour

    def on_pick_outline_color(self):
        # Live outline-colour picking (see on_pick_color): applies while dragging.
        prev = QColor(self._outline_color)

        def _apply(col):
            if col.isValid():
                self._outline_color = QColor(col)
                self._update_outline_btn()
                self._on_style_changed()

        dlg = QColorDialog(self._outline_color, self.widget())
        dlg.setWindowTitle(self._tr("outline_color_dlg"))
        dlg.currentColorChanged.connect(_apply)
        if dlg.exec():
            _apply(dlg.selectedColor())
        else:
            _apply(prev)                  # cancelled -> restore the old colour

    def on_pick_outline2_color(self):
        # Live 2nd-outline-colour picking (see on_pick_color).
        prev = QColor(self._outline2_color)

        def _apply(col):
            if col.isValid():
                self._outline2_color = QColor(col)
                self._update_outline2_btn()
                self._on_style_changed()

        dlg = QColorDialog(self._outline2_color, self.widget())
        dlg.setWindowTitle(self._tr("outline2_color_dlg"))
        dlg.currentColorChanged.connect(_apply)
        if dlg.exec():
            _apply(dlg.selectedColor())
        else:
            _apply(prev)                  # cancelled -> restore the old colour

    def _on_auto_toggle(self):
        auto = self.auto_chk.isChecked()
        self.size_label.setText(
            self._tr("size_max") if auto else self._tr("size_fixed"))
        self.pad_spin.setEnabled(auto)
        self.round_chk.setEnabled(auto)
        if hasattr(self, "hyph_chk"):
            self.hyph_chk.setEnabled(auto)
            self.hyph_lang_combo.setEnabled(auto and self.hyph_chk.isChecked())
        self._update_text_preview()

    def _on_hyph_toggle(self):
        self.hyph_lang_combo.setEnabled(
            self.auto_chk.isChecked() and self.hyph_chk.isChecked())
        self._update_text_preview()

    def _resolve_hyph(self, code, text):
        """Resolve a hyphenation-language code. An explicit choice wins.
        'Auto' prefers the UI language (when its patterns are bundled), then
        a simple accent heuristic, then English."""
        if code and code != "auto":
            return code
        if self._lang in L.HYPH_LANGS:
            return self._lang
        return self._accent_lang(text) or "en"

    def _hyph_lang_for(self, text):
        """Hyphenation language for the CURRENT UI choice."""
        return self._resolve_hyph(
            self.hyph_lang_combo.currentData() or "auto", text)

    @staticmethod
    def _accent_lang(text):
        """Very rough language guess from a few distinctive accents (only used
        when the UI language has no bundled patterns). None if undecided."""
        t = text or ""
        if any(c in "ñ¡¿" for c in t):
            return "es"
        if any(c in "ãõ" for c in t):
            return "pt"
        if any(c in "œ" for c in t):
            return "fr"
        if any(c in "äöüßÄÖÜ" for c in t):
            return "de"
        return None

    def _current_text(self):
        # prefer the (possibly edited) content of the active field
        txt = self.active_edit.toPlainText()
        if txt.strip():
            return txt
        if not self._pairs:
            return ""
        return LP.unit_text(self._pairs[self._index])

    def on_bold_selection(self):
        """Toggle bold (``**...**``) on the selected words in the active field."""
        tc = self.active_edit.textCursor()
        start, end = tc.selectionStart(), tc.selectionEnd()
        if start == end:
            self._set_status(self._tr("st_bold_no_sel"))
            return
        text = self.active_edit.toPlainText()
        new, ns, ne = toggle_bold(text, start, end)
        self.active_edit.setPlainText(new)          # triggers textChanged -> preview
        cur = self.active_edit.textCursor()
        cur.setPosition(max(0, ns))
        cur.setPosition(max(0, ne), QTextCursor.MoveMode.KeepAnchor)
        self.active_edit.setTextCursor(cur)
        self.active_edit.setFocus()

    def _update_text_preview(self):
        """Redraw the live preview from the current (possibly edited) text."""
        if not hasattr(self, "preview"):
            return
        try:
            self.preview.set_text(self._current_text())
        except Exception:
            pass

    def _wire_preview(self):
        """Connect every control that affects appearance to the preview
        refresh."""
        try:
            self.font_picker.list.currentItemChanged.connect(
                lambda *a: self._update_text_preview())
            # also on familyChanged: a font set programmatically (a preset, or an
            # uninstalled name adopted by setCurrentFamily) blocks the list
            # signal above, so without this the live preview would keep the old
            # font while TextShapR already switched.
            self.font_picker.familyChanged.connect(
                lambda *a: self._update_text_preview())
        except Exception:
            pass
        for chk in (self.bold_chk, self.italic_chk, self.underline_chk,
                    self.liga_chk,
                    self.tidy_chk, self.comic_chk, self.crossbar_chk,
                    self.outline_chk, self.vertical_chk,
                    self.shadow_chk):
            chk.toggled.connect(lambda *a: self._update_text_preview())
        for combo in (self.align_combo, self.valign_combo, self.case_combo):
            combo.currentIndexChanged.connect(
                lambda *a: self._update_text_preview())
        for spin in (self.size_spin, self.pad_spin, self.spacing_spin,
                     self.outline_spin, self.outline2_spin,
                     self.shadow_x_spin, self.shadow_y_spin):
            spin.valueChanged.connect(lambda *a: self._update_text_preview())

    def _bp_link_active(self):
        """True when a detected BubblR bubble is armed to receive the next
        Insert (boxes exist and a valid current bubble is set). While this
        holds, the Type tab's Insert fills that bubble (and advances) instead
        of using the document selection."""
        return (bool(self._bp_boxes)
                and 0 <= self._bp_current < len(self._bp_boxes))

    def _bp_step(self, delta):
        """Step the current-bubble pointer by delta (for the ◀/▶ redo
        buttons); clamps to the ends."""
        if not self._bp_boxes:
            return
        cur = self._bp_current if self._bp_current >= 0 else 0
        self._bp_set_current(max(0, min(cur + delta, len(self._bp_boxes) - 1)))

    def _bp_update_nav(self):
        """Show/label the Type-tab bubble stepper to mirror BubblR state."""
        if not hasattr(self, "bubble_nav_widget"):
            return
        have = bool(self._bp_boxes)
        self.bubble_nav_widget.setVisible(have)
        if have:
            cur = self._bp_current + 1 if self._bp_current >= 0 else 0
            self.bubble_lbl.setText(
                self._tr("bubble_of").format(cur=cur, n=len(self._bp_boxes)))

    def on_insert(self):
        if not self._pairs:
            self._set_status(self._tr("st_nothing"), error=True)
            return
        family = self.font_picker.currentFamily()
        if not family:
            self._set_status(self._tr("st_no_font"), error=True)
            return
        text = self._current_text()
        # default shape from the auto-fit + round toggles
        shape = "ellipse" if (self.auto_chk.isChecked()
                              and self.round_chk.isChecked()) else "rect"
        # When a BubblR bubble is armed, Insert fills THAT bubble: use its
        # rect as the box and its detected shape (round bubbles -> ellipse).
        box = None
        linked = self._bp_link_active()
        if linked:
            b = self._bp_boxes[self._bp_current]
            box = (b["x"], b["y"], b["w"], b["h"])
            # Fit to whatever suits the bubble: an ellipse for round speech
            # bubbles, a rectangle for caption boxes / SFX / free text.
            if self.auto_chk.isChecked():
                shape = ("rect" if b.get("kind") == "sfx"
                         else ("ellipse" if b.get("shape") == "round"
                               else "rect"))
        ok, key, fmt = insert_text_layer(
            text,
            family,
            self.size_spin.value(),
            self._color,
            self.auto_chk.isChecked(),
            self.size_spin.value(),
            self.pad_spin.value() / 100.0,
            self.spacing_spin.value() / 100.0,
            self.outline_chk.isChecked(),
            self._outline_color,
            self.outline_spin.value(),
            self.bold_chk.isChecked(),
            self.italic_chk.isChecked(),
            self.underline_chk.isChecked(),
            self.align_combo.currentData() or "center",
            self.case_combo.currentData() or "none",
            self.tidy_chk.isChecked(),
            shape,
            self.shadow_chk.isChecked(),
            self._shadow_color,
            self.shadow_x_spin.value(),
            self.shadow_y_spin.value(),
            self.valign_combo.currentData() or "middle",
            self._index + 1,
            hyphenate=self.hyph_chk.isChecked(),
            hyph_lang=self._hyph_lang_for(text),
            replace_existing=self.replace_chk.isChecked(),
            box=box,
            comic=self.comic_chk.isChecked(),
            crossbar_i=self.crossbar_chk.isChecked(),
            vertical=self.vertical_chk.isChecked(),
            ligatures=self.liga_chk.isChecked(),
            outline2_color=self._outline2_color,
            outline2_px=self.outline2_spin.value(),
            pattern_img=(self._ensure_outline_pattern_img()
                         if (self._patterns_on()
                             and self.outline_chk.isChecked()) else None),
            pattern_scale=self.outline_pattern_scale_spin.value(),
            soft=(self._patterns_on() and self.outline_chk.isChecked()
                  and self.style_soft_chk.isChecked()),
            soft_color=self._style_soft_color,
            soft_px=self.style_soft_width_spin.value(),
            soft_blur=self.style_soft_blur_spin.value(),
            soft_pattern=self.style_soft_pattern_chk.isChecked(),
            pattern_target=(self.outline_pattern_target_combo.currentData()
                            or "outline1"),
        )
        self._set_status(self._insert_msg(key, fmt), error=not ok)
        if ok:
            self.font_picker.noteUsed(family)
            self._save_recents()
            self._save_settings()
            self._done.add(self._index)
            self._mark_done_row(self._index)
            self._schedule_session_save()
            if self._index < len(self._pairs) - 1:
                self._index += 1
            self._refresh_view()
            # in the BubblR flow, mark this bubble filled and step to the next
            if linked:
                self._bp_placed.add(self._bp_current)
                nxt = self._bp_next_bubble(self._bp_current + 1)
                self._bp_set_current(nxt if nxt is not None else -1)

    def _on_balloon_changed(self, *_args):
        """Name the text type the selected shape carries, so the shape list
        reads as what it means (cloud = thought) and not just how it looks."""
        sid = self.balloon_combo.currentData() or ""
        tid = BAL.SHAPE_FOR_TYPE.get(sid)
        self.balloon_hint.setText(
            self._tr("balloon_hint").format(kind=self._tr("tt_" + tid))
            if tid else "")

    def on_insert_balloon(self):
        """Draw the balloon itself as its own vector layer.

        Uses the same box as Insert does — the armed BubblR bubble if there is
        one, otherwise the selection — so a detected bubble can be redrawn in
        place. The balloon is a separate layer from the text on purpose: it has
        to sit under it, and the typesetter still has to move the tail to the
        speaker's mouth.
        """
        app = Krita.instance()
        doc = app.activeDocument()
        if doc is None:
            self._set_status(self._tr("st_no_doc"), error=True)
            return
        if self._bp_link_active():
            b = self._bp_boxes[self._bp_current]
            box = (b["x"], b["y"], b["w"], b["h"])
        else:
            sel = doc.selection()
            if sel is None:
                self._set_status(self._tr("st_balloon_no_box"), error=True)
                return
            box = (sel.x(), sel.y(), sel.width(), sel.height())
        shape = self.balloon_combo.currentData() or "oval"
        svg = BAL.balloon_svg(shape, box[0], box[1], box[2], box[3],
                              doc.width(), doc.height(),
                              tail=self.balloon_tail_chk.isChecked())
        if svg is None:
            self._set_status(self._tr("st_balloon_no_box"), error=True)
            return
        try:
            vlayer = doc.createVectorLayer(
                "TypeR — balloon ({})".format(shape))
            doc.rootNode().addChildNode(vlayer, None)
            vlayer.addShapesFromSvg(svg)
            doc.refreshProjection()
        except Exception as exc:   # pragma: no cover - depends on the Krita version
            self._set_status(
                self._tr("st_balloon_fail").format(exc=exc), error=True)
            return
        self._set_status(self._tr("st_balloon_inserted").format(
            shape=self._tr("balloon_" + shape)))

    def _insert_msg(self, key, fmt):
        """Status message for an insert result; notes when old layer(s) of the
        same line were replaced."""
        if fmt.get("px"):
            self._last_insert_px = fmt["px"]   # for TextShapR 'match size'
        msg = self._tr(key).format(**fmt)
        if fmt.get("replaced"):
            msg += "  " + self._tr("st_replaced")
        return msg

    def insert_arrangement(self, cand, advance, replace=None):
        """Insert a TextShapR candidate through the normal insert path. The
        chosen line breaks (and any hyphens) are baked into the text as hard
        breaks, and the size is capped at the candidate's px, so the layer
        matches the thumbnail exactly. Returns True on success."""
        family = self.font_picker.currentFamily()
        if not family:
            self._set_status(self._tr("st_no_font"), error=True)
            return False
        baked = "\n".join(L.runs_markup(runs) for runs in cand["lines"])
        ok, key, fmt = insert_text_layer(
            baked,
            family,
            cand["px"],
            self._color,
            True,                  # auto-fit (respects the baked hard breaks)
            cand["px"],            # cap at the candidate's size = WYSIWYG
            self.pad_spin.value() / 100.0,
            self.spacing_spin.value() / 100.0,
            self.outline_chk.isChecked(),
            self._outline_color,
            self.outline_spin.value(),
            self.bold_chk.isChecked(),
            self.italic_chk.isChecked(),
            self.underline_chk.isChecked(),
            self.align_combo.currentData() or "center",
            "none",                # case/tidy were applied at candidate time
            False,
            "rect",                # breaks are baked in -> rect reproduces them
            self.shadow_chk.isChecked(),
            self._shadow_color,
            self.shadow_x_spin.value(),
            self.shadow_y_spin.value(),
            self.valign_combo.currentData() or "middle",
            self._index + 1,
            hyphenate=False,       # hyphens are already in the baked text
            replace_existing=(self.replace_chk.isChecked()
                              if replace is None else replace),
            ligatures=self.liga_chk.isChecked(),
            outline2_color=self._outline2_color,
            outline2_px=self.outline2_spin.value(),
            pattern_img=(self._ensure_outline_pattern_img()
                         if (self._patterns_on()
                             and self.outline_chk.isChecked()) else None),
            pattern_scale=self.outline_pattern_scale_spin.value(),
            soft=(self._patterns_on() and self.outline_chk.isChecked()
                  and self.style_soft_chk.isChecked()),
            soft_color=self._style_soft_color,
            soft_px=self.style_soft_width_spin.value(),
            soft_blur=self.style_soft_blur_spin.value(),
            soft_pattern=self.style_soft_pattern_chk.isChecked(),
            pattern_target=(self.outline_pattern_target_combo.currentData()
                            or "outline1"),
        )
        self._set_status(self._insert_msg(key, fmt), error=not ok)
        if ok:
            self.font_picker.noteUsed(family)
            self._save_recents()
            self._save_settings()
            if self._pairs:
                self._done.add(self._index)
                self._mark_done_row(self._index)
                self._schedule_session_save()
                if advance and self._index < len(self._pairs) - 1:
                    self._index += 1
                self._refresh_view()
        return ok

    def _show_current(self):
        total = len(self._pairs)
        if total == 0:
            self.counter.setText("0 / 0")
            self.active_edit.blockSignals(True)
            self.active_edit.setPlainText("")
            self.active_edit.blockSignals(False)
            self.jp_ref.setText("")
            self._sync_page_indicator()
            self._update_text_preview()
            return
        self.counter.setText("{} / {}   \u2713 {}".format(
            self._index + 1, total, len(self._done)))
        ja, en = self._pairs[self._index]
        main_txt = en if en.strip() else ja
        # optional: pick the character from a "Name:" speaker prefix and strip it
        main_txt = self._maybe_auto_character(main_txt)
        self.active_edit.blockSignals(True)
        self.active_edit.setPlainText(main_txt)
        self.active_edit.blockSignals(False)
        if en.strip() and ja.strip():
            self.jp_ref.setText("JP: " + ja)
        else:
            self.jp_ref.setText("")
        self._sync_page_indicator()
        # refresh the live preview (textChanged is blocked here)
        self._update_text_preview()

    def _refresh_comments(self):
        """Show the notes for the line/page in front of you, or get out of the way."""
        panel = getattr(self, "_comments_panel", None)
        if panel is None:
            return
        cs = CM.for_unit(getattr(self, "_script_comments", []) or [],
                         self._index, self._pair_pages)
        if not cs:
            panel.setVisible(False)          # nothing to say -> take no room
            return
        parts = []
        for c in cs:
            where = (self._tr("cm_page") if c.scope == CM.SCOPE_PAGE
                     else self._tr("cm_line"))
            head = " \u00b7 ".join(x for x in (c.author, c.date, where) if x)
            body = _html.escape(c.text).replace("\n", "<br>")
            body = _LINKIFY.sub(r'<a href="\g<0>">\g<0></a>', body)
            for r in c.replies:
                body += ("<br><span style='color:#888'>\u21b3 %s</span>"
                         % _html.escape(r))
            parts.append(
                "<div style='margin-bottom:9px'>"
                "<span style='color:#888;font-size:11px'>%s</span><br>%s</div>"
                % (_html.escape(head), body))
        self.comments_view.setHtml("".join(parts))
        panel.setVisible(True)

    def _refresh_view(self):
        self._refresh_comments()
        self._show_current()
        # sync the table selection without feedback
        if self._pairs and 0 <= self._index < self.table.rowCount():
            self.table.blockSignals(True)
            self.table.selectRow(self._index)
            self.table.blockSignals(False)

    # mandatory override from DockWidget
    # ------------------------------------------------------------------
    # BubblR tab: detect bubbles, map script lines, per-bubble styles
    # ------------------------------------------------------------------

    def _build_bubblr_tab(self, lay):
        app = Krita.instance()

        # detection controls live in one movable panel; the overlay preview in
        # another so the two can be reordered / moved like every other panel.
        _det_pb = self._new_panel("bubblr_detect", "bubblr")
        det = _det_pb.body_layout()

        # detection row: backend + actions (wraps to the docker width)
        row = FlowLayout()
        self.bp_backend_combo = NoScrollComboBox()
        self.bp_backend_combo.addItem("", "heur")
        self.bp_backend_combo.addItem("", "ai")
        saved = app.readSetting("typer_kr", "bpBackend", "")
        if not saved:
            saved = "ai" if AB.find_ai_dir(
                app.readSetting("typer_kr", "aidir", "")) else "heur"
        self.bp_backend_combo.setCurrentIndex(1 if saved == "ai" else 0)
        self.bp_backend_combo.currentIndexChanged.connect(
            self._on_bp_backend)
        row.addWidget(self.bp_backend_combo)
        self.bp_detect_btn = QPushButton()
        self.bp_detect_btn.clicked.connect(self.on_bp_detect)
        row.addWidget(self.bp_detect_btn)
        self.bp_add_sel_btn = QPushButton()
        self.bp_add_sel_btn.clicked.connect(self.on_bp_add_from_selection)
        row.addWidget(self.bp_add_sel_btn)
        self.bp_reset_btn = QPushButton()
        self.bp_reset_btn.clicked.connect(self.on_bp_reset_order)
        row.addWidget(self.bp_reset_btn)
        # "Set reading order": while active, click the bubbles in the order
        # you want them numbered (finish by clicking them all, or click again
        # to cancel). Same effect as Ctrl+clicking, but as an explicit mode.
        self.bp_order_btn = QPushButton()
        self.bp_order_btn.setCheckable(True)
        self.bp_order_btn.toggled.connect(self._on_bp_order_toggle)
        row.addWidget(self.bp_order_btn)
        # "Mark SFX": while active, click a box to flip it between speech
        # bubble and SFX / free text (blue). Same mode idea as 'Set order'.
        self.bp_sfxmark_btn = QPushButton()
        self.bp_sfxmark_btn.setCheckable(True)
        self.bp_sfxmark_btn.toggled.connect(self._on_bp_sfxmark_toggle)
        row.addWidget(self.bp_sfxmark_btn)
        # "Toggle shape": while active, click a box to force it round <-> rect
        # (overrides the auto shape from the fill ratio).
        self.bp_shape_btn = QPushButton()
        self.bp_shape_btn.setCheckable(True)
        self.bp_shape_btn.toggled.connect(self._on_bp_shapemark_toggle)
        row.addWidget(self.bp_shape_btn)
        # "Edit boxes": draw a new box on empty canvas, drag a box body to move
        # it, drag a corner to resize; right-click still removes.
        self.bp_edit_btn = QPushButton()
        self.bp_edit_btn.setCheckable(True)
        self.bp_edit_btn.toggled.connect(self._on_bp_edit_toggle)
        row.addWidget(self.bp_edit_btn)
        # "Panel order": use Magi to detect comic panels and renumber the
        # bubbles panel-by-panel (fixes interleaving across side-by-side panels)
        self.bp_panelorder_btn = QPushButton()
        self.bp_panelorder_btn.clicked.connect(self.on_bp_panel_order)
        row.addWidget(self.bp_panelorder_btn)
        # Save / load the current boxes to a JSON sidecar, so labelling a page
        # can be paused and resumed (correct now, export later).
        self.bp_save_btn = QPushButton()
        self.bp_save_btn.clicked.connect(self.on_bp_save_boxes)
        row.addWidget(self.bp_save_btn)
        self.bp_load_btn = QPushButton()
        self.bp_load_btn.clicked.connect(self.on_bp_load_boxes)
        row.addWidget(self.bp_load_btn)
        det.addLayout(row)

        # AI model + sensitivity (which weights, and the detection thresholds)
        mrow = FlowLayout()
        self.bp_model_lbl = QLabel()
        mrow.addWidget(self.bp_model_lbl)
        self.bp_model_combo = NoScrollComboBox()
        self.bp_model_combo.addItem("", "auto")
        self.bp_model_combo.addItem("", "baseline")
        self.bp_model_combo.addItem("", "finetuned")
        self.bp_model_combo.addItem("", "kitsumed")
        self.bp_model_combo.addItem("", "hybrid")
        _mi = {"auto": 0, "baseline": 1, "finetuned": 2,
               "kitsumed": 3, "hybrid": 4}.get(
            app.readSetting("typer_kr", "bpModel", "auto"), 0)
        self.bp_model_combo.setCurrentIndex(_mi)
        self.bp_model_combo.currentIndexChanged.connect(
            lambda *_a: Krita.instance().writeSetting(
                "typer_kr", "bpModel",
                self.bp_model_combo.currentData() or "auto"))
        mrow.addWidget(self.bp_model_combo)
        # "where are my models?" — lists what is installed and opens the folder
        self.bp_models_btn = QPushButton()
        self.bp_models_btn.clicked.connect(self.on_bp_show_models)
        mrow.addWidget(self.bp_models_btn)
        self.bp_conf_lbl = QLabel()
        mrow.addWidget(self.bp_conf_lbl)
        self.bp_conf_spin = NoScrollSpinBox()
        self.bp_conf_spin.setRange(5, 95)
        self.bp_conf_spin.setSuffix(" %")
        self.bp_conf_spin.setValue(self._read_int_setting("bpConf", 40))
        self.bp_conf_spin.valueChanged.connect(
            lambda v: Krita.instance().writeSetting(
                "typer_kr", "bpConf", str(v)))
        mrow.addWidget(self.bp_conf_spin)
        self.bp_sfxconf_lbl = QLabel()
        mrow.addWidget(self.bp_sfxconf_lbl)
        self.bp_sfxconf_spin = NoScrollSpinBox()
        self.bp_sfxconf_spin.setRange(5, 95)
        self.bp_sfxconf_spin.setSuffix(" %")
        self.bp_sfxconf_spin.setValue(self._read_int_setting("bpSfxConf", 20))
        self.bp_sfxconf_spin.valueChanged.connect(
            lambda v: Krita.instance().writeSetting(
                "typer_kr", "bpSfxConf", str(v)))
        mrow.addWidget(self.bp_sfxconf_spin)
        det.addLayout(mrow)

        # options row (SFX handling is off by default for now: sfx boxes are
        # dropped AND script lines matching the SFX word DB are skipped)
        row = FlowLayout()
        self.bp_text_chk = QCheckBox()
        self.bp_text_chk.setChecked(
            app.readSetting("typer_kr", "bpReqText", "true") == "true")
        self.bp_text_chk.toggled.connect(
            lambda on: Krita.instance().writeSetting(
                "typer_kr", "bpReqText", "true" if on else "false"))
        row.addWidget(self.bp_text_chk)
        self.bp_sfx_chk = QCheckBox()
        self.bp_sfx_chk.setChecked(
            app.readSetting("typer_kr", "bpSfx", "false") == "true")
        self.bp_sfx_chk.toggled.connect(self._on_bp_sfx_toggle)
        row.addWidget(self.bp_sfx_chk)
        self.bp_rtl_chk = QCheckBox()
        self.bp_rtl_chk.setChecked(
            app.readSetting("typer_kr", "bpRtl", "true") == "true")
        self.bp_rtl_chk.toggled.connect(self._on_bp_rtl)
        row.addWidget(self.bp_rtl_chk)
        # Tiling: more accurate on big pages (finds small SFX/text) but slower
        # on weak machines. On by default; turn off for a fast, low-power run.
        self.bp_tile_chk = QCheckBox()
        self.bp_tile_chk.setChecked(
            app.readSetting("typer_kr", "bpTile", "false") == "true")
        self.bp_tile_chk.toggled.connect(
            lambda on: Krita.instance().writeSetting(
                "typer_kr", "bpTile", "true" if on else "false"))
        row.addWidget(self.bp_tile_chk)
        det.addLayout(row)

        row = FlowLayout()
        self.bp_selfollow_chk = QCheckBox()
        self.bp_selfollow_chk.setChecked(
            app.readSetting("typer_kr", "bpSelFollow", "true") == "true")
        self.bp_selfollow_chk.toggled.connect(
            lambda on: Krita.instance().writeSetting(
                "typer_kr", "bpSelFollow", "true" if on else "false"))
        row.addWidget(self.bp_selfollow_chk)
        self.bp_sfx_db_btn = QPushButton()
        self.bp_sfx_db_btn.clicked.connect(self.on_bp_sfx_db)
        row.addWidget(self.bp_sfx_db_btn)
        det.addLayout(row)

        # short hint: BubblR only marks the bubbles; text is placed from Type
        self.bp_hint_lbl = QLabel("")
        self.bp_hint_lbl.setStyleSheet("color: gray;")
        self.bp_hint_lbl.setWordWrap(True)
        det.addWidget(self.bp_hint_lbl)

        # actions: only training export remains (placement is done in Type)
        row = QHBoxLayout()
        self.bp_export_btn = QPushButton()
        self.bp_export_btn.clicked.connect(self.on_bp_export_training)
        row.addWidget(self.bp_export_btn)
        row.addStretch(1)
        det.addLayout(row)
        lay.addWidget(_det_pb)

        # overlay preview: the numbered bubbles on the page thumbnail
        _ov_pb = self._new_panel("bubblr_overlay", "bubblr")
        self.bp_overlay = BubbleOverlay()
        self.bp_overlay.boxClicked.connect(self._on_bp_box_clicked)
        self.bp_overlay.boxRemoved.connect(self._on_bp_box_removed)
        self.bp_overlay.boxAdded.connect(self._on_bp_box_added)
        self.bp_overlay.boxChanged.connect(self._on_bp_box_changed)
        self.bp_overlay.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # keyboard shortcuts while the overlay has focus (fast labelling)
        for keys, fn in (
                (("E", "."), lambda: self._bp_step(1)),
                (("Q", ","), lambda: self._bp_step(-1)),
                (("Delete", "Backspace"), self._bp_delete_current),
                (("S",), self._bp_toggle_current_sfx),
                (("R",), self._bp_toggle_current_shape)):
            for key in keys:
                sc = QShortcut(QKeySequence(key), self.bp_overlay)
                sc.setContext(Qt.ShortcutContext.WidgetShortcut)
                sc.activated.connect(fn)
        _ov_pb.body_layout().addWidget(self.bp_overlay, 2)
        lay.addWidget(_ov_pb, 2)

        self._on_bp_backend()

    def _on_bp_backend(self, *_a):
        mode = self.bp_backend_combo.currentData() or "heur"
        Krita.instance().writeSetting("typer_kr", "bpBackend", mode)
        # the text filter is a heuristic-only concept
        self.bp_text_chk.setVisible(mode == "heur")

    def _on_bp_sfx_toggle(self, on):
        """Whether free-text (SFX) boxes are kept; applied on the next
        Detect run."""
        Krita.instance().writeSetting(
            "typer_kr", "bpSfx", "true" if on else "false")

    # -- SFX word database ---------------------------------------------------

    def _bp_sfx_db_path(self):
        """Path of sfx_db.json in the shared ai folder, or None (then the
        user words live in the Krita setting 'sfxDb')."""
        d = AB.find_ai_dir(
            Krita.instance().readSetting("typer_kr", "aidir", ""))
        return os.path.join(d, "sfx_db.json") if d else None

    def _bp_sfx_words(self):
        """Combined seed + user SFX vocabulary."""
        path = self._bp_sfx_db_path()
        if path:
            seed, user = BB.load_sfx_db(path)
        else:
            seed = list(BB.SFX_SEED_WORDS)
            try:
                raw = Krita.instance().readSetting("typer_kr", "sfxDb", "")
                user = json.loads(raw) if raw else []
            except Exception:
                user = []
        return list(seed) + [w for w in user if w]

    def _bp_user_sfx_words(self):
        path = self._bp_sfx_db_path()
        if path:
            return BB.load_sfx_db(path)[1]
        try:
            raw = Krita.instance().readSetting("typer_kr", "sfxDb", "")
            return json.loads(raw) if raw else []
        except Exception:
            return []

    def _bp_save_user_sfx_words(self, words):
        path = self._bp_sfx_db_path()
        if path:
            seed, _user = BB.load_sfx_db(path)
            BB.save_sfx_db(path, words, seed)
        else:
            try:
                Krita.instance().writeSetting(
                    "typer_kr", "sfxDb", json.dumps(list(words)))
            except Exception:
                pass

    def on_bp_sfx_db(self):
        """Tiny editor for the user part of the SFX vocabulary."""
        dlg = QDialog(self.widget())
        dlg.setWindowTitle(self._tr("bp_sfx_db"))
        lay = QVBoxLayout(dlg)
        hint = QLabel(self._tr("bp_sfx_dlg_hint"))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        edit = QPlainTextEdit()
        edit.setPlainText("\n".join(self._bp_user_sfx_words()))
        lay.addWidget(edit, 1)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.resize(320, 380)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        words = [w.strip() for w in edit.toPlainText().split("\n")
                 if w.strip()]
        self._bp_save_user_sfx_words(words)

    # -- current bubble + selection sync ---------------------------------------

    def _bp_apply_selection(self):
        """Make the current bubble the Krita selection (when enabled), so
        the Type tab's Insert/TextShapR work on it too."""
        if not self.bp_selfollow_chk.isChecked():
            return
        if not (0 <= self._bp_current < len(self._bp_boxes)):
            return
        doc = Krita.instance().activeDocument()
        if doc is None:
            return
        b = self._bp_boxes[self._bp_current]
        x, y = int(b["x"]), int(b["y"])
        w, h = int(b["w"]), int(b["h"])
        try:
            sel = Selection()
            sel.select(x, y, w, h, 255)
            # a round bubble gets a matching ELLIPTICAL selection (a rectangle
            # would grab the corners outside the balloon). SFX / rect stay box.
            if (b.get("shape") == "round" and b.get("kind") != "sfx"
                    and 0 < w * h <= 4000000):
                sel.setPixelData(BB.ellipse_mask(w, h), x, y, w, h)
            doc.setSelection(sel)
        except Exception:
            pass

    def _bp_set_current(self, idx):
        """Move the current-bubble pointer (and the doc selection) to `idx`."""
        if not (0 <= idx < len(self._bp_boxes)):
            idx = -1
        self._bp_current = idx
        self._bp_refresh_overlay()
        self._bp_apply_selection()
        self._bp_update_nav()

    def _bp_reset_state(self):
        """After a (re)detect / reorder: forget which bubbles were placed and
        point at the first one. No script mapping is involved."""
        self._bp_placed = set()
        self._bp_set_current(0 if self._bp_boxes else -1)

    def _bp_next_bubble(self, start):
        """Next bubble index >= start that has not been placed yet, or None."""
        for k in range(max(0, start), len(self._bp_boxes)):
            if k not in self._bp_placed:
                return k
        return None

    # -- detection -----------------------------------------------------------

    def _on_style_changed(self, *_args):
        """A style control changed — re-fit TextShapR and its live preview.

        Debounced: dragging a spin box fires per tick, and each re-fit runs the
        full candidate search (plus a canvas insert when live is on), so doing
        it on every tick would stutter."""
        if getattr(self, "shapr_widget", None) is None:
            return
        t = getattr(self, "_style_timer", None)
        if t is None:
            t = QTimer(self.widget())
            t.setSingleShot(True)
            t.setInterval(250)
            t.timeout.connect(self._apply_style_changed)
            self._style_timer = t
        t.start()

    def _apply_style_changed(self):
        w = getattr(self, "shapr_widget", None)
        if w is None:
            return
        try:
            w.restyle()
        except Exception:      # noqa: BLE001 — a re-fit must never kill the UI
            pass

    def on_bp_show_models(self):
        """Answer "which models do I have and where are they?": list the
        weights the detector can load, mark which ones exist, and open the
        folder. Also points at where the trainer leaves a freshly trained
        model, since that is the file you copy in as the fine-tuned one."""
        app = Krita.instance()
        ai_dir = AB.find_ai_dir(app.readSetting("typer_kr", "aidir", ""))
        if not ai_dir:
            QMessageBox.information(self.widget(),
                                    self._tr("bp_models_title"),
                                    self._tr("bp_models_none"))
            return
        models_dir = os.path.join(ai_dir, "models")
        rows = []
        for choice, fname in (("baseline", "comic-text-bubble-detector.onnx"),
                              ("finetuned", "bubblr-finetuned.onnx")):
            path = os.path.join(models_dir, fname)
            if os.path.exists(path):
                state = "%.0f MB" % (os.path.getsize(path) / 1048576.0)
                if os.path.exists(path + ".promoted"):
                    state += " + promoted"
            else:
                state = "—"
            rows.append("  %-10s %-34s %s" % (choice, fname, state))
        msg = (self._tr("bp_models_dir") + "\n" + models_dir + "\n\n"
               + "\n".join(rows) + "\n\n" + self._tr("bp_models_trainer"))
        box = QMessageBox(self.widget())
        box.setWindowTitle(self._tr("bp_models_title"))
        box.setText(msg)
        box.setIcon(QMessageBox.Icon.Information)
        open_btn = box.addButton(self._tr("bp_models_open"),
                                 QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is open_btn:
            try:
                os.startfile(models_dir if os.path.isdir(models_dir)
                             else ai_dir)
            except (OSError, AttributeError):      # non-Windows / missing dir
                pass

    def _bp_ai_dir(self):
        app = Krita.instance()
        d = AB.find_ai_dir(app.readSetting("typer_kr", "aidir", ""))
        if d:
            return d
        picked = QFileDialog.getExistingDirectory(
            self.widget(), self._tr("bp_pick_ai"))
        if picked and AB.find_ai_dir(picked):
            app.writeSetting("typer_kr", "aidir", picked)
            return picked
        return None

    @staticmethod
    def _bp_save_page_png(gray, w, h, path):
        """Write the grayscale page to a PNG (input for the AI detector)."""
        data = bytes(gray)
        img = QImage(data, w, h, w, QImage.Format.Format_Grayscale8)
        return img.save(path, "PNG")

    @staticmethod
    def _bp_refine_shapes(boxes, gray, w, h):
        """Round vs. rect for AI bubble boxes: a caption box fills its bbox
        almost completely with white, an ellipse only ~78 %."""
        for b in boxes:
            if b.get("kind") != "bubble":
                continue
            step = max(1, int(((b["w"] * b["h"]) / 20000.0) ** 0.5))
            white = total = 0
            for y in range(b["y"], min(h, b["y"] + b["h"]), step):
                base = y * w
                for x in range(b["x"], min(w, b["x"] + b["w"]), step):
                    total += 1
                    if gray[base + x] >= BB.BRIGHT_THRESH:
                        white += 1
            frac = white / float(total or 1)
            b["shape"] = "rect" if frac >= 0.9 else "round"
            b["fill"] = frac
            # trace the real outline from the pixels for round/irregular
            # balloons; caption boxes (near-full fill) stay a plain rectangle.
            b.pop("poly", None)
            if frac < 0.9:
                try:
                    poly = BB.contour_in_box(
                        gray, w, h, (b["x"], b["y"], b["w"], b["h"]))
                except Exception:               # never let shape refine crash
                    poly = None
                if poly and len(poly) >= 3:
                    b["poly"] = poly

    def _bp_detect_ai(self, gray, w, h):
        """Run the external detector; boxes or None (status already set)."""
        ai_dir = self._bp_ai_dir()
        if not ai_dir:
            self._set_status(self._tr("st_bp_ai_missing"), error=True)
            return None
        tmp = os.path.join(tempfile.gettempdir(),
                           "typer_bp_page_%d.png" % os.getpid())
        try:
            if not self._bp_save_page_png(gray, w, h, tmp):
                self._set_status(
                    self._tr("st_bp_ai_error").format(
                        msg="could not write page"), error=True)
                return None
            try:
                tile = "auto" if self.bp_tile_chk.isChecked() else "off"
                boxes = AB.detect(
                    ai_dir, tmp, tile=tile,
                    model=self.bp_model_combo.currentData() or "auto",
                    conf=self.bp_conf_spin.value() / 100.0,
                    sfx_conf=self.bp_sfxconf_spin.value() / 100.0)
            except AB.AIUnavailableError:
                self._set_status(self._tr("st_bp_ai_missing"), error=True)
                return None
            except AB.AIRunError as exc:
                self._set_status(
                    self._tr("st_bp_ai_error").format(msg=exc), error=True)
                return None
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if not self.bp_sfx_chk.isChecked():
            boxes = [b for b in boxes if b.get("kind") != "sfx"]
        self._bp_refine_shapes(boxes, gray, w, h)
        return boxes

    def on_bp_detect(self):
        # BubblR marks bubbles on the page image — a loaded script is NOT
        # required (text is placed later from the Type tab).
        doc = Krita.instance().activeDocument()
        if doc is None:
            self._set_status(self._tr("st_no_doc"), error=True)
            return
        gray, a, b = grab_gray(doc)
        if gray is None:
            self._set_status(
                self._tr("st_bp_unsupported").format(model=a, depth=b),
                error=True)
            return
        w, h = a, b
        if (self.bp_backend_combo.currentData() or "heur") == "ai":
            boxes = self._bp_detect_ai(gray, w, h)
            if boxes is None:
                return
        else:
            boxes = BB.detect_bubbles(
                gray, w, h, require_text=self.bp_text_chk.isChecked())
            if self.bp_sfx_chk.isChecked():
                boxes = boxes + BB.detect_text_blocks(gray, w, h, boxes)
        self._bp_boxes = BB.reading_order(
            boxes, rtl=self.bp_rtl_chk.isChecked())
        self._bp_click_seq = []
        thumb = doc.thumbnail(600, max(1, int(h * 600 / float(w))))
        self.bp_overlay.set_page(thumb, w, h)
        self._bp_reset_state()
        self._bp_refresh()
        if self._bp_boxes:
            self._set_status(
                self._tr("st_bp_detected").format(n=len(self._bp_boxes)))
        else:
            self._set_status(self._tr("st_bp_none"), error=True)

    def _on_bp_rtl(self, checked):
        Krita.instance().writeSetting(
            "typer_kr", "bpRtl", "true" if checked else "false")
        if self._bp_boxes:
            self._bp_boxes = BB.reading_order(self._bp_boxes, rtl=checked)
            self._bp_click_seq = []
            self._bp_reset_state()
            self._bp_refresh()

    def on_bp_reset_order(self):
        if self._bp_boxes:
            self._bp_boxes = BB.reading_order(
                self._bp_boxes, rtl=self.bp_rtl_chk.isChecked())
        self._bp_click_seq = []
        self._bp_reset_state()
        self._bp_refresh()

    def on_bp_save_boxes(self):
        """Write the current boxes to a JSON sidecar so labelling can resume
        later (correct now, export another day)."""
        if not self._bp_boxes:
            self._set_status(self._tr("st_bp_export_none"), error=True)
            return
        doc = Krita.instance().activeDocument()
        base = "boxes"
        if doc is not None and doc.fileName():
            base = os.path.splitext(os.path.basename(doc.fileName()))[0]
        path, _ = QFileDialog.getSaveFileName(
            self, self._tr("bp_save_boxes"), base + ".bubblr.json",
            "BubblR boxes (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"boxes": self._bp_boxes}, fh)
            self._set_status(self._tr("st_bp_saved").format(
                name=os.path.basename(path)))
        except Exception as exc:                    # noqa: BLE001
            self._set_status(str(exc), error=True)

    def on_bp_load_boxes(self):
        """Load boxes from a JSON sidecar written by on_bp_save_boxes."""
        path, _ = QFileDialog.getOpenFileName(
            self, self._tr("bp_load_boxes"), "", "BubblR boxes (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            raw = data.get("boxes", data) if isinstance(data, dict) else data
            boxes = []
            for b in raw:
                boxes.append({"x": int(b["x"]), "y": int(b["y"]),
                              "w": int(b["w"]), "h": int(b["h"]),
                              "kind": b.get("kind", "bubble"),
                              "shape": b.get("shape", "rect"),
                              "score": float(b.get("score", 1.0))})
        except Exception as exc:                    # noqa: BLE001
            self._set_status(str(exc), error=True)
            return
        self._bp_boxes = boxes
        self._bp_click_seq = []
        self._bp_reset_state()
        self._bp_refresh()
        self._set_status(self._tr("st_bp_loaded").format(n=len(boxes)))

    def on_bp_panel_order(self):
        """Panel-aware reading order: detect comic panels with Magi, then
        renumber the bubbles panel by panel (a hybrid with the online model)."""
        if not self._bp_boxes:
            self._set_status(self._tr("st_bp_export_none"), error=True)
            return
        doc = Krita.instance().activeDocument()
        if doc is None:
            self._set_status(self._tr("st_no_doc"), error=True)
            return
        ai_dir = self._bp_ai_dir()
        if not ai_dir:
            self._set_status(self._tr("st_bp_ai_missing"), error=True)
            return
        gray, w, h = grab_gray(doc)
        if gray is None:
            self._set_status(
                self._tr("st_bp_unsupported").format(model=w, depth=h),
                error=True)
            return
        self._set_status(self._tr("st_bp_panels_wait"))
        tmp = os.path.join(tempfile.gettempdir(),
                           "typer_panels_%d.png" % os.getpid())
        try:
            self._bp_save_page_png(gray, w, h, tmp)
            try:
                panels = AB.detect_panels(ai_dir, tmp)
            except AB.AIUnavailableError:
                self._set_status(self._tr("st_bp_ai_missing"), error=True)
                return
            except AB.AIRunError as exc:
                self._set_status(
                    self._tr("st_bp_ai_error").format(msg=exc), error=True)
                return
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        self._bp_boxes = BB.order_by_panels(
            self._bp_boxes, panels, rtl=self.bp_rtl_chk.isChecked())
        self._bp_click_seq = []
        self._bp_reset_state()
        self._bp_refresh()
        self._set_status(self._tr("st_bp_panels").format(n=len(panels)))

    def _selection_fill(self, sel):
        """Fraction of the selection's bounding box that is actually
        selected (marked px / bbox area). A rectangular marquee is ~1.0,
        an elliptical one ~pi/4. Subsampled for speed; 1.0 on any error so
        the shape falls back to 'rect'."""
        try:
            w, h = int(sel.width()), int(sel.height())
            if w <= 0 or h <= 0:
                return 1.0
            data = sel.pixelData(sel.x(), sel.y(), w, h)
            if not data:
                return 1.0
            n = len(data)
            step = max(1, n // 20000)      # cap the work on huge selections
            marked = total = 0
            for i in range(0, n, step):
                total += 1
                if data[i]:
                    marked += 1
            return marked / float(total) if total else 1.0
        except Exception:
            return 1.0

    def on_bp_add_from_selection(self):
        doc = Krita.instance().activeDocument()
        if doc is None:
            self._set_status(self._tr("st_no_doc"), error=True)
            return
        sel = doc.selection()
        if sel is None or sel.width() <= 0 or sel.height() <= 0:
            self._set_status(self._tr("st_bp_no_sel"), error=True)
            return
        fill = self._selection_fill(sel)
        self._bp_boxes.append({"x": sel.x(), "y": sel.y(),
                               "w": sel.width(), "h": sel.height(),
                               "kind": "bubble",
                               "shape": BB.shape_from_fill(fill),
                               "fill": fill})
        self._bp_click_seq = []
        self._bp_reset_state()
        self._bp_refresh()
        self._set_status(
            self._tr("st_bp_added").format(n=len(self._bp_boxes)))

    # -- overlay interaction ---------------------------------------------------

    def _read_int_setting(self, key, default):
        try:
            return int(Krita.instance().readSetting(
                "typer_kr", key, str(default)) or default)
        except Exception:
            return default

    def _bp_exclusive_modes(self, keep):
        """Uncheck every click-mode button except `keep` so only one is on."""
        for name in ("bp_order_btn", "bp_sfxmark_btn", "bp_shape_btn",
                     "bp_edit_btn"):
            btn = getattr(self, name, None)
            if btn is not None and name != keep and btn.isChecked():
                btn.setChecked(False)

    def _on_bp_edit_toggle(self, on):
        """Enter/leave 'edit boxes' mode (draw / move / resize on the page)."""
        if on:
            self._bp_exclusive_modes("bp_edit_btn")
            self._set_status(self._tr("st_bp_edit_mode"))
        if hasattr(self, "bp_overlay"):
            self.bp_overlay.set_edit_mode(on)

    def _on_bp_box_added(self, x, y, w, h):
        self._bp_boxes.append({"x": int(round(x)), "y": int(round(y)),
                               "w": int(round(w)), "h": int(round(h)),
                               "kind": "bubble", "shape": "rect",
                               "score": 1.0})
        self._bp_click_seq = []
        self._bp_refresh()
        self._bp_set_current(len(self._bp_boxes) - 1)

    def _on_bp_box_changed(self, idx, x, y, w, h):
        if 0 <= idx < len(self._bp_boxes):
            b = self._bp_boxes[idx]
            b["x"], b["y"] = int(round(x)), int(round(y))
            b["w"], b["h"] = int(round(w)), int(round(h))
            b.pop("poly", None)     # box moved/resized -> old outline is stale
            self._bp_refresh_overlay()

    def _bp_delete_current(self):
        if 0 <= self._bp_current < len(self._bp_boxes):
            self._on_bp_box_removed(self._bp_current)

    def _bp_toggle_current_sfx(self):
        if 0 <= self._bp_current < len(self._bp_boxes):
            b = self._bp_boxes[self._bp_current]
            b["kind"] = "bubble" if b.get("kind") == "sfx" else "sfx"
            self._bp_refresh_overlay()

    def _bp_toggle_current_shape(self):
        if 0 <= self._bp_current < len(self._bp_boxes):
            b = self._bp_boxes[self._bp_current]
            b["shape"] = "rect" if b.get("shape") == "round" else "round"
            b.pop("poly", None)     # explicit override -> drop the traced outline
            self._bp_refresh_overlay()

    def _on_bp_order_toggle(self, on):
        """Enter/leave 'set reading order' mode. Leaving mid-way cancels the
        partial numbering."""
        if on:
            self._bp_exclusive_modes("bp_order_btn")
        if not on and self._bp_click_seq:
            self._bp_click_seq = []
            self._bp_refresh_overlay()
        if on:
            self._set_status(self._tr("st_bp_order_mode"))

    def _on_bp_sfxmark_toggle(self, on):
        """Enter/leave 'mark SFX' mode: clicking a box flips bubble <-> SFX."""
        if on:
            self._bp_exclusive_modes("bp_sfxmark_btn")
            self._set_status(self._tr("st_bp_sfx_mode"))

    def _on_bp_shapemark_toggle(self, on):
        """Enter/leave 'toggle shape' mode: clicking a box flips round <->
        rect, overriding the automatic shape."""
        if on:
            self._bp_exclusive_modes("bp_shape_btn")
            self._set_status(self._tr("st_bp_shape_mode"))

    def _on_bp_box_clicked(self, idx, ctrl):
        # 'mark SFX' mode: a click toggles the box kind (bubble <-> sfx).
        if (not ctrl and getattr(self, "bp_sfxmark_btn", None) is not None
                and self.bp_sfxmark_btn.isChecked()):
            if 0 <= idx < len(self._bp_boxes):
                b = self._bp_boxes[idx]
                b["kind"] = "bubble" if b.get("kind") == "sfx" else "sfx"
                self._bp_refresh_overlay()
            return
        # 'toggle shape' mode: a click flips the box shape (round <-> rect).
        if (not ctrl and getattr(self, "bp_shape_btn", None) is not None
                and self.bp_shape_btn.isChecked()):
            if 0 <= idx < len(self._bp_boxes):
                b = self._bp_boxes[idx]
                b["shape"] = "rect" if b.get("shape") == "round" else "round"
                b.pop("poly", None)   # explicit override -> drop traced outline
                self._bp_refresh_overlay()
            return
        ordering = ctrl or (hasattr(self, "bp_order_btn")
                            and self.bp_order_btn.isChecked())
        if not ordering:
            # plain click: make this the current bubble
            self._bp_set_current(idx)
            return
        if idx in self._bp_click_seq:
            return
        self._bp_click_seq.append(idx)
        if len(self._bp_click_seq) == len(self._bp_boxes):
            # every box clicked once -> apply the new order
            self._bp_boxes = [self._bp_boxes[i] for i in self._bp_click_seq]
            self._bp_click_seq = []
            if hasattr(self, "bp_order_btn"):
                self.bp_order_btn.setChecked(False)   # leave the mode
            self._bp_reset_state()
            self._bp_refresh()
            self._set_status(self._tr("st_bp_renumbered"))
            return
        self._bp_refresh_overlay()

    def _on_bp_box_removed(self, idx):
        del self._bp_boxes[idx]
        self._bp_click_seq = []
        self._bp_reset_state()
        self._bp_refresh()

    def _bp_refresh_overlay(self):
        pending = {b: n + 1 for n, b in enumerate(self._bp_click_seq)}
        self.bp_overlay.set_boxes(self._bp_boxes, pending,
                                  current=self._bp_current)

    def _bp_refresh(self):
        self._bp_refresh_overlay()
        self._bp_update_nav()

    # -- training-data export ------------------------------------------------------------

    def on_bp_export_training(self):
        doc = Krita.instance().activeDocument()
        if doc is None:
            self._set_status(self._tr("st_no_doc"), error=True)
            return
        if not self._bp_boxes:
            self._set_status(self._tr("st_bp_export_none"), error=True)
            return
        gray, a, b = grab_gray(doc)
        if gray is None:
            self._set_status(
                self._tr("st_bp_unsupported").format(model=a, depth=b),
                error=True)
            return
        w, h = a, b
        ai_dir = self._bp_ai_dir()
        if not ai_dir:
            self._set_status(self._tr("st_bp_ai_missing"), error=True)
            return
        base = os.path.splitext(
            os.path.basename(doc.fileName() or "page"))[0]
        base = "".join(ch if (ch.isalnum() or ch in "-_") else "_"
                       for ch in base) or "page"
        stem = "%s_%d" % (base, int(time.time()))
        boxes = list(self._bp_boxes)
        path = AB.export_training_example(
            ai_dir, stem,
            lambda p: self._bp_save_page_png(gray, w, h, p),
            boxes, w, h,
            save_preview_fn=lambda p: self._bp_save_preview_png(
                gray, w, h, boxes, p))
        self._set_status(
            self._tr("st_bp_exported").format(name=os.path.basename(path)))

    @staticmethod
    def _bp_save_preview_png(gray, w, h, boxes, path):
        """Write a human-viewable copy of the page with the markings drawn on
        top: numbered boxes, red = speech bubble, blue = SFX / free text,
        ellipse for round bubbles and rectangle otherwise. This is only for
        eyeballing what was labelled; training uses the plain PNG + .txt."""
        data = bytes(gray)
        base = QImage(data, w, h, w, QImage.Format.Format_Grayscale8)
        img = base.convertToFormat(QImage.Format.Format_RGB888)
        p = QPainter(img)
        try:
            f = p.font()
            f.setPixelSize(max(14, h // 90))
            f.setBold(True)
            p.setFont(f)
            pen_w = max(2, w // 400)
            bw, bh = max(26, w // 70), max(20, h // 110)
            for i, b in enumerate(boxes, 1):
                sfx = b.get("kind") == "sfx"
                col = QColor(70, 130, 230) if sfx else QColor(230, 60, 60)
                p.setPen(QPen(col, pen_w))
                p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                r = QRectF(float(b["x"]), float(b["y"]),
                           float(b["w"]), float(b["h"]))
                poly = b.get("poly")
                if poly and not sfx and len(poly) >= 3:
                    p.drawPolygon(QPolygonF(
                        [QPointF(float(px), float(py)) for px, py in poly]))
                elif b.get("shape") == "round" and not sfx:
                    p.drawEllipse(r)
                else:
                    p.drawRect(r)
                badge = QRectF(float(b["x"]), float(b["y"]),
                               float(bw), float(bh))
                p.fillRect(badge, col)
                p.setPen(QPen(QColor(255, 255, 255)))
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(i))
        finally:
            p.end()
        return img.save(path, "PNG")

    def canvasChanged(self, canvas):
        pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register():
    instance = Krita.instance()
    factory = DockWidgetFactory(
        "typer_kr",
        DockWidgetFactoryBase.DockPosition.DockRight,
        TyperDocker,
    )
    instance.addDockWidgetFactory(factory)
    # Pre-register a small pool of host dockers so detached panels can live in
    # a real Krita-dockable window. Krita only shows dockers registered here at
    # startup, hence the fixed pool; empty hosts just sit in the Dockers menu.
    for slot in range(MAX_DETACH_SLOTS):
        cls = type("TyperExtraHost%d" % (slot + 1),
                   (TyperExtraHost,), {"_SLOT": slot})
        instance.addDockWidgetFactory(DockWidgetFactory(
            "typer_extra_%d" % (slot + 1),
            DockWidgetFactoryBase.DockPosition.DockRight,
            cls,
        ))
