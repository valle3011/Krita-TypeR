"""TypeR for Krita - package initialization.

Registers the docker with Krita. The actual logic lives in typer_kr.py.
"""
from .typer_kr import register

register()
