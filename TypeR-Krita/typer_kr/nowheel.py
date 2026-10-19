# -*- coding: utf-8 -*-
"""Controls that ignore the mouse wheel until you have actually clicked them.

A tab full of sliders sits inside a scroll area, so the wheel is how you get
down the page - and every control it passes over would otherwise grab it and
change a value. The damage is quiet: a preset's size or an outline width
shifts while you were only scrolling, and nothing says so.

The rule is the one the docker already used for its combo boxes and spin
boxes: the wheel only works on a control that has focus, which it gets by
being clicked. Ignoring the event rather than swallowing it is what lets the
scroll area underneath receive it instead, so the page still scrolls.

Kept in its own module because the two panel modules cannot import it from
the docker - the docker imports them.
"""
from ._qt import Qt, QComboBox, QDoubleSpinBox, QSlider, QSpinBox


class _WheelOnlyWhenFocused(object):
    """Mixin: the wheel is for the control you picked, not the one you pass."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # StrongFocus = click and tab, but NOT the wheel: a control must not
        # take focus from being scrolled past, or the next turn of the wheel
        # would change it after all.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):        # noqa: N802 (Qt API)
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()              # let the scroll area have it


class NoScrollSlider(_WheelOnlyWhenFocused, QSlider):
    pass


class NoScrollSpinBox(_WheelOnlyWhenFocused, QSpinBox):
    pass


class NoScrollDoubleSpinBox(_WheelOnlyWhenFocused, QDoubleSpinBox):
    pass


class NoScrollComboBox(_WheelOnlyWhenFocused, QComboBox):
    pass


def protect(widget):
    """Apply the same rule to controls that are already built.

    For widgets that cannot easily be swapped for the classes above - a
    third-party panel, or one assembled elsewhere. Returns how many controls
    were changed, so a caller can tell whether it found anything.
    """
    kinds = (QSlider, QSpinBox, QDoubleSpinBox, QComboBox)
    done = 0
    for child in widget.findChildren(tuple(kinds)):
        if isinstance(child, _WheelOnlyWhenFocused):
            continue
        child.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        child.wheelEvent = _ignore_wheel(child)
        done += 1
    return done


def _ignore_wheel(child):
    """A wheelEvent bound to `child` that only works once it has focus."""
    original = type(child).wheelEvent

    def handler(event):
        if child.hasFocus():
            original(child, event)
        else:
            event.ignore()

    return handler
