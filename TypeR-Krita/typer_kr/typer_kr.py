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
import re
import json
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QFontMetricsF, QPainter, QPainterPath,
                         QBrush, QPen, QTextCursor)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QPlainTextEdit, QSpinBox, QCheckBox, QFileDialog, QColorDialog,
    QMessageBox, QSizePolicy, QFrame, QLineEdit, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox,
    QInputDialog, QScrollArea, QTabBar, QTabWidget, QToolButton, QMenu,
    QDialog, QButtonGroup,
)
from PyQt5.QtGui import QFontDatabase

from krita import DockWidget, DockWidgetFactory, DockWidgetFactoryBase, Krita

from . import layout as L
from . import langpair as LP


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
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoScrollSpinBox(QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class ScriptTabBar(QTabBar):
    """Tab bar for the loaded scripts. Adds browser-style middle-click-to-close
    on top of the normal close button."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
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
        "load_btn": "Load script (.docx / .xlsx / .odt / .txt)",
        "script_label": "Script (load a file or paste directly):",
        "editor_ph": "Paste the script here, or load a file above …",
        "skip_empty": "Skip empty lines",
        "analyze_btn": "Analyze · pair JP↔EN",
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
        "style": "Style:",
        "bold": "Bold",
        "italic": "Italic",
        "underline": "Underline",
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
        "st_preset_saved": "Preset ‘{name}’ saved.",
        "st_preset_applied": "Preset ‘{name}’ applied.",
        "st_preset_deleted": "Preset ‘{name}’ deleted.",
        "st_preset_none": "No preset selected.",
        "st_preset_name_empty": "Please enter a name.",
        "st_preset_exported": "Exported {n} preset(s).",
        "st_preset_imported": "Imported {n} preset(s).",
        "st_preset_import_fail": "Could not read the preset file.",
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
        "file_filter": "Scripts (*.docx *.xlsx *.xlsm *.odt *.txt *.md);;All files (*.*)",
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
        "tab_rename_prompt": "Tab name:",
        "st_nothing": "Nothing loaded. Paste a script and click ‘Analyze’.",
        "st_no_font": "No font selected.",
        "preview_empty": "(empty)",
        # main tabs
        "tab_type": "Type",
        "tab_style": "Style",
        "tab_presets": "Presets",
        "tab_setup": "Setup",
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
        "shaper_hint": "Click a shape to test it. Shift+number applies and advances.",
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
        "presets_by_char_tip": ("On: pick Manga → Character → preset – each "
                                "character can have its own font and style. "
                                "Off: pick Manga → preset – one flat list of "
                                "the manga's text presets (the character level "
                                "is hidden; new presets are stored under the "
                                "manga's default character)."),
    },
    "de": {
        "title": "TypeR für Krita",
        "language": "Sprache:",
        "load_btn": "Skript laden (.docx / .xlsx / .odt / .txt)",
        "script_label": "Skript (Datei laden oder direkt einfügen):",
        "editor_ph": "Hier das Skript einfügen oder oben eine Datei laden …",
        "skip_empty": "Leere Zeilen überspringen",
        "analyze_btn": "Analysieren · JP↔EN paaren",
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
        "style": "Stil:",
        "bold": "Fett",
        "italic": "Kursiv",
        "underline": "Unterstrichen",
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
        "st_preset_saved": "Preset ‚{name}‘ gespeichert.",
        "st_preset_applied": "Preset ‚{name}‘ angewendet.",
        "st_preset_deleted": "Preset ‚{name}‘ gelöscht.",
        "st_preset_none": "Kein Preset gewählt.",
        "st_preset_name_empty": "Bitte einen Namen eingeben.",
        "st_preset_exported": "{n} Preset(s) exportiert.",
        "st_preset_imported": "{n} Preset(s) importiert.",
        "st_preset_import_fail": "Preset-Datei konnte nicht gelesen werden.",
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
        "file_filter": "Skripte (*.docx *.xlsx *.xlsm *.odt *.txt *.md);;Alle Dateien (*.*)",
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
        "tab_rename_prompt": "Tab-Name:",
        "st_nothing": "Nichts geladen. Erst Skript einfügen und ‚Analysieren‘ klicken.",
        "st_no_font": "Keine Schrift gewählt.",
        "preview_empty": "(leer)",
        # main tabs
        "tab_type": "Setzen",
        "tab_style": "Stil",
        "tab_presets": "Presets",
        "tab_setup": "Einstellungen",
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
        "shaper_hint": "Klick testet eine Form. Umschalt+Zahl fügt ein und geht weiter.",
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
        "presets_by_char_tip": ("An: Manga → Charakter → Preset wählen – jeder "
                                "Charakter kann eigene Schrift und eigenen Stil "
                                "haben. Aus: Manga → Preset wählen – eine "
                                "flache Liste aller Text-Presets des Mangas "
                                "(die Charakter-Ebene ist ausgeblendet; neue "
                                "Presets landen beim Standard-Charakter des "
                                "Mangas)."),
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


def _text_element(text_lines, line_xs, y0, line_h, font_px, family,
                  fill_hex, stroke_hex=None, stroke_w=0.0,
                  bold=False, italic=False, underline=False, dx=0.0, dy=0.0):
    """text_lines: list of run lists ([(subtext, bold), ...] per line).
    line_xs: absolute LEFT x for each line. Lines are pre-centered/-aligned, so
    the element uses the default 'start' anchor – Krita's text tool keeps that
    absolute position when the shape is edited (a 'middle'/'end' anchor would be
    dropped and the text would snap to the corner). dx/dy shift the whole block
    (used for the offset shadow copy). Bold runs get font-weight='bold'."""
    tspans = []
    for i, runs in enumerate(text_lines):
        if not runs:
            continue
        x = line_xs[i] + dx
        y = y0 + dy + i * line_h
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
    if italic:
        attrs += ' font-style="italic"'
    if underline:
        attrs += ' text-decoration="underline"'
    if stroke_hex is not None and stroke_w > 0:
        attrs += (
            ' stroke="{s}" stroke-width="{w:.2f}" '
            'stroke-linejoin="round" stroke-linecap="round"'
        ).format(s=stroke_hex, w=stroke_w)
    return "<text {attrs}>{spans}</text>".format(attrs=attrs, spans="".join(tspans))


def _build_svg(text_lines, line_xs, y0, font_px, family, color, line_h, img_w, img_h,
               outline=False, outline_color=None, outline_px=0.0,
               bold=False, italic=False, underline=False,
               shadow=False, shadow_color=None, shadow_dx=0.0, shadow_dy=0.0):
    """SVG with optional shadow, optional outline and style (bold/italic/
    underline). Alignment is baked into `line_xs` (per-line absolute x) and the
    text uses the default 'start' anchor, so the inserted shape keeps its
    position when edited with Krita's text tool.

    Bottom-to-top order: shadow (offset copy), outline (thick line), fill.
    Everything is drawn as extra text copies so it works independently of the
    renderer (no filter/paint-order needed).
    """
    fill_hex = _hex(color)
    body = ""
    if shadow and shadow_color is not None and (shadow_dx or shadow_dy):
        sh = _hex(shadow_color)
        # the shadow takes the outline width so it keeps the full silhouette
        sw = 2.0 * outline_px if (outline and outline_px > 0) else 0.0
        body += _text_element(text_lines, line_xs, y0, line_h, font_px, family,
                              fill_hex=sh,
                              stroke_hex=(sh if sw > 0 else None), stroke_w=sw,
                              bold=bold, italic=italic, underline=underline,
                              dx=shadow_dx, dy=shadow_dy)
    if outline and outline_color is not None and outline_px > 0:
        ol = _hex(outline_color)
        body += _text_element(text_lines, line_xs, y0, line_h, font_px, family,
                              fill_hex=ol, stroke_hex=ol, stroke_w=2.0 * outline_px,
                              bold=bold, italic=italic, underline=underline)
    body += _text_element(text_lines, line_xs, y0, line_h, font_px, family,
                          fill_hex=fill_hex,
                          bold=bold, italic=italic, underline=underline)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="{w}" height="{h}">{body}</svg>'
    ).format(w=img_w, h=img_h, body=body)


def tidy_text(s):
    """Typographic clean-up: straight quotes -> curly quotes, ... -> …,
    -- -> —, multiple spaces -> one. Makes text look more professional
    without changing its content."""
    s = s.replace("...", "\u2026")
    s = re.sub(r"(?<!-)--(?!-)", "\u2014", s)
    # opening double quote after line start / whitespace / bracket
    s = re.sub(r'(^|[\s([{<\u2014])"', "\\1\u201c", s)
    s = s.replace('"', "\u201d")
    s = re.sub(r"(^|[\s([{<\u2014])'", "\\1\u2018", s)
    s = s.replace("'", "\u2019")
    s = re.sub(r"[ \t]{2,}", " ", s)
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


def prepare_text(line, case, tidy):
    """Prepare text before setting it (order: clean up, then letter case).

    case: "none" (unchanged), "upper" (UPPERCASE) or "lower" (lowercase).
    For backward compatibility case=True behaves like "upper", case=False like
    "none"."""
    out = line
    if tidy:
        out = tidy_text(out)
    if case is True or case == "upper":
        out = out.upper()
    elif case == "lower":
        out = out.lower()
    return out


ALIGN_ANCHOR = {"left": "start", "center": "middle", "right": "end"}


def _remove_existing_layers(doc, layer_index):
    """Remove the top-level layers that TypeR inserted earlier for the 1-based
    unit `layer_index` (matched by the exact 'TypeR NN — ' name prefix, so
    hand-made layers are never touched). Returns the number removed; never
    raises – a failed removal must not block the insert."""
    removed = 0
    try:
        root = doc.rootNode()
        for node in list(root.childNodes()):
            try:
                if L.is_typer_layer_name(node.name(), layer_index):
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
                      hyphenate=False, hyph_lang="en", replace_existing=False):
    """Insert a single line of text as a text layer.

    auto_fit=True: the line is wrapped automatically, balanced and scaled to the
    largest size that fits the current selection (= "where to"). Without a
    selection the whole image is used as the box.

    auto_fit=False: fixed size font_px, only split at embedded line breaks.

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

    line = prepare_text(line, case, tidy)
    line = line.replace("\r\n", "\n").replace("\r", "\n")
    clean, mask = parse_bold(line)
    if clean.strip() == "":
        return False, "st_empty_line", {}

    img_w = doc.width()
    img_h = doc.height()

    # determine the box + its center
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

    measurer = _make_measurer(font_family, line_spacing, bold, italic)

    if auto_fit:
        result = L.fit_text(clean, measurer, box_w, box_h, max_px, 6,
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

    # alignment: each line gets its own absolute left x (pre-centered/-aligned)
    # so the SVG can use the default 'start' anchor – this keeps the text in
    # place when it's later edited with Krita's text tool (text-anchor='middle'
    # was getting dropped, snapping the shape into the corner).
    width_of = measurer(font_px)[0]
    line_widths = [width_of(runs) for runs in text_lines]
    pad_x = box_w * padding_frac / 2.0
    line_xs = L.line_x_positions(
        line_widths, align, box_x + pad_x, cx, box_x + box_w - pad_x)

    y0 = L.vertical_start(valign, box_y, box_h, padding_frac,
                          len(text_lines), line_h, ascent, descent)
    svg = _build_svg(text_lines, line_xs, y0, font_px, font_family, color, line_h,
                     img_w, img_h, outline=outline, outline_color=outline_color,
                     outline_px=outline_px,
                     bold=bold, italic=italic, underline=underline,
                     shadow=shadow, shadow_color=shadow_color,
                     shadow_dx=shadow_dx, shadow_dy=shadow_dy)

    # replace mode: drop the layer(s) of an earlier insert of this unit first
    replaced = 0
    if replace_existing and layer_index is not None:
        replaced = _remove_existing_layers(doc, int(layer_index))

    try:
        root = doc.rootNode()
        snippet = (L.runs_text(text_lines[0])[:24] if text_lines else "").strip()
        if layer_index is not None:
            label = L.typer_layer_prefix(int(layer_index)) + snippet
        else:
            label = "TypeR — " + snippet
        vlayer = doc.createVectorLayer(label)
        root.addChildNode(vlayer, None)
        vlayer.addShapesFromSvg(svg)
        doc.refreshProjection()
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

    def __init__(self, recents=None, search_placeholder=""):
        super().__init__()
        self._all = list(QFontDatabase().families())
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
        self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setMinimumHeight(40)
        self.preview.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.preview)

        self._rebuild()

    # -- public API --

    def currentFamily(self):
        return self._current

    def setCurrentFamily(self, family):
        """Select a font programmatically (for presets). Make it visible if a
        filter is active."""
        if not family or family not in self._all:
            return
        self.search.blockSignals(True)
        self.search.setText("")
        self.search.blockSignals(False)
        self._apply_filter("")
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == family:
                self.list.setCurrentRow(i)
                self.list.scrollToItem(self.list.item(i))
                break

    def setRecents(self, recents):
        self._recents = [r for r in recents if r in self._all]

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
            item.setData(Qt.UserRole, fam)
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
            fam = item.data(Qt.UserRole)
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
        fam = current.data(Qt.UserRole)
        self._current = fam
        self.preview.setText(fam + "  –  AaBb 123")
        f = QFont(fam)
        f.setPixelSize(20)
        self.preview.setFont(f)


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
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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
            "spacing": d.spacing_spin.value() / 100.0,
            "size_ref": size_ref,
            "outline": d.outline_chk.isChecked(),
            "outline_color": QColor(d._outline_color),
            "outline_px": float(d.outline_spin.value()),
            "shadow": d.shadow_chk.isChecked(),
            "shadow_color": QColor(d._shadow_color),
            "shadow_dx": float(d.shadow_x_spin.value()),
            "shadow_dy": float(d.shadow_y_spin.value()),
            "hyphenate": d.hyph_chk.isChecked() and d.auto_chk.isChecked(),
            "hyph_lang": d._hyph_lang_for(self._text),
        }

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
        so the preview matches the inserted result."""
        lines = []
        for words in paras:
            if not words:
                lines.append([])
                continue
            cur, cur_w = [], 0.0
            queue = list(words)
            guard = 0
            while queue and guard < 100000:
                guard += 1
                wd = queue.pop(0)
                ww = self._word_w(wd, fmn, fmb, gbold)
                if not cur:
                    if ww <= avail_w:
                        cur, cur_w = [wd], ww
                    else:
                        res = (self._hyph_split(wd, avail_w, fmn, fmb, gbold, hyph)
                               if hyph else None)
                        if res:
                            left, right = res
                            lines.append([left])
                            queue.insert(0, right)
                            cur, cur_w = [], 0.0
                        else:
                            cur, cur_w = [wd], ww
                elif cur_w + space_w + ww <= avail_w:
                    cur.append(wd)
                    cur_w += space_w + ww
                else:
                    avail = avail_w - cur_w - space_w
                    res = (self._hyph_split(wd, avail, fmn, fmb, gbold, hyph)
                           if hyph else None)
                    if res:
                        left, right = res
                        cur.append(left)
                        lines.append(cur)
                        queue.insert(0, right)
                        cur, cur_w = [], 0.0
                    else:
                        lines.append(cur)
                        cur, cur_w = [wd], ww
            if cur:
                lines.append(cur)
        return lines

    def _fit(self, o, paras, avail_w, avail_h):
        """Largest integer pixel size at which the wrapped words fit.
        Returns (px, lines); lines is a list of word lists."""
        lo, hi, best = 6, 160, 6
        best_lines = [[]]
        hyph = o["hyph_lang"] if o.get("hyphenate") else None
        while lo <= hi:
            mid = (lo + hi) // 2
            fn, fb = self._fonts(o, mid)
            fmn, fmb = QFontMetricsF(fn), QFontMetricsF(fb)
            space_w = fmn.horizontalAdvance(" ")
            line_h = fmn.height() * o["spacing"]
            lines = self._wrap_words(paras, fmn, fmb, o["bold"], space_w,
                                     avail_w, hyph)
            total_h = line_h * len(lines)
            maxw = max((self._line_w(ws, fmn, fmb, o["bold"], space_w)
                        for ws in lines), default=0.0)
            if total_h <= avail_h and maxw <= avail_w:
                best, best_lines = mid, lines
                lo = mid + 1
            else:
                hi = mid - 1
        return best, best_lines

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        self._paint_background(p, w, h)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(0, 0, w - 1, h - 1)

        o = self._opts()
        prepared = prepare_text(self._text, o["case"], o["tidy"])
        prepared = prepared.replace("\r\n", "\n").replace("\r", "\n")
        clean, mask = parse_bold(prepared)
        if not clean.strip():
            p.setPen(QColor(0, 0, 0, 110))
            f = QFont()
            f.setItalic(True)
            f.setPixelSize(13)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter,
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
        fmn, fmb = QFontMetricsF(fn), QFontMetricsF(fb)
        space_w = fmn.horizontalAdvance(" ")
        line_h = fmn.height() * o["spacing"]
        ascent = fmn.ascent()
        block_h = line_h * len(lines)

        if o["valign"] == "top":
            y0 = m + ascent
        elif o["valign"] == "bottom":
            y0 = m + (avail_h - block_h) + ascent
        else:
            y0 = m + (avail_h - block_h) / 2.0 + ascent

        scale = fs / float(o["size_ref"])
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

        if o["shadow"]:
            sp = QPainterPath(path)
            sp.translate(o["shadow_dx"] * scale, o["shadow_dy"] * scale)
            p.fillPath(sp, QBrush(o["shadow_color"]))
        if o["outline"] and o["outline_px"] > 0:
            pen = QPen(o["outline_color"])
            pen.setWidthF(max(0.5, 2.0 * o["outline_px"] * scale))
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            p.strokePath(path, pen)
        p.fillPath(path, QBrush(o["color"]))
        p.end()

    def _paint_background(self, p, w, h):
        _paint_checker(p, w, h)


def _paint_checker(p, w, h):
    """Light-gray checkerboard (shows light and dark text colors well)."""
    p.fillRect(0, 0, w, h, QColor(0xEE, 0xEE, 0xEE))
    tile = 9
    p.setPen(Qt.NoPen)
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

class ShapeCard(QFrame):
    """One numbered thumbnail in the TextShapR grid: a fixed arrangement of the
    text (run lists per line) painted with the docker's current font/color/
    effects, scaled by the shared factor `scale` so all cards are comparable."""

    clicked = pyqtSignal(int)
    W, H = 200, 120

    def __init__(self, index, cand, opts, scale):
        super().__init__()
        self._index = index
        self._cand = cand
        self._o = opts
        self._scale = scale
        self._selected = False
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)

    def set_selected(self, on):
        if self._selected != bool(on):
            self._selected = bool(on)
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._index)
        super().mousePressEvent(event)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
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
        for i, runs in enumerate(lines):
            lw = run_w(runs)
            if o["align"] == "left":
                x = 6.0
            elif o["align"] == "right":
                x = w - 6.0 - lw
            else:
                x = (w - lw) / 2.0
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

        # same bottom-to-top order as the inserted layer: shadow, outline, fill
        if o["shadow"]:
            sp = QPainterPath(path)
            sp.translate(o["shadow_dx"] * s, o["shadow_dy"] * s)
            p.fillPath(sp, QBrush(o["shadow_color"]))
        if o["outline"] and o["outline_px"] > 0:
            pen = QPen(o["outline_color"])
            pen.setWidthF(max(0.5, 2.0 * o["outline_px"] * s))
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            p.strokePath(path, pen)
        p.fillPath(path, QBrush(o["color"]))

        # number badge (top-right) + selection frame
        p.setPen(QColor(0, 0, 0, 130))
        bf = QFont()
        bf.setPixelSize(11)
        p.setFont(bf)
        p.drawText(self.rect().adjusted(0, 3, -6, 0),
                   Qt.AlignRight | Qt.AlignTop, str(self._index + 1))
        frame = QPen(QColor(0x2D, 0x8C, 0xEB), 2) if self._selected \
            else QPen(QColor(0, 0, 0, 70), 1)
        p.setPen(frame)
        p.setBrush(Qt.NoBrush)
        p.drawRect(1, 1, w - 2, h - 2)
        p.end()


class TextShapRDialog(QDialog):
    """Modal picker: shows the current line wrapped into several candidate
    shapes (mode bar: Balanced / Round / Tall / Wide, plus a Hyphenation
    toggle) as numbered thumbnails. Click selects; Apply inserts the chosen
    arrangement through the normal insert path; Apply + next also advances.
    Number keys select a card, Shift+number applies and advances."""

    _MODES = ("balanced", "round", "tall", "wide")

    def __init__(self, docker):
        super().__init__(docker.widget())
        self._docker = docker
        t = docker._tr
        self.setWindowTitle(t("shaper_title"))
        self.resize(470, 620)

        lay = QVBoxLayout()
        self.setLayout(lay)

        bar = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for i, mode in enumerate(self._MODES):
            b = QPushButton(t("shaper_" + mode))
            b.setCheckable(True)
            if i == 0:
                b.setChecked(True)
            self._mode_group.addButton(b, i)
            bar.addWidget(b)
        self._mode_group.buttonClicked.connect(lambda *_a: self._refresh())
        # hyphenation is a toggle on top of the mode, not exclusive with it
        self.hyph_btn = QPushButton(t("shaper_hyph"))
        self.hyph_btn.setCheckable(True)
        self.hyph_btn.setChecked(docker.hyph_chk.isChecked())
        self.hyph_btn.toggled.connect(lambda *_a: self._refresh())
        bar.addWidget(self.hyph_btn)
        lay.addLayout(bar)

        self._grid_host = QWidget()
        self._grid = QGridLayout()
        self._grid.setSpacing(8)
        self._grid_host.setLayout(self._grid)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.StyledPanel)
        scroll.setWidget(self._grid_host)
        lay.addWidget(scroll, 1)

        self._empty = QLabel(t("shaper_empty"))
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignCenter)
        self._grid.addWidget(self._empty, 0, 0, 1, 2)

        self._hint = QLabel(t("shaper_hint"))
        self._hint.setStyleSheet("color: gray;")
        self._hint.setWordWrap(True)
        lay.addWidget(self._hint)

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.apply_btn = QPushButton(t("shaper_apply"))
        self.apply_btn.clicked.connect(lambda: self._apply(False))
        foot.addWidget(self.apply_btn)
        self.apply_next_btn = QPushButton(t("shaper_apply_next"))
        self.apply_next_btn.setDefault(True)
        self.apply_next_btn.clicked.connect(lambda: self._apply(True))
        foot.addWidget(self.apply_next_btn)
        self.close_btn = QPushButton(t("close"))
        self.close_btn.clicked.connect(self.reject)
        foot.addWidget(self.close_btn)
        lay.addLayout(foot)

        self._cards = []
        self._cands = []
        self._sel = -1
        self._refresh()

    # -- data --

    def _box(self):
        """Box to fit into: the selection, else the whole image, else a
        default box (no document open). Returns (w, h, has_doc)."""
        try:
            doc = Krita.instance().activeDocument()
        except Exception:
            doc = None
        if doc is None:
            return 400.0, 300.0, False
        sel = doc.selection()
        if sel is not None:
            try:
                w, h = float(sel.width()), float(sel.height())
                if w > 0 and h > 0:
                    return w, h, True
            except Exception:
                pass
        return float(doc.width()), float(doc.height()), True

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
            "shadow": d.shadow_chk.isChecked(),
            "shadow_color": QColor(d._shadow_color),
            "shadow_dx": float(d.shadow_x_spin.value()),
            "shadow_dy": float(d.shadow_y_spin.value()),
        }

    def _refresh(self):
        """Regenerate the candidates for the current line and rebuild the
        cards. Never raises; with no font/text it shows a hint instead."""
        d = self._docker
        for card in self._cards:
            self._grid.removeWidget(card)
            card.deleteLater()
        self._cards = []
        self._cands = []
        self._sel = -1

        family = d.font_picker.currentFamily()
        prepared = prepare_text(d._current_text(),
                                d.case_combo.currentData() or "none",
                                d.tidy_chk.isChecked())
        prepared = prepared.replace("\r\n", "\n").replace("\r", "\n")
        clean, mask = parse_bold(prepared)
        box_w, box_h, has_doc = self._box()

        if family and clean.strip():
            measurer = _make_measurer(family,
                                      d.spacing_spin.value() / 100.0,
                                      d.bold_chk.isChecked(),
                                      d.italic_chk.isChecked())
            mode = self._MODES[max(0, self._mode_group.checkedId())]
            try:
                self._cands = L.shape_candidates(
                    clean, measurer, box_w, box_h,
                    d.size_spin.value(), 6, d.pad_spin.value() / 100.0,
                    mode=mode, hyphenate=self.hyph_btn.isChecked(),
                    lang=d._hyph_lang_for(clean), mask=mask, limit=10)
            except Exception:
                self._cands = []

        have = bool(self._cands)
        self._empty.setVisible(not have)
        self.apply_btn.setEnabled(have)
        self.apply_next_btn.setEnabled(have)
        self._hint.setText(self._docker._tr(
            "shaper_hint" if has_doc else "shaper_no_doc"))
        if not have:
            return
        o = self._opts()
        # one shared scale so the size differences between shapes stay visible
        scale = min((ShapeCard.W - 12) / box_w, (ShapeCard.H - 12) / box_h)
        for i, cand in enumerate(self._cands):
            card = ShapeCard(i, cand, o, scale)
            card.clicked.connect(self._select)
            self._grid.addWidget(card, i // 2, i % 2)
            self._cards.append(card)
        self._select(0)

    # -- interaction --

    def _select(self, index):
        if not (0 <= index < len(self._cards)):
            return
        self._sel = index
        for i, card in enumerate(self._cards):
            card.set_selected(i == index)

    def _apply(self, advance):
        if not (0 <= self._sel < len(self._cands)):
            return
        ok = self._docker.insert_arrangement(self._cands[self._sel], advance)
        if ok and advance:
            self._refresh()        # show the shapes for the next line

    @staticmethod
    def _digit(event):
        """Digit 0-9 of a key event, robust against Shift (which turns the key
        into a symbol on most layouts). None if not a digit key."""
        vk = event.nativeVirtualKey()      # Windows/X11: VK stays '0'..'9'
        if 0x30 <= vk <= 0x39:
            return vk - 0x30
        k = event.key()
        if Qt.Key_0 <= k <= Qt.Key_9:
            return k - Qt.Key_0
        return None

    def keyPressEvent(self, event):
        digit = self._digit(event)
        if digit is not None:
            index = 9 if digit == 0 else digit - 1       # key 0 = card 10
            if 0 <= index < len(self._cards):
                self._select(index)
                if event.modifiers() & Qt.ShiftModifier:
                    self._apply(True)
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Docker UI
# ---------------------------------------------------------------------------

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
        self._shadow_color = QColor(0, 0, 0)
        self._lang = self._load_lang()
        self._groups = self._load_groups()
        self._group = ""
        self._char = ""
        self._script_path = ""             # file name of the active script
        self._preset_usage = self._load_preset_usage()
        # Multiple loaded scripts ("tabs"). Each session is a dict with a unique
        # id; the QTabBar stores that id as tab data, so tab order and the
        # session list stay decoupled (reordering tabs is harmless). The live
        # self._pairs/_index/_done/… always mirror the ACTIVE session and are
        # snapshotted back into it on every tab switch/close.
        self._sessions = []
        self._active_sid = None
        self._next_sid = 1

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
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(page)
            self.main_tabs.addTab(scroll, "")
            return lay

        lay_type = _page()       # everyday insert loop
        lay_style = _page()      # font variants, alignment, effects, fitting
        lay_presets = _page()    # manga -> character -> style presets
        lay_setup = _page()      # language + panel layout

        # --- language selector (Setup tab) ---
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
        lay_setup.addLayout(lang_row)

        # --- collapsible "Layout & sizes" panel ---
        # Lets the user resize or hide the big parts of the docker (preview,
        # script box, JP/EN table, font list) and remembers it across restarts.
        v = self._load_view()
        defaults = self._view_defaults()
        for k, dv in defaults.items():
            v.setdefault(k, dv)

        self.view_toggle = QPushButton()
        self.view_toggle.setCheckable(True)
        self.view_toggle.setChecked(bool(v["open"]))
        lay_setup.addWidget(self.view_toggle)

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
        view_grid.setColumnStretch(0, 1)
        view_lay.addLayout(view_grid)
        self.view_reset_btn = QPushButton()
        self.view_reset_btn.clicked.connect(self._on_view_reset)
        view_lay.addWidget(self.view_reset_btn)
        lay_setup.addWidget(self.view_box)
        # replace the layer(s) of an earlier insert when a line is re-inserted
        self.replace_chk = QCheckBox()
        self.replace_chk.setChecked(self._load_replace_existing())
        self.replace_chk.toggled.connect(self._on_replace_toggle)
        lay_setup.addWidget(self.replace_chk)
        # presets: with a character level (default) or one flat list per manga
        self.by_char_chk = QCheckBox()
        self.by_char_chk.setChecked(self._load_by_char())
        self.by_char_chk.toggled.connect(self._on_by_char_toggle)
        lay_setup.addWidget(self.by_char_chk)
        lay_setup.addStretch(1)
        self.view_box.setVisible(self.view_toggle.isChecked())

        # wire up after the initial values are set, so nothing fires early
        self.view_toggle.toggled.connect(self._on_view_toggle)
        for _w in (self.v_preview_chk, self.v_editor_chk, self.v_table_chk,
                   self.v_fonts_chk):
            _w.toggled.connect(self._on_view_changed)
        for _w in (self.v_preview_h, self.v_editor_h, self.v_table_h,
                   self.v_fonts_h):
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
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        preset_row.addWidget(self.preset_combo, 1)
        # the rarely-used preset actions live in one compact "⋯" menu instead
        # of two full button rows
        self.preset_menu_btn = QToolButton()
        self.preset_menu_btn.setText("⋯")
        self.preset_menu_btn.setPopupMode(QToolButton.InstantPopup)
        preset_menu = QMenu(self.preset_menu_btn)
        self.preset_save_act = preset_menu.addAction("")
        self.preset_save_act.triggered.connect(self.on_preset_save)
        self.preset_del_act = preset_menu.addAction("")
        self.preset_del_act.triggered.connect(self.on_preset_delete)
        preset_menu.addSeparator()
        self.preset_import_act = preset_menu.addAction("")
        self.preset_import_act.triggered.connect(self.on_preset_import)
        self.preset_export_act = preset_menu.addAction("")
        self.preset_export_act.triggered.connect(self.on_preset_export)
        self.preset_menu_btn.setMenu(preset_menu)
        preset_row.addWidget(self.preset_menu_btn)
        lay_presets.addLayout(preset_row)
        lay_presets.addStretch(1)

        # --- load a file (Type tab) ---
        self.load_btn = QPushButton()
        self.load_btn.clicked.connect(self.on_load)
        lay_type.addWidget(self.load_btn)

        # --- script input ---
        # Generously sized so the parsed/pasted script is easy to read and edit.
        self.lbl_script = QLabel()
        lay_type.addWidget(self.lbl_script)
        # Tabs for several loaded scripts (browser-style: closable + middle-click,
        # reorderable, eliding long names, with scroll buttons in a narrow dock).
        self.script_tabs = ScriptTabBar()
        self.script_tabs.setTabsClosable(True)
        self.script_tabs.setMovable(True)
        self.script_tabs.setExpanding(False)
        self.script_tabs.setDrawBase(False)
        self.script_tabs.setElideMode(Qt.ElideMiddle)
        self.script_tabs.setUsesScrollButtons(True)
        self.script_tabs.currentChanged.connect(self._on_tab_changed)
        self.script_tabs.tabCloseRequested.connect(self._close_tab)
        self.script_tabs.tabBarDoubleClicked.connect(self._rename_tab)
        lay_type.addWidget(self.script_tabs)
        self.editor = QPlainTextEdit()
        self.editor.setMinimumHeight(170)
        self.editor.setMaximumHeight(320)
        lay_type.addWidget(self.editor)

        opt_row = QHBoxLayout()
        self.skip_empty = QCheckBox()
        self.skip_empty.setChecked(True)
        self.skip_empty.stateChanged.connect(self.analyze)
        opt_row.addWidget(self.skip_empty)
        self.analyze_btn = QPushButton()
        self.analyze_btn.clicked.connect(self.analyze)
        opt_row.addWidget(self.analyze_btn)
        lay_type.addLayout(opt_row)

        lay_type.addWidget(self._hline())

        # --- two-column JP/EN view ---
        self.lbl_align = QLabel()
        lay_type.addWidget(self.lbl_align)
        self.table = QTableWidget(0, 2)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.itemSelectionChanged.connect(self._on_table_select)
        self.table.cellDoubleClicked.connect(self._on_table_double)
        lay_type.addWidget(self.table, 1)

        # --- navigation + preview ---
        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton()
        self.prev_btn.clicked.connect(self.on_prev)
        self.next_btn = QPushButton()
        self.next_btn.clicked.connect(self.on_next)
        self.reset_btn = QPushButton()
        self.reset_btn.clicked.connect(self.on_reset_progress)
        self.counter = QLabel("0 / 0")
        self.counter.setAlignment(Qt.AlignCenter)
        nav_row.addWidget(self.prev_btn)
        nav_row.addWidget(self.counter, 1)
        nav_row.addWidget(self.next_btn)
        nav_row.addWidget(self.reset_btn)
        lay_type.addLayout(nav_row)

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
        lay_type.addLayout(page_row)

        self.active_edit = QPlainTextEdit()
        self.active_edit.setMinimumHeight(42)
        self.active_edit.setMaximumHeight(70)
        self.active_edit.textChanged.connect(self._update_text_preview)
        lay_type.addWidget(self.active_edit)
        bold_row = QHBoxLayout()
        self.bold_sel_btn = QPushButton()
        self.bold_sel_btn.clicked.connect(self.on_bold_selection)
        bold_row.addWidget(self.bold_sel_btn)
        bold_row.addStretch(1)
        lay_type.addLayout(bold_row)
        self.lbl_preview = QLabel("")
        self.lbl_preview.setStyleSheet("color: gray; margin-top: 2px;")
        lay_type.addWidget(self.lbl_preview)
        self.preview = TextPreview(self)
        lay_type.addWidget(self.preview)
        self.jp_ref = QLabel("")
        self.jp_ref.setWordWrap(True)
        self.jp_ref.setStyleSheet("color: gray;")
        lay_type.addWidget(self.jp_ref)

        lay_type.addWidget(self._hline())

        # --- font picker + text color (the everyday choices stay on Type) ---
        self.lbl_font = QLabel()
        lay_type.addWidget(self.lbl_font)
        self.font_picker = FontPicker(self._load_recents(),
                                      self._tr("font_search_ph"))
        lay_type.addWidget(self.font_picker)
        color_row = QHBoxLayout()
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self.on_pick_color)
        color_row.addWidget(self.color_btn, 1)
        lay_type.addLayout(color_row)
        self._update_color_btn()

        # --- insert + TextShapR ---
        insert_row = QHBoxLayout()
        self.insert_btn = QPushButton()
        self.insert_btn.clicked.connect(self.on_insert)
        insert_row.addWidget(self.insert_btn, 1)
        self.shaper_btn = QPushButton()
        self.shaper_btn.clicked.connect(self.on_open_shaper)
        insert_row.addWidget(self.shaper_btn)
        lay_type.addLayout(insert_row)

        # --- font style (variant: bold/italic/underline)  (Style tab) ---
        style_row = QHBoxLayout()
        self.lbl_style = QLabel()
        style_row.addWidget(self.lbl_style)
        self.bold_chk = QCheckBox()
        self.italic_chk = QCheckBox()
        self.underline_chk = QCheckBox()
        style_row.addWidget(self.bold_chk)
        style_row.addWidget(self.italic_chk)
        style_row.addWidget(self.underline_chk)
        style_row.addStretch(1)
        lay_style.addLayout(style_row)

        # --- alignment + text processing ---
        align_row = QHBoxLayout()
        self.lbl_alignment = QLabel()
        align_row.addWidget(self.lbl_alignment)
        self.align_combo = NoScrollComboBox()
        for code in ("left", "center", "right"):
            self.align_combo.addItem("", code)
        self.align_combo.setCurrentIndex(1)  # center
        align_row.addWidget(self.align_combo, 1)
        lay_style.addLayout(align_row)

        valign_row = QHBoxLayout()
        self.lbl_valign = QLabel()
        valign_row.addWidget(self.lbl_valign)
        self.valign_combo = NoScrollComboBox()
        for code in ("top", "middle", "bottom"):
            self.valign_combo.addItem("", code)
        self.valign_combo.setCurrentIndex(1)  # middle
        valign_row.addWidget(self.valign_combo, 1)
        lay_style.addLayout(valign_row)

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
        lay_style.addLayout(text_row)

        # --- remaining style options ---
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
        self.spacing_spin.setRange(80, 250)
        self.spacing_spin.setValue(105)
        grid.addWidget(self.spacing_spin, 2, 1)
        lay_style.addLayout(grid)

        # --- outline: checkbox on the tab, color + width in a small popup ---
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
        self.outline_close_btn = QPushButton()
        self.outline_close_btn.clicked.connect(self.outline_dlg.accept)
        out_dlg_lay.addWidget(self.outline_close_btn)

        out_row = QHBoxLayout()
        self.outline_chk = QCheckBox()
        self.outline_chk.stateChanged.connect(self._on_outline_toggle)
        out_row.addWidget(self.outline_chk)
        self.outline_more_btn = QPushButton()
        self.outline_more_btn.clicked.connect(self.outline_dlg.show)
        out_row.addWidget(self.outline_more_btn)
        out_row.addStretch(1)
        lay_style.addLayout(out_row)
        self._update_outline_btn()

        # --- shadow: checkbox on the tab, color + offset in a small popup ---
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

        sh_row = QHBoxLayout()
        self.shadow_chk = QCheckBox()
        self.shadow_chk.stateChanged.connect(self._on_shadow_toggle)
        sh_row.addWidget(self.shadow_chk)
        self.shadow_more_btn = QPushButton()
        self.shadow_more_btn.clicked.connect(self.shadow_dlg.show)
        sh_row.addWidget(self.shadow_more_btn)
        sh_row.addStretch(1)
        lay_style.addLayout(sh_row)
        self._update_shadow_btn()

        # --- auto-fit ---
        self.auto_chk = QCheckBox()
        self.auto_chk.setChecked(True)
        self.auto_chk.stateChanged.connect(self._on_auto_toggle)
        lay_style.addWidget(self.auto_chk)

        self.round_chk = QCheckBox()
        self.round_chk.stateChanged.connect(self._on_auto_toggle)
        lay_style.addWidget(self.round_chk)

        # --- hyphenation (split long words at syllable points) ---
        self.hyph_chk = QCheckBox()
        self.hyph_chk.stateChanged.connect(self._on_hyph_toggle)
        lay_style.addWidget(self.hyph_chk)
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
        lay_style.addLayout(hyph_row)
        lay_style.addStretch(1)

        # status line below the tabs, always visible
        self.status = QLabel("")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        self.setWidget(main)

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
        self.main_tabs.setTabText(0, t("tab_type"))
        self.main_tabs.setTabText(1, t("tab_style"))
        self.main_tabs.setTabText(2, t("tab_presets"))
        self.main_tabs.setTabText(3, t("tab_setup"))
        self.lang_label.setText(t("language"))
        self.view_toggle.setText(t("view_toggle"))
        self.view_hint.setText(t("view_hint"))
        self.v_preview_chk.setText(t("view_preview"))
        self.v_editor_chk.setText(t("view_editor"))
        self.v_table_chk.setText(t("view_table"))
        self.v_fonts_chk.setText(t("view_fonts"))
        self.view_reset_btn.setText(t("view_reset"))
        self.load_btn.setText(t("load_btn"))
        self.lbl_script.setText(t("script_label"))
        self.editor.setPlaceholderText(t("editor_ph"))
        self.skip_empty.setText(t("skip_empty"))
        self.analyze_btn.setText(t("analyze_btn"))
        self.lbl_align.setText(t("align_label"))
        self.table.setHorizontalHeaderLabels([t("col_source"), t("col_translation")])
        self.prev_btn.setText(t("prev"))
        self.next_btn.setText(t("next"))
        self.reset_btn.setText(t("reset_btn"))
        self.lbl_page.setText(t("page_jump"))
        self.active_edit.setPlaceholderText(t("active_ph"))
        self.lbl_preview.setText(t("preview_label"))
        self._update_text_preview()
        self.lbl_font.setText(t("font"))
        self.font_picker.set_search_placeholder(t("font_search_ph"))
        self.lbl_style.setText(t("style"))
        self.bold_chk.setText(t("bold"))
        self.italic_chk.setText(t("italic"))
        self.underline_chk.setText(t("underline"))
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
        self.tidy_chk.setToolTip(t("tidy_tip"))
        self.round_chk.setText(t("round"))
        self.round_chk.setToolTip(t("round_tip"))
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
        self.outline_more_btn.setText(t("outline_more"))
        self.outline_dlg.setWindowTitle(t("outline"))
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
        self.shaper_btn.setText(t("shaper_btn"))
        self.shaper_btn.setToolTip(t("shaper_btn_tip"))
        self.replace_chk.setText(t("replace_existing"))
        self.replace_chk.setToolTip(t("replace_existing_tip"))
        self.by_char_chk.setText(t("presets_by_char"))
        self.by_char_chk.setToolTip(t("presets_by_char_tip"))
        # re-label the page combo / status in the new language
        self._refresh_pages_combo()

    # -- UI helpers --

    def _hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
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

    def _on_outline_toggle(self):
        on = self.outline_chk.isChecked()
        self.outline_color_btn.setEnabled(on)
        self.outline_spin.setEnabled(on)
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
        col = QColorDialog.getColor(self._shadow_color, self.widget(),
                                    self._tr("shadow_color_btn"))
        if col.isValid():
            self._shadow_color = col
            self._update_shadow_btn()

    def _set_status(self, msg, error=False):
        self.status.setStyleSheet("color: #c0392b;" if error else "color: gray;")
        self.status.setText(msg)

    # -- main tabs (remember the last-used one) --

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
                   self.v_table_h, self.v_fonts_h)
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
            "outline": self.outline_chk.isChecked(),
            "outline_w": self.outline_spin.value(),
            "bold": self.bold_chk.isChecked(),
            "italic": self.italic_chk.isChecked(),
            "underline": self.underline_chk.isChecked(),
            "align": self.align_combo.currentData() or "center",
            "valign": self.valign_combo.currentData() or "middle",
            "case": self.case_combo.currentData() or "none",
            "tidy": self.tidy_chk.isChecked(),
            "color": self._color.name(),
            "outline_color": self._outline_color.name(),
            "shadow": self.shadow_chk.isChecked(),
            "shadow_x": self.shadow_x_spin.value(),
            "shadow_y": self.shadow_y_spin.value(),
            "shadow_color": self._shadow_color.name(),
            "hyphenate": self.hyph_chk.isChecked(),
            "hyph_lang": self.hyph_lang_combo.currentData() or "auto",
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
            if "outline" in d:
                self.outline_chk.setChecked(bool(d["outline"]))
            if "outline_w" in d:
                self.outline_spin.setValue(int(d["outline_w"]))
            if "bold" in d:
                self.bold_chk.setChecked(bool(d["bold"]))
            if "italic" in d:
                self.italic_chk.setChecked(bool(d["italic"]))
            if "underline" in d:
                self.underline_chk.setChecked(bool(d["underline"]))
            if d.get("case") in ("none", "upper", "lower"):
                self.case_combo.setCurrentIndex(
                    {"none": 0, "upper": 1, "lower": 2}[d["case"]])
            elif "caps" in d:                       # old presets/settings
                self.case_combo.setCurrentIndex(1 if d["caps"] else 0)
            if "tidy" in d:
                self.tidy_chk.setChecked(bool(d["tidy"]))
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
        self._char = ""
        self._ensure_levels()
        self._save_groups()
        self._refresh_groups_combo()
        self._refresh_chars_combo()
        self._refresh_presets_combo()
        self._set_status(self._tr("st_group_deleted").format(name=g))

    # ---- Character level ----
    def _refresh_chars_combo(self, select=None):
        self._ensure_levels()
        self.char_combo.blockSignals(True)
        self.char_combo.clear()
        for ch in sorted(self._cur_chars().keys(), key=lambda s: s.lower()):
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
        self._refresh_chars_combo(select=name)
        self._refresh_presets_combo()
        self._set_status(self._tr("st_char_saved").format(name=name))

    def on_char_delete(self):
        ch = self.char_combo.currentData()
        if ch is None or ch not in self._cur_chars():
            self._set_status(self._tr("st_char_none"), error=True)
            return
        del self._groups[self._group][ch]
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
            for label, ch, name in LP.flatten_presets(self._cur_chars()):
                self.preset_combo.addItem(label, (ch, name))
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

    def on_preset_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self.widget(), self._tr("preset_file_open"),
            "", self._tr("preset_filter"))
        if not path:
            return
        try:
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
        self._set_status(self._tr("st_preset_imported").format(n=count))

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

    def _new_untitled(self):
        """Add an empty, unnamed script tab."""
        name = LP.unique_untitled([s["name"] for s in self._sessions],
                                  base=self._tr("tab_untitled"))
        self._add_session(name, "", "", do_analyze=False)

    def _init_first_session(self):
        """Ensure exactly one tab exists at startup."""
        if not self._sessions:
            self._new_untitled()

    def _on_tab_changed(self, tab_i):
        if tab_i < 0:
            return
        sid = self.script_tabs.tabData(tab_i)
        if sid is None or sid == self._active_sid:
            return
        self._snapshot_active()
        self._restore_by_sid(sid)

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
            return
        # activate whatever tab Qt now shows as current
        cur = self.script_tabs.currentIndex()
        self._active_sid = None            # force a full restore
        self._restore_by_sid(self.script_tabs.tabData(cur))

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

        self._add_session(LP.default_tab_label(path), path, text, do_analyze=True)
        self._set_status(self._tr("st_loaded").format(
            name=os.path.basename(path), n=len(self._pairs)))

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
        self._populate_table()
        self._refresh_pages_combo()
        self._refresh_view()

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._pairs))
        for r, (ja, en) in enumerate(self._pairs):
            self.table.setItem(r, 0, QTableWidgetItem(ja))
            self.table.setItem(r, 1, QTableWidgetItem(en))
        self.table.blockSignals(False)
        self.table.resizeRowsToContents()

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
        col = QColorDialog.getColor(self._color, self.widget(),
                                    self._tr("color_dlg"))
        if col.isValid():
            self._color = col
            self._update_color_btn()

    def on_pick_outline_color(self):
        col = QColorDialog.getColor(self._outline_color, self.widget(),
                                    self._tr("outline_color_dlg"))
        if col.isValid():
            self._outline_color = col
            self._update_outline_btn()

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

    def _hyph_lang_for(self, text):
        """Resolve the hyphenation language. An explicit choice wins. 'Auto'
        prefers the UI language (when its patterns are bundled), then a simple
        accent heuristic, then English."""
        code = self.hyph_lang_combo.currentData() or "auto"
        if code != "auto":
            return code
        if self._lang in L.HYPH_LANGS:
            return self._lang
        return self._accent_lang(text) or "en"

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
        cur.setPosition(max(0, ne), QTextCursor.KeepAnchor)
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
        except Exception:
            pass
        for chk in (self.bold_chk, self.italic_chk, self.underline_chk,
                    self.tidy_chk, self.outline_chk,
                    self.shadow_chk):
            chk.toggled.connect(lambda *a: self._update_text_preview())
        for combo in (self.align_combo, self.valign_combo, self.case_combo):
            combo.currentIndexChanged.connect(
                lambda *a: self._update_text_preview())
        for spin in (self.size_spin, self.pad_spin, self.spacing_spin,
                     self.outline_spin, self.shadow_x_spin, self.shadow_y_spin):
            spin.valueChanged.connect(lambda *a: self._update_text_preview())

    def on_insert(self):
        if not self._pairs:
            self._set_status(self._tr("st_nothing"), error=True)
            return
        family = self.font_picker.currentFamily()
        if not family:
            self._set_status(self._tr("st_no_font"), error=True)
            return
        text = self._current_text()
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
            "ellipse" if (self.auto_chk.isChecked()
                          and self.round_chk.isChecked()) else "rect",
            self.shadow_chk.isChecked(),
            self._shadow_color,
            self.shadow_x_spin.value(),
            self.shadow_y_spin.value(),
            self.valign_combo.currentData() or "middle",
            self._index + 1,
            hyphenate=self.hyph_chk.isChecked(),
            hyph_lang=self._hyph_lang_for(text),
            replace_existing=self.replace_chk.isChecked(),
        )
        self._set_status(self._insert_msg(key, fmt), error=not ok)
        if ok:
            self.font_picker.noteUsed(family)
            self._save_recents()
            self._save_settings()
            self._done.add(self._index)
            self._mark_done_row(self._index)
            if self._index < len(self._pairs) - 1:
                self._index += 1
            self._refresh_view()

    def _insert_msg(self, key, fmt):
        """Status message for an insert result; notes when old layer(s) of the
        same line were replaced."""
        msg = self._tr(key).format(**fmt)
        if fmt.get("replaced"):
            msg += "  " + self._tr("st_replaced")
        return msg

    def on_open_shaper(self):
        """Open the TextShapR picker for the current line."""
        dlg = TextShapRDialog(self)
        dlg.exec_()

    def insert_arrangement(self, cand, advance):
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
            replace_existing=self.replace_chk.isChecked(),
        )
        self._set_status(self._insert_msg(key, fmt), error=not ok)
        if ok:
            self.font_picker.noteUsed(family)
            self._save_recents()
            self._save_settings()
            if self._pairs:
                self._done.add(self._index)
                self._mark_done_row(self._index)
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

    def _refresh_view(self):
        self._show_current()
        # sync the table selection without feedback
        if self._pairs and 0 <= self._index < self.table.rowCount():
            self.table.blockSignals(True)
            self.table.selectRow(self._index)
            self.table.blockSignals(False)

    # mandatory override from DockWidget
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
