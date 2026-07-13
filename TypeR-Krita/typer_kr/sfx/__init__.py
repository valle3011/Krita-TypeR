# -*- coding: utf-8 -*-
"""SFX Helper as an embedded sub-package of TypeR.

Unlike the standalone MangaSFX plugin, this package does NOT register its own
Krita docker - TypeR instantiates MangaSFXDocker and hosts its widget in the
"SFX" tab instead. Import the class directly:

    from .sfx.sfx_docker import MangaSFXDocker
"""
