# -*- coding: utf-8 -*-
"""Publish a GitHub release for the version the plugin says it is.

    python tools/make_release.py --dry-run     # see the notes and the zip
    python tools/make_release.py               # tag, release, upload

Run it as the last step of a publish, after the plugin has been synced,
`write_version.py` has run and the commit has been pushed.

Nothing here is typed by hand twice. The version comes from the plugin's own
VERSION constant, the notes come from `typer_kr/whatsnew.py` - the same list
the docker shows after an update - so the release notes and the plugin can
never tell a user two different stories. A release whose notes were written
separately drifts within two versions; this one cannot drift at all.

The checks before it publishes are the point of the script as much as the
upload is: a tag that points at a commit nobody can fetch, or at a working
tree with uncommitted edits in it, is worse than no tag, because it looks
authoritative. So it refuses unless HEAD is clean, pushed, and carries the
version it is about to claim.
"""
import argparse
import importlib.util
import io
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
PLUGIN = os.path.join(ROOT, "TypeR-Krita")
BRANCH = "main"

#: everything an install needs, and nothing a user would have to ignore.
#: the layout is the one INSTALL.bat / install.sh require: the descriptor and
#: the typer_kr folder next to the script that copies them.
ASSET_FILES = [
    "typer_kr.desktop",
    "INSTALL.bat", "UPDATE.bat", "UNINSTALL.bat",
    "install.sh", "update.sh", "uninstall.sh",
    "README.md",
]
ASSET_TREE = "typer_kr"
ASSET_SKIP_DIRS = ("__pycache__",)
ASSET_SKIP_EXT = (".pyc", ".pyo")


def _printable():
    """Let an arrow or an umlaut reach a cp1252 console as '?' instead of
    killing the run - the notes file itself is always written as UTF-8."""
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):          # pragma: no cover
        pass


def _load(name, path):
    """Import a module by file path - these are siblings, not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def git(*args, **kw):
    """git in the repository, output stripped. Raises on failure."""
    out = subprocess.run(["git"] + list(args), cwd=ROOT, check=kw.get("check", True),
                         capture_output=True, text=True, encoding="utf-8")
    return (out.stdout or "").strip()


def gh(*args, **kw):
    """gh in the repository. Returns (returncode, stdout+stderr)."""
    out = subprocess.run(["gh"] + list(args), cwd=ROOT, check=False,
                         capture_output=True, text=True, encoding="utf-8")
    return out.returncode, ((out.stdout or "") + (out.stderr or "")).strip()


# --- what is being released -------------------------------------------------

def changelog_entry(version, changelog):
    """The (version, {lang: lines}) entry for `version`, or None."""
    for ver, langs in changelog:
        if ver == version:
            return langs
    return None


def notes(version, langs, asset_name):
    """The release body: both languages, then how to install it.

    Bilingual like the rest of the plugin, English first because that is what
    a stranger arriving from a search engine reads.
    """
    out = ["TypeR %s for Krita." % version, ""]
    out.append("## What's new")
    out.append("")
    for line in langs.get("en", []):
        out.append("- " + line)
    out.append("")
    out.append("## Neu in dieser Version")
    out.append("")
    for line in langs.get("de", []):
        out.append("- " + line)
    out.append("")
    out.append("## Install")
    out.append("")
    out.append("Download `%s`, unpack it, and run `INSTALL.bat` (Windows) or"
               % asset_name)
    out.append("`install.sh` (Linux/macOS). An existing install is overwritten in")
    out.append("place by `UPDATE.bat` / `update.sh` and keeps its settings.")
    out.append("")
    out.append("Then in Krita: *Settings → Configure Krita → Python Plugin")
    out.append("Manager*, tick **TypeR for Krita**, restart. The docker is under")
    out.append("*Settings → Dockers → TypeR*.")
    out.append("")
    out.append("Every earlier version's entry is in `typer_kr/whatsnew.py`; the")
    out.append("docker shows the ones you skipped the first time you start Krita")
    out.append("after updating.")
    return "\n".join(out) + "\n"


def asset_members():
    """(path on disk, name in the zip) for everything that gets packed."""
    members = []
    for name in ASSET_FILES:
        path = os.path.join(PLUGIN, name)
        if os.path.exists(path):
            members.append((path, name))
    base = os.path.join(PLUGIN, ASSET_TREE)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in sorted(dirnames) if d not in ASSET_SKIP_DIRS]
        for fn in sorted(filenames):
            if fn.endswith(ASSET_SKIP_EXT):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, PLUGIN).replace(os.sep, "/")
            members.append((path, rel))
    return members


def build_asset(version, out_dir):
    """Write TypeR-<version>.zip and return its path."""
    name = "TypeR-%s.zip" % version
    path = os.path.join(out_dir, name)
    members = asset_members()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, rel in members:
            z.write(src, rel)
    return path, members


# --- the checks -------------------------------------------------------------

def refuse(message):
    print("REFUSED: " + message)
    raise SystemExit(1)


def check_gh():
    """gh has to be there and logged in - and able to read where it stored it.

    Measured on this machine: `gh auth status` succeeds from a shell but fails
    with "not logged into any GitHub hosts" for any gh started by the Microsoft
    Store Python (3.13 here). A Store app runs with a restricted token that its
    children inherit, and gh keeps the token in the Windows credential store,
    which that token cannot read. Nothing is wrong with the login, so say which
    interpreter to use instead of letting gh's message send anyone off to
    `gh auth login`.
    """
    rc, out = gh("--version")
    if rc != 0:
        refuse("gh (GitHub CLI) is not available: " + out)
    rc, out = gh("auth", "status")
    if rc != 0:
        hint = ""
        if "WindowsApps" in sys.executable:
            hint = ("\nThis interpreter is the Microsoft Store Python, whose "
                    "restricted token cannot read the credential store gh "
                    "keeps its login in. Run the script with a normally "
                    "installed Python (`py -3.14 tools/make_release.py`); the "
                    "login itself is fine.")
        refuse("gh is not usable here:\n" + out + hint)


def check_repo_state():
    """HEAD must be clean, on the branch, and already on the remote."""
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != BRANCH:
        refuse("on branch %r, not %r - a release tag belongs on the published "
               "branch" % (branch, BRANCH))
    dirty = git("status", "--porcelain")
    if dirty:
        refuse("uncommitted changes - the tag would point at a commit that is "
               "not what you tested:\n" + dirty)
    git("fetch", "--quiet", "origin", BRANCH)
    local = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/" + BRANCH)
    if local != remote:
        ahead = git("rev-list", "--count", "origin/%s..HEAD" % BRANCH)
        refuse("HEAD is not on origin/%s (%s commit(s) unpushed) - push first, "
               "or the release would point at a commit nobody can fetch"
               % (BRANCH, ahead))
    return local


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="print the notes and the zip contents, publish nothing")
    ap.add_argument("--force", action="store_true",
                    help="an existing release of this version is updated "
                         "instead of refused")
    args = ap.parse_args(argv)
    _printable()

    wv = _load("typer_write_version", os.path.join(TOOLS, "write_version.py"))
    wn = _load("typer_whatsnew",
               os.path.join(PLUGIN, "typer_kr", "whatsnew.py"))

    version = wv.plugin_version()
    tag = "v" + version

    # the VERSION file is what the docker's update check fetches; if it has not
    # been regenerated, a release would announce a version the check cannot see
    published = io.open(os.path.join(ROOT, "VERSION"),
                        encoding="utf-8").read().strip()
    if published != version:
        refuse("VERSION says %r but the plugin says %r - run "
               "tools/write_version.py and commit" % (published, version))

    langs = changelog_entry(version, wn.CHANGELOG)
    if not langs:
        refuse("no changelog entry for %s in typer_kr/whatsnew.py - a release "
               "with nothing to read is a worse answer than none" % version)
    if not langs.get("en") or not langs.get("de"):
        refuse("the changelog entry for %s is missing a language" % version)

    out_dir = ROOT
    asset, members = build_asset(version, out_dir)
    body = notes(version, langs, os.path.basename(asset))

    print("=" * 64)
    print("TypeR %s  ->  tag %s" % (version, tag))
    print("=" * 64)
    print(body)
    print("-" * 64)
    print("asset %s  (%d files, %.0f KiB)"
          % (os.path.basename(asset), len(members),
             os.path.getsize(asset) / 1024.0))
    print("-" * 64)

    if args.dry_run:
        print("dry run: nothing published, zip left at %s" % asset)
        return 0

    check_gh()
    sha = check_repo_state()

    notes_path = os.path.join(out_dir, "RELEASE_NOTES.tmp.md")
    io.open(notes_path, "w", encoding="utf-8", newline="\n").write(body)
    try:
        rc, _out = gh("release", "view", tag)
        exists = rc == 0
        if exists and not args.force:
            refuse("release %s already exists - pass --force to update it, or "
                   "bump the plugin's VERSION" % tag)
        if exists:
            rc, out = gh("release", "edit", tag, "--title", "TypeR " + version,
                         "--notes-file", notes_path)
            if rc != 0:
                refuse("gh release edit failed:\n" + out)
            rc, out = gh("release", "upload", tag, asset, "--clobber")
            if rc != 0:
                refuse("gh release upload failed:\n" + out)
            print("updated release %s" % tag)
        else:
            rc, out = gh("release", "create", tag,
                         "--target", sha,
                         "--title", "TypeR " + version,
                         "--notes-file", notes_path,
                         "--latest",
                         asset)
            if rc != 0:
                refuse("gh release create failed:\n" + out)
            print(out)
            print("created release %s at %s" % (tag, sha[:7]))
    finally:
        if os.path.exists(notes_path):
            os.remove(notes_path)

    # so the local repository knows about the tag gh just made on GitHub
    git("fetch", "--tags", "--quiet", check=False)
    print("done. zip left at %s (gitignored)" % asset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
