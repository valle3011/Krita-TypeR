# -*- coding: utf-8 -*-
"""Is there a newer TypeR than the one running?

A Krita plugin has no updater and no package manager behind it: files are
copied over and that is the whole mechanism. So nothing tells you that a
version exists which fixes the thing you just worked around. This asks the
repository.

What it reads is a plain **VERSION** file at the repository root, not the
releases API. Every version is released now, so the API would answer - but a
six-byte file over `raw.githubusercontent.com` is a smaller thing to fetch
than a page of JSON, needs no token, and is not subject to the API's
unauthenticated hourly cap. Both the file and the release tag are generated
from the plugin's own VERSION constant, so they cannot disagree about which
version is out.

The rules this module exists to keep:

* **Never on the UI thread.** The docker calls `fetch_latest` from a worker;
  everything here is therefore plain and blocking, with a short timeout, and
  knows nothing about Qt.
* **At most once a day** (`due`), with the answer remembered. A check on every
  Krita start would be a request every time the program opens, for information
  that changes a few times a month.
* **Silence on failure.** No network, a proxy, GitHub down, a corporate
  firewall: all of it means "no answer", never an error in the user's face.
  There is nothing they could do about it and nothing is broken.
"""

import re
import urllib.error
import urllib.request

from .whatsnew import parse_version

#: Where the published version is written. Kept at the repository root rather
#: than inside the plugin folder so this fetch stays a few bytes.
VERSION_URL = ("https://raw.githubusercontent.com/valle3011/Krita-TypeR/"
               "main/VERSION")

#: Where to send someone who wants the new one.
PROJECT_URL = "https://github.com/valle3011/Krita-TypeR"

#: Seconds between checks.
CHECK_INTERVAL = 24 * 60 * 60

_TIMEOUT = 8
_VERSION_RE = re.compile(r"^\s*v?(\d+(?:\.\d+)*)\s*$")


def due(last_check, now, interval=CHECK_INTERVAL):
    """Whether enough time has passed to ask again.

    A `last_check` that cannot be read as a time counts as never, which is the
    safe way round: it asks once rather than never.
    """
    try:
        last = float(last_check or 0)
    except (TypeError, ValueError):
        last = 0.0
    if last > float(now):                 # clock moved backwards
        return True
    return float(now) - last >= float(interval)


def fetch_latest(url=VERSION_URL, timeout=_TIMEOUT, opener=None):
    """The published version as a string, or "" when there is no answer.

    `opener` is for the tests: anything with the urlopen signature.
    """
    get = opener or urllib.request.urlopen
    request = urllib.request.Request(
        url, headers={"User-Agent": "TypeR-for-Krita"})
    try:
        with get(request, timeout=timeout) as response:
            raw = response.read(256)
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    except Exception:                     # noqa: BLE001 - never worth raising
        return ""
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:                     # noqa: BLE001
        return ""
    match = _VERSION_RE.match(text.splitlines()[0] if text.splitlines() else "")
    return match.group(1) if match else ""


def is_newer(latest, current):
    """Whether `latest` is a version above `current`.

    Compared as numbers, because the scheme counts past nine: as text "1.9"
    sorts after "1.11". An unreadable version on either side is not news.
    """
    low, high = parse_version(current), parse_version(latest)
    if not high or not low:
        return False
    return high > low
