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
