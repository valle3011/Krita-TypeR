# -*- coding: utf-8 -*-
"""What changed in each version, and which of it a user has not seen yet.

A Krita plugin updates by having its files overwritten, so there is no moment
at which anything could announce itself. The docker therefore compares the
version it ships with against the last one it recorded having shown, and the
first time Krita is started after an update it says what is new.

Kept Qt-free and apart from the docker so the list is easy to extend and the
"which entries are new" rule can be tested on its own. Entries are newest
first, and each carries both interface languages, like the rest of the plugin.
"""

#: [(version, {lang: [line, ...]}), ...] - newest first.
CHANGELOG = [
    ("1.16", {
        "en": [
            "A Swap tab: once the cleans arrive, lift the finished "
            "typesetting off the raws onto them. Point it at the two "
            "folders, check the table \u2014 pages pair by the number "
            "in their name, and each row says what will happen before "
            "anything is written \u2014 and transfer. Only the bottom "
            "layer of each .kra is replaced; text, vectors, masks and "
            "effects are copied byte for byte. A smaller clean is "
            "refused unless you allow scaling, and a PNG per page is "
            "optional (rendered by Krita).",
        ],
        "de": [
            "Ein Swap-Reiter: Wenn die Cleans fertig sind, hebt er das "
            "fertige Typesetting von den Raws auf sie her\u00fcber. "
            "Beide Ordner angeben, Tabelle pr\u00fcfen \u2014 "
            "gepaart wird \u00fcber die Seitenzahl im Dateinamen, und "
            "jede Zeile sagt vorher, was passieren wird \u2014 dann "
            "\u00fcbertragen. Ersetzt wird nur die unterste Ebene "
            "jeder .kra; Text, Vektoren, Masken und Effekte kommen "
            "byteweise mit. Ein kleineres Clean wird abgelehnt, solange "
            "du Skalieren nicht erlaubst, und ein PNG pro Seite ist "
            "optional (von Krita gerendert).",
        ],
    }),
    ("1.15", {
        "en": [
            "The docker says when a newer TypeR has been published: a "
            "small line next to the build stamp, bottom right, linking "
            "to the project page. Looked up in the background at most "
            "once a day; nothing is sent but the request, and a failed "
            "check stays quiet. Switch it off under Setup if you would "
            "rather it did not ask.",
        ],
        "de": [
            "Der Docker sagt, wenn ein neueres TypeR ver\u00f6ffentlicht "
            "wurde: eine kleine Zeile unten rechts neben dem "
            "Build-Wert, verlinkt auf die Projektseite. Wird im "
            "Hintergrund nachgesehen, h\u00f6chstens einmal am Tag; "
            "\u00fcbertragen wird nichts au\u00dfer der Anfrage, und schl\u00e4gt "
            "sie fehl, bleibt es still. Unter Einstellungen "
            "abschaltbar.",
        ],
    }),
    ("1.14", {
        "en": [
            "The Fonts tab can preview your own text: type a line into "
            "the new \u201cPreview:\u201d field and every font in the list is "
            "drawn with it, so you can see which font suits that line "
            "rather than which one flatters its own name. Empty shows "
            "each font\u2019s name as before, and the name stays readable "
            "in grey behind the sample.",
        ],
        "de": [
            "Der Fonts-Reiter kann deinen eigenen Text zeigen: tipp eine "
            "Zeile in das neue Feld \u201eVorschau:\u201c, und jede Schrift in "
            "der Liste wird damit gezeichnet \u2014 so siehst du, welche "
            "Schrift zu dieser Zeile passt, statt welche ihren eigenen "
            "Namen gut aussehen l\u00e4sst. Leer zeigt wie bisher den Namen "
            "jeder Schrift, und der Name bleibt grau hinter der "
            "Vorschau lesbar.",
        ],
    }),
    ("1.13", {
        "en": [
            "Scripts can be loaded straight from a PDF. A two-column JP/EN "
            "table arrives already paired, and \u201cPage 3\u201d lines are picked up "
            "as page markers as usual. Text that wraps inside a table "
            "cell is joined back into one line. Pages that are scans "
            "have no text to read and say so \u2014 those need OCR first.",
        ],
        "de": [
            "Skripte lassen sich direkt aus einem PDF laden. Eine "
            "zweispaltige JP/EN-Tabelle kommt schon gepaart an, und "
            "\u201ePage 3\u201c-Zeilen werden wie gewohnt als Seitenmarken erkannt. "
            "Text, der in einer Tabellenzelle umbricht, wird wieder zu "
            "einer Zeile zusammengefasst. Seiten, die Scans sind, "
            "enthalten keinen Text und sagen das \u2014 die brauchen "
            "erst OCR.",
        ],
    }),
    ("1.12", {
        "en": [
            "Preset keybinds: give a style a key and press it when the "
            "speaker changes, instead of walking the character and preset "
            "dropdowns. The field sits under the preset list.",
            "A keybind can combine keys the way Ctrl+C does — and ordinary "
            "letters count, so A+B means hold A and press B. The order "
            "matters, so B+A is a different keybind.",
            "A for Akarie and A+B for Akarie bold can both be bound: holding "
            "A applies Akarie at once, adding B switches to the bold one.",
            "Keybinds belong to the manga, so the same few keys are free "
            "again in the next series.",
            "Google Docs scripts load again. Drive stopped letting any "
            "program read a .gdoc, so TypeR now looks the document up in the "
            "Drive client's own index, and asks for the link if that comes up "
            "empty.",
        ],
        "de": [
            "Tastenkürzel für Presets: gib einem Stil eine Taste und drück "
            "sie, wenn die sprechende Figur wechselt, statt durch die "
            "Auswahllisten zu klicken. Das Feld steht unter der Preset-Liste.",
            "Ein Kürzel kann Tasten kombinieren wie Strg+C — und normale "
            "Buchstaben zählen mit: A+B heißt A halten und B drücken. Die "
            "Reihenfolge zählt, B+A ist ein anderes Kürzel.",
            "A für Akarie und A+B für Akarie fett lassen sich beide belegen: "
            "A halten wendet sofort Akarie an, B dazu schaltet auf fett.",
            "Kürzel gehören zum Manga — in der nächsten Serie sind dieselben "
            "Tasten wieder frei.",
            "Google-Docs-Skripte laden wieder. Drive lässt eine .gdoc von "
            "keinem Programm mehr lesen, also schlägt TypeR das Dokument im "
            "lokalen Drive-Index nach — und fragt nach dem Link, wenn das "
            "nichts findet.",
        ],
    }),
    ("1.11", {
        "en": [
            "Batch tab: mark a page's bubbles, pair each with its line and "
            "fill them all in one run, each fitted with the shape TextShapR "
            "recommends. With a review mode that stops at every bubble, "
            "optional per-line font and preset overrides, and an Undo batch "
            "that removes exactly what the run created.",
            "Runs on Krita 6: the Qt binding is chosen at startup (PyQt6 on "
            "Krita 6.0+, PyQt5 on 5.x), so the same install works on both. "
            "The Setup tab shows which one was detected.",
            "Fonts are found by reading the font files themselves instead of "
            "the Windows registry, so repacked families and a family's Bold "
            "and Italic cuts are found at last — and a name that is spelled a "
            "little differently still reaches its font.",
            "TextShapR takes its line count from the bubble's shape rather "
            "than a fixed number, and ranks the candidates by how well they "
            "read.",
            "Main characters: mark the few who speak on every page and they "
            "head the character and preset dropdowns.",
            "Font bundles: favourites and presets export the actual font "
            "files alongside the JSON and install them on the other machine. "
            "Presets also export as an Excel table.",
        ],
        "de": [
            "Stapel-Reiter: die Bubbles einer Seite markieren, jeder ihre "
            "Zeile zuordnen und alle in einem Durchgang füllen — jede mit der "
            "Form, die TextShapR empfiehlt. Mit Prüfmodus, der an jeder "
            "Bubble hält, optionaler eigener Schrift und eigenem Preset pro "
            "Zeile, und einem Rückgängig, das genau die Ebenen des Durchgangs "
            "entfernt.",
            "Läuft auf Krita 6: die Qt-Anbindung wird beim Start gewählt "
            "(PyQt6 ab Krita 6.0, PyQt5 auf 5.x) — dieselbe Installation "
            "funktioniert auf beiden. Der Reiter Einstellungen zeigt, welche "
            "erkannt wurde.",
            "Schriften werden aus den Schriftdateien selbst gelesen statt aus "
            "der Windows-Registry. Dadurch werden umgepackte Familien und die "
            "Fett- und Kursiv-Schnitte einer Familie endlich gefunden — und "
            "ein leicht anders geschriebener Name findet trotzdem seine "
            "Schrift.",
            "TextShapR nimmt die Zeilenzahl aus der Form der Bubble statt aus "
            "einer festen Zahl und bewertet die Vorschläge danach, wie gut "
            "sie sich lesen.",
            "Hauptcharaktere: markier die paar, die auf jeder Seite reden — "
            "sie stehen dann oben in den Listen für Figur und Preset.",
            "Schrift-Pakete: Favoriten und Presets exportieren die "
            "Schriftdateien mit und installieren sie auf dem anderen Rechner. "
            "Presets lassen sich auch als Excel-Tabelle exportieren.",
        ],
    }),
    ("1.9", {
        "en": [
            "Fill a selection you drew yourself with a pattern or a gradient.",
            "Screentone gradients (dense to sparse) with a direction, plus "
            "diagonal, sand and sparkle screentones.",
            "TextShapR: the shape you pick stays picked — changing the size, "
            "font, colour or outline no longer silently reshapes it.",
            "Fonts tab: adjustable preview size, and a much faster list.",
        ],
        "de": [
            "Eine selbst gezogene Auswahl mit einem Muster oder Verlauf "
            "füllen.",
            "Rasterverläufe (dicht nach dünn) mit Richtung, dazu diagonale, "
            "Sand- und Funkel-Raster.",
            "TextShapR: die gewählte Form bleibt gewählt — Größe, Schrift, "
            "Farbe oder Kontur zu ändern formt sie nicht mehr stillschweigend "
            "um.",
            "Fonts-Reiter: einstellbare Vorschaugröße und eine deutlich "
            "schnellere Liste.",
        ],
    }),
    ("1.8", {
        "en": [
            "Style tab: pattern-filled and soft/blurred outlines, and a "
            "pattern fill for the text itself.",
            "Pattern generator and a pattern library: make one, name it, save "
            "it, pick it from thumbnails later.",
            "A “Missing fonts” window in Setup, listing what a script asks "
            "for that is not installed here.",
            "Fonts tab: one-click star and right-click categorise straight "
            "from the font picker.",
            "Fixed a scrambled main-tab order, including a one-time repair of "
            "an order that was already saved wrong.",
        ],
        "de": [
            "Stil-Reiter: musterfüllte und weiche Konturen, und eine "
            "Musterfüllung für den Text selbst.",
            "Mustergenerator und Musterbibliothek: eines bauen, benennen, "
            "speichern und später aus Miniaturbildern wählen.",
            "Fenster „Fehlende Schriften“ unter Einstellungen — es listet, "
            "was ein Skript verlangt und hier nicht installiert ist.",
            "Fonts-Reiter: mit einem Klick zum Favoriten machen und per "
            "Rechtsklick direkt in der Schriftauswahl einsortieren.",
            "Die durcheinandergeratene Reiter-Reihenfolge ist behoben — "
            "inklusive einmaliger Reparatur einer schon falsch gespeicherten.",
        ],
    }),
]


def parse_version(text):
    """A version as a tuple of numbers, for comparing: "1.11" -> (1, 11).

    Compared as numbers on purpose, because the scheme counts past nine:
    as text "1.9" would sort after "1.11". Anything unparsable is (), which
    compares lower than every real version.
    """
    out = []
    for part in str(text or "").strip().split("."):
        part = part.strip()
        if not part.isdigit():
            return tuple(out)
        out.append(int(part))
    return tuple(out)


def entries_since(seen, current, changelog=None):
    """The changelog entries between `seen` and `current`, newest first.

    An update that skips a version or two still gets told about all of them.
    Nothing is returned when `seen` is already at or past `current`, so the
    announcement happens exactly once per version - and `seen` being empty is
    the caller's decision to make, not this function's (see
    _whatsnew_baseline): here it simply means "has seen nothing", which shows
    everything.
    """
    lo = parse_version(seen)
    hi = parse_version(current)
    if not hi or lo >= hi:
        return []
    out = []
    for version, langs in (changelog if changelog is not None else CHANGELOG):
        v = parse_version(version)
        if lo < v <= hi:
            out.append((version, langs))
    out.sort(key=lambda e: parse_version(e[0]), reverse=True)
    return out


def lines_for(entries, lang):
    """[(version, [line, ...]), ...] in one language, falling back to English.

    A language that has not been translated yet must not turn the dialog into
    a blank box, which is the same rule the rest of the interface follows.
    """
    out = []
    for version, langs in entries:
        lines = langs.get(lang) or langs.get("en") or []
        if lines:
            out.append((version, [str(x) for x in lines]))
    return out
