# Publishing a version

Development happens in the working copy (`TypeR-Krita`, a separate repo); this
repository is what gets published. In order, after the plugin files have been
copied over:

1. `python tools/write_version.py` — regenerates `VERSION` from the plugin's
   own `VERSION` constant. The docker's update check fetches this file.
2. `python tools/sync_landing_readme.py` — rebuilds the landing `README.md`
   from the plugin one, keeping the landing page's own installation section.
3. Commit and **push** — the release tag has to point at a commit that exists
   on the remote.
4. `py -3.14 tools/make_release.py` — tags `v<version>`, writes the release
   notes from `typer_kr/whatsnew.py` and uploads `TypeR-<version>.zip`.
   `--dry-run` shows both without publishing anything.

Step 4 needs a **normally installed Python, not the Microsoft Store one**: a
Store app runs with a restricted token that its child processes inherit, and
that token cannot read the Windows credential store where `gh` keeps its
login, so every `gh` call reports "not logged into any GitHub hosts" although
the login is fine. The script checks for this and says so. Steps 1–3 run under
any interpreter.

Every version gets a release. Nothing in steps 1 and 4 is typed by hand: the
version comes from the plugin, the notes come from the changelog the docker
shows after an update. `make_release.py` refuses to publish if the working tree
is dirty, if the commit is not pushed, if `VERSION` disagrees with the plugin,
if the changelog has no entry for the version, or if the translations are
missing or were made from English that has since been edited — each of those
would produce a release that quietly lies about what is in it.

The asset is built from a fresh checkout of the tagged commit, never from the
working copy, so it holds the committed files with the line endings
`.gitattributes` asks for (`install.sh` LF, the `.bat` files CRLF).

## Languages

Release notes are **English, Japanese and Simplified Chinese** — not German:
the people who typeset manga are largely not German speakers, and a German one
reads English anyway, so a German column costs space without reaching anyone
the English does not. The plugin's own interface stays English/German; UI labels
are therefore left in English inside the translations, since a translated label
is one the reader cannot find in the program.

English lives with the plugin in `typer_kr/whatsnew.py` (the docker shows it
after an update); the translations live in `tools/release_i18n.py`:

```bash
python tools/release_i18n.py --check
```

Each translation is stamped with a fingerprint of the English it was made from.
Add a version's `ja` and `zh` lines — one per English line, same order — then
run `--stamp` once they match.

## Older versions

`--versions` lists every version in the history, the last commit that was it,
and whether it is released. `--version 1.11` releases one after the fact: the
tag goes on that commit, the zip is built from that commit's tree, and the
release never takes the “latest” pointer from the newest one.
