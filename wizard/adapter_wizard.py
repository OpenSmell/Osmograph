import sys
import logging
from pathlib import Path
from typing import Optional, Callable

import numpy as np

logger = logging.getLogger(__name__)

MIN_RECORDINGS = 3
RECOMMENDED_RECORDINGS = 5
TARGET_SUBSTANCES = ["garlic", "ginger", "cloves", "mint", "lemon", "coffee", "vinegar"]


class AdapterWizard:
    def __init__(self, model_dir: str | Path = ""):
        self._model_dir = Path(model_dir) if model_dir else Path.home() / ".cache" / "osmograph"
        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._model_path = self._model_dir / "adapter.pth"
        self._training_records: list[tuple[str, str]] = []
        self._model = None
        self._on_progress: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable) -> None:
        self._on_progress = callback

    def set_complete_callback(self, callback: Callable) -> None:
        self._on_complete = callback

    def add_recording(self, substance: str, csv_path: str) -> None:
        self._training_records.append((substance, csv_path))
        logger.info(f"Added recording: {substance} -> {csv_path}")

    def remove_recording(self, substance: str, csv_path: str = "") -> None:
        if csv_path:
            self._training_records = [
                (s, p) for s, p in self._training_records
                if not (s == substance and p == csv_path)
            ]
        else:
            self._training_records = [
                (s, p) for s, p in self._training_records if s != substance
            ]

    def clear_recordings(self) -> None:
        self._training_records.clear()

    @property
    def recording_count(self) -> int:
        return len(self._training_records)

    @property
    def substances(self) -> list[str]:
        return list(set(s for s, _ in self._training_records))

    @property
    def unique_substance_count(self) -> int:
        return len(self.substances)

    @property
    def is_ready(self) -> bool:
        return self.recording_count >= MIN_RECORDINGS and self.unique_substance_count >= 2

    @property
    def readiness_message(self) -> str:
        if self.recording_count < MIN_RECORDINGS:
            return f"Need {MIN_RECORDINGS} recordings (have {self.recording_count})"
        if self.unique_substance_count < 2:
            return "Need at least 2 different substances"
        return "Ready to train!"

    def train(self) -> dict:
        if not self.is_ready:
            return {"success": False, "error": self.readiness_message}

        if self._on_progress:
            self._on_progress(10)

        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "opensmell"))
            import opensmell
        except ImportError:
            return {"success": False, "error": "OpenSmell SDK not available"}

        if self._on_progress:
            self._on_progress(20)

        latents = []
        labels = []
        total = len(self._training_records)

        for idx, (substance, csv_path) in enumerate(self._training_records):
            if self._on_progress:
                self._on_progress(20 + int((idx / total) * 50))

            try:
                result = opensmell.process(csv_path)
                latents.append(result.latent)
                labels.append(substance)
            except Exception as e:
                logger.warning(f"Failed to process {csv_path}: {e}")
                continue

        if not latents:
            return {"success": False, "error": "No recordings could be processed"}

        if self._on_progress:
            self._on_progress(75)

        latent_matrix = np.stack(latents)
        unique_labels = list(set(labels))
        prototypes = {}
        for label in unique_labels:
            idxs = [i for i, l in enumerate(labels) if l == label]
            prototypes[label] = latent_matrix[idxs].mean(axis=0)

        if self._on_progress:
            self._on_progress(85)

        try:
            from sklearn.metrics.pairwise import cosine_similarity
            if len(latents) >= 4:
                test_idx = -1
                train_latents = latent_matrix[:test_idx]
                test_latent = latent_matrix[test_idx:]
                train_labels = labels[:test_idx]
                test_label = labels[test_idx]

                train_protos = {}
                for label in set(train_labels):
                    idxs = [i for i, l in enumerate(train_labels) if l == label]
                    train_protos[label] = train_latents[idxs].mean(axis=0)

                sims = []
                for proto_label, proto_vec in train_protos.items():
                    sim = cosine_similarity(test_latent, proto_vec.reshape(1, -1))[0][0]
                    sims.append(sim)
                avg_sim = float(np.mean(sims)) if sims else 0.0
            else:
                avg_sim = 0.0
        except Exception:
            avg_sim = 0.0

        try:
            self._train_adapter_module(latent_matrix, labels)
        except Exception as e:
            logger.warning(f"Adapter module training skipped: {e}")

        if self._on_progress:
            self._on_progress(100)

        result = {
            "success": True,
            "cosine_similarity": avg_sim,
            "substances_trained": unique_labels,
            "recording_count": len(latents),
            "model_path": str(self._model_path),
        }

        if self._on_complete:
            self._on_complete(result)

        return result

    def _train_adapter_module(self, latents: np.ndarray, labels: list[str]) -> None:
        import torch
        import torch.nn as nn

        n_substances = len(set(labels))
        if n_substances < 2 or latents.shape[0] < 4:
            return

        label_to_idx = {l: i for i, l in enumerate(set(labels))}
        targets = torch.tensor([label_to_idx[l] for l in labels], dtype=torch.long)
        X = torch.tensor(latents, dtype=torch.float32)

        model = nn.Sequential(
            nn.Linear(latents.shape[1], 64),
            nn.ReLU(),
            nn.Linear(64, n_substances),
        )
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        for epoch in range(50):
            optimizer.zero_grad()
            outputs = model(X)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()

        torch.save(model.state_dict(), str(self._model_path))
        logger.info(f"Adapter model saved to {self._model_path}")

    def load_model(self) -> bool:
        if not self._model_path.exists():
            return False
        try:
            import torch
            import torch.nn as nn

            self._model = nn.Sequential(
                nn.Linear(256, 64),
                nn.ReLU(),
                nn.Linear(64, 5),
            )
            self._model.load_state_dict(torch.load(str(self._model_path), map_location="cpu", weights_only=True))
            self._model.eval()
            return True
        except Exception as e:
            logger.warning(f"Failed to load adapter model: {e}")
            return False

    def predict(self, latent: np.ndarray) -> tuple[Optional[str], float]:
        if self._model is None and not self.load_model():
            return None, 0.0
        try:
            import torch
            with torch.no_grad():
                x = torch.tensor(latent.reshape(1, -1), dtype=torch.float32)
                out = self._model(x)
                probs = torch.softmax(out, dim=1)
                confidence, idx = torch.max(probs, dim=1)
                return None, float(confidence)
        except Exception:
            return None, 0.0
