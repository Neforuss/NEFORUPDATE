"""Persistent app settings (stored by Qt under HKCU\\Software\\Neforus\\NEFORUPDATE)."""
from __future__ import annotations

import json

from PySide6.QtCore import QSettings

from .merge import DEFAULT_ORDER


class Settings:
    def __init__(self) -> None:
        self.q = QSettings("Neforus", "NEFORUPDATE")

    def _json(self, key: str, default):
        raw = self.q.value(key, "")
        try:
            return json.loads(raw) if raw else default
        except (TypeError, ValueError):
            return default

    def _set_json(self, key: str, value) -> None:
        self.q.setValue(key, json.dumps(value))

    # theme: "system" | "light" | "dark"
    @property
    def theme(self) -> str:
        v = self.q.value("theme", "system")
        return v if v in ("system", "light", "dark") else "system"

    @theme.setter
    def theme(self, v: str) -> None:
        self.q.setValue("theme", v)

    @property
    def source_order(self) -> list[str]:
        order = [s for s in self._json("source_order", DEFAULT_ORDER) if s in DEFAULT_ORDER]
        return order + [s for s in DEFAULT_ORDER if s not in order]

    @source_order.setter
    def source_order(self, v: list[str]) -> None:
        self._set_json("source_order", v)

    @property
    def disabled_sources(self) -> list[str]:
        return self._json("disabled_sources", [])

    @disabled_sources.setter
    def disabled_sources(self, v: list[str]) -> None:
        self._set_json("disabled_sources", v)

    # item key -> True/False, only where the user differs from the recommendation
    @property
    def ticks(self) -> dict[str, bool]:
        return self._json("ticks", {})

    @ticks.setter
    def ticks(self, v: dict[str, bool]) -> None:
        self._set_json("ticks", v)

    # item key -> source id the user picked for that app
    @property
    def forced_sources(self) -> dict[str, str]:
        return self._json("forced_sources", {})

    @forced_sources.setter
    def forced_sources(self, v: dict[str, str]) -> None:
        self._set_json("forced_sources", v)

    # Untracked apps the user marked as "checked" (winget ARP ids)
    @property
    def hidden_untracked(self) -> list[str]:
        return self._json("hidden_untracked", [])

    @hidden_untracked.setter
    def hidden_untracked(self, v: list[str]) -> None:
        self._set_json("hidden_untracked", v)

    # Untracked apps the user linked to a winget package:
    # ARP id -> {"id": package id, "name": package name, "app": installed app's name}
    @property
    def links(self) -> dict[str, dict]:
        return self._json("links", {})

    @links.setter
    def links(self, v: dict[str, dict]) -> None:
        self._set_json("links", v)

    @property
    def scoop_refresh(self) -> bool:
        return self.q.value("scoop_refresh", "false") in (True, "true")

    @scoop_refresh.setter
    def scoop_refresh(self, v: bool) -> None:
        self.q.setValue("scoop_refresh", "true" if v else "false")

    def geometry(self):
        return self.q.value("geometry")

    def set_geometry(self, g) -> None:
        self.q.setValue("geometry", g)

    def as_source_settings(self) -> dict:
        return {"scoop_refresh": self.scoop_refresh, "links": self.links}
