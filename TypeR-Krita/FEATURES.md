# TypeR — what is where, and how to switch it off

A map of the plugin, so you can find a feature by name instead of reading 8,000
lines. Everything here is ours, so there is no "fork marker" to grep for — this
file is the index instead.

Line numbers drift; the names don't. Grep the name, not the number.

## The shape of it

| File | Lines | What it is |
|---|---:|---|
| `typer_kr.py` | ~12,500 | The docker: all six tabs, the insert path, the UI strings |
| `layout.py` | ~1,740 | The typesetting engine. **Qt-free, so it is unit-tested** |
| `bubbles.py` | ~1,400 | BubblR: bubble detection + batch pairing |
| `balloons.py` | ~290 | Balloon shape library. Qt-free, tested |
| `texttypes.py` | ~330 | The 21 manga text kinds + their fonts/styles |
| `langpair.py` | ~790 | Script parsing, JP↔EN pairing, presets |
| `comments.py` / `gdocs.py` / `gauth.py` | ~750 | Script comments from Word/Google Docs |
| `sfx/` | ~3,400 | The SFX tab (MangaSFX, vendored as a sub-package) |
| `sfx/modes.py` | ~230 | The five SFX strategies + kana→romaji. Qt-free, tested |
| `sfx/rule_search.py` | ~110 | SFX keyword matching + rule search. Qt-free, tested |

**Run the tests:** `python test_typer_logic.py` in the parent folder. They cover
everything Qt-free and need neither Krita nor PyQt.

## Features

### Vertical text (tategaki)

Columns running top to bottom, right to left, for narrow bubbles and signs.

- Engine: `layout.py` → `vertical_measurer()`, `column_y_positions()`,
  `horizontal_start()`
- Emitted as SVG: `typer_kr.py` → `_text_element(vertical=True)` writes
  `writing-mode="vertical-rl" text-orientation="upright"`
- Insert path: `insert_text_layer(vertical=…)`
- Preview: `PreviewWidget._vertical_path()`, `_metrics()`, `_vem`
- UI: `vertical_chk` in the Style tab; setting key `"vertical"`

**To switch off:** hide `vertical_chk`. The engine is dormant unless it is
checked. TextShapR ignores it on purpose — its candidates are fitted
horizontally.

**⚠ Before touching the fitter:** a vertical run's length is `characters × font
size`, **not** the sum of glyph advances — "I" and "W" differ in width but stack
identically. Transposing the box without `vertical_measurer` measures the wrong
axis and quietly breaks wrap and auto-fit. That is what `vertical_measurer`'s
docstring is about.

### Balloon shape library

Eight shapes drawn straight into a detected bubble or the selection.

- Generator: `balloons.py` — `shape_points()`, `balloon_path()`, `tail_path()`,
  `balloon_svg()`; the shapes themselves are the `SHAPES` table
- UI: `typer_kr.py` → the "Balloon" panel (`balloon_combo`, `balloon_btn`,
  `on_insert_balloon`)

**To switch off:** drop the `_new_panel("balloon", "type")` block in `_build_ui`.
`balloons.py` has no other caller.

**To add a shape:** add one row to `SHAPES` (a radius-modulation function, a
sample count, smooth or not) plus `SHAPE_ORDER`, `SHAPE_FOR_TYPE` and a
`balloon_<id>` string. Nothing else knows about the list.

**⚠ Krita does not stack `addShapesFromSvg` shapes in document order.** You
cannot hide anything under anything by ordering the SVG — that is why the tail's
base follows the balloon's real outline instead of being a straight chord.

### SFX strategies

The five ways to handle a Japanese sound effect: ignore / romaji / note /
overlay / redraw.

- Core: `sfx/modes.py` — `STRATEGIES`, `to_romaji()`, `note_marker()`,
  `note_line()`
- UI: `sfx/sfx_docker.py` → `strategy_combo` at the top of the tab,
  `_on_strategy_changed()`, the note row, `_place_note_list()`
- Behaviour: `_insert_sfx()` branches on the strategy; `_effective_text()` is
  where romaji is derived

**To switch off:** drop the strategy row in `_build_ui` and make `_strategy()`
return `"redraw"` — that is the old behaviour exactly.

**Not ported to Photoshop.** `sfx-core/` and `photoshop-sfx-helper-cep/` do not
have this yet.

### SFX rule search

A search box above the rule list in "Font suggestions", so ~80 built-in rules
plus your own stay findable.

- Core: `sfx/rule_search.py` — `rule_matches_query()`, plus `normalize_sfx()`
  and `keyword_matches()` (they used to live in `sfx_docker.py`). **Qt-free,
  tested**
- UI: `sfx/sfx_docker.py` → `rule_search`, `_on_rule_search()`,
  `rule_count_lbl` / `_update_rule_count()`; `_rebuild_rules()` filters
- Searches keyword, font and group; several words are ANDed; `font:`, `group:`
  and `kw:` limit a word to one field; stretched spellings still hit
  (`BOOOOM!` → the *boom* rule); Esc clears the field

**It is a view filter only** — `_all_rules()`, the suggestions and everything
persisted ignore it. To switch off: drop the `rule_search` widget in
`_build_ui`; `_rule_query` then stays `""` and nothing is filtered.

### Text types

21 kinds of manga text (dialogue, whisper, shout, radio, …), each with font
candidates and a full style.

- `texttypes.py` → `TEXT_TYPES`, `resolve_font()`, `effective_font()`,
  `missing_font()`
- UI: the "Kind of text" picker in the Style tab; per-type font overrides in
  Setup (`TextTypeFontsDialog`, setting key `ttFonts`)

**To add a type:** one entry in `TEXT_TYPES` + a `tt_<id>` string. Fonts are
*named, not shipped* — `resolve_font()` picks the first installed candidate.

### Main characters

Per manga, a set of characters that head the dropdowns instead of sitting in
the middle of an alphabetical list.

- setting key `mainChars` → `{manga: [character, …]}`
- `langpair.py` → `sort_characters()`, `flatten_presets(chars, favorites)`
  (Qt-free, so the ordering is unit-tested without Krita)
- UI: right-click the character combo (`_char_context_menu`), or Setup →
  `MainCharsDialog`; both dropdowns get a ★ and a separator between the blocks

**View only.** No preset is moved, renamed or copied, item data stays the plain
character name, and deleting a character or manga drops its entry. Anything that
reads a combo must keep using `currentData()`, never `currentText()` — the text
now carries the star.

### Font bundles (favourites, presets, SFX presets)

Everything that can be exported and names a font ships the font files with it,
so the receiving machine has nothing left to install by hand:

- favourites → `fontfav_ui.py` `_export_favorites()` (`favourites.json` + `fonts/`)
- main presets → `typer_kr.py` `_export_presets_bundle()` (`presets.json` + `fonts/`),
  `.json` and `.xlsx` stay available in the format dialog
- SFX presets/rules → `sfx/sfx_docker.py` `_write_sfx_bundle()`
- import side installs per user, no admin: `fontfiles.install_fonts()`

**The lookup is name-table based, not registry based** (`fontfiles.py`). Windows
registers a font under the name its installer chose, one entry per file, which
missed every repacked family whose registered name differs from the family Krita
lists — and could never find a family's Bold/Italic files. `FontFileIndex` reads
name IDs 1/2/4/16 out of every installed font file (`.ttc`/`.otc` faces and all
languages included), matches wanted families through the `fontmatch` ladder plus
a prefix-trim fallback for variable-font instance names, and returns **all** files
of a family. `collect_font_files(families) -> ({family: [paths]}, missing)`.

Parsing ~9000 font files cold takes tens of seconds, so results are cached on
disk (`%LOCALAPPDATA%\TypeR-Krita\fontindex.json`, keyed by mtime+size); later
runs re-read only what changed. Bump `_CACHE_VERSION` when the parser's output
changes, or stale entries survive.

### TextShapR

The visual picker for line-break arrangements.

- `layout.py` → the candidate search; `typer_kr.py` → `TextShapRWidget`,
  `ShapeCard`, `insert_arrangement()`

**The ★ is score-based, not "biggest that fits".** `score_arrangement()`
(`layout.py`) ranks every candidate in every mode — including Round, which used
to sort by size first and so put a lower-scoring card in the ★ slot.
`_dedup_similar()` then collapses shapes with the same line count and relative
width profile so the grid shows distinct choices.

**Shape outweighs bulk, deliberately:** aspect 1.1 + balance 0.8 + step 0.6 +
break quality 0.5 = 3.0 against fill 1.15 + size 1.0 = 2.15. When size and fill
carried more (they used to), "biggest and fullest" won nearly every ranking and
the shape terms could only break ties.

Two things the earlier model got structurally wrong, both fixed:

- **Line count came from a constant** (`_LINE_TARGET = 4`, charged
  `abs(k-4) ** 1.5` uncapped). In a tall bubble that charge reached 2.8 points
  and made a 25 %-full block beat a 77 %-full one. It now comes from the
  geometry — `ideal_line_count()` solves `k = sqrt(total_w / (line_h * aspect))`,
  which is scale-free — clamped to the mode's band and capped at
  `_LINE_PEN_MAX`. The old `_TALL_WIDE_BIAS` (a linear reward for line count,
  which turned Tall mode into a ladder of one-word lines) is gone.
- **One profile for all modes.** `_PROFILES` now holds the line band, line
  target, reading measure and stub ratio per mode, as the Photoshop original's
  `PROFILE_PRESETS` does; this port had hard-coded that table's *balanced*
  column everywhere.

New terms: **rim clearance** (a block running edge to edge in either direction —
an area ratio cannot see it), **line-to-line step** (a tapering stack scores like
the triangle it is), **sentence breaks** (`a trap. Now` at a line end) and
**phrase integrity** (`No / way!` split when it would have fitted — charged only
when the split was avoidable, so a narrow bubble's forced one-word lines are not
punished).

**The bubble outline is sampled, not assumed.** `TextShapRWidget._sel_shape()`
returns the selection's silhouette as ~20 normalised row widths, passed down as
`shape_candidates(..., shape_rows=…)`. With it, fill is judged against the real
bubble area, rim clearance against the bubble's width at each line's own height,
and "even lines" means each line uses its share of the room it has — a lens in a
balloon, a rectangle in a caption box. The block's vertical band matters:
a short block sits in the balloon's widest part and is judged rectangular; only
a block spanning the bubble wants the lens. Absent (no selection, other callers)
everything behaves rectangularly, exactly as before.

**A starved set rescues itself.** When the best candidate fills less than
`_STARVED_FILL` of the bubble — one long unbreakable word — the width sweep is
retried with syllable breaks even if the user left hyphenation off; the hyphen
penalty keeps those out of the way whenever a clean shape exists.

`shapr_probe.py` (repo root) prints the ★ and the runners-up for a dozen real
bubble/script combinations with the score broken down per term — that is how the
above was diagnosed, and how to check a weight change.

The score also weighs **break quality** — a bonus for lines that end at clause
punctuation (`_CLAUSE_END`), a penalty for a line of only punctuation — a
**reading measure** (per mode) that penalises over-long lines even when they fit,
and a **no-stub-line** penalty for a short interior line.
`dehyphenate()` (the inverse of `hyphenate()`/`split_word()`)
rejoins a word the source split across a line ("embar- rassing" -> "embarrassing",
but "Spider- Man" -> "Spider-Man"), realigning the bold mask; pass
`shape_candidates(..., dehyphenate=True)` to run it before shaping. These three
were adapted from the Photoshop TypeR's TextShapeR scoring model.

**The pick survives a re-fit.** Changing size/spacing/mode re-runs the whole
candidate search, so the card list is rebuilt — but `refresh()` remembers the
chosen arrangement (`_cand_key()`, its lines as markup) and selects it again;
`_restore_index()` falls back to the same slot, and only to card 1 when the text
itself changed. A hand-edited arrangement (break editor) is kept in `_custom`,
re-fitted with `L.fit_fixed_lines()` and put back into its slot, marked ✎.

### Hyphenation

Splitting long words at real syllable points (bundled TeX patterns) so the text
can be set bigger in a narrow bubble.

- `layout.py` → `hyphenate()`, `split_word()`, `wrap_greedy()`
- UI: "Hyphenate long words" in the Style tab, the *Hyphenation* toggle in
  TextShapR; the preview mirrors it in `_wrap_words()`

Four rules make it usable in practice:

1. **Punctuation is not part of the word** (`_core_span()`). Without this,
   `EMBARRASSING!` was not a plain word and never hyphenated — the common case
   at the end of a line of dialogue.
2. **A hyphen the word already has IS the break** (`_INWORD_BREAK`). A compound
   is split on its own hyphens first and each part hyphenated separately, and
   the position after an existing hyphen is offered as a break in its own right;
   `split_word()` then adds no second hyphen. Feeding `Yagi-kun` to the syllable
   patterns whole gave `Yag-` / `i-kun` (the obvious break missed) and
   `well-known` gave `well--` / `known` (a break landing right after the hyphen).
   The de-hyphenator knows the same thing from the other side: a lowercase
   Japanese honorific keeps its hyphen (`_KEEP_HYPHEN_SUFFIX`), so `Yagi- kun`
   comes back as `Yagi-kun` and not `Yagikun`.
3. **One split per word** (`HYPH_MAX_WORD_SPLITS`) and **at most two hyphen
   lines in a row** (`HYPH_MAX_LADDER`). Otherwise a word ends up shredded
   (`EM- / BAR- / RASS- / ING!`); when a split is refused, the size search just
   settles one step smaller.
4. **A word too wide for the rest of the line is retried on its own line**, so
   it is split against the full width instead of overflowing unhyphenated.

### Balloon tools

Drawing the balloon itself (shape dropdown + tail + "Insert balloon"), not just
the text in it.

- `balloons.py` + the `_new_panel("balloon", "type")` block; `on_insert_balloon()`

**Off by default.** Setup > Experimental > "Enable balloon tools" (setting
`enableBalloon`, default `false`) hides the whole panel — most pages already
come with their balloons drawn. `_on_enable_balloon()` only hides the panel, so
its settings survive; because every layout move ends in `box.show()`,
`_sync_gated_panels()` re-applies the switch after each of them.

### BubblR (AI bubble detection)

- `bubbles.py`, `ai_backend.py`; UI in the BubblR tab

**The switch:** `BUBBLR_LOCKED` at the top of `typer_kr.py`. `True` forces the
toggle off and hides the tab. ⚠️ **Set it back to `True` before publishing to
`Krita-TypeR`** unless the AI is ready — it is `False` here for local use only.

### Batch placement — the Batch tab

Mark the bubbles, pair each with a script line, press one button, and the whole
page is typeset. The everyday loop (Type tab: select a bubble, Insert, next)
stays exactly as it was — this is the second route, for a page whose bubbles are
already marked.

**It has its own tab, on purpose.** Marking bubbles and filling them is not an
AI feature, so it must not require the BubblR tab: `enableBatch` is independent
of `enableBubblr`, the Batch tab carries its own marking tools and its own page
view, and detection appears there as one accelerator button. With BubblR
switched off entirely, nothing here is lost.

- Tab: `_build_batch_tab()`; panels `batch_mark`, `batch_overlay`,
  `bubblr_batch` (the pairing table + the run). Toggle: "Enable Batch tab" in
  Setup > Experimental
- Core (Qt-free, tested): `bubbles.py` → `regions_from_mask()`,
  `assign_units()`, `batch_pairs()`, plus the older `insert_gap()` /
  `remove_gap()` which finally have a caller
- Run: `on_bp_batch_start()` → `_bp_batch_tick()` → `_bp_batch_finish()`;
  `on_bp_batch_undo()` takes a run back
- Headless fitting: `TextShapRWidget.candidates_for()` and `_fit_params()`,
  split out of `refresh()` so the batch gets the same ★ pick the cards would
  show for a bubble that is not on screen

**⚠ Two views, one box list.** A Qt widget lives in one place at a time, so the
BubblR tab and the Batch tab each build their own `BubbleOverlay`
(`_new_bubble_overlay`, registered in `_bp_overlays`). They are *views*:
`_bp_boxes` stays the single owner, `_bp_refresh_overlay` and `_bp_set_page`
fan out to every view. Boxes belong to the page, not to a tab — two separate
lists would break "detect in BubblR, then fill in Batch" and leave the user
with two contradictory markings.

The same goes for the click modes. `_bp_mode_btns` maps a mode
(`order`/`sfx`/`shape`/`edit`) to *all* its buttons across the tabs;
`_bp_sync_mode_btns` keeps them showing the same state and `_bp_apply_mode`
holds the effect, so a mode cannot be on in one tab and off in the other while
both overlays share their boxes. Anything driving a mode goes through
`_on_bp_mode_toggle`, never through a single button.

**Marking the bubbles.** Detection fills the box list as before, but
"Add bubble from selection" now splits a selection into its **unconnected
parts**: hold Shift, drag the marquee over one balloon after another, and each
part becomes its own box (`_boxes_from_selection` → `regions_from_mask`). Krita
has exactly one selection, so without that split the bounding box would span the
whole page.

**Pairing.** "Assign lines" maps the lines 1:1 onto the boxes in reading order.
SFX boxes are passed over *without consuming a line*, so one sound effect in the
middle does not shift every following bubble by one. The table below is
editable: each row has the bubble, a line picker and the text, and "Insert gap"
/ "Remove gap" fix an off-by-one after a false detection. "This page only"
limits the range to the current page's units (`_page_unit_range`) — one image is
one page.

**Picking a line, four ways.** The per-row dropdown is the precise one; the
other three exist because a 200-line script makes it slow. Rows are
multi-selectable (`_bp_batch_rows` — selection, else the current row):
"Take current line" gives the selected bubbles the Type tab's current line and
the ones after it; "Assign by clicking" (`_bp_batch_line_clicked`, hooked into
`_on_table_select`) turns the Type tab's table into the picker — click a line,
it goes to the armed bubble and the batch steps to the next, skipping SFX
boxes; and the search box filters what the dropdowns offer. **A row's own line
always survives the filter**, or filtering would silently drop pairings.

**Style per line (opt-in, setting `batchStyle`).** Two extra columns — font and
preset — appear only when the checkbox is on, because on a page of ordinary
dialogue they are just in the way. Empty means "use the Type/Style tabs", which
is the behaviour without the feature. `_bp_style` holds one dict per *box*
(`{"font":…, "preset":…}`), and "Assign current style" / "Use current style"
stamp or clear the current style on the selected rows (those two string keys had
been sitting unused since the first import).

**⚠ A per-row style becomes the docker's real style for one bubble.** The whole
insert path reads the live controls, so `_bp_apply_row_style` applies the preset
through the normal `_apply_preset` and sets the font on the real picker; a
second style channel would mean a second copy of the Style tab. It runs *before*
the fitting, so the candidates already reflect it. The run remembers the user's
own settings (`_collect_settings` at start) and `_bp_batch_finish` restores them
— only when something was actually restyled, so an ordinary run costs nothing.
The font wins over the preset's font when a row names both.

**⚠ The run drives the normal insert path, it is not a second one.** Each step
puts the box into the *document selection* (`_select_box`) and then calls
`insert_arrangement(..., replace=True)`. Everything downstream — the fitter, the
round-bubble shape profile, `TypeR NN — ` naming, the green done marks, "match
size" — therefore behaves exactly as it does for a hand-placed line, and there
is no second code path to keep in sync. A round box becomes an *elliptical*
selection, so the text is fitted to the balloon and not to its corners.

**⚠ It is a chain of single-shot timers, not a loop.** `_bp_batch_tick` places
one bubble and re-arms itself (`_BATCH_TICK_MS`). A plain loop would freeze the
docker for the length of a whole page and make Stop unclickable.

**Review mode** parks on every bubble with the shape cards up instead of taking
the recommendation unattended; the run is continued by the *insert path itself*
(the hook at the end of `insert_arrangement`), so applying a shape by button,
"Apply + next" or a number key all work.

**Undo.** Krita's Python API cannot fold N inserts into one undo step, so
undoing a batch by hand would be N times Ctrl+Z. `on_bp_batch_undo()` instead
removes exactly the `TypeR NN — ` layers the run wrote
(`_remove_existing_layers` per unit) — shorter, and it cannot eat anything the
batch did not create.

**To switch off:** uncheck "Enable Batch tab" (the page widget is kept alive,
like every other hideable tab). To remove it from the code, drop
`_build_batch_tab` and its call, plus the `batch` entries in `_tab_layouts` and
`_tab_defaults`. The `bubbles.py` helpers have no other caller; the hook in
`insert_arrangement` is guarded by `self._bp_run is None` and does nothing
without the panel.

### SFX tab

MangaSFX is vendored as `typer_kr/sfx/` and hosted inside TypeR's SFX tab.

- `typer_kr.py` → `_sfx_docker`, the `_new_panel("sfx_panel", "sfx")` block
- Switch: "Enable SFX tab" in Setup > Experimental

### Script comments

Notes from a Word/Google-Docs script, shown against the line they belong to.

- `comments.py` (model + docx reader), `gdocs.py` (.gdoc → export/OAuth),
  `gauth.py` (OAuth PKCE)
- UI: the Google panel in Setup; the comments panel in the Type tab

**The default is the export path, not OAuth** — deliberately. `drive.readonly` is
a *restricted* scope: it needs an annual security audit and, unverified, caps the
project at 100 users for its lifetime. A Google .docx export keeps the comments
and its anchors are more precise anyway.

### TypeR Lab — the layout experiment (`typer_lab/`, a SEPARATE plugin)

Not part of TypeR. A second docker, "TypeR Lab (test)" in Settings > Dockers,
that answers one question: does the per-line work stop hurting if it all sits in
one view?

The measured problem it targets: three things you change **per line** — the kind
of text, the size, and bold/case/align — live in the *Style* tab while you work
in the *Type* tab. That is the tab ping-pong. (Setup/BubblR/TextShapR/SFX are
places you go on purpose; tabs suit them.)

What it does: the style controls become a three-row strip above the work zone,
and the per-line panels (`nav_line`, `jp_en_table`, `comments`, `active_field`,
`live_preview`, `insert`, `balloon`) follow underneath. The rest stays tabbed.

**It is not a copy.** It builds its own `TyperDocker` instance and re-hosts *that
instance's live widgets* — same QComboBox, same signals, same insert path, only
a different arrangement. So there is no second copy of the logic to keep in sync,
and the real TypeR cannot break: it is a different instance in a different
docker. (Same trick TypeR itself uses to host MangaSFX in its SFX tab.)

**To remove entirely:** delete `typer_lab/` and `typer_lab.desktop`. Nothing
references it.

**If it wins:** the strip's layout is the part worth moving into TypeR proper —
not this file.

## Conventions

- **Qt-free where possible.** `layout.py`, `balloons.py`, `texttypes.py`,
  `langpair.py`, `sfx/modes.py` import no Qt, which is what makes them testable
  without Krita. Keep it that way: if a function needs no widget, it does not
  belong in `typer_kr.py`.
- **Strings.** English is the source language in the `LANG` table; `_tr()` falls
  back to English per key, so a partial translation is fine. Add new keys to `en`
  and `de`; the other four inherit.
- **Panels.** Each panel is `_new_panel(id, tab)` + a `_PANEL_TITLES` entry, and
  the user can reorder or move them between tabs. Add a panel by copying that
  pattern; nothing else needs to know.
- **`insert_text_layer()`'s new parameters go at the END** — one call site passes
  positionally.
- **Deploying to the editor build:** copy the changed files into
  `C:\krita-dev\_install\share\krita\pykrita\typer_kr\` and delete `__pycache__`.
