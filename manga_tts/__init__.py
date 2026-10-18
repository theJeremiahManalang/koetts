"""Manga-TTS Python workflow interface. Provider dependencies are lazy.

Import PipelineConfig and PipelineRouter here; commands/results live in schemas.
The web interface and CLI submit commands to the same router.
"""
from .config import PipelineConfig
from .router import PipelineRouter

__all__ = ["PipelineConfig", "PipelineRouter"]
