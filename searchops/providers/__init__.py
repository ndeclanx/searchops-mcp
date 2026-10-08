# SPDX-License-Identifier: MIT

"""Data provider abstractions.

Each provider wraps a single external data source (GSC, PageSpeed, etc.)
behind a typed interface.  The shared ``DataProvider`` protocol ensures every
provider exposes ``reinitialize()``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from searchops.providers.gsc import GSCProvider


@runtime_checkable
class DataProvider(Protocol):
    """Minimal protocol every data provider must satisfy."""

    def reinitialize(self) -> tuple[bool, str, str]:
        """Re-read configuration and verify connectivity.

        Returns (ok, category, detail).
        """
        ...


# Module-level singleton — tools import this directly.
gsc_provider = GSCProvider()
