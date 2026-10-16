"""Lesen und Schreiben von Krita-.kra-Dateien - genug davon, um die unterste
Paint-Ebene (das Raw) durch ein anderes Bild (den Clean) zu ersetzen.

Eine .kra ist ein ZIP. Die Pixel einer Paint-Ebene liegen darin als eine Datei
im Kachel-Format:

    VERSION 2\\n TILEWIDTH 64\\n TILEHEIGHT 64\\n PIXELSIZE 4\\n DATA <n>\\n
    <x>,<y>,LZF,<bytes>\\n <flag><daten>   * n

Die Pixel einer Kachel liegen planar (erst alle B, dann alle G, R, A).

<flag> muss 1 (LZF) sein. Das Format sieht 0 fuer "unkomprimiert" vor, aber in
206596 nachgemessenen Kacheln echter Dateien steht ausnahmslos 1 - und Krita
rendert Flag-0-Kacheln als Streifenmuster. Ebenso gilt dort ausnahmslos
<bytes> <= Rohgroesse+1; groessere Kacheln bringen Krita zum Absturz. Beides
haelt lzf_compress ein.
"""

import copy
import re
import shutil
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET

KRA_NS = "http://www.calligra.org/DTD/krita"
_NS = {"k": KRA_NS}

# sonst serialisiert ElementTree die Ebenen als <ns0:layer .../>
ET.register_namespace("", KRA_NS)


class KraError(Exception):
    """Die Datei sieht nicht so aus, wie SwapR es erwartet."""


# --------------------------------------------------------------------------
# LZF
# --------------------------------------------------------------------------

def lzf_decompress(data, expected_size):
    out = bytearray()
    ip, n = 0, len(data)
    while ip < n:
        ctrl = data[ip]
        ip += 1
        if ctrl < 32:                       # literal run
            ln = ctrl + 1
            out += data[ip:ip + ln]
            ip += ln
        else:                               # back reference
            ln = ctrl >> 5
            ref = len(out) - ((ctrl & 0x1F) << 8) - 1
            if ln == 7:
                ln += data[ip]
                ip += 1
            ref -= data[ip]
            ip += 1
            if ref < 0:
                raise KraError("LZF-Daten defekt")
            for _ in range(ln + 2):
                out.append(out[ref])
                ref += 1
    if len(out) != expected_size:
        raise KraError(f"LZF: {len(out)} statt {expected_size} Bytes")
    return bytes(out)


_RUN = re.compile(rb"(.)\1{2,}", re.S)

MAX_REF = 264           # ln = 7+255 -> 264 kopierte Bytes
MAX_LITERAL = 32        # Steuerbyte 0..31 == 1..32 Literale
MAX_DISTANCE = 8192     # ((ctrl & 0x1f) << 8) + low + 1
MIN_REF = 3             # kuerzere Treffer passen nicht in eine Referenz


def _flush(out, lit):
    for i in range(0, len(lit), MAX_LITERAL):
        chunk = lit[i:i + MAX_LITERAL]
        out.append(len(chunk) - 1)
        out.extend(chunk)
    del lit[:]


def _emit_copy(out, distance, length):
    """length Bytes aus distance Bytes Abstand kopieren (Literale vorher leeren).

    Unter MIN_REF Bytes gibt es keine gueltige Kodierung: ln waere 0 und das
    Steuerbyte damit < 32, was der Decoder als Literal-Lauf liest. Der Aufrufer
    muss solche Reste als Literale schreiben.
    """
    if length < MIN_REF:
        raise KraError(f"Referenz ueber {length} Bytes ist nicht kodierbar")
    d = distance - 1
    high, low = d >> 8, d & 0xFF
    while length:
        take = min(length, MAX_REF)
        if 0 < length - take < MIN_REF:        # keinen zu kurzen Rest lassen
            take = length - MIN_REF
        ln = take - 2
        if ln < 7:
            out.append((ln << 5) | high)
        else:
            out.append((7 << 5) | high)
            out.append(ln - 7)
        out.append(low)
        length -= take


def _compress_runs(out, lit, data):
    """Laeufe gleicher Bytes als Referenzen, alles andere als Literale."""
    pos = 0
    for m in _RUN.finditer(data):
        start, end = m.start(), m.end()
        if start > pos:
            lit.extend(data[pos:start])
        if end - start - 1 < MIN_REF:
            lit.extend(data[start:end])        # zu kurz, lohnt sich ohnehin nicht
        else:
            lit.append(data[start])            # erstes Byte des Laufs als Literal
            _flush(out, lit)
            _emit_copy(out, 1, end - start - 1)  # Abstand 1 == dasselbe Byte
        pos = end
    if pos < len(data):
        lit.extend(data[pos:])


def lzf_compress(data, plane_size=None):
    """LZF-Strom - kein vollstaendiger Kompressor, aber schnell und ausreichend.

    Gesucht werden nur Laeufe gleicher Bytes (per Regex in C-Geschwindigkeit
    statt byteweise in Python) sowie identische Kanalebenen. Beides trifft bei
    Manga genau zu: grosse weisse Flaechen, konstanter Alpha-Kanal, und bei
    Graustufen sind R, G und B Byte fuer Byte gleich.

    Zwei an 206596 echten Kacheln nachgemessene Eigenschaften muessen gelten:
    Flag 1, und die Nutzlast ist nie groesser als die Rohdaten. Laesst sich ein
    Block nicht kleiner kodieren, kommt None zurueck - dann darf der Aufrufer
    keine Datei schreiben, sonst stuerzt Krita ab.
    """
    out = bytearray()
    lit = bytearray()

    planes = []
    if plane_size and plane_size > 0 and len(data) % plane_size == 0:
        planes = [data[i:i + plane_size] for i in range(0, len(data), plane_size)]

    if len(planes) > 1:
        for idx, plane in enumerate(planes):
            # Zeigt eine fruehere, identische Ebene in Reichweite? Dann genuegen
            # ein paar Referenzen statt der ganzen Ebene.
            dup = next((back * plane_size
                        for back in range(1, idx + 1)
                        if back * plane_size <= MAX_DISTANCE
                        and planes[idx - back] == plane), None)
            if dup is not None:
                _flush(out, lit)
                _emit_copy(out, dup, plane_size)
            else:
                _compress_runs(out, lit, plane)
        _flush(out, lit)
    else:
        _compress_runs(out, lit, data)
        _flush(out, lit)

    return bytes(out) if len(out) < len(data) else None


# --------------------------------------------------------------------------
# Kachel-Datei
# --------------------------------------------------------------------------

class TileHeader:
    __slots__ = ("version", "tile_w", "tile_h", "pixel_size", "count")

    def __init__(self, version, tile_w, tile_h, pixel_size, count):
        self.version = version
        self.tile_w = tile_w
        self.tile_h = tile_h
        self.pixel_size = pixel_size
        self.count = count


def read_tile_header(blob):
    pos = 0
    fields = {}
    for _ in range(5):
        eol = blob.find(b"\n", pos)
        if eol < 0:
            raise KraError("Ebenendatei hat keinen lesbaren Kopf")
        try:
            key, value = blob[pos:eol].split(b" ", 1)
        except ValueError:
            raise KraError("Ebenendatei hat keinen lesbaren Kopf")
        fields[key.decode("ascii", "replace")] = value.decode("ascii", "replace")
        pos = eol + 1
    try:
        hdr = TileHeader(
            int(fields["VERSION"]), int(fields["TILEWIDTH"]),
            int(fields["TILEHEIGHT"]), int(fields["PIXELSIZE"]),
            int(fields["DATA"]),
        )
    except (KeyError, ValueError):
        raise KraError(f"Unerwarteter Ebenen-Kopf: {fields}")
    return hdr, pos


def iter_tiles(blob):
    """Liefert (x, y, rohe_pixel_bytes) fuer jede Kachel."""
    hdr, pos = read_tile_header(blob)
    expected = hdr.tile_w * hdr.tile_h * hdr.pixel_size
    for _ in range(hdr.count):
        eol = blob.find(b"\n", pos)
        if eol < 0:
            raise KraError("Kachel-Zeile abgeschnitten")
        parts = blob[pos:eol].decode("ascii", "replace").split(",")
        if len(parts) != 4:
            raise KraError(f"Unerwartete Kachel-Zeile: {parts}")
        x, y, _comp, size = int(parts[0]), int(parts[1]), parts[2], int(parts[3])
        pos = eol + 1
        payload = blob[pos:pos + size]
        pos += size
        if len(payload) != size:
            raise KraError("Kachel-Daten abgeschnitten")
        flag, body = payload[0], payload[1:]
        data = body if flag == 0 else lzf_decompress(body, expected)
        yield x, y, data


def build_tile_blob(bgra, width, height, tile_w=64, tile_h=64, pixel_size=4):
    """Baut eine Ebenendatei aus einem BGRA-Puffer (zeilenweise, 4 Byte/Pixel).

    Deckt das gesamte Bild mit einem Kachelraster ab 0,0 ab; Kacheln am Rand
    werden mit dem letzten Pixel-Wert 0 aufgefuellt (liegt ausserhalb der
    Leinwand und ist damit unsichtbar).

    pixel_size 8 schreibt 16 Bit pro Kanal (RGBA16). Krita legt dann jedes Byte
    eines Pixels als eigene Ebene ab: B-low, B-high, G-low, ... Aus 8 Bit wird
    v * 257, also low == high - dieselbe Ebene zweimal, was lzf_compress als
    Referenz kodiert.
    """
    if pixel_size not in (4, 8):
        raise KraError(f"{pixel_size} Byte/Pixel werden nicht unterstuetzt")
    stride = width * 4
    if len(bgra) != stride * height:
        raise KraError(f"Pixelpuffer hat {len(bgra)} statt {stride * height} Bytes")

    tile_px = tile_w * tile_h
    empty_row = bytes(tile_w * 4)
    chunks = []
    count = 0

    for ty in range(0, height, tile_h):
        for tx in range(0, width, tile_w):
            # Kachel zeilenweise einsammeln (interleaved BGRA)
            rows = []
            for row in range(tile_h):
                y = ty + row
                if y >= height:
                    rows.append(empty_row)
                    continue
                start = y * stride + tx * 4
                end = min(start + tile_w * 4, y * stride + stride)
                chunk = bgra[start:end]
                if len(chunk) < tile_w * 4:
                    chunk = chunk + bytes(tile_w * 4 - len(chunk))
                rows.append(chunk)
            inter = b"".join(rows)
            # in planar umsortieren - strided slicing laeuft in C
            chans = [inter[c::4] for c in range(4)]
            if pixel_size == 8:
                chans = [p for c in chans for p in (c, c)]
            planar = b"".join(chans)
            if len(planar) != tile_px * pixel_size:
                raise KraError("Interne Kachelgroesse falsch")
            packed = lzf_compress(planar, tile_px)
            if packed is None:
                raise KraError(
                    f"Kachel bei {tx},{ty} laesst sich nicht komprimieren - "
                    "Krita vertraegt keine Kachel, die groesser als die "
                    "Rohdaten ist. Bitte melden, mit welchem Bild das passiert.")
            payload = b"\x01" + packed                       # 1 = LZF
            chunks.append(f"{tx},{ty},LZF,{len(payload)}\n".encode("ascii"))
            chunks.append(payload)
            count += 1

    header = (
        f"VERSION 2\nTILEWIDTH {tile_w}\nTILEHEIGHT {tile_h}\n"
        f"PIXELSIZE {pixel_size}\nDATA {count}\n"
    ).encode("ascii")
    return header + b"".join(chunks)


# --------------------------------------------------------------------------
# Dokument
# --------------------------------------------------------------------------

class KraDocument:
    def __init__(self, path):
        self.path = str(path)
        try:
            with zipfile.ZipFile(self.path) as z:
                self._names = z.namelist()
                maindoc = z.read("maindoc.xml")
        except KeyError:
            raise KraError("maindoc.xml fehlt - das ist keine gueltige .kra")
        except zipfile.BadZipFile:
            raise KraError("Datei ist kein lesbares ZIP - .kra defekt?")

        self.tree = ET.ElementTree(ET.fromstring(maindoc))
        image = self.tree.getroot().find("k:IMAGE", _NS)
        if image is None:
            raise KraError("maindoc.xml enthaelt kein <IMAGE>")
        self.image = image
        self.doc_name = image.get("name") or ""
        try:
            self.width = int(image.get("width"))
            self.height = int(image.get("height"))
        except (TypeError, ValueError):
            raise KraError("Bildgroesse in maindoc.xml nicht lesbar")
        self.colorspace = image.get("colorspacename") or ""
        self.xres = _float(image.get("x-res"), 72.0)
        self.yres = _float(image.get("y-res"), 72.0)

    def layers_element(self):
        layers = self.image.find("k:layers", _NS)
        if layers is None:
            raise KraError("Dokument hat keine Ebenen")
        return layers

    def top_level_layers(self):
        layers = self.image.find("k:layers", _NS)
        return list(layers.findall("k:layer", _NS)) if layers is not None else []

    def background_layer(self):
        """Unterste Ebene der obersten Ebene - in maindoc.xml steht sie zuletzt."""
        layers = self.top_level_layers()
        if not layers:
            raise KraError("Dokument hat keine Ebenen")
        bottom = layers[-1]
        if bottom.get("nodetype") != "paintlayer":
            raise KraError(
                f"Unterste Ebene ist {bottom.get('nodetype')!r} "
                f"({bottom.get('name')!r}), keine Malebene"
            )
        return bottom

    def layer_file(self, layer):
        return f"{self.doc_name}/layers/{layer.get('filename')}"

    def read_layer_header(self, layer):
        with zipfile.ZipFile(self.path) as z:
            with z.open(self.layer_file(layer)) as fh:
                head = fh.read(256)
        return read_tile_header(head)[0]

    def describe(self):
        return [
            (l.get("name") or "", l.get("nodetype") or "", l.get("visible") == "1")
            for l in self.top_level_layers()
        ]


class OutputKra:
    """Die neue .kra - erst vollstaendig im Speicher.

    So wird das PNG aus genau dem gerendert, was hinterher in der Datei steht,
    und mergedimage.png/preview.png lassen sich vor dem Schreiben ersetzen.
    maindoc.xml kommt beim Schreiben aus doc.tree, Aenderungen dort gelten.
    """

    def __init__(self, doc):
        self.doc = doc
        self._entries = {}          # name -> [date_time, external_attr, daten]
        with zipfile.ZipFile(doc.path) as z:
            for info in z.infolist():
                self._entries[info.filename] = [
                    info.date_time, info.external_attr, z.read(info.filename)]

    def names(self):
        return list(self._entries)

    def has(self, name):
        return name in self._entries

    def read(self, name):
        if name == "maindoc.xml":
            return self.maindoc()
        try:
            return self._entries[name][2]
        except KeyError:
            raise KraError(f"Eintrag fehlt in der .kra: {name}")

    def set(self, name, data):
        if name in self._entries:
            self._entries[name][2] = data
        else:
            self._entries[name] = [time.localtime()[:6], 0o644 << 16, data]

    def remove(self, name):
        self._entries.pop(name, None)

    def maindoc(self):
        xml = ET.tostring(self.doc.tree.getroot(), encoding="UTF-8", xml_declaration=True)
        return _restore_doctype(xml)

    def write(self, out_path):
        tmp = str(out_path) + ".part"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            # mimetype muss laut ODF-Konvention unkomprimiert zuerst stehen
            names = sorted(self._entries, key=lambda n: n != "mimetype")
            for name in names:
                date_time, attr, data = self._entries[name]
                if name == "maindoc.xml":
                    data = self.maindoc()
                info = zipfile.ZipInfo(name, date_time=date_time)
                info.compress_type = (zipfile.ZIP_STORED if name == "mimetype"
                                      else zipfile.ZIP_DEFLATED)
                info.external_attr = attr
                zout.writestr(info, data)
        shutil.move(tmp, str(out_path))


def node_entries(names, doc_name, filename):
    """Alle ZIP-Eintraege einer Ebene/Maske: 'layer7', 'layer7.icc',
    'layer7.shapelayer/content.svg' ... - aber nicht 'layer70'."""
    base = f"{doc_name}/layers/{filename}"
    return [n for n in names if n == base or n.startswith(base + ".")]


def replace_background(src_path, bgra, img_w, img_h):
    """Kopie von src_path im Speicher, in der die unterste Malebene die
    uebergebenen Pixel (8-Bit BGRA) traegt. Gibt (OutputKra, ebenenname)."""
    doc = KraDocument(src_path)
    if (img_w, img_h) != (doc.width, doc.height):
        raise KraError(
            f"Groesse passt nicht: Clean ist {img_w}x{img_h}, "
            f"die .kra ist {doc.width}x{doc.height}"
        )

    layer = doc.background_layer()
    # Farbraum zuerst: GRAYAU16 haette ebenfalls 8 Byte/Pixel und wuerde von
    # einer reinen Groessenpruefung nicht erwischt.
    space = layer.get("colorspacename") or doc.colorspace
    want = {"RGBA": 4, "RGBA16": 8}
    if space not in want:
        raise KraError(
            f"Ebene ist {space}, nicht RGBA oder RGBA16 - "
            "SwapR kann nur 8- und 16-Bit-RGBA-Ebenen umbauen")
    hdr = doc.read_layer_header(layer)
    if hdr.pixel_size != want[space]:
        raise KraError(
            f"Ebene ist {space}, hat aber {hdr.pixel_size} Byte/Pixel - "
            "das passt nicht zusammen")

    # Offset der Ebene zuruecksetzen, wir schreiben ab 0,0. Die Deckkraft auch:
    # beim Typesetten wird das Raw gern abgedunkelt, der Clean soll voll decken.
    layer.set("x", "0")
    layer.set("y", "0")
    layer.set("opacity", "255")

    out = OutputKra(doc)
    out.set(doc.layer_file(layer),
            build_tile_blob(bgra, img_w, img_h, hdr.tile_w, hdr.tile_h, hdr.pixel_size))
    return out, layer.get("name") or ""


_NUMBERED = re.compile(r"^(.*?)(\d+)$")


def transplant_layers(ts_path, clean_path):
    """Ersetzt die unterste Malebene von ts_path durch alle Ebenen der
    Clean-.kra - byte-identisch, also verlustfrei und weiter bearbeitbar.

    Gibt (OutputKra, name_der_ersetzten_ebene, [namen_der_clean_ebenen]).
    """
    doc = KraDocument(ts_path)
    clean = KraDocument(clean_path)
    if (clean.width, clean.height) != (doc.width, doc.height):
        raise KraError(
            f"Groesse passt nicht: Clean ist {clean.width}x{clean.height}, "
            f"die .kra ist {doc.width}x{doc.height} - "
            "eine Clean-.kra kann nicht skaliert werden")

    bottom = doc.background_layer()
    new_layers = clean.top_level_layers()
    if not new_layers:
        raise KraError("Clean-.kra hat keine Ebenen")
    for el in new_layers:
        for node in el.iter():
            if node.get("keyframes"):
                raise KraError(f"Clean-Ebene {node.get('name')!r} ist animiert - "
                               "wird nicht unterstuetzt")
            if node.get("layerstyle"):
                raise KraError(f"Clean-Ebene {node.get('name')!r} hat einen Ebenenstil - "
                               "wird nicht unterstuetzt")

    out = OutputKra(doc)

    # Raw-Ebene samt Masken und Dateien raus
    for node in bottom.iter():
        if node.get("filename"):
            for n in node_entries(out.names(), doc.doc_name, node.get("filename")):
                out.remove(n)

    # Neue Dateinamen, die mit nichts im TS kollidieren
    used = [node.get("filename") for node in doc.image.iter() if node.get("filename")]
    counter = max([int(m.group(2)) for m in map(_NUMBERED.match, used) if m] + [0]) + 1
    uuids = {node.get("uuid") for node in doc.image.iter() if node.get("uuid")}

    copies = [copy.deepcopy(el) for el in new_layers]
    with zipfile.ZipFile(clean.path) as z:
        clean_names = z.namelist()
        for el in copies:
            for node in el.iter():
                node.attrib.pop("selected", None)
                if node.get("uuid") in uuids:
                    node.set("uuid", "{%s}" % uuid.uuid4())
                old = node.get("filename")
                if not old:
                    continue
                m = _NUMBERED.match(old)
                new = f"{m.group(1) if m else old}{counter}"
                counter += 1
                node.set("filename", new)
                src_base = f"{clean.doc_name}/layers/{old}"
                for n in node_entries(clean_names, clean.doc_name, old):
                    out.set(f"{doc.doc_name}/layers/{new}{n[len(src_base):]}", z.read(n))

    layers = doc.layers_element()
    pos = list(layers).index(bottom)
    layers.remove(bottom)
    for i, el in enumerate(copies):
        layers.insert(pos + i, el)

    return out, bottom.get("name") or "", [el.get("name") or "" for el in copies]


_DOCTYPE = (
    b"<!DOCTYPE DOC PUBLIC '-//KDE//DTD krita 2.0//EN' "
    b"'http://www.calligra.org/DTD/krita-2.0.dtd'>"
)


def _restore_doctype(xml_bytes):
    """ElementTree wirft die DOCTYPE-Zeile weg; Krita erwartet sie."""
    if b"<!DOCTYPE" in xml_bytes:
        return xml_bytes
    idx = xml_bytes.find(b"?>")
    if idx < 0:
        return _DOCTYPE + b"\n" + xml_bytes
    return xml_bytes[:idx + 2] + b"\n" + _DOCTYPE + xml_bytes[idx + 2:]


def _float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------

_NUM = re.compile(r"\d+")


def page_number(filename):
    """Erste Zahl im Dateinamen - 'page 1-Recuperado.jpg' -> 1, '10.png.kra' -> 10."""
    stem = filename
    for suffix in (".kra", ".psd"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
    m = _NUM.search(stem)
    return int(m.group()) if m else None
