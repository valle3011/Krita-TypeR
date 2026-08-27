"""Qt binding shim so the plugin runs on BOTH PyQt5 (Krita 5.x) and PyQt6
(Krita 6.0+).

The binding is chosen automatically at import time — PyQt6 if present, else
PyQt5 — because which one exists is fixed by the running Krita and can't be a
runtime choice (the import happens before any UI could offer a switch).

Every Qt symbol the plugin uses is re-exported here, so the rest of the code
does ``from ._qt import Qt, QColor, QDialog, …`` instead of naming a binding.
All three Qt modules are star-imported into this one namespace, which also makes
Qt 6's module moves (e.g. ``QShortcut``/``QAction`` from QtWidgets to QtGui)
transparent — the name is found whichever module now holds it.

Enum access still has to be written in the *scoped* form (``Qt.AlignmentFlag.
AlignCenter``, not ``Qt.AlignCenter``): PyQt6 requires it and PyQt5 ≥ 5.15 also
accepts it, so one spelling works on both. This shim does not paper over that.

Only the standard library + the Qt binding are used (no third-party qtpy)."""

try:                                            # Krita 6.0+ ships PyQt6
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import *                  # noqa: F401,F403
    from PyQt6.QtGui import *                   # noqa: F401,F403
    from PyQt6.QtWidgets import *               # noqa: F401,F403
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, pyqtProperty  # noqa: F401
    PYQT = 6
except ImportError:                             # Krita 5.x ships PyQt5
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import *                  # noqa: F401,F403
    from PyQt5.QtGui import *                   # noqa: F401,F403
    from PyQt5.QtWidgets import *               # noqa: F401,F403
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, pyqtProperty  # noqa: F401
    PYQT = 5

#: Qt runtime version string, e.g. "6.11.0".
QT_VERSION = QtCore.QT_VERSION_STR


def binding_name():
    """Human-readable name of the active binding, e.g. 'PyQt6'."""
    return "PyQt%d" % PYQT


def binding_info():
    """One-line 'PyQt6 · Qt 6.11.0' style summary for the Setup display."""
    return "%s · Qt %s" % (binding_name(), QT_VERSION)


def font_families():
    """Installed font family names. Qt 6 made ``QFontDatabase`` fully static
    (it can no longer be instantiated); Qt 5 needs an instance. This hides that
    difference so callers just get the list."""
    if PYQT >= 6:
        return QFontDatabase.families()
    return QFontDatabase().families()
