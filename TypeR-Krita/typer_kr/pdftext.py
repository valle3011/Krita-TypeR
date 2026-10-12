# -*- coding: utf-8 -*-
"""Read the text out of a PDF script, using nothing but the standard library.

Translation scripts turn up as PDFs, usually a table of Japanese against
English. Krita's embedded Python has no PDF library and a plugin cannot install
one, so this reads the format directly: `zlib` for the compressed streams and
plain scanning for the rest.

What it does and does not do, deliberately:

* **Text only.** A PDF's text is a series of positioned glyph runs with no
  notion of a line, let alone a table cell. So every run is collected with the
  point it is drawn at, runs sharing a baseline become a row, and a wide gap
  within a row becomes a cell boundary (a tab) - which is what gives TypeR the
  two-column `source<TAB>translation` rows it already understands.
* **Glyph codes are mapped through the font's ToUnicode CMap.** Without it a
  subset font's codes are not characters at all: in the file this was written
  for, "Page" is stored as 0x33 0x44 0x4A 0x48.
* **No scanned pages.** Text drawn as an image needs OCR, which is not
  something to smuggle into a typesetting plugin. Such a file reports that it
  holds no text rather than returning nothing.
* **No encryption and no object streams.** Both are refused by name, so the
  message says what is wrong instead of producing half a script.
"""

import re
import unicodedata
import zlib

#: Catches `N G obj … endobj`. The generation number is kept out of the key:
#: incremental updates append a newer object with the same number, and taking
#: the last occurrence is exactly the right answer.
_OBJ = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)
_REF = re.compile(rb"(\d+)\s+0\s+R")
_PAGE_TYPE = re.compile(rb"/Type\s*/Page(?![\w])")

#: Two runs are on the same line when their baselines are closer than this, in
#: PDF units (1/72 inch). Generous enough for the superscript-ish jitter a word
#: processor leaves behind, far below a line's height.
_LINE_TOL = 3.0

#: A vertical corridor must be at least this wide to count as a column
#: boundary, in PDF units. Below it, ordinary word spacing starts to qualify.
_MIN_CORRIDOR = 10.0


class PdfError(Exception):
    """The PDF cannot be read, with a reason worth showing the user.

    `kind` is one of "notpdf", "encrypted", "objstm", "notext" or "open", so
    the docker can put it in the interface language; `str(e)` stays readable on
    its own for anywhere that has no table to look it up in.
    """

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Object layer
# ---------------------------------------------------------------------------

def _objects(raw):
    return {int(m.group(1)): m.group(3) for m in _OBJ.finditer(raw)}


def _stream_data(body):
    """The decompressed stream of an object body ("" when there is none)."""
    m = _STREAM.search(body)
    if not m:
        return b""
    head = body[:m.start()]
    data = m.group(1)
    if b"/FlateDecode" not in head:
        return data
    try:
        return zlib.decompress(data)
    except zlib.error:
        try:                              # truncated or mis-declared length
            return zlib.decompressobj().decompress(data)
        except Exception:
            return b""


def _balanced(data, i):
    """The value starting at `data[i]`: a dict, an array, or a bare token.

    Brackets are counted and strings are stepped over, because a regex cannot
    do this. `/Resources <</ProcSet […] /Font <<…>>>>` ends at its first inner
    `>>` for any non-greedy match, which cuts the value off before /Font.
    """
    if data[i:i + 2] == b"<<":
        depth, j = 0, i
        while j < len(data):
            if data[j:j + 1] == b"(":                  # a string may hold >>
                j = _skip_string(data, j)
                continue
            if data[j:j + 2] == b"<<":
                depth += 1
                j += 2
            elif data[j:j + 2] == b">>":
                depth -= 1
                j += 2
                if not depth:
                    return data[i:j]
            else:
                j += 1
        return data[i:]
    if data[i:i + 1] == b"[":
        depth, j = 0, i
        while j < len(data):
            c = data[j:j + 1]
            if c == b"(":
                j = _skip_string(data, j)
                continue
            if c == b"[":
                depth += 1
            elif c == b"]":
                depth -= 1
                if not depth:
                    return data[i:j + 1]
            j += 1
        return data[i:]
    m = re.match(rb"(/[^\s/<>\[\]()]+|<[0-9A-Fa-f\s]*>|[-+\d.]+|\w+)", data[i:])
    return m.group(1) if m else b""


def _skip_string(data, i):
    """Index just past the `(…)` string starting at `i`."""
    depth, j = 1, i + 1
    while j < len(data) and depth:
        c = data[j:j + 1]
        if c == b"\\":
            j += 2
            continue
        if c == b"(":
            depth += 1
        elif c == b")":
            depth -= 1
        j += 1
    return j


def _get(objs, body, key):
    """The value of `key` in a dict body, one indirect reference followed."""
    for m in re.finditer(re.escape(key) + rb"(?![\w.])", body):
        j = m.end()
        while j < len(body) and body[j:j + 1].isspace():
            j += 1
        ref = re.match(rb"(\d+)\s+0\s+R\b", body[j:])
        if ref:
            return objs.get(int(ref.group(1)), b"")
        val = _balanced(body, j)
        if val:
            return val
    return b""


def _pages(objs):
    """Page object numbers in reading order.

    Walked through the page tree rather than taken from object order, which
    only happens to agree in simply built files.
    """
    root = None
    for body in objs.values():
        if b"/Catalog" in body:
            m = re.search(rb"/Pages\s+(\d+)\s+0\s+R", body)
            if m:
                root = int(m.group(1))
                break
    found, seen = [], set()

    def walk(num, depth):
        if depth > 64 or num in seen or num not in objs:
            return
        seen.add(num)
        body = objs[num]
        kids = re.search(rb"/Kids\s*\[(.*?)\]", body, re.S)
        if kids:
            for k in _REF.findall(kids.group(1)):
                walk(int(k), depth + 1)
        elif _PAGE_TYPE.search(body + b" "):
            found.append(num)

    if root is not None:
        walk(root, 0)
    if not found:
        found = sorted(n for n, b in objs.items()
                       if _PAGE_TYPE.search(b + b" "))
    return found


# ---------------------------------------------------------------------------
# Fonts: glyph code -> text
# ---------------------------------------------------------------------------

def _cmap(data):
    """{code: text} from a ToUnicode CMap's bfchar / bfrange sections."""
    out = {}

    def utf16(h):
        try:
            return bytes.fromhex(h.decode("ascii")).decode("utf-16-be")
        except Exception:
            return ""

    for sec in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", sec):
            out[int(src, 16)] = utf16(dst)
    for sec in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
        # the "<lo> <hi> [<a> <b> …]" form lists one target per code
        for lo, arr in re.findall(
                rb"<([0-9A-Fa-f]+)>\s*<[0-9A-Fa-f]+>\s*\[(.*?)\]", sec, re.S):
            start = int(lo, 16)
            for k, dst in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", arr)):
                out[start + k] = utf16(dst)
        for lo, hi, dst in re.findall(
                rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", sec):
            a, b, base = int(lo, 16), int(hi, 16), int(dst, 16)
            for i in range(a, min(b, a + 0xFFFF) + 1):
                try:
                    out[i] = chr(base + (i - a))
                except ValueError:
                    pass
    return out


def _fonts(objs, page_body):
    """{resource name: (cmap, code width in bytes)} for one page."""
    res = _get(objs, page_body, b"/Resources")
    fdict = _get(objs, res, b"/Font")
    out = {}
    for name, num in re.findall(rb"/([^\s/<>\[\]]+)\s+(\d+)\s+0\s+R", fdict):
        body = objs.get(int(num), b"")
        wide = b"/Type0" in body or b"/Identity-H" in body
        tu = _get(objs, body, b"/ToUnicode")
        cmap = _cmap(_stream_data(tu)) if tu else {}
        out[name.decode("latin-1")] = (cmap, 2 if wide else 1)
    return out


def _decode(data, cmap, width):
    if width == 2:
        codes = [int.from_bytes(data[i:i + 2], "big")
                 for i in range(0, len(data) - 1, 2)]
    else:
        codes = list(data)
    if cmap:
        return "".join(cmap.get(c, "") for c in codes)
    # no CMap: a simple font's codes are usually its characters outright
    return data.decode("latin-1", "replace")


# ---------------------------------------------------------------------------
# Content streams
# ---------------------------------------------------------------------------

def _mul(m, n):
    """m then n, as PDF 3x2 matrices (a, b, c, d, e, f)."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2,
            c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2)


_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

_TOKEN = re.compile(rb"""
      (?P<name>/[^\s/<>\[\](){}]+)
    | (?P<num>[-+]?(?:\d+\.?\d*|\.\d+))
    | (?P<str>\()
    | (?P<hex><[0-9A-Fa-f\s]*>)
    | (?P<arr>\[)
    | (?P<dict><<|>>)
    | (?P<op>[A-Za-z'"*][A-Za-z0-9'"*]*)
""", re.X)


def _runs(content, fonts):
    """Every glyph run of a content stream as (x, y, size, text).

    A plain operand-stack walk: anything but the text and matrix operators is
    skipped, which is what keeps this short enough to trust.
    """
    out = []
    stack = []                       # operand stack
    gs = []                          # graphics-state stack for q / Q
    ctm = _IDENTITY
    tm = tlm = _IDENTITY
    cmap, width, size, leading = {}, 1, 0.0, 0.0
    i, n = 0, len(content)

    def show(raw):
        if not raw:
            return
        text = _decode(raw, cmap, width)
        if not text:
            return                   # a space IS a run: dropping it would
                                     # glue the words either side together
        m = _mul(tm, ctm)
        out.append((m[4], m[5], size, text))

    while i < n:
        m = _TOKEN.match(content, i)
        if not m:
            i += 1
            continue
        i = m.end()
        kind = m.lastgroup
        if kind == "num":
            stack.append(float(m.group()))
            continue
        if kind == "name":
            stack.append(m.group())
            continue
        if kind == "hex":
            h = re.sub(rb"[^0-9A-Fa-f]", b"", m.group()[1:-1])
            if len(h) % 2:
                h += b"0"
            stack.append(bytes.fromhex(h.decode("ascii")))
            continue
        if kind == "str":
            j = _skip_string(content, m.start())
            stack.append(_unescape(content[m.start() + 1:j - 1]))
            i = j
            continue
        if kind == "arr":
            j, items = i, []
            while j < n and content[j:j + 1] != b"]":
                mm = _TOKEN.match(content, j)
                if not mm:
                    j += 1
                    continue
                if mm.lastgroup == "str":
                    k = _skip_string(content, mm.start())
                    items.append(_unescape(content[mm.start() + 1:k - 1]))
                    j = k
                    continue
                if mm.lastgroup == "hex":
                    h = re.sub(rb"[^0-9A-Fa-f]", b"", mm.group()[1:-1])
                    if len(h) % 2:
                        h += b"0"
                    items.append(bytes.fromhex(h.decode("ascii")))
                j = mm.end()
            stack.append(items)
            i = j + 1
            continue
        if kind == "dict":
            continue
        op = m.group()
        if op == b"q":
            gs.append(ctm)
        elif op == b"Q":
            ctm = gs.pop() if gs else _IDENTITY
        elif op == b"cm" and len(stack) >= 6:
            ctm = _mul(tuple(stack[-6:]), ctm)
        elif op == b"BT":
            tm = tlm = _IDENTITY
        elif op == b"Tf":
            if len(stack) >= 2 and isinstance(stack[-2], bytes):
                cmap, width = fonts.get(stack[-2][1:].decode("latin-1"),
                                        ({}, 1))
            if stack and isinstance(stack[-1], float):
                size = stack[-1]
        elif op == b"TL" and stack:
            leading = stack[-1]
        elif op in (b"Td", b"TD") and len(stack) >= 2:
            if op == b"TD":
                leading = -stack[-1]
            tm = tlm = _mul((1.0, 0.0, 0.0, 1.0, stack[-2], stack[-1]), tlm)
        elif op == b"Tm" and len(stack) >= 6:
            tm = tlm = tuple(stack[-6:])
        elif op == b"T*":
            tm = tlm = _mul((1.0, 0.0, 0.0, 1.0, 0.0, -leading), tlm)
        elif op == b"Tj" and stack:
            show(stack[-1] if isinstance(stack[-1], bytes) else b"")
        elif op == b"'":
            tm = tlm = _mul((1.0, 0.0, 0.0, 1.0, 0.0, -leading), tlm)
            show(stack[-1] if stack and isinstance(stack[-1], bytes) else b"")
        elif op == b'"':
            tm = tlm = _mul((1.0, 0.0, 0.0, 1.0, 0.0, -leading), tlm)
            show(stack[-1] if stack and isinstance(stack[-1], bytes) else b"")
        elif op == b"TJ" and stack and isinstance(stack[-1], list):
            show(b"".join(x for x in stack[-1] if isinstance(x, bytes)))
        if op:
            del stack[:]
    return out


def _unescape(s):
    out = bytearray()
    i = 0
    simple = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}
    while i < len(s):
        c = s[i]
        if c == 0x5C and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            if 0x30 <= nxt <= 0x37:
                dig, j = b"", i + 1
                while j < len(s) and len(dig) < 3 and 0x30 <= s[j] <= 0x37:
                    dig += s[j:j + 1]
                    j += 1
                out.append(int(dig, 8) & 0xFF)
                i = j
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return bytes(out)


# ---------------------------------------------------------------------------
# Runs -> rows of cells
# ---------------------------------------------------------------------------

def _text_width(text, size):
    """Roughly how wide a run is. Enough to find the empty bands.

    The real answer is in the font's /Widths or /W array; this estimate - full
    width for East Asian characters, half for the rest - is accurate enough to
    tell a corridor from a word space, and keeps a font-metrics parser out of
    the module.
    """
    w = 0.0
    for ch in text:
        w += size * (1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.5)
    return w


def _corridors(runs, min_width):
    """Vertical bands no run crosses, as (left, right) in page coordinates."""
    if not runs:
        return []
    spans = sorted((r[0], r[0] + _text_width(r[3], r[2])) for r in runs)
    out, reach = [], spans[0][1]
    for left, right in spans[1:]:
        if left - reach >= min_width:
            out.append((reach, left))
        reach = max(reach, right)
    return out


def column_splits(pages_runs, min_width=_MIN_CORRIDOR):
    """The x positions where a new column starts, for the whole document.

    A corridor is only believed when the same one turns up on at least half of
    the pages that hold text: a single page's longest line can leave a gap that
    looks exactly like a column, while a table's boundary repeats by
    construction. Positions are rounded to whole units before being counted,
    since a table aligns its cells but a renderer rounds.
    """
    pages_with_text = [r for r in pages_runs if r]
    if not pages_with_text:
        return []
    counts = {}
    for runs in pages_with_text:
        for _left, right in _corridors(runs, min_width):
            key = round(right)
            counts[key] = counts.get(key, 0) + 1
    need = max(1, (len(pages_with_text) + 1) // 2)
    return sorted(x for x, n in counts.items() if n >= need)


def rows_from_runs(runs, splits=()):
    """Glyph runs grouped into rows of cells, top to bottom, left to right.

    A PDF has no lines: runs sharing a baseline are one. `splits` are the x
    positions where a new cell begins, from column_splits() - with none, a row
    is a single cell and the result is plain text.
    """
    if not runs:
        return []
    rows = []
    for x, y, size, text in sorted(runs, key=lambda r: (-r[1], r[0])):
        if rows and abs(rows[-1][0] - y) <= _LINE_TOL:
            rows[-1][1].append((x, text))
        else:
            rows.append((y, [(x, text)]))
    out = []
    for _y, frags in rows:
        frags.sort(key=lambda f: f[0])
        cells = [[] for _ in range(len(splits) + 1)]
        for x, text in frags:
            col = 0
            for i, edge in enumerate(splits, 1):
                if x >= edge - 0.5:
                    col = i
            cells[col].append(text)
        row = [" ".join("".join(c).split()) for c in cells]
        while row and not row[-1]:
            row.pop()
        if any(row):
            out.append(row)
    return out


def page_rows(path):
    """[(page number, [[cell, …], …]), …] for the whole file."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        raise PdfError("open", "Could not open the PDF: %s" % e)
    if not raw.startswith(b"%PDF"):
        raise PdfError("notpdf", "That file is not a PDF.")
    if re.search(rb"/Encrypt\b", raw):
        raise PdfError("encrypted",
                       "This PDF is encrypted. Save it without a password "
                       "(or export the script as .docx) and load that.")
    objs = _objects(raw)
    if not objs and re.search(rb"/ObjStm\b", raw):
        raise PdfError("objstm",
                       "This PDF stores its objects compressed, which TypeR "
                       "cannot unpack. Re-save it as PDF 1.4, or export the "
                       "script as .docx.")
    # the runs first, the columns after: a table's boundary is only
    # recognisable from the whole document, not from one page or one row
    per_page = []
    for num in _pages(objs):
        body = objs.get(num, b"")
        contents = _get(objs, body, b"/Contents")
        datas = []
        if contents.strip().startswith(b"["):
            for ref in _REF.findall(contents):
                datas.append(_stream_data(objs.get(int(ref), b"")))
        else:
            datas.append(_stream_data(contents))
        fonts = _fonts(objs, body)
        runs = []
        for d in datas:
            if d:
                runs.extend(_runs(d, fonts))
        per_page.append(runs)
    splits = column_splits(per_page)
    return [(i, rows_from_runs(runs, splits))
            for i, runs in enumerate(per_page, 1)]


def read_pdf(path):
    """The PDF's text as a script: one row per line, cells tab separated.

    Tabs are what TypeR's own two-column parsing reads as
    `source<TAB>translation`, so a JP/EN table arrives already paired.
    """
    pages = page_rows(path)
    lines = []
    for _num, rows in pages:
        for row in rows:
            lines.append("\t".join(row))
    if not any(l.strip() for l in lines):
        raise PdfError("notext",
                       "This PDF holds no text TypeR can read - its pages are "
                       "probably scans. A scan needs OCR first; or load the "
                       "script as .docx / .txt instead.")
    return "\n".join(lines)
