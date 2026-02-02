"""Perception Layer — Detectors.

Re-exports the detector interface::

    from src.perception.detectors import Detector
"""

from src.perception.detectors.base import Detector

__all__ = ["Detector"]
