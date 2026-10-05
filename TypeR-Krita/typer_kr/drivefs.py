# -*- coding: utf-8 -*-
"""The document id behind a .gdoc that cannot be read at all.

A .gdoc is meant to be a four-line JSON stub, and `gdocs.read_stub()` simply
opens it. On current Google Drive for Desktop that no longer works: the
virtual drive answers every read of a .gdoc / .gsheet / .gslides shortcut
with ERROR_INVALID_FUNCTION, which Python surfaces as

    OSError: [Errno 22] Invalid argument

even though `os.stat()` cheerfully reports the file as 176 bytes. It is not a
Python problem and not a permission problem — `type`, PowerShell and a plain
file copy all fail the same way. The bytes are simply never handed out; only
Drive's own shell handler knows what is in them.

What the client *does* leave readable is its local index: an ordinary SQLite
file per signed-in account under

    %LOCALAPPDATA%\\Google\\DriveFS\\<account>\\metadata_sqlite_db

with one row per item, carrying both the Drive id and the on-disk name. So the
id can be looked up by name instead of read out of the file.

Names repeat, though — a folder of chapters holds a dozen files called
`TL.gdoc` — so a name alone is not an answer. `stable_parents` gives each
item's parents, and the path we were handed gives the folder names they should
have, so the candidates are scored by how far up that chain they agree and
only a single clear winner counts. The drive root is not part of that: Drive
localises it (`Meine Ablage` on a German account, mounted as `My Drive`), so
matching stops wherever the names stop agreeing.

This is Drive's private storage and it may change shape. Every failure here is
therefore a plain "" — the caller falls back to asking for the document link,
which needs no client at all.
"""

import os
import sqlite3

_LEAF = ("SELECT stable_id, id FROM items "
         "WHERE local_title = ? AND trashed = 0 AND is_folder = 0")

_PARENTS = ("SELECT p.parent_stable_id, i.local_title "
            "FROM stable_parents p "
            "LEFT JOIN items i ON i.stable_id = p.parent_stable_id "
            "WHERE p.item_stable_id = ?")

# the streamed drive and the mirrored folders keep separate indexes with the
# same schema; a .gdoc can sit in either
_DB_NAMES = ("metadata_sqlite_db", "mirror_metadata_sqlite.db")


def _drivefs_dir():
    """Where the Drive client keeps its per-account state."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:                                   # macOS
        base = os.path.expanduser("~/Library/Application Support")
    return os.path.join(base, "Google", "DriveFS")


def _databases():
    """Every account index on this machine (both may be absent)."""
    root = _drivefs_dir()
    out = []
    try:
        accounts = sorted(os.listdir(root))
    except OSError:
        return out
    for acct in accounts:
        for name in _DB_NAMES:
            p = os.path.join(root, acct, name)
            if os.path.isfile(p):
                out.append(p)
    return out


def _connect(path):
    """Read-only connection, or None.

    Drive keeps the database open with a write-ahead log, so read-only is the
    only safe way in. When even that is refused (the client holding a lock),
    `immutable` reads the main file alone — possibly a few minutes stale,
    which for a document id is the same answer.
    """
    quoted = path.replace("?", "%3f").replace("#", "%23").replace("\\", "/")
    for mode in ("mode=ro", "immutable=1"):
        try:
            con = sqlite3.connect("file:%s?%s" % (quoted, mode),
                                  uri=True, timeout=2.0)
            con.execute("SELECT 1 FROM items LIMIT 1")
            return con
        except Exception:
            continue
    return None


def _ancestor_score(con, stable_id, folders, depth=0):
    """How many of `folders` (nearest first) this item's ancestors match."""
    if depth >= len(folders):
        return 0
    want = folders[depth].casefold()
    best = 0
    for parent_id, title in con.execute(_PARENTS, (stable_id,)):
        if (title or "").casefold() != want:
            continue
        best = max(best, 1 + _ancestor_score(con, parent_id, folders,
                                             depth + 1))
    return best


def _candidates(con, name, folders):
    """(score, doc_id) for every indexed item that could be this path."""
    out = []
    for stable_id, doc_id in con.execute(_LEAF, (name,)):
        if doc_id:
            out.append((_ancestor_score(con, stable_id, folders), doc_id))
    return out


def path_parts(path):
    """(filename, folder names from the file outwards) for a .gdoc path."""
    path = os.path.normpath(path)
    name = os.path.basename(path)
    folders = []
    parent = os.path.dirname(path)
    while True:
        head, tail = os.path.split(parent)
        if not tail:
            break
        folders.append(tail)
        if head == parent:
            break
        parent = head
    return name, folders


def resolve_doc_id(path, databases=None):
    """The Drive id for this .gdoc, or "" when it cannot be pinned down.

    "" covers every way this can come up short — no Drive client, an index
    that has moved on, or several documents of that name that the folders do
    not tell apart. A wrong document would be worse than asking.
    """
    name, folders = path_parts(path)
    if not name:
        return ""
    found = []
    for db in (databases if databases is not None else _databases()):
        con = _connect(db)
        if con is None:
            continue
        try:
            found.extend(_candidates(con, name, folders))
        except sqlite3.Error:
            continue                              # schema moved on; try the next
        finally:
            con.close()
    if not found:
        return ""
    best = max(score for score, _ in found)
    winners = {doc_id for score, doc_id in found if score == best}
    return winners.pop() if len(winners) == 1 else ""
