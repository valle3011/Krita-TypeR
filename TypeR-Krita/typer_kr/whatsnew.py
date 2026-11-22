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
    ("1.22.7", {
        "en": [
            "Ctrl+Alt+C opens the text colour dialog. Choosing a colour "
            "is two clicks into a panel otherwise, and it is wanted in "
            "the middle of a page rather than at the start of one. "
            "Krita's own Ctrl+Alt+C (canvas size) loses the key while "
            "the docker is up, and like every TypeR key it can be "
            "rebound in Setup.",
            "A font you find in the search window can be kept where you "
            "found it: right-click it and it goes into the Fonts tab's "
            "favourites. Until now the only thing you could do with a "
            "font you had just found was use it once - starring it "
            "meant leaving and finding it a second time. The window has "
            "the real Fonts panel on loan rather than a copy, so the "
            "starred list behind the tab bar is right the moment the "
            "menu closes.",
            "A brand-new installation is now told that TypeR listens "
            "for keys at all. One short window at the first start, "
            "Ctrl+Space as the example, and a button that goes straight "
            "to the full list in Setup - which is also the answer to "
            "how you make your own. Ctrl+Space because it is the only "
            "key that already works on a fresh install: the outline "
            "keys want a text layer and the preset keys want presets "
            "that do not exist yet.",
            "That window waits for a document and for a moment when "
            "nothing else wants answering, so it does not arrive on top "
            "of a dialog or while Krita is in the background - and it "
            "never comes twice. Nobody who already has TypeR is "
            "greeted, which would make it the one thing in the plugin "
            "nobody can check, so writing the word again into its "
            "setting asks for it once more.",
        ],
        "de": [
            "Strg+Alt+C öffnet den Textfarben-Dialog. Eine Farbe zu "
            "wählen sind sonst zwei Klicks in ein Panel hinein, und "
            "gebraucht wird sie mitten auf einer Seite, nicht am "
            "Anfang. Kritas eigenes Strg+Alt+C (Leinwandgröße) verliert "
            "die Taste, solange der Docker offen ist; wie jede "
            "TypeR-Taste ist sie in Setup umbelegbar.",
            "Eine Schrift, die du im Suchfenster findest, kannst du "
            "dort behalten, wo du sie gefunden hast: Rechtsklick, und "
            "sie wandert in die Favoriten des Fonts-Tabs. Bisher konnte "
            "man mit einer gerade gefundenen Schrift nur eines tun — "
            "sie einmal benutzen; für den Stern musste man das Fenster "
            "verlassen und sie ein zweites Mal suchen. Das Fenster hat "
            "den echten Fonts-Tab geliehen, keine Kopie, also stimmt "
            "die Liste hinter der Reiterleiste in dem Moment, in dem "
            "das Menü zugeht.",
            "Eine frisch installierte TypeR sagt jetzt überhaupt "
            "erstmal, dass sie auf Tasten hört. Ein kurzes Fenster beim "
            "ersten Start, Strg+Leertaste als Beispiel und ein Knopf "
            "direkt zur vollständigen Liste in Setup — die zugleich die "
            "Antwort darauf ist, wie man eigene vergibt. "
            "Strg+Leertaste, weil es die einzige Taste ist, die auf "
            "einer frischen Installation schon stimmt: die Konturtasten "
            "brauchen eine Textebene, die Preset-Tasten brauchen "
            "Presets, die es noch nicht gibt.",
            "Dieses Fenster wartet auf ein Dokument und auf einen "
            "Moment, in dem nichts anderes beantwortet werden will — es "
            "landet also nicht auf einem Dialog und nicht, während "
            "Krita im Hintergrund steht —, und es kommt kein zweites "
            "Mal. Wer TypeR schon hat, wird nie begrüßt, womit es das "
            "einzige wäre, das niemand prüfen kann: das Wort again in "
            "seine Einstellung geschrieben holt es noch einmal.",
        ],
    }),
    ("1.22.6", {
        "en": [
            "Six keys for the outlines, because switching one on and "
            "nudging its width is something you do over and over on one "
            "page and it meant opening a dialog every time. Ctrl+Alt+O "
            "turns the outline on and off, Ctrl+Alt+Up/Down makes it "
            "wider or narrower, and the same with Shift held does the "
            "second outline. All six are rebindable in Setup. The "
            "second outline has no switch of its own - 0 px is what off "
            "means there - so its toggle remembers the width it is "
            "switching away from and puts that back.",
            "The font window (Ctrl+Space) has three tabs now. Search is "
            "the list it always was. Fonts is the Fonts tab itself, "
            "lent to the window while it is open, so the fonts you "
            "starred and sorted into categories are a click away "
            "instead of a window away. Presets is new: pick a manga, "
            "pick a character, and there are the fonts they talk in, "
            "each with the preset it was saved in. That answers \u201cI "
            "want the font this character uses\u201d, which a list of "
            "family names cannot. A manga whose presets were saved "
            "without characters skips that middle column.",
            "Resting on one of those presets shows its hotkey, so the "
            "window also answers how to reach it without the mouse.",
            "The hotkey list in Setup has a search over it. It matches "
            "the key, what it does and which manga it belongs to all at "
            "once, and the key in both spellings - the stored "
            "Ctrl+Alt+O and the Strg+Alt+O you see. It says \u201c3 of "
            "97 keys match\u201d while you type, or that nothing is "
            "bound to it and the key is free, which is the question you "
            "were asking.",
            "Fixed: the confirmation added to deleting a preset went "
            "through a message box the automated tests could not "
            "answer, and they had been stopping at that point ever "
            "since without saying so. Every confirmation in the docker "
            "goes through one place now, which a test can answer - and "
            "what each answer does is tested both ways.",
        ],
        "de": [
            "Sechs Tasten für die Konturen, weil eine anzuschalten und "
            "in der Breite nachzuziehen etwas ist, das man auf einer "
            "Seite immer wieder tut — und dafür jedes Mal ein Fenster "
            "aufgehen musste. Strg+Alt+O schaltet die Kontur an und "
            "aus, Strg+Alt+Hoch/Runter macht sie breiter oder schmaler, "
            "dasselbe mit Umschalt gilt der zweiten Kontur. Alle sechs "
            "sind in Setup umbelegbar. Die zweite Kontur hat keinen "
            "eigenen Schalter — dort heißt 0 px aus —, deshalb merkt "
            "sich ihr Umschalter die Breite, von der er wegschaltet, "
            "und legt sie zurück.",
            "Das Schriftfenster (Strg+Leertaste) hat jetzt drei Reiter. "
            "Suche ist die Liste, die es immer war. Schriften ist der "
            "Fonts-Tab selbst, dem Fenster geliehen, solange es offen "
            "ist — die Schriften, die du mit Stern und Kategorien "
            "sortiert hast, sind also einen Klick entfernt statt ein "
            "Fenster. Presets ist neu: Manga auswählen, Charakter "
            "auswählen, und da stehen die Schriften, in denen er "
            "spricht, jede mit dem Preset, in dem sie gespeichert "
            "wurde. Das beantwortet „ich will die Schrift, die dieser "
            "Charakter benutzt“ — was eine Liste von Schriftnamen nicht "
            "kann. Bei einem Manga, dessen Presets ohne Charaktere "
            "gespeichert sind, fällt die mittlere Spalte weg.",
            "Wer auf so einem Preset verweilt, sieht dessen Hotkey — "
            "das Fenster sagt also auch, wie man ohne Maus dorthin "
            "kommt.",
            "Über der Hotkey-Liste in Setup steht eine Suche. Sie "
            "trifft Taste, Bedeutung und Manga gleichzeitig, und die "
            "Taste in beiden Schreibweisen — dem gespeicherten "
            "Ctrl+Alt+O und dem Strg+Alt+O, das du siehst. Während du "
            "tippst steht darunter „3 von 97 Tasten passen“ oder eben, "
            "dass nichts darauf liegt und die Taste frei ist — also "
            "genau die Frage, die man gestellt hat.",
            "Behoben: die Rückfrage vor dem Löschen eines Presets lief "
            "über ein Meldungsfenster, das die automatischen Tests "
            "nicht beantworten konnten — und sie blieben seitdem an "
            "dieser Stelle stehen, ohne es zu sagen. Jede Rückfrage im "
            "Docker geht jetzt durch eine einzige Stelle, die ein Test "
            "beantworten kann, und was jede Antwort bewirkt, ist in "
            "beide Richtungen geprüft.",
        ],
    }),
    ("1.22.5", {
        "en": [
            "TextShapR recommends a better shape, and this time it was "
            "measured rather than judged by eye. 1238 lettered blocks "
            "out of eleven finished chapters were handed back to the "
            "shaper, and the question asked of each was: where does the "
            "arrangement the letterer actually chose come out in the "
            "ranking? First for 36.1 % of them before this version, "
            "45.9 % after; in the top three for 81.3 % before and 86.6 "
            "% after.",
            "The one thing those pages said that no amount of looking "
            "at bubbles would have: the shaper wanted one line too few. "
            "Of the blocks where it disagreed, 86 % were an argument "
            "about the number of lines rather than where to break them, "
            "and nearly always it had picked exactly one line fewer. "
            "Geometry says how many lines of this height a bubble's "
            "proportions imply; a letterer also breaks for sense, and "
            "that almost always means more, shorter lines. The ideal "
            "leans half a line that way now.",
            "Fixed: where nothing on offer could fill the selection - a "
            "whole panel selected with the size left where it sits for "
            "speech bubbles - it recommended two long lines lost in the "
            "middle of it. Four of the judgements stop telling "
            "candidates apart at once in that case, and what was left "
            "paid a two-line stack for an absence, since two lines are "
            "trivially even and have no step between them to be ragged. "
            "A judgement with nothing to judge is no longer worth full "
            "marks, the line-count charge keeps its order past the "
            "point where it used to stop, and the shape of the block "
            "takes the weight the fill cannot use. None of it can touch "
            "a bubble the text does fill.",
            "The size is still the real answer for a selection that "
            "big: at 52 px nothing fills a whole panel, and the shaper "
            "is only picking the best of a bad set.",
        ],
        "de": [
            "TextShapR schlägt eine bessere Form vor — und diesmal ist "
            "das gemessen und nicht nach Augenmaß beurteilt. 1238 "
            "gesetzte Textblöcke aus elf fertigen Kapiteln sind an den "
            "Shaper zurückgegeben worden, mit der Frage: auf welchem "
            "Platz landet die Anordnung, die der Letterer tatsächlich "
            "gewählt hat? Vor dieser Version bei 36,1 % auf Platz eins, "
            "danach bei 45,9 %; unter den ersten drei vorher 81,3 %, "
            "danach 86,6 %.",
            "Das eine, was diese Seiten verraten haben und kein Blick "
            "auf Sprechblasen: dem Shaper fehlte eine Zeile. Von den "
            "Blöcken, bei denen er widersprach, ging es in 86 % um die "
            "*Anzahl* der Zeilen und nicht darum, wo umgebrochen wird — "
            "und fast immer hatte er genau eine Zeile weniger gewählt. "
            "Die Geometrie sagt, wie viele Zeilen dieser Höhe die "
            "Proportionen einer Blase verlangen; ein Letterer bricht "
            "aber auch nach Sinn um, und das heißt fast immer mehr und "
            "kürzere Zeilen. Das Ideal neigt sich jetzt um eine halbe "
            "Zeile in diese Richtung.",
            "Behoben: wo nichts die Auswahl füllen konnte — ein ganzes "
            "Panel markiert, die Größe aber auf dem Wert für "
            "Sprechblasen — empfahl er zwei lange Zeilen, verloren in "
            "der Mitte. Vier der Bewertungen hören in dem Fall "
            "gleichzeitig auf zu unterscheiden, und was übrig blieb, "
            "bezahlte einen Zweizeiler für eine Abwesenheit: zwei "
            "Zeilen sind trivial ausgewogen und haben keinen "
            "Zeilensprung, der ungleichmäßig sein könnte. Eine "
            "Bewertung ohne Beweislage bekommt keine Bestnote mehr, die "
            "Zeilenzahl-Strafe behält ihre Reihenfolge über den Punkt "
            "hinaus, an dem sie früher stehenblieb, und die Form des "
            "Blocks übernimmt das Gewicht, das die Füllung nicht nutzen "
            "kann. Nichts davon kann eine Blase anfassen, die der Text "
            "füllt.",
            "Die Größe bleibt trotzdem die eigentliche Antwort bei so "
            "einer Auswahl: bei 52 px füllt nichts ein ganzes Panel, "
            "und der Shaper wählt nur das Beste aus einem schlechten "
            "Satz.",
        ],
    }),
    ("1.22.4", {
        "en": [
            "Nothing is deleted for good any more. Deleting a preset "
            "used to be one click with no question and no way back. It "
            "asks now - and whatever leaves the preset list is kept "
            "under “Setup → Recently deleted” with its manga, its "
            "character and the time it went, to be put back with one "
            "click. That holds for an import that overwrote a group or "
            "a reset just as much as for the delete button, because "
            "what is kept is whatever the list lost, however it lost "
            "it.",
            "Liquify follows the hand now. A cap stopped a point once "
            "it had moved 1.6 brush widths, so a stroke went dead a "
            "third of the way in - dragging five times as far and ten "
            "times as far gave the same picture - and using a wider "
            "brush elsewhere on the same letter silently rewrote the "
            "warp already there. The cap is gone.",
            "The force slider reads true. The dab sat at the end of its "
            "step, so the material was always behind the middle of the "
            "brush where the brush has least grip; at low force it fell "
            "out of the brush altogether. Measured as the share of the "
            "drag the material takes, the slider gave 2 / 6 / 17 / 41 / "
            "100 % at 10 / 25 / 50 / 75 / 100. It now gives 14 / 25 / "
            "47 / 82 / 100, and at full force the material goes exactly "
            "where the hand goes.",
            "A wide brush no longer shreds the letter. How finely the "
            "outline was walked came from the brush, so the widest "
            "brush - the one you reach for to make a soft bend - gave "
            "the coarsest outline and collapsed thin strokes into "
            "hairlines. It comes from the letter now. The ring under "
            "the pointer was also drawn a quarter too big; it is the "
            "size that really works. And Expand, Pinch and the twirls "
            "go on working while the hand is still, which they were "
            "always supposed to do.",
            "Fixed: pointing at a letter that another letter had been "
            "dragged across picked the wrong one. The letter was chosen "
            "by a square around its middle, so the box of the letter on "
            "top reached over its neighbour's ink - and the brush then "
            "said “nothing under the brush there” over ink you could "
            "plainly see, or quietly deformed the letter you were not "
            "pointing at. The ink decides now.",
        ],
        "de": [
            "Nichts wird mehr endgültig gelöscht. Ein Preset zu löschen "
            "war ein Klick ohne Nachfrage und ohne Weg zurück. Jetzt "
            "wird gefragt — und was aus der Preset-Liste verschwindet, "
            "liegt unter „Setup → Kürzlich gelöscht“ mit Manga, "
            "Charakter und Zeitpunkt und lässt sich mit einem Klick "
            "zurücklegen. Das gilt für einen Import, der eine Gruppe "
            "überschrieben hat, genauso wie für den Löschen-Knopf: "
            "aufgehoben wird, was die Liste verloren hat, egal wodurch.",
            "Verflüssigen folgt jetzt der Hand. Eine Grenze stoppte "
            "einen Punkt, sobald er 1,6 Pinselbreiten gewandert war — "
            "ein Strich war nach einem Drittel tot, fünfmal und zehnmal "
            "so weit ziehen ergab dasselbe Bild — und ein breiterer "
            "Pinsel anderswo am selben Buchstaben schrieb die "
            "bestehende Verformung stillschweigend um. Die Grenze ist "
            "weg.",
            "Der Kraftregler liest sich richtig. Der Pinselabdruck saß "
            "am Ende seines Schritts, das Material also immer hinter "
            "der Pinselmitte, wo der Pinsel am wenigsten greift; bei "
            "kleiner Kraft fiel es ganz aus dem Pinsel. Gemessen am "
            "Anteil des Zugwegs gab der Regler 2 / 6 / 17 / 41 / 100 % "
            "bei 10 / 25 / 50 / 75 / 100. Jetzt gibt er 14 / 25 / 47 / "
            "82 / 100, und bei voller Kraft geht das Material exakt "
            "dahin, wo die Hand hingeht.",
            "Ein breiter Pinsel zerfetzt den Buchstaben nicht mehr. Wie "
            "fein die Kontur abgelaufen wurde, kam vom Pinsel — der "
            "breiteste Pinsel, den man für eine weiche Biegung nimmt, "
            "gab also die gröbste Kontur und ließ dünne Striche zu "
            "Haarlinien zusammenfallen. Das kommt jetzt vom Buchstaben. "
            "Der Ring unter dem Zeiger war außerdem ein Viertel zu groß "
            "gezeichnet; er hat jetzt die Größe, die wirklich wirkt. "
            "Und Aufblasen, Einziehen und die Wirbel arbeiten weiter, "
            "während die Hand stillsteht — wie vorgesehen.",
            "Behoben: auf einen Buchstaben zu zeigen, über den ein "
            "anderer gezogen wurde, traf den falschen. Der Buchstabe "
            "wurde über ein Quadrat um seine Mitte gesucht, das "
            "Kästchen des oberen griff also über die Tinte des Nachbarn "
            "— und der Pinsel meldete dann „nichts unter dem Pinsel“ "
            "über deutlich sichtbarer Tinte oder verformte "
            "stillschweigend den Buchstaben, auf den du nicht gezeigt "
            "hast. Jetzt entscheidet die Tinte.",
        ],
    }),
    ("1.22.3", {
        "en": [
            "The Giongo tab is laid out the way the web tool it is "
            "modelled on is laid out. The canvas has a column of its "
            "own, with the tool in hand and the letter size above it "
            "and that tool’s own settings, the actions and the legend "
            "under it. The settings are nine named panes in two columns "
            "- Text, Letter style, Layout, Favourites, Intensity, Fill, "
            "Outline, Shadow & motion, Save, Gacha - with every type on "
            "a strip across the top of them, the one that best suits "
            "what you typed starred. A slider is now a short name over "
            "a rail, three side by side, which is why all of that fits "
            "in a window at once.",
            "Liquify and Points no longer have a section each in the "
            "settings: the tool is the switch, and the brush sits under "
            "the canvas while the brush is in hand. A gacha roll fills "
            "the canvas instead of six thumbnails in a corner, and says "
            "how to get back.",
            "The sound dictionary opens under the text field rather "
            "than in a window over the panel, grouped and scrolling, "
            "and it has grown from 65 sounds to 156 - explosions, "
            "dread, shock and silence, water, eating, everyday small "
            "sounds, and a Latin half, because a scanlation sets BOOM "
            "and not ドーン. ▦ beside a group draws the whole group in the "
            "look you have now and saves it as one sheet.",
            "New: favourites. Save a look under a name and drop it onto "
            "the next sound - the words and whatever you did to that "
            "one shape stay where they are. New: a switch for the "
            "handles, so the ring and the arrows are out of the way "
            "while you look at the result. New: the settings to and "
            "from the clipboard as text, which is what a docker can "
            "offer instead of a share link.",
        ],
        "de": [
            "Der Giongo-Tab ist so angeordnet wie das Web-Werkzeug, "
            "nach dem er gebaut ist. Die Leinwand hat eine eigene "
            "Spalte, mit dem Werkzeug in der Hand und der "
            "Buchstabengröße darüber und den Einstellungen dieses "
            "Werkzeugs, den Aktionen und der Legende darunter. Die "
            "Einstellungen sind neun benannte Bereiche in zwei Spalten "
            "- Text, Schriftbild, Anordnung, Favoriten, Stärke, "
            "Füllung, Kontur, Schatten & Bewegung, Speichern, Gacha - "
            "mit allen Arten auf einem Streifen darüber, die am besten "
            "passende mit Stern. Ein Regler ist jetzt ein kurzer Name "
            "über einer Schiene, drei nebeneinander; deshalb passt das "
            "alles auf einmal in ein Fenster.",
            "Verflüssigen und Punkte haben keine eigenen Abschnitte "
            "mehr: das Werkzeug ist der Schalter, und der Pinsel sitzt "
            "unter der Leinwand, solange der Pinsel in der Hand ist. "
            "Ein Gacha-Wurf füllt die Leinwand statt sechs Briefmarken "
            "in einer Ecke und sagt, wie man zurückkommt.",
            "Das Laut-Verzeichnis öffnet sich unter dem Textfeld statt "
            "in einem Fenster über dem Panel, gruppiert und scrollend, "
            "und ist von 65 auf 156 Laute gewachsen - Explosionen, "
            "Grauen, Schock und Stille, Wasser, Essen, Alltagsgeräusche "
            "und eine lateinische Hälfte, denn eine Scanlation setzt "
            "BOOM und nicht ドーン. ▦ neben einer Gruppe zeichnet die "
            "ganze Gruppe im aktuellen Look und speichert sie als ein "
            "Blatt.",
            "Neu: Favoriten. Einen Look unter einem Namen speichern und "
            "auf den nächsten Laut werfen - die Worte und alles, was du "
            "an dieser einen Form gemacht hast, bleiben. Neu: ein "
            "Schalter für die Griffe, damit Ring und Pfeile beim "
            "Anschauen nicht im Weg sind. Neu: die Einstellungen als "
            "Text in die Zwischenablage und zurück - das ist, was ein "
            "Docker statt eines Share-Links anbieten kann.",
        ],
    }),
    ("1.22.2", {
        "en": [
            "“Report a problem…” now brings the errors with it. The "
            "places that used to swallow one write it down instead - a "
            "preview that could not be drawn, an insert that failed, a "
            "file that would not save - and so does every error the "
            "plugin shows you in its status line. Anything nobody "
            "caught at all is caught once, too. The last dozen are "
            "kept, each with the last few lines of its traceback, and "
            "they go into the report under “What the plugin noticed”. "
            "Still nothing is sent on its own.",
            "Fixed: the handler that watches the tab bar for dropped "
            "panels could be asked to work after the docker it belongs "
            "to was already gone, and raised instead of quietly giving "
            "up. It only showed up once the report started catching "
            "what nobody caught.",
        ],
        "de": [
            "„Problem melden…“ bringt jetzt die Fehler mit. Die "
            "Stellen, die bisher einen verschluckt haben, schreiben ihn "
            "auf - eine Vorschau, die nicht gezeichnet werden konnte, "
            "ein fehlgeschlagenes Einfügen, eine Datei, die sich nicht "
            "speichern ließ - und ebenso jeder Fehler, den das Plugin "
            "dir in der Statuszeile zeigt. Was niemand gefangen hat, "
            "wird einmal zentral gefangen. Die letzten zwölf bleiben "
            "erhalten, je mit den letzten Zeilen ihres Tracebacks, und "
            "stehen im Bericht unter „What the plugin noticed“. Von "
            "allein wird weiterhin nichts gesendet.",
            "Behoben: der Handler, der die Tab-Leiste auf abgelegte "
            "Panels beobachtet, konnte noch arbeiten sollen, nachdem "
            "der Docker, zu dem er gehört, schon weg war - und warf "
            "einen Fehler, statt stillschweigend aufzugeben. "
            "Aufgefallen ist das erst, als der Bericht anfing, "
            "Ungefangenes zu fangen.",
        ],
    }),
    ("1.22.1", {
        "en": [
            "A patch release: what a couple of recordings turned up, "
            "and a way to tell me about the next one.",
            "“Halftone” drew a *gradient* - dots growing from nothing "
            "at the top of the word to solid at the bottom - so the "
            "upper half of every letter dissolved into its white "
            "outline and the lettering read as a white blob. There are "
            "two fills now, as in the tool this rebuilds: “Halftone” is "
            "flat, “Halftone gradient” is the shaded one. (The SVG "
            "export had been writing the flat one all along, so the "
            "preview and the saved file did not even agree.)",
            "The tool in hand was all but invisible: a checked button "
            "in a dark theme looks like an unchecked one, so a drag "
            "with the eraser looked like a drag with the brush doing "
            "nothing. The tool in hand is marked now, and a drag that "
            "touches no letter says so instead of doing nothing in "
            "silence.",
            "A letter opened for point editing keeps its own outline "
            "and no longer follows the font - which is the point of "
            "opening it, but it happened silently. The count of letters "
            "with their own outline is shown under the canvas whatever "
            "tool is in hand, and changing the font says it.",
            "With Power, Roughness or Momentum turned up, everything "
            "the mouse pointed at sat a little beside the letter it was "
            "drawn as: the panel laid the letters out from the settings "
            "as typed, the renderer from the settings with the macros "
            "applied.",
            "Closing the popped-out window could take Krita down with "
            "it (QScrollArea::takeWidget in the close event, twice in "
            "the crash log). The window never takes the panel out of "
            "its scroll area now.",
            "New: “Report a problem…” beside the version in Setup. It "
            "gathers the version, Krita, Qt, the system and the "
            "settings in play, shows you the lot, and lets you copy it, "
            "save it, or open a prefilled issue. Nothing is sent on its "
            "own, and nothing is collected that you are not shown.",
        ],
        "de": [
            "Ein Patch-Release: was zwei Aufnahmen zutage gebracht "
            "haben, und ein Weg, mir das nächste Mal Bescheid zu sagen.",
            "„Raster“ zeichnete einen *Verlauf* - Punkte, die von "
            "nichts oben bis voll unten wachsen - also löste sich die "
            "obere Hälfte jedes Buchstabens in seiner weißen Kontur auf "
            "und das Lettering las sich als weißer Klumpen. Jetzt gibt "
            "es zwei Füllungen, wie im Vorbild: „Raster“ ist flach, "
            "„Rasterverlauf“ ist der schattierte. (Der SVG-Export "
            "schrieb ohnehin schon immer das flache - Vorschau und "
            "Datei waren also nie gleich.)",
            "Welches Werkzeug an war, sah man kaum: ein gedrückter "
            "Knopf im dunklen Thema sieht aus wie ein nicht gedrückter, "
            "also wirkte ein Zug mit dem Radierer wie ein Pinselzug, "
            "der nichts tut. Das aktive Werkzeug ist jetzt markiert, "
            "und ein Zug, der keinen Buchstaben trifft, sagt es, statt "
            "stumm nichts zu tun.",
            "Ein für die Punkte geöffneter Buchstabe behält seine "
            "eigene Kontur und folgt der Schrift nicht mehr - genau "
            "dafür ist das Öffnen da, aber es geschah stillschweigend. "
            "Die Zahl der Buchstaben mit eigener Kontur steht jetzt "
            "unter der Leinwand, bei jedem Werkzeug, und ein "
            "Schriftwechsel sagt es.",
            "Mit aufgedrehter Wucht, Rauheit oder Schwung zeigte alles, "
            "worauf die Maus zielte, ein Stück neben den gezeichneten "
            "Buchstaben: das Panel setzte die Buchstaben aus den "
            "getippten Werten, der Renderer aus denen mit den Makros "
            "darauf.",
            "Das Schließen des herausgezogenen Fensters konnte Krita "
            "mitreißen (QScrollArea::takeWidget im Close-Event, zweimal "
            "im Absturzprotokoll). Das Fenster nimmt das Panel nicht "
            "mehr aus seinem Scrollbereich.",
            "Neu: „Problem melden…“ neben der Version im Setup-Tab. "
            "Sammelt Version, Krita, Qt, System und die gerade "
            "eingestellten Werte, zeigt dir alles, und du kannst es "
            "kopieren, speichern oder ein vorausgefülltes Issue öffnen. "
            "Von allein wird nichts gesendet, und nichts gesammelt, was "
            "du nicht siehst.",
        ],
    }),
    ("1.22", {
        "en": [
            "The Giongo tab (drawn sound effects) grew a lot this time, "
            "and it is “use it and tell me what breaks” rather than "
            "finished. Expect rough edges, especially in Liquify: the "
            "brush does what it says, but it is blunt - a firm stroke "
            "smears a word rather than nudging it, and it has no "
            "pressure, no smoothing and no undo while the mouse is down. "
            "Everything here can be undone (Ctrl+Z), and nothing touches "
            "your page until you insert it.",
            "The letters can be drawn on now. Four tools sit over the "
            "preview: move a letter, push it about with a brush "
            "(Liquify), take hold of the outline’s own points, or wipe "
            "parts of it away. A letter you have edited still follows the "
            "layout, the path and the per-letter moves, and one undo "
            "takes a whole stroke back.",
            "Your own lettering can be the letter style. Point the import "
            "at images, a folder or a ZIP — each file is the letter its "
            "name is (ド.png is ド) — and they are traced into outlines "
            "once and then drawn like any other letter, fill, outlines "
            "and all.",
            "A dictionary of 65 known sound effects to pick from instead "
            "of typing: kana, reading and what it means, searchable in "
            "German and English, and picking one sets the look that suits "
            "it.",
            "New in the look: a caption beside the effect (a small “BOOM” "
            "under a drawn ドカーン), a dakuten button for ア゙ and ン゙, "
            "negative lettering, line-only and line-in-halftone fills, "
            "noise lines in three hands, and decorations — impact rays, "
            "debris, sparkle, drops.",
            "Undo and redo in the panel, on Ctrl+Z and Ctrl+Y, with every "
            "change a step — and while you are typing in the text field "
            "the keys belong to the field.",
            "Saving: every layer as its own PNG in one ZIP (all on the "
            "same canvas, so they stack again), a PSD written by Krita "
            "itself, and a size of 1× to 4× for PNG and ZIP. Font files "
            "that are not installed can be loaded by hand, and there is a "
            "font list that shows each font in itself.",
            "The tab is much faster. One frame with thicken and two "
            "outlines cost 1352 ms and now costs 33; dragging a letter "
            "cost 23 ms a step and now costs 2. Thicken and outline are "
            "the same operation twice, and a letter’s shape does not "
            "depend on where it sits — both were being recomputed from "
            "nothing, sixty times a second.",
            "Pulled out into its own window, the tab now has the "
            "lettering filling the left and the settings beside it. The "
            "window also fits on the screen again: it used to be taller "
            "than 1080 px and could not be made shorter, so it sat with "
            "its bottom edge under the desktop.",
        ],
        "de": [
            "Der Giongo-Tab (gezeichnete Soundeffekte) hat diesmal viel "
            "dazubekommen, und er ist eher „benutz ihn und sag mir, was "
            "kaputtgeht“ als fertig. Rechne mit rauen Kanten, vor allem "
            "bei Verflüssigen: der Pinsel tut, was draufsteht, ist aber "
            "grob — ein fester Strich verschmiert ein Wort, statt es "
            "anzuschubsen, und es gibt weder Druck noch Glättung noch ein "
            "Undo während die Maus unten ist. Alles hier lässt sich "
            "zurücknehmen (Strg+Z), und nichts fasst deine Seite an, "
            "bevor du es einfügst.",
            "Man kann die Buchstaben jetzt bearbeiten. Über der Vorschau "
            "liegen vier Werkzeuge: Buchstaben bewegen, ihn mit einem "
            "Pinsel herumschieben (Verflüssigen), die Punkte der Kontur "
            "selbst anfassen oder Teile wegwischen. Ein bearbeiteter "
            "Buchstabe folgt weiter dem Layout, dem Pfad und den "
            "Einzelbuchstaben-Edits, und ein Undo nimmt einen ganzen "
            "Strich zurück.",
            "Eigene Letterings können der Buchstabenstil sein. Der Import "
            "nimmt Bilder, einen Ordner oder ein ZIP — jede Datei ist der "
            "Buchstabe, nach dem sie heißt (ド.png ist ド) — zeichnet sie "
            "einmal nach und setzt sie danach wie jeden anderen "
            "Buchstaben, mit Füllung, Konturen und allem.",
            "Ein Wörterbuch mit 65 bekannten Lauteffekten zum Auswählen "
            "statt Tippen: Kana, Lesung und Bedeutung, durchsuchbar auf "
            "Deutsch und Englisch, und mit dem Laut kommt gleich der "
            "passende Look.",
            "Neu im Aussehen: eine Beischrift neben dem Effekt (ein "
            "kleines „BOOM“ unter einem gezeichneten ドカーン), ein "
            "Dakuten-Knopf für ア゙ und ン゙, Negativ-Lettering, die "
            "Füllungen „nur Linie“ und „Linie im Raster“, Rauschlinien in "
            "drei Händen und Deko — Aufprallstrahlen, Trümmer, Funkeln, "
            "Tropfen.",
            "Undo und Redo im Panel, auf Strg+Z und Strg+Y, und jede "
            "Änderung ist ein Schritt — während du im Textfeld tippst, "
            "gehören die Tasten dem Textfeld.",
            "Speichern: jede Ebene als eigenes PNG in einem ZIP (alle auf "
            "derselben Fläche, also wieder stapelbar), ein PSD, das Krita "
            "selbst schreibt, und eine Größe von 1× bis 4× für PNG und "
            "ZIP. Nicht installierte Schriftdateien lassen sich von Hand "
            "laden, und es gibt eine Schriftliste, die jede Schrift in "
            "sich selbst zeigt.",
            "Der Tab ist deutlich schneller. Ein Bild mit Verdicken und "
            "zwei Konturen kostete 1352 ms und kostet jetzt 33; einen "
            "Buchstaben zu ziehen kostete 23 ms pro Schritt und kostet "
            "jetzt 2. Verdicken und Kontur sind dieselbe Rechnung "
            "zweimal, und die Form eines Buchstabens hängt nicht davon "
            "ab, wo er steht — beides wurde sechzigmal pro Sekunde neu "
            "ausgerechnet.",
            "Im eigenen Fenster füllt das Lettering jetzt die linke Seite "
            "und die Einstellungen stehen daneben. Das Fenster passt auch "
            "wieder auf den Bildschirm: es war höher als 1080 px und ließ "
            "sich nicht kleiner machen, saß also mit der Unterkante unter "
            "dem Desktop.",
        ],
    }),
    ("1.21", {
        "en": [
            "The script is something you write now, not only something "
            "you load. \u201c+ New\u201d starts an empty one, a line can be "
            "edited where it is read \u2014 in the table with F2 or the "
            "right click, or in the field above the preview \u2014 and "
            "lines can be inserted, deleted and moved. A page break can be "
            "set by hand where the script forgot one; the automatic "
            "\u201cPage 12\u201d detection is untouched and still does the "
            "work. A corrected line now goes back into the script text as "
            "well, so Analyze no longer quietly undoes it.",
            "The Batch tab holds the script itself. Every line is there, "
            "ticked and already paired with a bubble \u2014 untick what "
            "should not be placed instead of filling in what should. You "
            "can type straight into a line, and Enter writes the next one; "
            "page bars show where a page begins; a picker switches between "
            "the open scripts without leaving the tab.",
            "Text now fits the real outline of the bubble. \u201cRound\u201d "
            "used to inscribe an ellipse in the box around your selection, "
            "which spills out of anything that is not an oval \u2014 a "
            "cloud, a shout, a bubble with a tail. The selection mask is "
            "the shape, so each line is limited by the narrowest part it "
            "crosses and centred where it actually sits. A rectangular "
            "marquee has no shape to follow and keeps the old behaviour.",
            "Ctrl+Space anywhere in Krita opens a font search: type a few "
            "letters and the font is on the text, favourites first, each "
            "row drawn in its own font. The preview can be switched off.",
            "Setup lists every hotkey, TypeR\u2019s own and the preset keys "
            "you bound yourself, with the character, the preset and the "
            "manga each belongs to \u2014 and TypeR\u2019s own keys can be "
            "rebound there. A combination a preset already owns is refused "
            "rather than quietly taken.",
            "Setup has a Credits section: for every feature, whose idea it "
            "was and who wrote it. A good part of this plugin rebuilds "
            "somebody else\u2019s idea, and now it says so.",
            "The font properties window finds the other versions of a "
            "font. Windows lists \u201cAnime Ace\u201d, \u201cAnime Ace 2.0 "
            "BB\u201d and \u201cAnime Ace 3 BB\u201d as three unrelated "
            "families; they are shown together now, under their own "
            "heading, with the cuts of the open one above them.",
        ],
        "de": [
            "Das Skript ist jetzt etwas, das du schreibst, nicht nur etwas, "
            "das du l\u00e4dst. \u201e+ Neu\u201c f\u00e4ngt ein leeres an, eine "
            "Zeile l\u00e4sst sich dort \u00e4ndern, wo man sie liest \u2014 in "
            "der Tabelle mit F2 oder Rechtsklick, oder im Feld \u00fcber der "
            "Vorschau \u2014 und Zeilen lassen sich einf\u00fcgen, l\u00f6schen "
            "und verschieben. Einen Seitenwechsel kannst du von Hand "
            "setzen, wo das Skript keinen hat; die automatische "
            "\u201ePage 12\u201c-Erkennung bleibt unangetastet und macht "
            "weiter die Arbeit. Eine korrigierte Zeile geht jetzt auch in "
            "den Skripttext zur\u00fcck \u2014 Analysieren macht sie nicht "
            "mehr still r\u00fcckg\u00e4ngig.",
            "Der Stapel-Reiter hat das Skript selbst drin. Jede Zeile steht "
            "da, angehakt und schon einer Blase zugeordnet \u2014 du hakst "
            "ab, was nicht gesetzt werden soll, statt einzutragen, was "
            "gesetzt werden soll. Du kannst direkt in eine Zeile tippen, "
            "und Enter legt die n\u00e4chste an; Seitenbalken zeigen, wo "
            "eine Seite beginnt; eine Auswahl wechselt das Skript, ohne "
            "den Reiter zu verlassen.",
            "Text passt sich jetzt der echten Blasenkontur an. \u201eRund\u201c "
            "hat bisher eine Ellipse in den Kasten um deine Auswahl "
            "gelegt, und die steht bei allem \u00fcber, was kein Oval ist "
            "\u2014 Wolke, Schrei, Blase mit Tail. Die Auswahlmaske ist die "
            "Form: jede Zeile wird von der schmalsten Stelle begrenzt, die "
            "sie durchquert, und sitzt dort zentriert, wo sie wirklich "
            "liegt. Eine rechteckige Auswahl hat keine Form zum Folgen und "
            "beh\u00e4lt das bisherige Verhalten.",
            "Strg+Leertaste \u00f6ffnet \u00fcberall in Krita eine "
            "Schriftsuche: ein paar Buchstaben tippen und die Schrift "
            "sitzt, Favoriten zuerst, jede Zeile in ihrer eigenen Schrift "
            "gezeichnet. Die Vorschau l\u00e4sst sich abschalten.",
            "Die Einstellungen listen jedes Tastenk\u00fcrzel auf \u2014 die "
            "von TypeR und die Preset-Tasten, die du selbst belegt hast, "
            "mit Charakter, Preset und Manga. Die TypeR-eigenen Tasten "
            "lassen sich dort umbelegen. Eine Kombination, die schon einem "
            "Preset geh\u00f6rt, wird abgelehnt statt still \u00fcbernommen.",
            "Die Einstellungen haben einen Credits-Abschnitt: zu jeder "
            "Funktion, von wem die Idee kam und wer sie geschrieben hat. "
            "Ein guter Teil dieses Plugins baut die Idee von jemand "
            "anderem nach, und jetzt steht es da.",
            "Das Schrift-Eigenschaftenfenster findet die anderen Versionen "
            "einer Schrift. Windows f\u00fchrt \u201eAnime Ace\u201c, "
            "\u201eAnime Ace 2.0 BB\u201c und \u201eAnime Ace 3 BB\u201c als "
            "drei Familien ohne Zusammenhang; sie stehen jetzt zusammen, "
            "unter eigener \u00dcberschrift, mit den Schnitten der offenen "
            "dar\u00fcber.",
        ],
    }),
    ("1.20", {
        "en": [
            "A font in the Fonts tab now has a properties window: "
            "right-click a favourite and choose Properties, or press "
            "Alt+Enter. General says what the font is, where its files "
            "are and how big they are; Family lists every cut of it "
            "that is installed, and a double-click moves the window to "
            "that cut; Presets shows every preset the font is used by "
            "\u2014 with its manga, its character and the preset's "
            "name \u2014 and names the text types set to it.",
            "The mouse wheel no longer moves a slider or changes a "
            "dropdown while you scroll past it: it scrolls the tab, "
            "the way a wheel should. A control still answers the wheel "
            "once you have clicked into it.",
        ],
        "de": [
            "Eine Schrift im Fonts-Tab hat jetzt ein "
            "Eigenschaften-Fenster: Rechtsklick auf einen Favoriten, "
            "\u201eEigenschaften\u201c, oder Alt+Enter. "
            "\u201eAllgemein\u201c sagt, was die Schrift ist, wo ihre "
            "Dateien liegen und wie gro\u00df sie sind; "
            "\u201eFamilie\u201c listet jeden installierten Schnitt "
            "davon, und ein Doppelklick holt diesen Schnitt ins "
            "Fenster; \u201ePresets\u201c zeigt jedes Preset, das die "
            "Schrift benutzt \u2014 mit Manga, Charakter und "
            "Preset-Name \u2014 und nennt die Textarten, die auf sie "
            "gesetzt sind.",
            "Das Mausrad verstellt keinen Regler und kein Auswahlfeld "
            "mehr, wenn du daran vorbeiscrollst: Es scrollt den Tab, "
            "wie ein Mausrad soll. Angeklickt reagiert ein "
            "Bedienelement weiterhin auf das Rad.",
        ],
    }),
    ("1.19", {
        "en": [
            "Patterns are far less work to get in: load any piece of a "
            "repeating pattern as a pattern file \u2014 a screenshot, "
            "a scan, however much of it \u2014 and TypeR works out how "
            "far it repeats, shows the tile laid out side by side and "
            "offers to cut the crop down to it. The crop has to show "
            "the pattern at least twice; a file that is already one "
            "tile is used as it is. Colours and transparency are kept.",
        ],
        "de": [
            "Muster sind viel weniger Arbeit: Lade irgendein "
            "St\u00fcck eines sich wiederholenden Musters als "
            "Musterdatei \u2014 Screenshot, Scan, egal wie viel \u2014 "
            "und TypeR rechnet aus, alle wie viel Pixel es sich "
            "wiederholt, zeigt die Kachel aneinandergelegt und bietet "
            "an, den Ausschnitt darauf zu k\u00fcrzen. Der Ausschnitt "
            "muss das Muster mindestens zweimal zeigen; eine Datei, die "
            "schon eine Kachel ist, wird unver\u00e4ndert genommen. "
            "Farben und Transparenz bleiben erhalten.",
        ],
    }),
    ("1.18", {
        "en": [
            "Colouring a whole line needs no selection any more: with "
            "nothing selected, the Colour button takes the line the "
            "cursor is in. In a field with several lines only that one "
            "is taken, and Ctrl+A first colours all of them. A line "
            "colour replaces the colours of single words inside it, and "
            "Remove colour on a line clears every colour in it.",
        ],
        "de": [
            "F\u00fcr eine ganze Zeile musst du nichts mehr markieren: "
            "Ist nichts markiert, nimmt der Farbe-Knopf die Zeile, in "
            "der der Cursor steht. Bei mehreren Zeilen im Feld nur "
            "diese eine \u2014 mit Strg+A vorher alle. Eine "
            "Zeilenfarbe ersetzt die Farben einzelner W\u00f6rter "
            "darin, und \u201eFarbe entfernen\u201c auf einer Zeile "
            "r\u00e4umt alle Farben darin weg.",
        ],
    }),
    ("1.17", {
        "en": [
            "Single words can have their own colour: select a word in "
            "the active line and press Colour \u2014 the button takes "
            "the colour it shows, the arrow opens the list, a picker "
            "and Remove colour. It is written into the line as "
            "{#e03030|word}, like **bold**, so it survives saving and "
            "editing, and you can type it by hand ({red|word} works "
            "too). Outline and shadow keep their own colours, which is "
            "what keeps a coloured word readable.",
        ],
        "de": [
            "Einzelne W\u00f6rter k\u00f6nnen eine eigene Farbe "
            "haben: Wort im aktiven Textfeld markieren und auf Farbe "
            "dr\u00fccken \u2014 der Knopf nimmt die angezeigte "
            "Farbe, der Pfeil \u00f6ffnet die Liste, einen "
            "Farbw\u00e4hler und \u201eFarbe entfernen\u201c. Es "
            "steht als {#e03030|Wort} in der Zeile, wie **fett**, "
            "\u00fcberlebt also Speichern und Bearbeiten und l\u00e4sst "
            "sich auch von Hand tippen ({red|Wort} geht ebenso). Kontur "
            "und Schatten behalten ihre eigene Farbe \u2014 genau das "
            "h\u00e4lt ein farbiges Wort lesbar.",
        ],
    }),
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
