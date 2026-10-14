# -*- coding: utf-8 -*-
"""Publish a GitHub release for the version the plugin says it is.

    py -3.14 tools/make_release.py --dry-run        # see the notes and the zip
    py -3.14 tools/make_release.py                  # tag, release, upload
    py -3.14 tools/make_release.py --version 1.11   # an older version, after the fact
    py -3.14 tools/make_release.py --versions       # which versions the history holds

Run it as the last step of a publish, after the plugin has been synced,
`write_version.py` has run and the commit has been pushed.

Nothing here is typed by hand twice. The version comes from the plugin's own
VERSION constant, the English notes come from `typer_kr/whatsnew.py` - the same
list the docker shows after an update - and the Japanese and Chinese come from
`release_i18n.py`, stamped with a fingerprint of the English they were made
from. A release whose notes were written separately drifts within two
versions; these cannot drift without the script saying so.

The checks before it publishes are the point of the script as much as the
upload is: a tag that points at a commit nobody can fetch, or at a working
tree with uncommitted edits in it, is worse than no tag, because it looks
authoritative. So it refuses unless the commit is clean, pushed, and carries
the version it is about to claim.

`--version` releases a version that is already in the history: the tag goes on
the last commit that *was* that version, and the zip is built from that
commit's tree rather than from today's files, so the asset is what that version
actually shipped. Those releases never take the "latest" pointer away from the
newest one.

It needs a normally installed Python, not the Microsoft Store one - see
check_gh() for why.
"""
import argparse
import importlib.util
import io
import os
import re
import shutil
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
#: bubblr_dev is unlocked development work that the published repo does not
#: ignore the way the working copy does. It has never been committed here, and
#: skipping it means a release can never be the accident that publishes it.
ASSET_SKIP_DIRS = ("__pycache__", "bubblr_dev")
ASSET_SKIP_EXT = (".pyc", ".pyo")

_VERSION_CONST = re.compile(r'^VERSION\s*=\s*"([^"]+)"', re.M)


def _printable():
    """Let an arrow or a kanji reach a cp1252 console as '?' instead of
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


def refuse(message):
    print("REFUSED: " + message)
    raise SystemExit(1)


# --- which commit was which version ----------------------------------------

def version_at(sha):
    """The plugin's VERSION constant as of `sha`, or "" if it had none."""
    out = subprocess.run(
        ["git", "show", "%s:TypeR-Krita/typer_kr/typer_kr.py" % sha],
        cwd=ROOT, capture_output=True)
    if out.returncode:
        return ""
    m = _VERSION_CONST.search(out.stdout.decode("utf-8", "replace"))
    return m.group(1) if m else ""


def version_commits():
    """{version: (sha, date, subject)} - the LAST commit that was each version.

    The last one, not the one that bumped the constant: a version is whatever
    the tree held while it carried that number, including the README fixes
    that came after the sync commit.
    """
    log = git("log", "--reverse", "--format=%H %ad %s", "--date=short")
    found = {}
    for line in log.splitlines():
        sha, date, subject = line.split(" ", 2)
        ver = version_at(sha)
        if ver:
            found[ver] = (sha, date, subject)
    return found


def _sorted_versions(versions):
    def key(v):
        try:
            return [int(p) for p in v.split(".")]
        except ValueError:                        # pragma: no cover
            return [0]
    return sorted(versions, key=key)


# --- what is being released -------------------------------------------------

def changelog_entry(version, changelog):
    """The {lang: lines} entry for `version`, or None."""
    for ver, langs in changelog:
        if ver == version:
            return langs
    return None


def notes(version, en_lines, translations, sections, asset_name):
    """The release body: every language's own section, then how to install it.

    English first because it is the one language every reader here is likely to
    have; the plugin's own labels are left in English inside the translations
    because its interface only speaks English and German.
    """
    out = ["TypeR %s for Krita." % version, ""]
    for lang, heading in sections:
        lines = en_lines if lang == "en" else translations.get(lang, [])
        if not lines:
            continue
        out.append("## " + heading)
        out.append("")
        out.extend("- " + line for line in lines)
        out.append("")
    out.append("---")
    out.append("")
    out.append("## Install")
    out.append("")
    out.append("Download `%s`, unpack it, and run `INSTALL.bat` (Windows) or "
               "`install.sh`" % asset_name)
    out.append("(Linux/macOS). An existing install is overwritten in place by "
               "`UPDATE.bat` /")
    out.append("`update.sh` and keeps its settings. Then in Krita: *Settings "
               "→ Configure Krita →")
    out.append("Python Plugin Manager*, tick **TypeR for Krita**, restart - "
               "the docker is under")
    out.append("*Settings → Dockers → TypeR*. The plugin's own "
               "interface is English or German.")
    out.append("")
    out.append("インストール：`%s` "
               "を展開して、`INSTALL.bat`"
               "（Windows）または" % asset_name)
    out.append("`install.sh`（Linux / macOS）"
               "を実行します。"
               "更新は `UPDATE.bat` / `update.sh` で、"
               "設定は")
    out.append("保持されます。Krita で "
               "*Settings → Configure Krita → Python Plugin "
               "Manager* から")
    out.append("**TypeR for Krita** を有効にして"
               "再起動してください。"
               "パットは *Settings → Dockers → "
               "TypeR*")
    out.append("にあります。"
               "プラグインの表示言語"
               "は英語とドイツ語です"
               "。")
    out.append("")
    out.append("安装：解压 `%s`，运行 "
               "`INSTALL.bat`（Windows）或 `install.sh`"
               % asset_name)
    out.append("（Linux / macOS）。升级请用 "
               "`UPDATE.bat` / `update.sh`，设置会保"
               "留。然后在 Krita 中打开")
    out.append("*Settings → Configure Krita → Python Plugin "
               "Manager*，勾选 **TypeR for Krita** "
               "后重启；")
    out.append("面板位于 *Settings → Dockers → "
               "TypeR*。插件界面为英语"
               "或德语。")
    out.append("")
    out.append("Every version's entry is in `typer_kr/whatsnew.py`; the docker "
               "shows the ones")
    out.append("you skipped the first time you start Krita after updating.")
    return "\n".join(out) + "\n"


def asset_members(base):
    """(path on disk, name in the zip) for everything that gets packed."""
    members, missing = [], []
    for name in ASSET_FILES:
        path = os.path.join(base, name)
        if os.path.exists(path):
            members.append((path, name))
        else:
            missing.append(name)
    tree = os.path.join(base, ASSET_TREE)
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames[:] = [d for d in sorted(dirnames) if d not in ASSET_SKIP_DIRS]
        for fn in sorted(filenames):
            if fn.endswith(ASSET_SKIP_EXT):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, base).replace(os.sep, "/")
            members.append((path, rel))
    return members, missing


def build_asset(version, base, out_dir):
    """Write TypeR-<version>.zip from the tree at `base`."""
    name = "TypeR-%s.zip" % version
    path = os.path.join(out_dir, name)
    members, missing = asset_members(base)
    if not any(rel == "typer_kr.desktop" for _s, rel in members):
        refuse("no typer_kr.desktop in %s - the installers need it next to "
               "the typer_kr folder" % base)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, rel in members:
            z.write(src, rel)
    return path, members, missing


# --- the checks -------------------------------------------------------------

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


def check_clean():
    """No uncommitted changes - a release is cut from committed history."""
    dirty = git("status", "--porcelain")
    if dirty:
        refuse("uncommitted changes - commit or stash them first:\n" + dirty)


def check_pushed(sha):
    """`sha` must be on origin/BRANCH, or the tag points at nothing fetchable."""
    git("fetch", "--quiet", "origin", BRANCH)
    remote = git("rev-parse", "origin/" + BRANCH)
    merged = subprocess.run(["git", "merge-base", "--is-ancestor", sha, remote],
                            cwd=ROOT, capture_output=True)
    if merged.returncode != 0:
        refuse("%s is not on origin/%s - push first, or the release would "
               "point at a commit nobody can fetch" % (sha[:8], BRANCH))


# --- the run ----------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", default=None,
                    help="release a version that is already in the history "
                         "(default: the one the plugin currently says)")
    ap.add_argument("--versions", action="store_true",
                    help="list the versions the history holds, and exit")
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
    i18n = _load("typer_release_i18n", os.path.join(TOOLS, "release_i18n.py"))

    current = wv.plugin_version()
    history = version_commits()

    if args.versions:
        print("version  commit    date        last commit that was it")
        for ver in _sorted_versions(history):
            sha, date, subject = history[ver]
            rc, _out = gh("release", "view", "v" + ver)
            print("%-8s %s  %s  %-46s %s"
                  % (ver, sha[:8], date, subject[:46],
                     "released" if rc == 0 else "-"))
        return 0

    version = args.version or current
    backfill = version != current
    tag = "v" + version

    if version not in history:
        refuse("no commit in this repository was version %s (known: %s)"
               % (version, ", ".join(_sorted_versions(history))))
    sha, date, subject = history[version]

    # A release that already exists is defined by its tag, not by what the
    # history says today: `gh release edit` cannot move a tag, so re-running
    # with --force must build from where the tag actually points, or the asset
    # would come from a commit the release does not name.
    git("fetch", "--tags", "--quiet", check=False)
    at_tag = subprocess.run(["git", "rev-parse", "--verify", "--quiet",
                             tag + "^{commit}"], cwd=ROOT, capture_output=True,
                            text=True)
    if at_tag.returncode == 0:
        tagged = at_tag.stdout.strip()
        if tagged and tagged != sha:
            print("note: %s already points at %s, building from there "
                  "(history's last %s commit is %s)"
                  % (tag, tagged[:8], version, sha[:8]))
            sha = tagged
            date = git("show", "-s", "--format=%ad", "--date=short", sha)
            subject = git("show", "-s", "--format=%s", sha)

    langs = changelog_entry(version, wn.CHANGELOG)
    if not langs or not langs.get("en"):
        refuse("no English changelog entry for %s in typer_kr/whatsnew.py - a "
               "release with nothing to read is a worse answer than none"
               % version)
    en_lines = langs["en"]

    why = i18n.problem_with(version, en_lines)
    if why:
        refuse(why)

    if not backfill:
        # the VERSION file is what the docker's update check fetches; if it has
        # not been regenerated, a release would announce a version the check
        # cannot see. Older versions predate the file, so this is for the
        # current one only.
        published = io.open(os.path.join(ROOT, "VERSION"),
                            encoding="utf-8").read().strip()
        if published != version:
            refuse("VERSION says %r but the plugin says %r - run "
                   "tools/write_version.py and commit" % (published, version))

    # The zip is always built from a fresh checkout of the target commit, never
    # from the working copy. Two reasons, both measured: an older release then
    # holds what that version actually shipped rather than today's files; and
    # the line endings are the ones .gitattributes asks for - the working copy
    # here is LF throughout, while a checkout gives install.sh its required LF
    # and the .bat files their CRLF. (An LF-only .bat does run on this Windows:
    # labels and goto were exercised and exited 0. It is still not what the
    # repository says those files should look like.)
    worktree = None
    try:
        worktree = os.path.join(
            os.environ.get("TEMP", ROOT), "typer-release-%s" % version)
        if os.path.exists(worktree):
            git("worktree", "remove", "--force", worktree, check=False)
            shutil.rmtree(worktree, ignore_errors=True)
        git("worktree", "add", "--quiet", "--detach", worktree, sha)
        base = os.path.join(worktree, "TypeR-Krita")

        asset, members, missing = build_asset(version, base, ROOT)
        body = notes(version, en_lines, i18n.NOTES.get(version, {}),
                     i18n.SECTIONS, os.path.basename(asset))

        print("=" * 64)
        print("TypeR %s  ->  tag %s at %s (%s)" % (version, tag, sha[:8], date))
        print("        %s" % subject[:56])
        print("=" * 64)
        print(body)
        print("-" * 64)
        print("asset %s  (%d files, %.0f KiB, built from %s)"
              % (os.path.basename(asset), len(members),
                 os.path.getsize(asset) / 1024.0, sha[:8]))
        if missing:
            print("not in that tree: %s" % ", ".join(missing))
        print("-" * 64)

        if args.dry_run:
            print("dry run: nothing published, zip left at %s" % asset)
            return 0

        check_gh()
        check_clean()
        check_pushed(sha)

        notes_path = os.path.join(ROOT, "RELEASE_NOTES.tmp.md")
        io.open(notes_path, "w", encoding="utf-8", newline="\n").write(body)
        try:
            rc, _out = gh("release", "view", tag)
            exists = rc == 0
            if exists and not args.force:
                refuse("release %s already exists - pass --force to update it, "
                       "or bump the plugin's VERSION" % tag)
            # an older version must never take the "latest" pointer: GitHub
            # hands it to whatever was created most recently unless told
            latest = "true" if not backfill else "false"
            if exists:
                rc, out = gh("release", "edit", tag,
                             "--title", "TypeR " + version,
                             "--notes-file", notes_path,
                             "--latest=" + latest)
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
                             "--latest=" + latest,
                             asset)
                if rc != 0:
                    refuse("gh release create failed:\n" + out)
                print(out)
                print("created release %s at %s%s"
                      % (tag, sha[:8], "" if not backfill else " (not latest)"))
        finally:
            if os.path.exists(notes_path):
                os.remove(notes_path)
    finally:
        if worktree:
            git("worktree", "remove", "--force", worktree, check=False)
            shutil.rmtree(worktree, ignore_errors=True)

    # so the local repository knows about the tag gh just made on GitHub
    git("fetch", "--tags", "--quiet", check=False)
    print("done. zip left at %s (gitignored)" % asset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
