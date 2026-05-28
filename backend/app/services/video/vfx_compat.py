"""
MoviePy 2.x compatibility shim for video effects.

MoviePy 2.x removed the .fx() method from clips and changed effects to classes.
All call sites now use:
    clip.with_effects([vfx.FadeIn(duration)])
    clip.with_effects([vfx.FadeOut(duration)])
    clip.with_effects([vfx.FadeIn(duration), vfx.FadeOut(duration)])
"""
from moviepy.video.fx import FadeIn, FadeOut  # noqa: F401  (re-exported)

__all__ = ["FadeIn", "FadeOut"]
