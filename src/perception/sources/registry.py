"""SourceRegistry — central catalogue of active data sources.

Provides registration, lookup, and aggregate health reporting for all
data sources in the Perception Layer.
"""

from __future__ import annotations

from typing import Dict, List

from src.perception.health import SourceHealth
from src.perception.sources.base import DataSource


class SourceRegistry:
    """Thread-safe registry of ``DataSource`` instances.

    Usage::

        registry = SourceRegistry()
        registry.register(my_tushare_source)
        registry.register(my_sina_source)

        all_sources = registry.all()
        report = registry.health_report()
    """

    def __init__(self) -> None:
        self._sources: Dict[str, DataSource] = {}

    def register(self, source: DataSource) -> None:
        """Register a data source.

        Args:
            source: The ``DataSource`` instance to register.

        Raises:
            ValueError: If a source with the same name is already
                registered.
        """
        if source.name in self._sources:
            raise ValueError(
                f"Source '{source.name}' is already registered"
            )
        self._sources[source.name] = source

    def unregister(self, name: str) -> None:
        """Remove a data source by name.

        Args:
            name: Name of the source to remove.

        Raises:
            KeyError: If no source with that name exists.
        """
        if name not in self._sources:
            raise KeyError(f"Source '{name}' is not registered")
        del self._sources[name]

    def get(self, name: str) -> DataSource:
        """Look up a data source by name.

        Args:
            name: Unique name of the source.

        Returns:
            The registered ``DataSource`` instance.

        Raises:
            KeyError: If the source is not found.
        """
        try:
            return self._sources[name]
        except KeyError:
            raise KeyError(f"Source '{name}' is not registered")

    def all(self) -> List[DataSource]:
        """Return all registered data sources.

        Returns:
            List of ``DataSource`` instances (insertion order).
        """
        return list(self._sources.values())

    def health_report(self) -> Dict[str, SourceHealth]:
        """Aggregate health snapshots for every registered source.

        Returns:
            A dict mapping source name → ``SourceHealth`` snapshot.
        """
        return {name: src.health() for name, src in self._sources.items()}

    @property
    def names(self) -> List[str]:
        """List of registered source names."""
        return list(self._sources.keys())

    def __len__(self) -> int:
        return len(self._sources)

    def __contains__(self, name: str) -> bool:
        return name in self._sources

    def __repr__(self) -> str:
        return f"<SourceRegistry sources={self.names}>"
