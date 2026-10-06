"""Registered update sources. Add new ones (pip, npm, vendor updaters) to ALL_SOURCES."""
from .base import Callbacks, Candidate, Context, Job, Result, Source
from .chocolatey import ChocolateySource
from .linked import LinkedSource
from .msstore import StoreSource
from .scoop import ScoopSource
from .windows_update import WindowsUpdateSource
from .winget import WingetSource


def all_sources() -> list[Source]:
    return [WingetSource(), StoreSource(), ChocolateySource(), ScoopSource(), LinkedSource(), WindowsUpdateSource()]


__all__ = ["Callbacks", "Candidate", "Context", "Job", "Result", "Source", "all_sources"]
