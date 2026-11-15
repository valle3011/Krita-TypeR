# -*- coding: utf-8 -*-
"""A dictionary of Japanese sound effects, to pick from instead of type.

Qt-free on purpose, like `giongo.py` itself: the list and the search are
data and arithmetic, and the panel only shows them.

Each entry carries the kana as it is usually drawn, a romaji reading, an
English and a German gloss, and the `giongo` type that suits it - so
picking a sound can set the look as well, which is the whole point of
picking it from a list rather than typing it.

The glosses are what the sound *means*, not a translation to letter into
the page: a scanlation would set "BOOM", not "huge impact".
"""

#: (kana, romaji, type, English, German)
SOUNDS = [
    # --- impact -----------------------------------------------------------
    ("ドン", "don", "impact", "a solid hit", "harter Schlag"),
    ("ドカーン", "dokaan", "impact", "a big explosion",
     "große Explosion"),
    ("ドゴォ", "dogo", "impact", "a heavy, dull blow",
     "dumpfer schwerer Schlag"),
    ("バキッ", "baki", "impact", "something breaking",
     "etwas bricht"),
    ("ガシャーン", "gashaan", "impact",
     "glass or metal smashing", "Glas oder Metall zerbirst"),
    ("ズドン", "zudon", "impact", "a shot, or a huge drop",
     "Schuss oder schwerer Aufprall"),
    ("バン", "ban", "impact", "a bang, a slammed door",
     "Knall, zugeschlagene Tür"),
    ("ドガッ", "doga", "impact", "a crunching impact",
     "krachender Aufprall"),
    ("ガーン", "gaan", "impact", "shock, being stunned",
     "Schock, wie vor den Kopf geschlagen"),
    # --- slash ------------------------------------------------------------
    ("シュッ", "shu", "slash", "a swift movement through air",
     "schnelle Bewegung durch die Luft"),
    ("ズバッ", "zuba", "slash", "a clean cut",
     "sauberer Schnitt"),
    ("ザシュ", "zashu", "slash", "a cut that draws blood",
     "Schnitt, der Blut zieht"),
    ("スパッ", "supa", "slash", "a light, clean slice",
     "leichter, sauberer Schnitt"),
    ("シャキーン", "shakiin", "slash",
     "a blade drawn, steel ringing", "Klinge gezogen, Stahl klingt"),
    ("ヒュン", "hyun", "slash", "something flying past",
     "etwas saust vorbei"),
    ("ビュッ", "byu", "slash", "a hard gust or throw",
     "harter Wurf oder Windstoß"),
    ("ザン", "zan", "slash", "a decisive cut",
     "entscheidender Hieb"),
    # --- rumble -----------------------------------------------------------
    ("ゴゴゴ", "gogogo", "rumble", "dread, a building menace",
     "drohendes Grollen, böse Vorahnung"),
    ("ドドド", "dododo", "rumble", "pounding, a stampede",
     "Dröhnen, Getrampel"),
    ("ズズズ", "zuzuzu", "rumble", "something heavy dragging",
     "etwas Schweres schleift"),
    ("ガタガタ", "gatagata", "rumble", "rattling, shaking",
     "Klappern, Erzittern"),
    ("ゴロゴロ", "gorogoro", "rumble",
     "thunder, or rolling about", "Donner oder Herumrollen"),
    ("ザワザワ", "zawazawa", "rumble", "a murmuring crowd",
     "raunende Menge"),
    ("グラグラ", "guragura", "rumble", "unsteady, swaying",
     "wackelig, schwankend"),
    # --- cute -------------------------------------------------------------
    ("キュン", "kyun", "cute", "a pang of affection",
     "Herzstich vor Zuneigung"),
    ("ドキドキ", "dokidoki", "cute", "a racing heart",
     "Herzklopfen"),
    ("ふわふわ", "fuwafuwa", "cute", "soft and floating",
     "weich und schwebend"),
    ("もふもふ", "mofumofu", "cute", "fluffy, strokeable",
     "flauschig"),
    ("ぷにっ", "puni", "cute", "soft and squishy",
     "weich und quietschig"),
    ("キラキラ", "kirakira", "cute", "sparkling, shining",
     "funkelnd"),
    ("にこっ", "niko", "cute", "a smile",
     "ein Lächeln"),
    ("ぽわっ", "powa", "cute", "a warm, dreamy glow",
     "warmes, verträumtes Leuchten"),
    # --- drops ------------------------------------------------------------
    ("ぽたぽた", "potapota", "drops", "dripping",
     "Tropfen fällt um Tropfen"),
    ("ぴちゃ", "picha", "drops", "a small splash",
     "kleines Platschen"),
    ("ザーザー", "zaazaa", "drops", "pouring rain",
     "strömender Regen"),
    ("しとしと", "shitoshito", "drops", "a quiet drizzle",
     "leiser Nieselregen"),
    ("バシャン", "bashan", "drops", "a big splash",
     "großer Platscher"),
    ("チャプ", "chapu", "drops", "water lapping",
     "plätscherndes Wasser"),
    # --- glare ------------------------------------------------------------
    ("ジーッ", "jii", "glare", "a long, fixed stare",
     "langes, starres Anstarren"),
    ("ジロリ", "jirori", "glare", "a sidelong glance",
     "Seitenblick"),
    ("ギロッ", "giro", "glare", "a sharp glare",
     "scharfer Blick"),
    ("ヌッ", "nu", "glare", "looming into view",
     "taucht bedrohlich auf"),
    ("ズイッ", "zui", "glare", "leaning right in",
     "rückt dicht heran"),
    ("ピキ", "piki", "glare", "a vein popping, irritation",
     "Zornesader, Gereiztheit"),
    # --- pop --------------------------------------------------------------
    ("ポン", "pon", "pop", "a light pop or pat",
     "leichtes Plopp oder Klaps"),
    ("パッ", "pa", "pop", "something appearing at once",
     "etwas erscheint schlagartig"),
    ("ぴょん", "pyon", "pop", "a hop",
     "Hüpfer"),
    ("ヒョイ", "hyoi", "pop", "picked up lightly",
     "leichthin aufgehoben"),
    ("ポヨン", "poyon", "pop", "a bouncy wobble",
     "federndes Wackeln"),
    ("パチン", "pachin", "pop", "a snap of the fingers",
     "Fingerschnippen"),
    # --- small ------------------------------------------------------------
    ("こそこそ", "kosokoso", "small", "sneaking about",
     "heimliches Schleichen"),
    ("ちょこん", "chokon", "small", "sitting there, tiny",
     "sitzt da, ganz klein"),
    ("ことっ", "koto", "small", "a small object set down",
     "kleiner Gegenstand abgesetzt"),
    ("そっ", "so", "small", "quietly, gently",
     "leise, sachte"),
    ("てくてく", "tekuteku", "small", "plodding along",
     "tappt dahin"),
    ("ぺたぺた", "petapeta", "small", "bare feet padding",
     "nackte Füße tapsen"),
    ("シーン", "shiin", "small", "silence - the loudest one",
     "Stille - die lauteste von allen"),
    # --- machine ----------------------------------------------------------
    ("ピピッ", "pipi", "machine", "a device beeping",
     "Gerät piept"),
    ("ガチャ", "gacha", "machine", "a handle, a lock, a door",
     "Klinke, Schloss, Tür"),
    ("カチッ", "kachi", "machine", "a click, a switch",
     "Klicken, ein Schalter"),
    ("ブーン", "buun", "machine", "a motor humming",
     "brummender Motor"),
    ("ビーッ", "bii", "machine", "a buzzer, an alarm",
     "Summer, Alarm"),
    ("ウィーン", "wiin", "machine", "something servo-driven",
     "etwas fährt motorisch"),
    ("チーン", "chiin", "machine", "a bell, a till, a microwave",
     "Klingel, Kasse, Mikrowelle"),
    ("ジリリリ", "jiririri", "machine", "an alarm ringing",
     "schrillender Wecker"),
    # --- more, by the same types ------------------------------------------
    ("ドカン", "dokan", "impact", "an explosion", "Explosion"),
    ("ズガーン", "zugaan", "impact", "a shattering blast",
     "zerschmetternde Detonation"),
    ("バリーン", "bariin", "impact", "glass breaking",
     "Glas zerspringt"),
    ("ベキッ", "beki", "impact", "something snapping",
     "etwas knackt durch"),
    ("メキメキ", "mekimeki", "impact",
     "wood or bone giving way", "Holz oder Knochen gibt nach"),
    ("パリン", "parin", "impact", "something small breaking",
     "etwas Kleines zerbricht"),
    ("ドゴォォン", "dogoon", "impact",
     "a huge, deep crash", "riesiger dumpfer Einschlag"),
    ("ガッシャン", "gasshan", "impact",
     "a heavy metal clatter", "schweres Metallscheppern"),
    ("ザンッ", "zan", "slash", "a decisive cut",
     "entscheidender Hieb"),
    ("ダッシュ", "dasshu", "slash", "a dash",
     "Spurt"),
    ("バッ", "ba", "slash", "a sudden move",
     "plötzliche Bewegung"),
    ("ズザッ", "zuza", "slash", "skidding to a stop",
     "schlitternder Halt"),
    ("ビュン", "byun", "slash", "something flying past",
     "etwas saust vorbei"),
    ("ゾゾゾ", "zozozo", "rumble", "dread creeping up",
     "Grauen kriecht hoch"),
    ("ゴオオ", "gooo", "rumble", "a roar in the distance",
     "fernes Dröhnen"),
    ("ドッドッ", "doddo", "rumble", "pounding footfalls",
     "stampfende Schritte"),
    ("ズーン", "zuun", "glare", "a heavy, sinking mood",
     "bleierne Stimmung"),
    ("ドキッ", "doki", "glare", "a single startled heartbeat",
     "ein erschrockener Herzschlag"),
    ("ギクッ", "giku", "glare", "being caught out",
     "ertappt"),
    ("ゾクッ", "zoku", "glare", "a shiver down the back",
     "Schauer über den Rücken"),
    ("ハッ", "ha", "glare", "a sudden realisation",
     "plötzliche Erkenntnis"),
    ("ガビーン", "gabiin", "glare", "comic despair",
     "komische Verzweiflung"),
    ("しーん", "shiin", "glare", "silence, nobody says a word",
     "Stille, keiner sagt ein Wort"),
    ("ポツン", "potsun", "glare", "left alone",
     "allein zurückgelassen"),
    ("きらっ", "kira", "cute", "one small sparkle",
     "ein kleines Funkeln"),
    ("ふわっ", "fuwa", "cute", "something light and soft",
     "etwas Leichtes, Weiches"),
    ("ぴかっ", "pika", "cute", "a bright flash",
     "heller Blitz"),
    ("ほわわ", "howawa", "cute", "going dreamy",
     "ins Träumen geraten"),
    ("ドボーン", "doboon", "drops", "falling into water",
     "Sturz ins Wasser"),
    ("ザバァ", "zabaa", "drops", "water surging",
     "Wasser schwappt"),
    ("ビシャッ", "bisha", "drops", "a wet splat",
     "nasser Klatscher"),
    ("ばしゃっ", "basha", "drops", "a splash underfoot",
     "Platschen unter den Füßen"),
    ("じゃぶじゃぶ", "jabujabu", "drops",
     "wading about", "Waten im Wasser"),
    ("ぽちゃん", "pochan", "drops", "a small plop",
     "kleines Platsch"),
    ("ポタッ", "pota", "drops", "a single drip",
     "einzelner Tropfen"),
    ("ストン", "suton", "small", "something set down lightly",
     "etwas wird leicht abgesetzt"),
    ("パタン", "patan", "small", "a door closing",
     "Tür schließt"),
    ("バタン", "batan", "small", "a door slammed",
     "Tür knallt zu"),
    ("ピンポーン", "pinpoon", "small", "a doorbell",
     "Türklingel"),
    ("もぐもぐ", "mogumogu", "small", "chewing",
     "Kauen"),
    ("ゴクッ", "goku", "small", "a gulp",
     "Schluck"),
    ("パクッ", "paku", "small", "a bite",
     "Bissen"),
    ("バリバリ", "baribari", "small", "crunching",
     "Knuspern"),
    ("ドーン", "doon", "pop", "a dramatic reveal",
     "dramatischer Auftritt"),
    ("バーン", "baan", "pop", "a loud entrance",
     "lauter Auftritt"),
    ("ジャーン", "jaan", "pop", "ta-da",
     "Tadä"),
    ("ズコー", "zukoo", "pop", "falling over at a bad joke",
     "Umfallen bei einem schlechten Witz"),
    ("ピコーン", "pikoon", "pop", "an idea arriving",
     "ein Einfall"),
    ("ガシャン", "gashan", "machine", "machinery clanking",
     "Maschine scheppert"),
    ("カチャカチャ", "kachakacha", "machine",
     "keys or a keyboard", "Tasten oder Schlüssel"),

    # --- the Latin half ----------------------------------------------------
    # What a scanlation actually sets. The reading is the word itself, so
    # the search finds them the same way.
    ("BOOM!", "boom", "impact", "a huge impact", "gewaltiger Einschlag"),
    ("BAM!", "bam", "impact", "a hard hit", "harter Treffer"),
    ("WHAM!", "wham", "impact", "a heavy blow", "schwerer Schlag"),
    ("POW!", "pow", "impact", "a punch landing", "ein Treffer"),
    ("THUD!", "thud", "impact", "a dull drop", "dumpfer Aufprall"),
    ("BANG!", "bang", "impact", "a bang or a shot", "Knall oder Schuss"),
    ("CRASH!", "crash", "impact", "something coming down",
     "etwas stürzt ein"),
    ("SMASH!", "smash", "impact", "something broken apart",
     "etwas zerschlägt"),
    ("KRAK!", "krak", "impact", "a sharp break", "scharfer Bruch"),
    ("KABOOM!", "kaboom", "impact", "an explosion", "Explosion"),
    ("WHOOSH", "whoosh", "slash", "rushing past", "sausend vorbei"),
    ("SWOOSH", "swoosh", "slash", "a sweeping move",
     "schwungvolle Bewegung"),
    ("SLASH", "slash", "slash", "a cut", "Schnitt"),
    ("SHING!", "shing", "slash", "a blade drawn", "Klinge gezogen"),
    ("ZIP", "zip", "slash", "darting away", "wegflitzen"),
    ("RUMBLE", "rumble", "rumble", "a low, long roll",
     "tiefes langes Grollen"),
    ("GRRRR", "grrrr", "rumble", "a growl", "Knurren"),
    ("DOOM", "doom", "rumble", "dread closing in", "nahendes Unheil"),
    ("ROAR", "roar", "rumble", "a roar", "Brüllen"),
    ("SPLASH!", "splash", "drops", "hitting water", "Aufschlag im Wasser"),
    ("SPLOOSH!", "sploosh", "drops", "a bigger splash",
     "größerer Spritzer"),
    ("DRIP", "drip", "drops", "a single drop", "einzelner Tropfen"),
    ("PLOP", "plop", "drops", "something small falling in",
     "etwas Kleines fällt hinein"),
    ("SPARKLE", "sparkle", "cute", "glittering", "Funkeln"),
    ("TWINKLE", "twinkle", "cute", "a small twinkle", "kleines Blinken"),
    ("BOING", "boing", "cute", "a bounce", "Sprungfeder"),
    ("POP!", "pop", "cute", "a small pop", "kleines Plopp"),
    ("KNOCK", "knock", "small", "knocking", "Klopfen"),
    ("CLICK", "click", "small", "a switch or a latch",
     "Schalter oder Riegel"),
    ("TAP", "tap", "small", "a light touch", "leichtes Tippen"),
    ("CREAK", "creak", "small", "something old giving",
     "etwas Altes ächzt"),
    ("BEEP", "beep", "machine", "an electronic beep",
     "elektronischer Piepser"),
    ("VROOM", "vroom", "machine", "an engine", "Motor"),
    ("BZZT", "bzzt", "machine", "electricity arcing",
     "Stromschlag"),
    ("CLANK", "clank", "machine", "metal on metal",
     "Metall auf Metall"),
    ("GASP!", "gasp", "glare", "a sharp intake of breath",
     "scharfes Luftholen"),
    ("GULP...", "gulp", "glare", "swallowing hard",
     "schweres Schlucken"),
    ("THUMP", "thump", "glare", "a heartbeat", "Herzschlag"),
    ("TA-DA!", "tada", "pop", "a reveal", "Enthüllung"),
    ("HUH?!", "huh", "pop", "not following", "versteht nichts"),
    ("WHAT?!", "what", "pop", "disbelief", "Unglaube"),
]
#: long vowels in romaji, so "dokan" finds "dokaan"
_VOWELS = "aeiou"


def plain(romaji):
    """`dokaan` -> `dokan`: doubled vowels collapsed, dashes dropped.

    People type what they hear, not the transcription with its long
    vowels, so the search has to meet them there.
    """
    out = []
    for ch in (romaji or "").lower():
        if ch in "-_ ":
            continue
        if out and ch == out[-1] and ch in _VOWELS:
            continue
        out.append(ch)
    return "".join(out)


def entries():
    """Every sound, as dicts - easier to read at the call site."""
    return [{"kana": k, "romaji": r, "type": t, "en": en, "de": de}
            for k, r, t, en, de in SOUNDS]


def gloss(entry, lang="en"):
    """What the sound means, in the interface language we have."""
    return entry.get(lang) or entry.get("en") or ""


def find(query, lang="en", kind=None):
    """The sounds matching `query`, best first.

    Matches the kana, the reading (with or without its long vowels) and
    the meaning. `kind` limits it to one giongo type.
    """
    q = (query or "").strip().lower()
    qp = plain(q)
    out = []
    for e in entries():
        if kind and e["type"] != kind:
            continue
        if not q:
            out.append((2, e))
            continue
        rom, pr = e["romaji"].lower(), plain(e["romaji"])
        if q == rom or qp == pr or q == e["kana"]:
            rank = 0
        elif e["kana"].startswith(q) or rom.startswith(qp or q) \
                or pr.startswith(qp or q):
            rank = 1
        elif q in e["kana"] or qp in pr or q in rom:
            rank = 2
        elif q in gloss(e, lang).lower() or q in e["en"].lower():
            rank = 3
        else:
            continue
        out.append((rank, e))
    out.sort(key=lambda p: (p[0], p[1]["romaji"]))
    return [e for _r, e in out]


def by_type():
    """{type: [entry, ...]} in the order they are listed above."""
    groups = {}
    for e in entries():
        groups.setdefault(e["type"], []).append(e)
    return groups

def is_latin(entry):
    """Is this one of the Latin entries?

    Read off the sound itself rather than stored: a sound written in
    plain ASCII is the Latin one. A kana entry never is.
    """
    text = entry["kana"] if isinstance(entry, dict) else entry
    try:
        text.encode("ascii")
    except (UnicodeEncodeError, AttributeError):
        return False
    return True


def groups(lang="en"):
    """[(script, type, [entry, ...])] - Latin first, then the kana.

    What the panel shows: the sounds in named groups rather than one
    long list, which is the only way a hundred of them can be looked
    through at all.
    """
    out = []
    for latin in (True, False):
        seen = []
        for e in entries():
            if is_latin(e) is not latin:
                continue
            for script, tid, items in seen:
                if tid == e["type"]:
                    items.append(e)
                    break
            else:
                seen.append(("latin" if latin else "ja", e["type"], [e]))
        out.extend(seen)
    return out
