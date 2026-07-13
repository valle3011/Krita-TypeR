# -*- coding: utf-8 -*-
"""Bridge to the external BubblR-AI detector (stdlib only, no Qt/Krita).

The AI lives in `BubblR-Test/ai/` with its own venv; this module runs its
`detect.py` as a subprocess and parses the JSON result. Everything here is
importable by plain python, so it is unit-testable outside Krita.
"""

import json
import os
import subprocess
import time

# Where the ai/ folder is expected when the user never picked one (the
# development checkout on this machine); the docker stores a user-picked
# path in the Krita setting "bubblr_test/aidir".
DEFAULT_AI_DIR = r"C:\Users\valle\Desktop\ClaudeProgram\BubblR-Test\ai"
DETECT_TIMEOUT = 90            # seconds; first run loads the 170 MB model
PANEL_TIMEOUT = 240           # Magi is large; first run also downloads it


class AIUnavailableError(Exception):
    """The ai/ folder or its venv/model is not set up."""


class AIRunError(Exception):
    """detect.py started but failed; str() holds the reason."""


def _venv_python(ai_dir):
    return os.path.join(ai_dir, ".venv", "Scripts", "python.exe")


def find_ai_dir(setting_value=""):
    """Return a usable ai/ folder (setting first, then the default
    location) or None. Usable = detect.py plus the venv python exist."""
    for cand in (setting_value, DEFAULT_AI_DIR):
        if not cand:
            continue
        if (os.path.exists(os.path.join(cand, "detect.py"))
                and os.path.exists(_venv_python(cand))):
            return cand
    return None


def parse_detect_json(text):
    """Parse detect.py's JSON output into a list of box dicts with the
    fields the docker expects (x/y/w/h int, kind, score). Raises
    AIRunError on malformed output."""
    try:
        data = json.loads(text)
        raw = data["boxes"]
        boxes = []
        for b in raw:
            kind = b["kind"]
            if kind not in ("bubble", "sfx"):
                continue
            boxes.append({
                "x": int(b["x"]), "y": int(b["y"]),
                "w": int(b["w"]), "h": int(b["h"]),
                "kind": kind,
                "shape": "rect",          # bubbles get refined by the docker
                "fill": 1.0,
                "score": float(b.get("score", 0.0)),
            })
        return boxes
    except (ValueError, KeyError, TypeError) as exc:
        raise AIRunError("bad detector output: %s" % exc)


def _clean_env():
    """Environment for the detector subprocess WITHOUT Krita's Python.

    Krita exports PYTHONPATH/PYTHONHOME pointing at its bundled Python
    3.10; inherited by the venv's 3.12 interpreter they make it load the
    wrong stdlib and crash with "bad magic number in 'encodings'" before
    our script even starts. Strip every PYTHON* variable."""
    return {k: v for k, v in os.environ.items()
            if not k.upper().startswith("PYTHON")}


def detect(ai_dir, image_path, conf=0.4, sfx_conf=0.25, tile="auto",
           model="auto", timeout=DETECT_TIMEOUT, python_exe=None, script=None):
    """Run the external detector on `image_path`; returns box dicts.

    `tile` controls slicing: "auto" (tile big pages), "on" (always) or "off"
    (fast, downscaled — for weak machines). `model` selects the weights:
    "auto" (fine-tuned only if promoted, else baseline), "baseline" or
    "finetuned". `conf`/`sfx_conf` are the detection thresholds.
    `python_exe`/`script` exist for tests (default: the ai venv python and
    ai_dir/detect.py). Raises AIUnavailableError / AIRunError."""
    python_exe = python_exe or _venv_python(ai_dir)
    script = script or os.path.join(ai_dir, "detect.py")
    if not os.path.exists(python_exe) or not os.path.exists(script):
        raise AIUnavailableError(ai_dir or "(no ai folder)")
    out_path = os.path.join(
        os.path.dirname(image_path),
        "bubblr_ai_%d.json" % int(time.time() * 1000))
    cmd = [python_exe, script, "--image", image_path, "--out", out_path,
           "--conf", str(conf), "--sfx-conf", str(sfx_conf),
           "--tile", tile, "--model", model]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout, env=_clean_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise AIRunError("detector timed out after %ds" % timeout)
    except OSError as exc:
        raise AIRunError(str(exc))
    try:
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").strip()
            raise AIRunError(err or "exit code %d" % proc.returncode)
        try:
            with open(out_path, "r", encoding="utf-8") as fh:
                return parse_detect_json(fh.read())
        except OSError as exc:
            raise AIRunError("no detector output: %s" % exc)
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


# --- panels (Magi) for panel-aware reading order ------------------------------

def parse_panels_json(text):
    """Parse panels.py output into a list of x/y/w/h panel dicts."""
    data = json.loads(text)
    out = []
    for p in data.get("panels", []):
        try:
            out.append({"x": int(p["x"]), "y": int(p["y"]),
                        "w": int(p["w"]), "h": int(p["h"]),
                        "score": float(p.get("score", 1.0))})
        except (KeyError, ValueError, TypeError):
            continue
    return out


def detect_panels(ai_dir, image_path, timeout=PANEL_TIMEOUT,
                  python_exe=None, script=None):
    """Run the Magi panel detector on `image_path`; returns panel box dicts.
    Raises AIUnavailableError / AIRunError like detect()."""
    python_exe = python_exe or _venv_python(ai_dir)
    script = script or os.path.join(ai_dir, "panels.py")
    if not os.path.exists(python_exe) or not os.path.exists(script):
        raise AIUnavailableError(ai_dir or "(no ai folder)")
    out_path = os.path.join(
        os.path.dirname(image_path),
        "bubblr_panels_%d.json" % int(time.time() * 1000))
    cmd = [python_exe, script, "--image", image_path, "--out", out_path]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout, env=_clean_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise AIRunError("panel detector timed out after %ds" % timeout)
    except OSError as exc:
        raise AIRunError(str(exc))
    try:
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").strip()
            raise AIRunError(err or "exit code %d" % proc.returncode)
        try:
            with open(out_path, "r", encoding="utf-8") as fh:
                return parse_panels_json(fh.read())
        except OSError as exc:
            raise AIRunError("no panel output: %s" % exc)
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


# --- training-data export -----------------------------------------------------

KIND_CLASS = {"bubble": 0, "sfx": 1}


def dataset_root(ai_dir):
    """Where training data lives. If <ai_dir>/dataset_root.txt exists and
    names an existing folder (e.g. a shared Google Drive folder), that is the
    store so two people can pool their labelled pages; otherwise the local
    <ai_dir>/dataset."""
    cfg = os.path.join(ai_dir, "dataset_root.txt")
    try:
        with open(cfg, "r", encoding="utf-8") as fh:
            p = fh.read().strip()
        if p and os.path.isdir(p):
            return p
    except OSError:
        pass
    return os.path.join(ai_dir, "dataset")


def make_yolo_label(boxes, img_w, img_h):
    """YOLO-format label text for the exported page: one
    `class cx cy w h` line per box, all normalized to 0..1 and clamped.
    Boxes without a known kind default to bubble."""
    lines = []
    for b in boxes:
        cls = KIND_CLASS.get(b.get("kind", "bubble"), 0)
        cx = (b["x"] + b["w"] / 2.0) / float(img_w)
        cy = (b["y"] + b["h"] / 2.0) / float(img_h)
        w = b["w"] / float(img_w)
        h = b["h"] / float(img_h)
        cx = min(1.0, max(0.0, cx))
        cy = min(1.0, max(0.0, cy))
        w = min(1.0, max(0.0, w))
        h = min(1.0, max(0.0, h))
        lines.append("%d %.6f %.6f %.6f %.6f" % (cls, cx, cy, w, h))
    return "\n".join(lines) + "\n" if lines else ""


def export_training_example(ai_dir, stem, save_image_fn, boxes,
                            img_w, img_h, save_preview_fn=None):
    """Save one training sample into ai_dir/dataset/: the page image (via
    `save_image_fn(png_path)`, so the caller brings Qt) and the YOLO label.

    If `save_preview_fn` is given it is called with a path in
    dataset/preview/ to write a human-viewable copy with the markings drawn
    on top (so you can check by eye what was labelled). Returns the image
    path."""
    root = dataset_root(ai_dir)
    images = os.path.join(root, "images", "train")
    labels = os.path.join(root, "labels", "train")
    os.makedirs(images, exist_ok=True)
    os.makedirs(labels, exist_ok=True)
    img_path = os.path.join(images, stem + ".png")
    save_image_fn(img_path)
    with open(os.path.join(labels, stem + ".txt"), "w",
              encoding="utf-8") as fh:
        fh.write(make_yolo_label(boxes, img_w, img_h))
    if save_preview_fn is not None:
        preview = os.path.join(root, "preview")
        os.makedirs(preview, exist_ok=True)
        try:
            save_preview_fn(os.path.join(preview, stem + ".png"))
        except Exception:
            pass          # a preview is a nicety; never fail the export over it
    return img_path
