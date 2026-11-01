"""Live quote search orchestration boundary.

No carrier adapter is enabled in this release. This module deliberately reports that
state instead of fabricating quotes. Approved provider adapters can be registered here
once credentials, contracts, and data-handling requirements are in place.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class QuoteProvider(Protocol):
    provider_id: str
    display_name: str

    async def search(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        """Return only quotes actually issued by the provider."""
        ...


@dataclass(frozen=True)
class ProviderState:
    provider_id: str
    display_name: str
    enabled: bool
    reason: str


# Intentionally empty until a real, authorized carrier/aggregator integration is added.
PROVIDERS: list[QuoteProvider] = []


def provider_status() -> dict[str, Any]:
    enabled = [p for p in PROVIDERS]
    return {
        "live_search_enabled": bool(enabled),
        "provider_count": len(enabled),
        "providers": [
            {"id": p.provider_id, "name": p.display_name, "status": "enabled"}
            for p in enabled
        ],
        "message": (
            "Live quote search is not configured yet. Add an approved provider adapter "
            "and its credentials before requesting real insurer rates."
            if not enabled else "Live quote providers are configured."
        ),
        "manual_quotes_supported": True,
        "simulated_quotes_used": False,
    }
