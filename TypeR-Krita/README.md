# TypeR for Krita

A Krita docker for typesetting manga/comic translations. It recreates the core
of the Photoshop plugin *TypeR* as far as Krita's Python API allows: load a
translation script, step through it line by line, and drop each line into the
image as a text layer that auto-fits the speech bubble you selected.

The user interface is bilingual (**English / Deutsch**) and switchable at the
top of the docker; the choice is remembered between sessions.

> Only modules from the Python standard library are used (`zipfile`,
> `xml.etree`, …). Nothing extra has to be installed.

---

## Installation

1. Copy the `typer_kr` folder **and** `typer_kr.desktop` into Krita's
   `pykrita` resource folder:
   - Windows: `%APPDATA%\krita\pykrita\`
   - Linux: `~/.local/share/krita/pykrita/`
   - macOS: `~/Library/Application Support/krita/pykrita/`
2. Start Krita and enable the plugin under
   **Settings → Configure Krita → Python Plugin Manager → "TypeR for Krita"**.
3. Restart Krita and open the docker via **Settings → Dockers → TypeR for Krita**.

---

## Quick start (auto mode – recommended)

1. **Load a script** – Word `.docx`, Excel `.xlsx`, LibreOffice `.odt`, or
   `.txt`/`.md`. You can also paste text directly into the input box. The script
   is analyzed automatically on load (or click **Analyze**).
2. The table shows **Japanese (source)** and **Translation** side by side, so it
   is obvious which translation belongs to which line. Click a row to select it,
   or use **◀ Back** / **Next ▶**.
3. **Where:** select the speech bubble with a selection tool.
4. **Which font:** type in the search box, pick a font from the list (recently
   used fonts are pinned to the top with ★). Optionally choose a color.
5. **Insert translation.** The text wraps automatically, is balanced evenly and
   scaled to the largest size that fits – centered in the selection. The plugin
   then advances to the next unit.

---

## Multiple scripts (tabs)

You can keep several scripts open at once. Each loaded script gets its own
**tab** above the script box (browser-style):

- **Switch** tabs to work on a different script — its text, parsed JP/EN units,
  page navigation, current line and the green "done" marks are all kept per tab
  and restored instantly (the file is not re-read).
- Loading a file that's **already open** just jumps to its existing tab instead
  of opening it twice.
- **Close** a tab with its × (or middle-click), like a browser tab. Closing the
  last one leaves an empty *Untitled* tab.
- Tabs show the **file name**; **double-click** a tab to give it your own name.
  The full path is shown as a tooltip. Tabs can be dragged to reorder.

Not (yet) done: open tabs are **not** remembered across a Krita restart, and
re-running *Analyze* on a tab re-parses it and resets that tab's "done" marks.

## Pages ("Page N" markers)

Translation scripts usually separate the dialogue per manga page with a marker
line. When the script is read in, TypeR scans for the keyword **Page** and uses
those markers to track which page each line belongs to.

**Recognized marker formats** (case-insensitive, one per line):

```
Page 1
PAGE 01
Page1
--- Page 3 ---
[Page 5]
=== PAGE 12 ===
Page 4-5        (a spread)
Seite 7         (German keyword also works)
Page            (no number -> auto-numbered)
```

A line only counts as a marker when the whole line is essentially just the
keyword (plus an optional number and decoration). Normal dialogue such as
`Turn the page` or `Pages of history` is **not** mistaken for a marker.

**Page numbers are also sanity-checked.** Real page numbers never decrease, so
TypeR keeps only the markers that form an increasing sequence (preferring
consecutive pages). If a character on page 3 has a line that is literally
`Page 5` while the next real marker is `Page 4`, the out-of-order `Page 5` is
treated as ordinary dialogue rather than a page break.

What you get:

- A **page indicator** next to the navigation buttons shows the page of the
  current line, e.g. `Page 3 / 20`.
- A **Jump to page** dropdown lets you jump straight to the first line of any
  page.
- The marker lines themselves are kept out of the translation table, so only
  real dialogue units are listed.

If a script contains no `Page` markers, the page controls stay hidden and
everything else works exactly as before.

---

## Different script styles

Translation scripts are written in many different ways. TypeR normalizes the
common variations automatically, so nothing ends up shifted, doubled or with
stray markup inside a bubble:

- **Plain alternating lines** – Japanese line, then its English line, repeated
  (the typical `.txt`/`.docx` script). Paired directly.
- **Two-column spreadsheets** (`.xlsx`) – Japanese in one column, English in the
  next; cells are read left to right, top to bottom and paired the same way.
- **`JP` / `EN` column headers** – some scripts repeat a literal `JP` and `EN`
  header line under every page. These are recognized as headers and skipped, so
  they never appear as empty/garbled units.
- **Bubble-type prefixes** – scripts that tag each line with the kind of bubble,
  e.g. `{}: thought`, `“”: speech`, `(): whisper`, `[]: narration`, `//: note`,
  `SFX: sound`, `ST:`. The leading tag is stripped automatically, so only the
  real text goes into the bubble. Only this fixed set of tags is removed –
  genuine text like `Act93: Takaya` (where `Act93` is content) is left intact.
- **English-only scripts** – every line simply becomes its own unit; the
  Japanese column stays empty.
- **Speaker prefixes** – lines like `Sakamoto: Hi there`. With **Auto-character**
  enabled (checkbox under the character dropdown, on by default), if the speaker
  name matches one of your characters in the current manga, TypeR switches to
  that character and applies its first style preset – and removes the `Name:`
  prefix from the inserted text. A name that matches no character is left alone,
  so unrelated `Word:` lines are never touched.

> Edge case: if a script lays out a whole **block of Japanese followed by a
> block of English** (e.g. a character-profile box) instead of alternating line
> by line, the lines are still all present but may not pair up one-to-one. Use
> the editable active field / the JP reference to line them up.

---

## Features

- **Readers without character errors.** A `.docx`/`.odt`/`.xlsx` is really a ZIP
  of XML; TypeR parses it as real Unicode instead of plain text. For `.txt`
  several encodings are tried (UTF-8, Windows-1252, latin-1), so no single
  character can cause a read error. (The old binary `.doc`/`.xls` format is not
  supported – save as `.docx`/`.xlsx` or `.txt`.)
- **Japanese / English pairing.** Each line's language is detected
  (kana/kanji = Japanese, latin letters = English). Source and translation are
  paired automatically and the script's order (JA-first or EN-first) is detected
  on its own. Pure English scripts work too (the left column is then empty).
- **Fast font picker** that scales to thousands of fonts: an instant text
  filter, recently used fonts on top, and a preview only for the selected font.
- **Auto-fit** to the selection (size + wrapping), with **even line balancing**
  for a calm, oval block, and an optional **round-bubble (ellipse)** mode.
- **Automatic hyphenation** (new, optional): long words that don't fit are split
  at **linguistically correct syllable points** (with a “-”), so the text can
  reach a bigger size in narrow bubbles – e.g. `hy-phen-ation`, `type-set-ting`.
  Uses Liang's algorithm with bundled, freely-licensed TeX patterns for
  **English and German** (see *Hyphenation* below). Minimum 2 letters before / 3
  after a break; words under 5–6 letters are never split. Toggle it with the
  **“Hyphenate long words”** checkbox + a language dropdown (Auto / English /
  Deutsch). Off by default → exactly the old behavior.
- **Live preview** that renders the active line with the chosen font and every
  setting (color, outline, shadow, alignment, case, wrapping) in the same order
  as the inserted layer.
- **Styling:** bold / italic / underline, per-word bold via `**…**`, horizontal
  and vertical alignment, letter case (Normal / UPPERCASE / lowercase), smart
  punctuation, line spacing and inner padding.
- **Outline** and **drop shadow** for readability on busy backgrounds.
- **Presets** in three levels – **Manga → Character → style preset** – that can
  be saved, switched, imported and exported as `.json`.
- **Progress tracking:** inserted lines are marked green in the table; each
  layer gets a descriptive name like `TypeR 03 — DON'T MOVE`.
- Larger, comfortable **script input box** so a pasted/parsed script is easy to
  read and edit.
- **Adjustable layout** (see below) – resize or hide the bigger parts of the
  docker to taste.

---

## Layout & sizes (customizing the docker)

Everyone likes a different layout, so the big parts of the docker can be resized
or switched off. Click the **⚙ Layout & sizes** button near the top of the
docker to open a small panel where you can, for each of these parts:

- **Live preview**, **Script box**, **JP/EN table** and **Font list** –
- tick/untick the checkbox to **show or hide** it, and
- set its **height in pixels** with the spinner next to it.

For example, if you find the preview too tall, lower its height; if you don't
need it at all, untick it and it disappears completely. **Reset layout** puts
everything back to the defaults. Your choices are remembered across restarts.

The whole docker now lives in a scroll area, so shrinking or hiding parts never
squishes or clips anything – it just scrolls if the content is taller than the
panel.

---

## Workflow tips

- After analyzing, work bubble by bubble: the counter (e.g. `3 / 40 ✓ 5`), the
  table and the active field stay in sync.
- The **active text field** is editable – adjust the wording, or press **Enter**
  to insert a manual line break that is kept verbatim.
- **Insert** (button) or **double-click** a table row creates the layer and
  jumps to the next line.
- Turn off **Auto-fit** for a fixed size (centered in the selection/image,
  without automatic wrapping).

---

## Hyphenation

Hyphenation is **opt-in** (the “Hyphenate long words” checkbox, only active with
auto-fit). When on, a word that is wider than the line is split at a valid
syllable point and a “-” is added, which usually lets the whole text grow to a
noticeably bigger size in narrow bubbles. Bold/italic and per-word `**bold**`
are preserved across the split, and normal paragraphs keep their even balancing
(hyphenation only kicks in when a word truly doesn't fit).

The break points come from **Liang's algorithm** (the same method TeX,
LibreOffice and browsers use) together with the bundled pattern files in
`typer_kr/hyph/`:

| Language | File | Source / license |
| --- | --- | --- |
| English (US) | `hyph-en-us.pat.txt`, `.hyp.txt` | hyph-utf8 / tex-hyphen, © G. D. C. Kuiken – free redistribution permitted |
| German (1996) | `hyph-de-1996.pat.txt` | hyph-utf8 / tex-hyphen – MIT |
| Spanish | `hyph-es.pat.txt` | hyph-utf8 / tex-hyphen, © Javier Bezos – MIT/X11 |
| French | `hyph-fr.pat.txt` | hyph-utf8 / tex-hyphen – MIT |
| Portuguese | `hyph-pt.pat.txt`, `.hyp.txt` | hyph-utf8 / tex-hyphen – BSD 3-clause |
| Italian | `hyph-it.pat.txt` | hyph-utf8 / tex-hyphen, © C. Beccari – LPPL/MIT |

The full notices are in `typer_kr/hyph/LICENSE.txt`. Nothing needs to be
installed; everything ships with the plugin. Pick the language in the
**hyphenation language dropdown** (only languages with bundled patterns are
offered); “Auto” uses the interface language when its patterns exist, otherwise
a small accent heuristic, otherwise English.

---

## Project layout

| File | Purpose |
| --- | --- |
| `typer_kr/typer_kr.py` | Docker UI, readers, text-layer insertion |
| `typer_kr/langpair.py` | Language detection, JP/EN pairing, **Page** markers |
| `typer_kr/layout.py` | Pure layout logic: wrapping, balancing, ellipse fit, **hyphenation** |
| `typer_kr/hyph/` | Bundled, freely-licensed hyphenation patterns + LICENSE |
| `typer_kr/__init__.py` | Registers the docker with Krita |
| `typer_kr/Manual.html` | In-app manual (shown by Krita's plugin manager) |
| `typer_kr.desktop` | Krita plugin descriptor |

All code comments and docstrings are in English. The user interface is
available in **English, German, Spanish, French, Portuguese and Italian**
(switchable at the top of the docker). English and German are fully translated;
the other languages cover the core/most-visible strings and **fall back to
English** for the rest, so the UI is always complete — native-speaker review is
welcome to finish them. Adding a language = add a block to the `LANG` dict in
`typer_kr.py` and an entry to `LANG_ORDER`.
