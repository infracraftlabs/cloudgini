"""Maps a stored account to its provider. Adding AWS or Azure means one new class and one line here."""
from __future__ import annotations

from ..models import Account
from .base import CloudProvider
from .simulated import SimulatedProvider

_cache: dict[str, CloudProvider] = {}


def get_provider(account: Account) -> CloudProvider:
    if account.id not in _cache:
        if account.provider == "simulated":
            _cache[account.id] = SimulatedProvider()
        elif account.provider == "gcp":
            from .gcp import GcpProvider  # optional dependency: pip install .[gcp]
            from ..config import get_settings
            _cache[account.id] = GcpProvider(project_id=account.scope_id, billing_table=get_settings().gcp_billing_table or None)
        else:
            raise ValueError(f"provider '{account.provider}' is not implemented yet")
    return _cache[account.id]


def reset_cache() -> None:
    _cache.clear()
