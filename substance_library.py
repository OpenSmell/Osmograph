"""Substance library for open-set recognition.

Stores feature vectors per substance and does nearest-neighbor matching
with distance-based rejection for unknown substances.

Usage:
    lib = SubstanceLibrary()
    lib.add("garlic", feature_vector)
    lib.add("cinnamon", feature_vector)
    label, distance, is_known = lib.match(feature_vector, threshold=0.5)
"""
import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class SubstanceLibrary:
    def __init__(self, path: Optional[Path] = None):
        self._vectors: dict[str, list[np.ndarray]] = {}
        self._path = path or Path.home() / ".config" / "Osmograph" / "substance_library.json"
        self._load()

    @property
    def substances(self) -> list[str]:
        return sorted(self._vectors.keys())

    @property
    def count(self) -> int:
        return len(self._vectors)

    def add(self, substance: str, vector: np.ndarray) -> None:
        key = substance.strip().lower().replace(" ", "_")
        if key not in self._vectors:
            self._vectors[key] = []
        self._vectors[key].append(vector.astype(np.float32).copy())
        self._save()

    def remove(self, substance: str) -> None:
        key = substance.strip().lower().replace(" ", "_")
        self._vectors.pop(key, None)
        self._save()

    def clear(self) -> None:
        self._vectors.clear()
        self._save()

    def match(self, vector: np.ndarray, threshold: float = 0.5
              ) -> tuple[str, float, bool]:
        if not self._vectors:
            return "unknown", 1.0, False

        vec = vector.astype(np.float32).flatten()
        best_label = "unknown"
        best_dist = float("inf")

        for label, vecs in self._vectors.items():
            for ref in vecs:
                ref_f = ref.flatten()
                if np.allclose(ref_f, 0) or np.allclose(vec, 0):
                    dist = float(np.linalg.norm(vec - ref_f))
                else:
                    if np.linalg.norm(ref_f) == 0 or np.linalg.norm(vec) == 0:
                        dist = float(np.linalg.norm(vec - ref_f))
                    else:
                        cos = float(np.dot(vec, ref_f) / (
                            np.linalg.norm(vec) * np.linalg.norm(ref_f) + 1e-8
                        ))
                        dist = 1.0 - cos

                if dist < best_dist:
                    best_dist = dist
                    best_label = label

        normalized_dist = min(1.0, max(0.0, best_dist))
        is_known = normalized_dist <= threshold
        return best_label, normalized_dist, is_known

    def fingerprint(self, vector: np.ndarray) -> Optional[str]:
        label, dist, known = self.match(vector)
        return label if known else None

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            for label, vecs in self._vectors.items():
                data[label] = [v.tolist() for v in vecs]
            with open(self._path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save substance library: {e}")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path) as f:
                data = json.load(f)
            for label, vecs in data.items():
                self._vectors[label] = [np.array(v, dtype=np.float32) for v in vecs]
            logger.info(f"Loaded {len(self._vectors)} substances from library")
        except Exception as e:
            logger.warning(f"Failed to load substance library: {e}")
