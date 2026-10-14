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
4. `python tools/make_release.py` — tags `v<version>`, writes the release notes
   from `typer_kr/whatsnew.py` and uploads `TypeR-<version>.zip`.
   `--dry-run` shows both without publishing anything.

Every version gets a release. Nothing in steps 1 and 4 is typed by hand: the
version comes from the plugin, the notes come from the changelog the docker
shows after an update. `make_release.py` refuses to publish if the working tree
is dirty, if the commit is not pushed, if `VERSION` disagrees with the plugin,
or if the changelog has no entry for the version — each of those would produce
a release that quietly lies about what is in it.
