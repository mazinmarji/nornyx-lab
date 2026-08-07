"""Browser-academy application layer.

This package is deliberately separate from the legacy Rich/Typer surface.  It
exposes typed curriculum, scenario, assessment, contract, and learner-record
services that can be rendered by any browser client without parsing prose.
"""

from .schemas import API_VERSION

__all__ = ["API_VERSION"]

