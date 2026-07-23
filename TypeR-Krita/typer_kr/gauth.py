"""Google sign-in for TypeR, using nothing but the standard library.

Krita's embedded Python has no google-auth / googleapiclient, and a Krita
plugin cannot pip-install into it, so this implements the OAuth 2.0
"installed app" flow directly: PKCE + a loopback redirect, per Google's
current guidance for desktop apps.

**TypeR ships no credentials on purpose.** The repository is public, so a
bundled client secret would simply be readable by anyone; and an app asking
for Google's *sensitive* Docs/Drive scopes is capped at 100 users and pushed
into the verification process. Instead each user brings a client ID from
their own Google Cloud project (OAuth client type "Desktop app"). That keeps
the public plugin credential-free, avoids the user cap, and needs no
verification.

Two things worth knowing about the account this is used with:

* On a personal Gmail the consent screen's user type must be "External". If
  its publishing status is left at "Testing", Google revokes refresh tokens
  after 7 days — i.e. a weekly re-login. Setting the project to
  "In production" (even unverified, clicking past the warning once) gives a
  long-lived refresh token.
* A desktop-app client has no usable secret by definition, which is why PKCE
  carries the security here. The secret is therefore optional below.

Tokens are cached per client ID in Krita's settings; nothing is written to
the plugin folder.
"""

import base64
import hashlib
import http.server
import json
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"

# Read the document text and its comments. Both are "sensitive" scopes, which
# is exactly why the client ID has to be the user's own (see module docstring).
SCOPES = (
    "https://www.googleapis.com/auth/documents.readonly "
    "https://www.googleapis.com/auth/drive.readonly"
)

_TIMEOUT = 30


class AuthError(Exception):
    """Sign-in failed in a way the user needs to hear about."""


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _pkce_pair():
    """A PKCE verifier plus its S256 challenge."""
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        raise AuthError(_explain(body) or ("HTTP %s" % e.code))
    except urllib.error.URLError as e:
        raise AuthError("No connection to Google: %s" % e.reason)


def _explain(body):
    """Turn Google's error JSON into something a user can act on."""
    try:
        d = json.loads(body)
    except Exception:
        return body[:200] if body else ""
    err = d.get("error") or ""
    desc = d.get("error_description") or ""
    if err == "invalid_grant":
        return ("Google rejected the saved sign-in (invalid_grant). This is "
                "usually the 7-day expiry that applies while the Cloud project "
                "is still in 'Testing'. Set it to 'In production' and sign in "
                "again.")
    if err == "invalid_client":
        return "That client ID is not valid for a desktop app."
    if err == "access_denied":
        return "Sign-in was cancelled."
    return ("%s: %s" % (err, desc)).strip(": ")


class _Catcher(http.server.BaseHTTPRequestHandler):
    """Catches the one redirect Google sends back to the loopback address."""

    result = None

    def do_GET(self):  # noqa: N802 (http.server API)
        q = urllib.parse.urlparse(self.path).query
        params = dict(urllib.parse.parse_qsl(q))
        type(self).result = params
        ok = "code" in params
        msg = ("TypeR is signed in. You can close this tab."
               if ok else
               "Sign-in failed: %s" % params.get("error", "unknown"))
        body = ("<html><body style='font:16px sans-serif;padding:40px'>"
                "<h3>%s</h3></body></html>" % msg).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass  # a Krita plugin has no console to spam


def sign_in(client_id, client_secret="", open_browser=True, timeout=180):
    """Run the loopback + PKCE flow and return a token dict.

    Blocks until the user finishes in the browser, or `timeout` seconds pass.
    Returns the token dict (access_token / refresh_token / expires_at / ...).
    """
    if not client_id:
        raise AuthError("No client ID set.")

    verifier, challenge = _pkce_pair()
    port = _free_port()
    redirect_uri = "http://127.0.0.1:%d/" % port

    _Catcher.result = None
    srv = http.server.HTTPServer(("127.0.0.1", port), _Catcher)
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()

    args = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # refresh token only comes back with these two
        "access_type": "offline",
        "prompt": "consent",
    }
    url = AUTH_URI + "?" + urllib.parse.urlencode(args)
    if open_browser:
        import webbrowser
        webbrowser.open(url)

    t.join(timeout)
    try:
        srv.server_close()
    except Exception:
        pass

    params = _Catcher.result
    if not params:
        raise AuthError("Timed out waiting for the browser sign-in.")
    if "error" in params:
        raise AuthError(_explain(json.dumps(params)))

    fields = {
        "client_id": client_id,
        "code": params["code"],
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        fields["client_secret"] = client_secret
    tok = _post_form(TOKEN_URI, fields)
    return _stamp(tok)


def _stamp(tok):
    """Turn Google's expires_in into an absolute time we can check later."""
    tok = dict(tok)
    if "expires_in" in tok:
        tok["expires_at"] = time.time() + float(tok["expires_in"]) - 60
    return tok


def refresh(tok, client_id, client_secret=""):
    """Swap a refresh token for a fresh access token."""
    rt = (tok or {}).get("refresh_token")
    if not rt:
        raise AuthError("Not signed in.")
    fields = {
        "client_id": client_id,
        "refresh_token": rt,
        "grant_type": "refresh_token",
    }
    if client_secret:
        fields["client_secret"] = client_secret
    new = _post_form(TOKEN_URI, fields)
    merged = dict(tok)
    merged.update(_stamp(new))
    merged["refresh_token"] = rt      # Google does not resend it
    return merged


def is_fresh(tok):
    return bool(tok) and tok.get("access_token") and \
        time.time() < float(tok.get("expires_at") or 0)


def ensure(tok, client_id, client_secret=""):
    """Return a usable token, refreshing only when it has actually expired."""
    if is_fresh(tok):
        return tok
    return refresh(tok, client_id, client_secret)


def get_json(url, tok):
    """GET a Google API endpoint with a bearer token."""
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer %s" % tok["access_token"]})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        if e.code in (401, 403):
            raise AuthError(_explain(body) or
                            "Google refused access (%s). Is the document "
                            "shared with this account?" % e.code)
        raise AuthError(_explain(body) or ("HTTP %s" % e.code))
    except urllib.error.URLError as e:
        raise AuthError("No connection to Google: %s" % e.reason)
