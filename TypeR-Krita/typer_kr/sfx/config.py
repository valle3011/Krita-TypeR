# -*- coding: utf-8 -*-
"""
=====================================================================
  HIER ANPASSEN  –  Fonts, Presets, Mood-Mapping, Startwerte
=====================================================================
Alles, was du regelmäßig ändern willst, steht in dieser einen Datei.
Du musst den restlichen Code nicht anfassen.
"""

# ---------------------------------------------------------------------
# 1) FONTS
# ---------------------------------------------------------------------
# Du musst NICHT alle Fonts von Hand eintragen: Das Dropdown wird
# automatisch mit ALLEN installierten System-Fonts gefüllt – einfach
# reintippen und suchen. Die Namen kommen direkt aus Qt, stimmen also
# garantiert mit Kritas Schreibweise überein.
#
# SFX_FONTS ist nur noch deine FAVORITEN-Liste: Diese Fonts erscheinen
# zum Schnellzugriff ganz oben im Dropdown (über einem Trennstrich).
# Der erste Eintrag ist der Standard beim Öffnen.
SFX_FONTS = [
    "CC Wild Words",     # <- Standard / Schnellzugriff (Dialog & "Soft")
    "CC Shout Out",      # deine laute SFX-Schrift
    "Impact",            # immer vorhanden -> Fallback
    "Creepster",         # Horror-Platzhalter (später ersetzen)
]

# Zusätzlich alle installierten System-Fonts anzeigen? (empfohlen: True)
SHOW_ALL_SYSTEM_FONTS = True

# ---------------------------------------------------------------------
# 2) PRESETS  -> ein Klick setzt Font + Größe + Farben + Outline
# ---------------------------------------------------------------------
# Das sind die INTEGRIERTEN Presets. Weitere Presets legst du bequem
# direkt im Docker an (Button „Aktuelles als Preset speichern“) – die
# werden gespeichert und bleiben erhalten.
#
# "outline_px" = sichtbare Konturstärke in Pixeln.
# "keywords"   = optionale Schlüsselwörter (klein) für den Mood-Vorschlag:
#                tippst du so ein Wort in den SFX-Text, schlägt der Docker
#                dieses Preset vor. Leere Liste/weglassen = kein Vorschlag.
SFX_PRESETS = [
    {
        "name": "Loud",
        "font": "CC Shout Out",
        "size": 160,
        "fill": "#000000",      # schwarz
        "outline": "#ffffff",   # weiß
        "outline_px": 8,
        "keywords": ["boom", "crash", "bang", "explo"],
    },
    {
        "name": "Soft",
        "font": "CC Wild Words",
        "size": 90,
        "fill": "#3a3a3a",      # dunkelgrau
        "outline": "#ffffff",
        "outline_px": 3,
        "keywords": ["whisper", "soft"],
    },
    {
        "name": "Horror",
        "font": "Creepster",
        "size": 140,
        "fill": "#000000",      # schwarz
        "outline": "#c0140f",   # blutrot
        "outline_px": 6,
        "keywords": ["scream", "blood", "horror"],
    },
]

# ---------------------------------------------------------------------
# 3) MOOD-VORSCHLAG
# ---------------------------------------------------------------------
# Hier ist nichts mehr einzustellen: Der Mood-Vorschlag nutzt die
# "keywords" der Presets oben (integrierte UND die im Docker selbst
# angelegten). Willst du ein Wort einem Stil zuordnen, gib dem passenden
# Preset einfach ein Schlüsselwort.

# ---------------------------------------------------------------------
# 4) STARTWERTE der Regler beim Öffnen des Dockers
# ---------------------------------------------------------------------
DEFAULTS = {
    "size": 140,
    "fill": "#000000",
    "outline": "#ffffff",
    "outline_px": 8,
    # zweite (äußere) Outline für einen doppelten Rand – Breite 0 = aus
    "outline2": "#000000",
    "outline2_px": 0,
    # Schatten (Schlagschatten als versetzte Kopie) – standardmäßig aus
    "shadow": False,
    "shadow_color": "#000000",
    "shadow_dx": 6,
    "shadow_dy": 6,
}

# ---------------------------------------------------------------------
# 4b) ARBEITS-MODI  (Manga / Manhwa / Doujin)
# ---------------------------------------------------------------------
# Own rules are tagged with the mode they were created in. While a mode is
# active, suggestions and the rule list use only that mode's own rules (rules
# without a mode always apply; built-in rules apply too). Mode-less legacy rules
# adopt the active mode once, at load time (see sfx_docker migration).
SFX_MODES = ["manga", "manhwa", "doujin"]
SFX_MODE_NAMES = {"manga": "Manga", "manhwa": "Manhwa", "doujin": "Doujin"}

# ---------------------------------------------------------------------
# 5) EINGEBAUTE FONT-REGELN  (Stichwort -> Font(s), nach Stimmung gruppiert)
# ---------------------------------------------------------------------
# Diese Regeln sind sofort aktiv: Tippst du oben ein passendes SFX-Wort,
# schlägt der Docker die zugehörigen Fonts vor (nach Gruppen sortiert).
# Eigene Regeln im Docker kommen zusätzlich dazu und überschreiben nichts.
#
# Die Stichwörter decken englische UND romanisierte japanische Onomatopöie
# ab (z. B. "doki" = Herzklopfen, "gashan" = Klirren, "zan" = Schnitt).
# Lange/gedehnte Schreibweisen werden automatisch erkannt ("BOOOOM" -> boom).
#
# WICHTIG: Die Fonts müssen in Windows installiert sein, damit Krita sie
# anzeigt. Die hier genutzten Namen sind die echten Familiennamen der
# Blambot-Comic-Schriften (BadaBoom, Blambot FXPro, Astounder usw.).
SFX_RULES = [
    {"group": "Boom / Explosion",
     "keywords": ["boom", "kaboom", "bam", "bang", "blam", "blast", "explode",
                  "burst", "detonate", "kablam", "badoom", "thoom", "doom",
                  "doomf", "slam", "don", "donn", "dokan", "dogan", "dosun",
                  "doshin", "kapow", "kablooey", "whoomph", "fwoom", "krakoom"],
     "fonts": ["BadaBoom Pro BB", "A.C.M.E. Explosive",
               "Astounder Squared BB"]},
    {"group": "Hit / Punch",
     "keywords": ["pow", "wham", "smack", "slap", "thud", "thump", "bonk",
                  "whack", "whomp", "whump", "bump", "bop", "knock", "kick",
                  "punch", "chop", "uppercut", "bash", "ram", "charge",
                  "impact", "hit", "doga", "dogo", "gotsu", "baki", "sock", "wallop", "clobber", "biff", "konk",
                  "krak"],
     "fonts": ["BeatDown BB", "Astounder Squared BB", "ActionFigure BB"]},
    {"group": "Crash / Break",
     "keywords": ["crash", "smash", "crack", "clash", "break", "shatter",
                  "crunch", "gasha", "bakin", "pakin", "paki", "bari", "kersplat", "splinter", "crumble", "krak"],
     "fonts": ["Autodestruct BB", "A.C.M.E. Explosive"]},
    {"group": "Slash / Cut / Tear",
     "keywords": ["slash", "slice", "cut", "stab", "pierce", "swipe", "shing",
                  "jab", "poke", "snap", "rip", "tear", "zan", "giri"],
     "fonts": ["Brushzerker BB", "Armor Piercing BB"]},
    {"group": "Gunfire",
     "keywords": ["shot", "gun", "ratatat", "tatatat", "ping", "pew", "blam", "kapow", "dakka", "budda", "bratatat",
                  "ratatatat"],
     "fonts": ["Bulletproof BB", "Armor Piercing BB"]},
    {"group": "Metal / Clang / Click",
     "keywords": ["clang", "clink", "clunk", "clank", "kachi", "katsu", "click",
                  "clack", "tick", "tock", "ting", "twang", "thunk", "doink",
                  "plunk", "clatter", "gatan", "gata", "goton", "gacha", "gakin",
                  "gokin", "kaan", "kiin"],
     "fonts": ["Armor Piercing BB", "Armored Science BB", "Android Nation BB"]},
    {"group": "Whoosh / Dash",
     "keywords": ["dash", "whoosh", "woosh", "swoosh", "swish", "fwoosh", "fwip",
                  "whiz", "zing", "voom", "vwoom", "rush", "fwash", "fwish",
                  "shoop", "shoopf", "run", "sprint", "race", "suu", "sutto"],
     "fonts": ["Blowhole BB", "BlackHole BB", "Astrogator BB"]},
    {"group": "Jump / Fall / Slide",
     "keywords": ["hop", "skip", "jump", "leap", "land", "bounce", "roll",
                  "tumble", "fall", "collapse", "slide", "slip", "skid"],
     "fonts": ["ActionFigure BB", "Astounder Round BB"]},
    {"group": "Friction / Creak",
     "keywords": ["scrape", "scratch", "scuff", "creak", "screech", "grind",
                  "girii"],
     "fonts": ["AtlandSketches BB", "Brushzerker BB"]},
    {"group": "Rumble / Shake",
     "keywords": ["rumble", "rattle", "shake", "tremble", "quake", "shiver",
                  "racket", "noise", "gogo", "goro", "gorogoro"],
     "fonts": ["Autodestruct BB", "Astounder Squared BB"]},
    {"group": "Engine / Electronic",
     "keywords": ["beep", "boop", "buzz", "bzzz", "vrrr", "whirr", "vroom",
                  "zoom", "rev", "engine", "toot", "honk", "ding", "dong",
                  "ring", "alarm", "brrring", "mecha", "robot"],
     "fonts": ["Android Nation BB", "Astrogator BB"]},
    {"group": "Electric / Spark",
     "keywords": ["zap", "zzt", "bzzzt", "spark", "flash", "biri", "bachi",
                  "pachi", "bishi", "crackle", "sizzle", "fizz"],
     "fonts": ["BlackHole BB", "Android Nation BB"]},
    {"group": "Sparkle / Shine / Magic",
     "keywords": ["shine", "sparkle", "kira", "pika", "glimmer", "gleam",
                  "twinkle", "shimmer", "blink", "wink", "gira", "glow",
                  "magic"],
     "fonts": ["Arcanum BB", "Astounder Round BB"]},
    {"group": "Water / Liquid",
     "keywords": ["splash", "splish", "sploosh", "drip", "drop", "plop", "pour",
                  "gush", "spray", "splatter", "bubble", "ripple", "wave",
                  "stream", "shower", "plip", "glug", "glub", "gurgle", "blub",
                  "basha", "pasha", "poro", "pota", "gutsu"],
     "fonts": ["Blowhole BB", "Astounder Round BB"]},
    {"group": "Eating / Mouth",
     "keywords": ["munch", "chomp", "nom", "nibble", "chew", "gobble", "slurp",
                  "sip", "gulp", "swallow", "burp", "zuru"],
     "fonts": ["Blambot Casual", "AveAve BB"]},
    {"group": "Cry / Sob",
     "keywords": ["sob", "boohoo", "waaah", "wail", "whimper", "cry", "hic",
                  "sniff"],
     "fonts": ["Blambot Casual", "Anime Ace 2.0 BB"]},
    {"group": "Breath / Sleep",
     "keywords": ["gasp", "cough", "hack", "sigh", "pant", "huff", "puff",
                  "breathe", "groan", "moan", "yawn", "snore", "doze", "sleep",
                  "faint", "zzz"],
     "fonts": ["Blambot Casual", "Afterlife BB"]},
    {"group": "Whisper / Silence",
     "keywords": ["murmur", "mumble", "whisper", "psst", "shhh", "hush",
                  "mutter", "koso", "shiin", "shin"],
     "fonts": ["Anime Ace 2.0 BB", "Background Echo", "Afterlife BB"]},
    {"group": "Laugh / Smile",
     "keywords": ["giggle", "chuckle", "snicker", "cackle", "haha", "hehe",
                  "fufu", "kukuku", "teehee", "wahaha", "niko", "niyari",
                  "nita", "hahaha", "heehee", "mwahaha", "guffaw",
                  "snort", "hyuk"],
     "fonts": ["Blambot Casual", "Astromonkey"]},
    {"group": "Roar / Growl",
     "keywords": ["roar", "growl", "grr", "snarl", "howl", "grah", "graa",
                  "gao"],
     "fonts": ["Always Angry BB", "Braaains BB", "BloodyMurder BB"]},
    {"group": "Scream / Shout",
     "keywords": ["scream", "yell", "shout", "shriek", "gyaa", "gyan", "kyaa",
                  "uwaa", "uwah", "hyaa", "hiss", "aaah", "aieee", "yaaah", "gyaaa"],
     "fonts": ["Always Angry BB", "BigBadBold BB"]},
    {"group": "Reaction",
     "keywords": ["eek", "ack", "ugh", "oof", "ow", "aah", "eh", "huh", "wha",
                  "yikes", "gaan", "gah", "argh", "whoa", "ouch", "yow", "hmph",
                  "tsk", "meh", "oops", "phew", "uh-oh"],
     "fonts": ["ActionFigure BB", "Anime Ace 2.0 BB"]},
    {"group": "Heartbeat / Tension / Stare",
     "keywords": ["doki", "kyun", "piku", "bikun", "biku", "jii", "throb",
                  "heartbeat", "drum", "beat", "badump", "bathump", "dun",
                  "zawa", "stare", "glare", "look", "peek", "peep", "nod",
                  "tilt", "turn"],
     "fonts": ["Astounder Squared BB", "Afterlife BB", "BloodyMurder BB"]},
    {"group": "Touch / Grab / Soft",
     "keywords": ["cling", "grab", "clutch", "squeeze", "hug", "pet", "stroke",
                  "rub", "tickle", "pinch", "flick", "peta", "beta", "pera",
                  "mofu", "fuwa", "noro", "sara", "hira"],
     "fonts": ["Astounder Round LC BB", "A Brush No", "Blambot Casual"]},
    {"group": "Pop / Bounce",
     "keywords": ["pop", "poof", "fwump", "boing", "pon", "pyon", "poyo",
                  "fluff", "boink", "sproing", "bloop", "blip"],
     "fonts": ["Astounder Round BB", "AveAve BB", "Blambot Casual"]},
    {"group": "Flutter / Flap",
     "keywords": ["flutter", "rustle", "swirl", "spin", "twirl", "flap",
                  "basa", "batan"],
     "fonts": ["Astounder Round LC BB", "A Brush No"]},
    {"group": "Footsteps / Taps",
     "keywords": ["tap", "pat", "step", "tok", "toko", "patter", "pitter",
                  "clop", "stomp", "stamp", "march", "shuffle", "drag",
                  "trudge"],
     "fonts": ["Blambot Casual", "Astounder Round BB"]},
    {"group": "Clap / Cheer",
     "keywords": ["clap", "applause", "cheer", "yay", "hooray", "tada"],
     "fonts": ["ActionFigure BB", "BigBadBold BB"]},
    {"group": "Animal",
     "keywords": ["nyaa", "nyan", "meow", "purr", "woof", "bark", "arf",
                  "chirp", "tweet", "caw", "hoot", "croak", "ribbit"],
     "fonts": ["Blambot Casual", "Astromonkey"]},
]

# ---------------------------------------------------------------------------
# Sprache der Regeln
#
# Jede Regel gehört zu EINER Sprache ("lang"). Im Docker ist immer eine
# Regelsprache aktiv; nur Regeln dieser Sprache werden angezeigt und wirken.
# Der Spezialwert "*" heißt "immer aktiv, sprachübergreifend" – damit bleiben
# die romanisierten japanischen Onomatopöie (doki, gashan, zan …) in JEDER
# Sprache verfügbar (Manga-SFX werden weltweit oft romaji geschrieben).
#
# Die obigen, englisch beschrifteten Regeln werden hier als "en" markiert;
# danach folgen die universellen Romaji-Regeln ("*") sowie eingebaute Regelsätze
# für Deutsch ("de") und Spanisch ("es"). Eigene Regeln im Docker bekommen die
# gerade aktive Regelsprache. (Romaji bewusst als "*" statt "ja", damit sie
# nicht verschwinden, wenn man eine andere Sprache wählt.)
# ---------------------------------------------------------------------------

for _r in SFX_RULES:                       # bestehende Regeln sind Englisch
    _r.setdefault("lang", "en")

SFX_RULES += [
    # --- Universell: romanisierte japanische Onomatopöie (immer aktiv) -----
    {"group": "JP Impact", "lang": "*",
     "keywords": ["don", "dokan", "dosun", "doshin", "dogan", "gogo", "goro"],
     "fonts": ["BadaBoom Pro BB", "Astounder Squared BB"]},
    {"group": "JP Hit", "lang": "*",
     "keywords": ["doki", "doka", "baki", "doga", "gotsu", "gusha", "boko"],
     "fonts": ["BeatDown BB", "Astounder Squared BB"]},
    {"group": "JP Crash", "lang": "*",
     "keywords": ["gasha", "gashan", "gachan", "bakin", "pakin", "bari"],
     "fonts": ["Autodestruct BB", "A.C.M.E. Explosive"]},
    {"group": "JP Slash", "lang": "*",
     "keywords": ["zan", "zash", "giri", "suba", "shaki"],
     "fonts": ["Brushzerker BB", "Armor Piercing BB"]},
    {"group": "JP Metal", "lang": "*",
     "keywords": ["gakin", "gokin", "kaan", "kiin", "gatan", "gacha"],
     "fonts": ["Armor Piercing BB", "Android Nation BB"]},
    {"group": "JP Electric", "lang": "*",
     "keywords": ["biri", "bachi", "pachi", "bishi"],
     "fonts": ["BlackHole BB", "Android Nation BB"]},
    {"group": "JP Sparkle", "lang": "*",
     "keywords": ["kira", "pika", "gira"],
     "fonts": ["Arcanum BB", "Astounder Round BB"]},
    {"group": "JP Heartbeat", "lang": "*",
     "keywords": ["doki", "kyun", "piku", "bikun", "zawa"],
     "fonts": ["Astounder Squared BB", "Afterlife BB"]},
    {"group": "JP Soft", "lang": "*",
     "keywords": ["peta", "beta", "fuwa", "mofu", "pyon", "pon", "sara",
                  "koso", "niko"],
     "fonts": ["Blambot Casual", "Astounder Round BB"]},
    {"group": "JP Water", "lang": "*",
     "keywords": ["basha", "pasha", "poro", "pota", "gutsu"],
     "fonts": ["Blowhole BB", "Astounder Round BB"]},
    {"group": "JP Silence", "lang": "*",
     "keywords": ["shiin", "shin"],
     "fonts": ["Afterlife BB", "Background Echo"]},

    # --- Deutsch -----------------------------------------------------------
    {"group": "Knall", "lang": "de",
     "keywords": ["bumm", "bum", "peng", "pang", "wumm", "rumms", "kawumm",
                  "päng", "wamm"],
     "fonts": ["BadaBoom Pro BB", "A.C.M.E. Explosive", "Astounder Squared BB"]},
    {"group": "Schlag", "lang": "de",
     "keywords": ["bums", "klatsch", "patsch", "zack", "batsch", "plopp",
                  "knuff"],
     "fonts": ["BeatDown BB", "Astounder Squared BB"]},
    {"group": "Krachen", "lang": "de",
     "keywords": ["krach", "splitter", "knack", "ratsch", "klirr", "bersten"],
     "fonts": ["Autodestruct BB", "A.C.M.E. Explosive"]},
    {"group": "Metall", "lang": "de",
     "keywords": ["kling", "klong", "scheppern", "klimper", "klong"],
     "fonts": ["Armor Piercing BB", "Android Nation BB"]},
    {"group": "Wusch", "lang": "de",
     "keywords": ["wusch", "schwupp", "zisch", "sausen", "flitz", "wuff"],
     "fonts": ["Blowhole BB", "BlackHole BB"]},
    {"group": "Schrei", "lang": "de",
     "keywords": ["aaah", "waaah", "hilfe", "brüll", "kreisch", "röhr", "argh"],
     "fonts": ["Always Angry BB", "BigBadBold BB"]},
    {"group": "Leise", "lang": "de",
     "keywords": ["flüster", "psst", "schnief", "schluchz", "murmel", "tapp",
                  "klopf", "schnarch"],
     "fonts": ["Blambot Casual", "Anime Ace 2.0 BB"]},
    {"group": "Lachen", "lang": "de",
     "keywords": ["haha", "hihi", "hoho", "kicher", "gröl", "grins"],
     "fonts": ["Blambot Casual", "Astromonkey"]},

    # --- Spanisch ----------------------------------------------------------
    {"group": "Explosión", "lang": "es",
     "keywords": ["bum", "bam", "pum", "cataplum", "catapum", "buum", "boom"],
     "fonts": ["BadaBoom Pro BB", "A.C.M.E. Explosive", "Astounder Squared BB"]},
    {"group": "Golpe", "lang": "es",
     "keywords": ["pam", "paf", "zas", "plaf", "toma", "cataplaf", "zasca"],
     "fonts": ["BeatDown BB", "Astounder Squared BB"]},
    {"group": "Romper", "lang": "es",
     "keywords": ["crac", "cras", "plas", "crunch", "chas"],
     "fonts": ["Autodestruct BB", "A.C.M.E. Explosive"]},
    {"group": "Metal", "lang": "es",
     "keywords": ["clin", "clon", "tolon", "tilin", "ñiqui"],
     "fonts": ["Armor Piercing BB", "Android Nation BB"]},
    {"group": "Veloz", "lang": "es",
     "keywords": ["fiu", "zum", "fium", "swoosh", "shht"],
     "fonts": ["Blowhole BB", "BlackHole BB"]},
    {"group": "Grito", "lang": "es",
     "keywords": ["aaah", "aaay", "socorro", "grr", "guaaa", "buaaa"],
     "fonts": ["Always Angry BB", "BigBadBold BB"]},
    {"group": "Suave", "lang": "es",
     "keywords": ["psst", "shh", "snif", "muac", "toc", "ronc", "glup"],
     "fonts": ["Blambot Casual", "Anime Ace 2.0 BB"]},
    {"group": "Risa", "lang": "es",
     "keywords": ["jaja", "jiji", "jeje", "muajaja", "joro"],
     "fonts": ["Blambot Casual", "Astromonkey"]},

    # --- CYL Manga-SFX cheat-sheet (always active) -------------------------
    # Taken from CYL's Manga SFX cheat sheet + community font sheets; extends
    # the mood groups with the extra download fonts. Cheat-sheet readings are
    # best-effort; these fonts must be installed to render. Font names are the
    # real installed family names (BOXER SHORTS -> "Boxer Shorts BB",
    # CCGeek Speak -> "CCGeekSpeak", DEARLYDEPARTED -> "DearlyDeparted BB").
    {"group": "Boom / Explosion", "lang": "*",
     "keywords": ["boom", "don", "donn", "dokan", "dosun", "doshin", "dogan",
                  "kaboom", "bam", "bang", "blast", "doom"],
     "fonts": ["DOMINOS BLAST", "BadaBoom Pro BB", "A.C.M.E. Explosive"]},
    {"group": "Hit / Punch", "lang": "*",
     "keywords": ["doga", "dogo", "ga", "gan", "baki", "gotsu", "pow", "wham",
                  "smack", "thud", "bonk", "hit", "punch", "bash", "impact"],
     "fonts": ["CCGeekSpeak", "METAL HEAD", "DARKNESS RISING", "BeatDown BB",
               "Astounder Squared BB"]},
    {"group": "Crash / Break", "lang": "*",
     "keywords": ["gasha", "gashan", "gachan", "bakin", "pakin", "bari",
                  "crash", "smash", "crack", "shatter", "break", "crunch"],
     "fonts": ["Speechless", "CRUDEX", "Autodestruct BB", "A.C.M.E. Explosive"]},
    {"group": "Slash / Cut / Tear", "lang": "*",
     "keywords": ["zan", "zash", "zuba", "dori", "giri", "shaki", "suba",
                  "slash", "slice", "cut", "stab", "rip", "tear"],
     "fonts": ["Jackbrush", "BLACKISH", "Brushzerker BB", "Armor Piercing BB"]},
    {"group": "Metal / Clang / Click", "lang": "*",
     "keywords": ["ka", "kan", "gakin", "gokin", "kaan", "kiin", "gatan",
                  "gacha", "clang", "clink", "clank", "clack", "click"],
     "fonts": ["Kabut Hitam", "Armor Piercing BB", "Android Nation BB"]},
    {"group": "Whoosh / Dash", "lang": "*",
     "keywords": ["za", "zaa", "dash", "fi", "fyu", "fu", "whoosh", "woosh",
                  "swoosh", "swish", "fwoosh", "suu", "sutto", "zoom", "rush"],
     "fonts": ["HEATERS", "DJB Brit's Thin Pen", "Blowhole BB", "BlackHole BB"]},
    {"group": "Engine / Electronic", "lang": "*",
     "keywords": ["bururo", "buroro", "vroom", "vroon", "brrr", "vrrr",
                  "engine", "rev", "mecha"],
     "fonts": ["CDX Amraam", "Android Nation BB", "Astrogator BB"]},
    {"group": "Friction / Creak", "lang": "*",
     "keywords": ["scrape", "scratch", "scuff", "creak", "screech", "grind",
                  "girii", "kiri", "zaza"],
     "fonts": ["SUPERSCRATCHY", "AtlandSketches BB", "Brushzerker BB"]},
    {"group": "Sparkle / Shine / Magic", "lang": "*",
     "keywords": ["sharara", "kira", "pika", "gira", "shine", "sparkle",
                  "glimmer", "twinkle", "shimmer"],
     "fonts": ["Spicy Chicken", "Arcanum BB", "Astounder Round BB"]},
    {"group": "Heartbeat / Tension / Stare", "lang": "*",
     "keywords": ["biku", "bikun", "doki", "kyun", "piku", "jii", "zawa",
                  "yura", "throb", "heartbeat", "stare", "glare"],
     "fonts": ["Runescript", "CDX Hollow", "DearlyDeparted BB",
               "Astounder Squared BB", "Afterlife BB"]},
    {"group": "Rumble / Shake", "lang": "*",
     "keywords": ["furu", "buru", "gogo", "goro", "rumble", "rattle", "shake",
                  "tremble", "quake", "shiver"],
     "fonts": ["Mango", "Autodestruct BB", "Astounder Squared BB"]},
    {"group": "Flutter / Flap", "lang": "*",
     "keywords": ["pasa", "sara", "hira", "basa", "flutter", "rustle", "swirl",
                  "flap"],
     "fonts": ["COOKIESANDCREAM", "Sketchies", "Astounder Round LC BB",
               "A Brush No"]},
    {"group": "Touch / Grab / Soft", "lang": "*",
     "keywords": ["gyu", "yuwa", "peta", "beta", "fuwa", "mofu", "squeeze",
                  "hug", "grab", "pet", "rub", "soft"],
     "fonts": ["Natural", "CHIPPIE", "SS Soapy hands", "Blambot Casual"]},
    {"group": "Pop / Bounce", "lang": "*",
     "keywords": ["pon", "pyon", "poyo", "baa", "paa", "gu", "pop", "poof",
                  "boing", "fluff"],
     "fonts": ["Imaginary Friend BB", "Telefante", "Astounder Round BB",
               "AveAve BB"]},
    {"group": "Footsteps / Taps", "lang": "*",
     "keywords": ["ta", "tatta", "tot", "toko", "pa", "tap", "pat", "step",
                  "patter", "clop", "stomp"],
     "fonts": ["Reminder Notes", "CDX Sidewinder", "Blambot Casual",
               "Astounder Round BB"]},
    {"group": "Clap / Cheer", "lang": "*",
     "keywords": ["paan", "pan", "clap", "applause", "cheer", "yay", "hooray",
                  "tada"],
     "fonts": ["DJB Me and My Shadow", "ActionFigure BB", "BigBadBold BB"]},
    {"group": "Laugh / Smile", "lang": "*",
     "keywords": ["kusu", "haha", "hehe", "fufu", "kukuku", "giggle", "chuckle",
                  "snicker", "cackle", "teehee"],
     "fonts": ["Butterfly Ball", "Bugbear", "CDX Seven Cent Pen", "Astromonkey"]},
    {"group": "Scream / Shout", "lang": "*",
     "keywords": ["aa", "waa", "gyaa", "kyaa", "uwaa", "scream", "yell",
                  "shout", "shriek"],
     "fonts": ["BLANK RIVER", "LHF COMICCAPS", "Always Angry BB",
               "BigBadBold BB"]},
    {"group": "Reaction", "lang": "*",
     "keywords": ["oo", "ah", "eh", "huh", "eek", "ack", "oof", "gaan", "wha"],
     "fonts": ["Brightest Melody", "GREATHUNT", "ActionFigure BB",
               "Anime Ace 2.0 BB"]},
    {"group": "Breath / Sleep", "lang": "*",
     "keywords": ["hi", "haa", "gasp", "sigh", "pant", "huff", "puff",
                  "breathe", "doze", "sleep", "zzz"],
     "fonts": ["Burobu", "Boxer Shorts BB", "Blambot Casual", "Afterlife BB"]},
]
