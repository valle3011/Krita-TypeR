# -*- coding: utf-8 -*-
"""Pure layout model for the customizable TypeR docker (Qt-free, testable).

The docker's UI is decomposed into named *panels* (script box, font picker,
BubblR overlay, ...). This module owns the JSON-able config that says which
tabs exist, their names and order, which panels each tab contains and in
which order, which panels are detached into a host docker / floating window,
and whether editing is locked.

Every mutation is a pure function that returns a NEW, validated config and
never loses a known panel — so a stale or corrupt saved config can never
brick the docker (see :func:`repair`). All the hard logic lives here so it
can be unit-tested with plain ``python`` (no Krita/PyQt5).
"""

import copy


# The built-in panels and the default tab layout. `DEFAULT_TABS` is the
# single source of truth for what a fresh install looks like; `PANELS` is the
# full set of known panel ids (order = a sensible fallback order used when
# `repair` has to re-home an orphaned panel).
PANELS = (
    "script_box", "jp_en_table", "nav_line", "active_field",
    "font_picker", "color_pick", "presets", "live_preview",
    "style_basic", "style_size", "style_outline", "style_shadow",
    "hyphenation",
    "bubblr_detect", "bubblr_overlay", "bubblr_map",
    "shapr_panel", "sfx_panel",
    "setup_general", "layout_sizes",
)

# tab id -> (default display-name key, [panel ids]).  Presets now lives in
# the Type tab (its own tab is gone); BubblR keeps its three panels.
DEFAULT_TABS = (
    ("type", "tab_type", ["script_box", "jp_en_table", "nav_line",
                          "active_field", "font_picker", "color_pick",
                          "presets", "live_preview"]),
    ("style", "tab_style", ["style_basic", "style_size", "style_outline",
                            "style_shadow", "hyphenation"]),
    ("bubblr", "tab_bubblr", ["bubblr_detect", "bubblr_overlay",
                              "bubblr_map"]),
    ("setup", "tab_setup", ["setup_general", "layout_sizes"]),
    ("shapr", "tab_shapr", ["shapr_panel"]),
    ("sfx", "tab_sfx", ["sfx_panel"]),
)

# how many generic host dockers are pre-registered for detached panels
MAX_DETACH_SLOTS = 3


def default_layout():
    """A fresh config: the built-in tabs, nothing detached, locked."""
    return {
        "tabs": [{"id": tid, "name": None, "namekey": nk,
                  "panels": list(panels)}
                 for tid, nk, panels in DEFAULT_TABS],
        "detached": [],
        "locked": True,
    }


# --- lookup helpers ----------------------------------------------------------

def _tab(cfg, tab_id):
    for t in cfg["tabs"]:
        if t["id"] == tab_id:
            return t
    return None


def find_panel(cfg, panel):
    """(tab_id, index) of `panel` in the tabs, or (None, -1). Detached
    panels are not 'in a tab', so they return (None, -1)."""
    for t in cfg["tabs"]:
        if panel in t["panels"]:
            return t["id"], t["panels"].index(panel)
    return None, -1

def is_detached(cfg, panel):
    return any(panel in d["panels"] for d in cfg.get("detached", []))


def all_placed_panels(cfg):
    """Every panel id currently referenced (in a tab or detached)."""
    seen = []
    for t in cfg["tabs"]:
        seen.extend(t["panels"])
    for d in cfg.get("detached", []):
        seen.extend(d["panels"])
    return seen


def panel_locked(cfg, panel):
    return panel in cfg.get("locked_panels", [])


# --- mutations (all return a new, repaired config) ---------------------------

def _clone(cfg):
    return copy.deepcopy(cfg)


def _remove_panel_everywhere(cfg, panel):
    for t in cfg["tabs"]:
        if panel in t["panels"]:
            t["panels"].remove(panel)
    for d in cfg.get("detached", []):
        if panel in d["panels"]:
            d["panels"].remove(panel)
    cfg["detached"] = [d for d in cfg.get("detached", []) if d["panels"]]


def move_panel(cfg, panel, to_tab, index=None):
    """Move `panel` into tab `to_tab` at `index` (append when None). No-op
    for an unknown panel or missing target tab."""
    cfg = _clone(cfg)
    if panel not in PANELS or _tab(cfg, to_tab) is None:
        return repair(cfg)
    _remove_panel_everywhere(cfg, panel)
    dest = _tab(cfg, to_tab)["panels"]
    if index is None or index < 0 or index > len(dest):
        dest.append(panel)
    else:
        dest.insert(index, panel)
    return repair(cfg)


def reorder_panel(cfg, tab_id, old_index, new_index):
    """Move a panel within one tab from old_index to new_index."""
    cfg = _clone(cfg)
    t = _tab(cfg, tab_id)
    if t is None or not (0 <= old_index < len(t["panels"])):
        return repair(cfg)
    panel = t["panels"].pop(old_index)
    new_index = max(0, min(new_index, len(t["panels"])))
    t["panels"].insert(new_index, panel)
    return repair(cfg)


def rename_tab(cfg, tab_id, name):
    """Give a tab a custom display name (empty/None -> back to the default
    localized name via its namekey)."""
    cfg = _clone(cfg)
    t = _tab(cfg, tab_id)
    if t is not None:
        t["name"] = (name or None)
    return repair(cfg)


def add_tab(cfg, name, tab_id=None):
    """Append a new empty tab; returns (cfg, new_tab_id)."""
    cfg = _clone(cfg)
    existing = {t["id"] for t in cfg["tabs"]}
    if not tab_id or tab_id in existing:
        n = 1
        while ("tab%d" % n) in existing:
            n += 1
        tab_id = "tab%d" % n
    cfg["tabs"].append({"id": tab_id, "name": (name or None),
                        "namekey": None, "panels": []})
    return repair(cfg), tab_id


def remove_tab(cfg, tab_id):
    """Delete a tab; its panels move to the first remaining tab so nothing
    is ever lost. Refuses to remove the last tab."""
    cfg = _clone(cfg)
    if len(cfg["tabs"]) <= 1:
        return repair(cfg)
    victim = _tab(cfg, tab_id)
    if victim is None:
        return repair(cfg)
    cfg["tabs"].remove(victim)
    dest = cfg["tabs"][0]["panels"]
    for p in victim["panels"]:
        if p not in dest:
            dest.append(p)
    return repair(cfg)


def reorder_tabs(cfg, order):
    """Reorder tabs by a list of tab ids; unknown ids ignored, missing ids
    appended in their old order."""
    cfg = _clone(cfg)
    by_id = {t["id"]: t for t in cfg["tabs"]}
    new = [by_id[i] for i in order if i in by_id]
    for t in cfg["tabs"]:
        if t not in new:
            new.append(t)
    cfg["tabs"] = new
    return repair(cfg)


def detach(cfg, panels, slot):
    """Detach one or more panels into host `slot` (0-based). They leave
    their tab. A slot already in use is replaced (its panels go back to a
    tab first)."""
    cfg = _clone(cfg)
    panels = [p for p in panels if p in PANELS]
    if not panels or slot < 0 or slot >= MAX_DETACH_SLOTS:
        return repair(cfg)
    # free the slot if occupied
    for d in list(cfg.get("detached", [])):
        if d.get("slot") == slot:
            _reattach_group(cfg, d["panels"])
    for p in panels:
        _remove_panel_everywhere(cfg, p)
    cfg.setdefault("detached", []).append(
        {"panels": list(panels), "slot": slot, "floating": False})
    return repair(cfg)


def _reattach_group(cfg, panels, to_tab=None):
    cfg["detached"] = [d for d in cfg.get("detached", [])
                       if not any(p in d["panels"] for p in panels)]
    dest_id = to_tab if _tab(cfg, to_tab) else cfg["tabs"][0]["id"]
    dest = _tab(cfg, dest_id)["panels"]
    for p in panels:
        if p not in dest:
            dest.append(p)


def reattach(cfg, panels, to_tab=None):
    """Bring detached panels back into a tab (first tab when to_tab is
    None/unknown)."""
    cfg = _clone(cfg)
    _reattach_group(cfg, [p for p in panels if p in PANELS], to_tab)
    return repair(cfg)


def set_locked(cfg, locked):
    cfg = _clone(cfg)
    cfg["locked"] = bool(locked)
    return repair(cfg)


def set_panel_locked(cfg, panel, locked):
    """Pin/unpin a single panel so it can't be dragged even in edit mode."""
    cfg = _clone(cfg)
    lp = set(cfg.get("locked_panels", []))
    if locked:
        lp.add(panel)
    else:
        lp.discard(panel)
    cfg["locked_panels"] = sorted(lp)
    return repair(cfg)


# --- the safety net ----------------------------------------------------------

def repair(cfg, known_panels=PANELS):
    """Return a structurally valid config:

    * drop unknown panel ids and duplicates (keep first occurrence),
    * drop detached groups referencing no known panel; clamp slots,
    * re-home every *missing* known panel (e.g. one a plugin update just
      added) to a sensible default tab so it can't disappear,
    * guarantee at least one tab exists,
    * coerce the top-level keys to the right types.

    `known_panels` is a parameter so a test can simulate an older/newer
    panel set.
    """
    known = list(known_panels)
    known_set = set(known)
    if not isinstance(cfg, dict):
        cfg = default_layout()
    tabs = cfg.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        base = default_layout()
        tabs = base["tabs"]
    out_tabs = []
    seen = set()
    used_ids = set()
    for t in tabs:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        if not isinstance(tid, str) or not tid or tid in used_ids:
            n = 1
            while ("tab%d" % n) in used_ids:
                n += 1
            tid = "tab%d" % n
        used_ids.add(tid)
        panels = []
        for p in (t.get("panels") or []):
            if p in known_set and p not in seen:
                panels.append(p)
                seen.add(p)
        out_tabs.append({"id": tid,
                        "name": t.get("name") if isinstance(
                            t.get("name"), str) else None,
                        "namekey": t.get("namekey")
                        if isinstance(t.get("namekey"), str) else None,
                        "panels": panels})
    if not out_tabs:
        out_tabs = default_layout()["tabs"]
        seen = set(p for t in out_tabs for p in t["panels"])

    # detached groups
    out_det = []
    used_slots = set()
    for d in (cfg.get("detached") or []):
        if not isinstance(d, dict):
            continue
        ps = [p for p in (d.get("panels") or [])
              if p in known_set and p not in seen]
        if not ps:
            continue
        slot = d.get("slot")
        if not isinstance(slot, int) or slot < 0 or slot >= MAX_DETACH_SLOTS \
                or slot in used_slots:
            slot = next((s for s in range(MAX_DETACH_SLOTS)
                         if s not in used_slots), None)
            if slot is None:
                # no free slot -> put them back into the first tab instead
                out_tabs[0]["panels"].extend(ps)
                seen.update(ps)
                continue
        used_slots.add(slot)
        out_det.append({"panels": ps, "slot": slot,
                        "floating": bool(d.get("floating", False))})
        seen.update(ps)

    # re-home any known panel that went missing (new panel after update,
    # or one lost in a corrupt file) using the default tab mapping
    default_home = {}
    for tid, _nk, plist in DEFAULT_TABS:
        for p in plist:
            default_home[p] = tid
    for p in known:
        if p in seen:
            continue
        home_id = default_home.get(p)
        home = _tab({"tabs": out_tabs}, home_id) if home_id else None
        (home or out_tabs[0])["panels"].append(p)
        seen.add(p)

    locked_panels = sorted(set(p for p in (cfg.get("locked_panels") or [])
                               if p in known_set))
    return {"tabs": out_tabs, "detached": out_det,
            "locked": bool(cfg.get("locked", True)),
            "locked_panels": locked_panels}
