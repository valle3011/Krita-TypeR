"""Script comments — one model, several sources.

A translation script carries notes: "this is a pun", "check page 12", "not
sure about this line". Those live as comments in the document, and the
typesetter needs them *next to the line they belong to* — not in a separate
window they have to keep cross-referencing.

Where a comment comes from should not matter to the rest of TypeR, so both
sources normalise into the same `Comment`:

* **.docx** — `word/comments.xml` holds the text, and `document.xml` marks the
  anchored span with `commentRangeStart`/`commentRangeEnd`, which gives exact
  paragraph indices. Google Docs exports keep their comments, so this already
  works for scripts exported from Drive.
* **Google Docs API** — the Drive comments endpoint has no usable paragraph
  index (its `anchor` is opaque), but it does return `quotedFileContent`: the
  text the comment is attached to. Matching that against the script lines
  gives the same anchoring. See gdocs.py.

Scope follows what the comment actually marks: a comment spanning a single
line belongs to that line, one spanning several belongs to the page.
"""

import re
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

SCOPE_LINE = "line"
SCOPE_PAGE = "page"


class Comment(object):
    """One note from the script, already tied to the lines it marks.

    `lines` are indices into the script's paragraph list. `scope` is derived,
    not stored by the author: a note that marks one line is about that line;
    one that spans several is about the page.
    """

    __slots__ = ("id", "author", "date", "text", "resolved", "replies",
                 "quoted", "lines")

    def __init__(self, id="", author="", date="", text="", resolved=False,
                 replies=None, quoted="", lines=None):
        self.id = id
        self.author = author
        self.date = date
        self.text = text
        self.resolved = resolved
        self.replies = list(replies or ())
        self.quoted = quoted
        self.lines = sorted(set(lines or ()))

    @property
    def scope(self):
        return SCOPE_LINE if len(self.lines) <= 1 else SCOPE_PAGE

    def __repr__(self):
        return "<Comment %s %s lines=%s %r>" % (
            self.id, self.scope, self.lines, self.text[:30])


def _para_text(p):
    return "".join(t.text or "" for t in p.iter(W + "t"))


# Google's .docx export glues a comment's reactions onto the end of its text,
# so "nah use it" arrives as "nah use it1 total reactionguilhbr reacted with 👍
# at 2025-09-28 09:12 AM". Cut it back to what the person actually wrote.
# No \b after "reaction": the export runs it straight into the next word
# ("…reactionguilhbr reacted with…"), so there is no word boundary to match.
_REACTIONS = re.compile(r"\d+\s*total\s*reactions?.*$", re.S | re.I)


def _clean(text):
    text = _REACTIONS.sub("", text or "")
    return text.replace("\xa0", " ").strip()


def from_docx(path):
    """Read the comments of a .docx, anchored to paragraph indices.

    Returns [] for a document without comments — that is the normal case, not
    an error.
    """
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        return []
    try:
        names = z.namelist()
        if "word/comments.xml" not in names:
            return []

        meta = {}
        croot = ET.fromstring(z.read("word/comments.xml"))
        for cm in croot.iter(W + "comment"):
            cid = cm.get(W + "id")
            meta[cid] = {
                "author": cm.get(W + "author") or "",
                "date": (cm.get(W + "date") or "")[:10],
                "text": _clean("".join(t.text or "" for t in cm.iter(W + "t"))),
            }

        # walk the body once, remembering which paragraphs each id spans
        droot = ET.fromstring(z.read("word/document.xml"))
        body = droot.find(W + "body")
        spans = {}
        quoted = {}
        open_ids = set()
        for idx, p in enumerate(body.iter(W + "p")):
            starts = {s.get(W + "id") for s in p.iter(W + "commentRangeStart")}
            ends = {s.get(W + "id") for s in p.iter(W + "commentRangeEnd")}
            open_ids |= starts
            # a paragraph counts for every range that is open across it
            for cid in open_ids:
                spans.setdefault(cid, set()).add(idx)
                quoted.setdefault(cid, []).append(_para_text(p))
            open_ids -= ends

        out = []
        for cid, m in meta.items():
            out.append(Comment(
                id=cid, author=m["author"], date=m["date"], text=m["text"],
                quoted=" / ".join(t for t in quoted.get(cid, []) if t)[:200],
                lines=spans.get(cid, ()),
            ))
        out.sort(key=lambda c: (c.lines[0] if c.lines else 1 << 30, c.id))
        return out
    except Exception:
        # a malformed script must never stop the user from typesetting
        return []
    finally:
        try:
            z.close()
        except Exception:
            pass


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def attach_by_quote(comments, lines):
    """Anchor comments that only know their quoted text (the Google path).

    Drive returns `quotedFileContent` rather than a paragraph index, so the
    quote is matched against the script lines. Comments that already know
    their lines are left alone.
    """
    norm_lines = [_norm(l) for l in lines]
    for c in comments:
        if c.lines or not c.quoted:
            continue
        q = _norm(c.quoted)
        if not q:
            continue
        hits = [i for i, l in enumerate(norm_lines) if l and (l in q or q in l)]
        if not hits:
            # fall back to the longest quoted fragment that does match
            for frag in sorted(re.split(r"\s*/\s*|\n", c.quoted),
                               key=len, reverse=True):
                fq = _norm(frag)
                if len(fq) < 3:
                    continue
                hits = [i for i, l in enumerate(norm_lines) if l and fq in l]
                if hits:
                    break
        c.lines = sorted(set(hits))
    return comments


def anchor_to_units(comments, unit_texts):
    """Re-anchor comments from script lines onto TypeR's translation units.

    A comment knows the paragraphs it marks, but TypeR works in *units* (a
    JA/EN pair), and pairing drops the source line numbers — so the paragraph
    index cannot be carried across. The quoted text can: it is matched against
    the units, exactly like the Google path does with `quotedFileContent`.

    Comments whose quote matches nothing keep no anchor and simply never show,
    which is better than pinning them to the wrong line.
    """
    norm_units = [_norm(t) for t in unit_texts]
    for c in comments:
        c.lines = []
        if not c.quoted:
            continue
        frags = [f for f in re.split(r"\s*/\s*|\n", c.quoted) if _norm(f)]
        hits = set()
        for frag in frags:
            fq = _norm(frag)
            if len(fq) < 3:
                continue
            for i, u in enumerate(norm_units):
                if u and (fq in u or u in fq):
                    hits.add(i)
        c.lines = sorted(hits)
    return comments


def for_unit(comments, index, unit_pages):
    """What to show while the typesetter sits on unit `index`.

    A note marking a single unit is about that unit. A note spanning several is
    about the page, so it stays up for the whole page rather than blinking in
    and out as you step through the lines it happens to touch.

    `unit_pages` is TypeR's per-unit page label list (_pair_pages).
    """
    if index is None or index < 0:
        return []
    page = unit_pages[index] if 0 <= index < len(unit_pages) else ""
    out = []
    for c in comments:
        if not c.lines:
            continue
        if c.scope == SCOPE_LINE:
            if index in c.lines:
                out.append(c)
        else:
            pages = {unit_pages[i] for i in c.lines
                     if 0 <= i < len(unit_pages)}
            if page in pages:
                out.append(c)
    return out


def for_line(comments, line_index):
    """Comments a given line should show: its own, plus the page-wide ones."""
    return [c for c in comments
            if (c.scope == SCOPE_LINE and line_index in c.lines)
            or (c.scope == SCOPE_PAGE and c.lines and
                c.lines[0] <= line_index <= c.lines[-1])]


def for_lines(comments, line_indices):
    """Every comment touching any of `line_indices` (i.e. the current page)."""
    want = set(line_indices or ())
    if not want:
        return []
    out = []
    for c in comments:
        if not c.lines:
            continue
        # page-scope comments span their whole range, not just the marked ends
        touched = set(range(c.lines[0], c.lines[-1] + 1)) if c.scope == SCOPE_PAGE \
            else set(c.lines)
        if touched & want:
            out.append(c)
    return out


def has_any(comments, line_indices):
    """Whether a page has anything to say — drives auto-hiding the docker."""
    return bool(for_lines(comments, line_indices))
