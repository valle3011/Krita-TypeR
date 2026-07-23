"""Read a Google Docs script (text + comments) into TypeR's own model.

A `.gdoc` on disk is not a document — it is a four-line JSON stub pointing at
Drive:

    {"doc_id": "1JCX54…", "email": "you@gmail.com"}

so the text has to be fetched. Two endpoints are involved, because neither
gives both halves:

* **Docs API** `documents.get` → the paragraphs.
* **Drive API** `comments.list` → the comments. Drive's `anchor` field is
  opaque for Docs, so a comment cannot be turned into a paragraph index
  directly. It does return `quotedFileContent` — the text the note is stuck
  to — which comments.attach_by_quote() matches back onto the lines. Same
  anchoring, no undocumented formats.

The Drive endpoint is also the richer source: unlike a .docx export it keeps
replies and the resolved flag.
"""

import json
import urllib.parse

from . import gauth
from .comments import Comment

DOCS_GET = "https://docs.googleapis.com/v1/documents/%s"
DRIVE_COMMENTS = "https://www.googleapis.com/drive/v3/files/%s/comments"
EXPORT_URL = "https://docs.google.com/document/d/%s/export?format=docx"

_COMMENT_FIELDS = ("comments(id,content,author/displayName,createdTime,"
                   "resolved,quotedFileContent/value,"
                   "replies(content,author/displayName,createdTime)),"
                   "nextPageToken")


def is_gdoc(path):
    return (path or "").lower().endswith(".gdoc")


def read_stub(path):
    """The document id inside a .gdoc shortcut.

    Raises ValueError with something readable, because "it didn't work" is
    useless when the file looks like a document to the user.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception as e:
        raise ValueError("Could not read the .gdoc shortcut: %s" % e)
    doc_id = d.get("doc_id") or d.get("resource_id") or ""
    if ":" in doc_id:                      # older stubs: "document:<id>"
        doc_id = doc_id.split(":", 1)[1]
    if not doc_id:
        raise ValueError("That .gdoc has no document id in it.")
    return doc_id


def export_url(doc_id):
    """Browser URL that downloads the doc as .docx (comments included).

    Kept as a fallback: it needs no API access at all, only a logged-in
    browser, which is handy when sign-in is not set up.
    """
    return EXPORT_URL % doc_id


def _para_text(el):
    """Flatten one structural element into its plain text."""
    para = el.get("paragraph")
    if not para:
        return None
    out = []
    for pe in para.get("elements", ()):
        run = pe.get("textRun")
        if run:
            out.append(run.get("content", ""))
    return "".join(out).replace("\v", "\n").rstrip("\n")


def fetch_lines(doc_id, tok):
    """The document's paragraphs, in order.

    Empty paragraphs are kept: they are what separates the script's blocks,
    and dropping them would shift every index the comments point at.
    """
    doc = gauth.get_json(DOCS_GET % doc_id, tok)
    body = (doc.get("body") or {}).get("content") or []
    lines = []
    for el in body:
        t = _para_text(el)
        if t is not None:
            lines.append(t)
    return lines


def fetch_comments(doc_id, tok, include_resolved=False):
    """Every comment on the document, as TypeR Comments (not yet anchored).

    The caller runs comments.attach_by_quote() against the script lines to
    turn `quoted` into line indices.
    """
    out = []
    page_token = ""
    while True:
        args = {"fields": _COMMENT_FIELDS, "pageSize": "100",
                "includeDeleted": "false"}
        if page_token:
            args["pageToken"] = page_token
        url = (DRIVE_COMMENTS % doc_id) + "?" + urllib.parse.urlencode(args)
        data = gauth.get_json(url, tok)
        for c in data.get("comments", ()):
            if c.get("resolved") and not include_resolved:
                continue
            author = ((c.get("author") or {}).get("displayName")) or ""
            replies = []
            for r in c.get("replies", ()):
                ra = ((r.get("author") or {}).get("displayName")) or ""
                rc = (r.get("content") or "").strip()
                if rc:
                    replies.append("%s: %s" % (ra, rc) if ra else rc)
            out.append(Comment(
                id=c.get("id") or "",
                author=author,
                date=(c.get("createdTime") or "")[:10],
                text=(c.get("content") or "").strip(),
                resolved=bool(c.get("resolved")),
                replies=replies,
                quoted=((c.get("quotedFileContent") or {}).get("value") or ""),
            ))
        page_token = data.get("nextPageToken") or ""
        if not page_token:
            break
    return out


def load(path_or_id, tok, include_resolved=False):
    """Everything TypeR needs from a Google Doc: (lines, anchored comments)."""
    from . import comments as CM

    doc_id = read_stub(path_or_id) if is_gdoc(path_or_id) else path_or_id
    lines = fetch_lines(doc_id, tok)
    cs = fetch_comments(doc_id, tok, include_resolved=include_resolved)
    CM.attach_by_quote(cs, lines)
    cs.sort(key=lambda c: (c.lines[0] if c.lines else 1 << 30, c.id))
    return lines, cs
