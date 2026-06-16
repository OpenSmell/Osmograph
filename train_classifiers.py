#!/usr/bin/env python3
"""Train classifiers from your own e-nose recordings.

Usage:
    python train_classifiers.py

This script looks for recordings in ~/Osmograph_Recordings/ (created
automatically by Osmograph when you record). Customize the RECORDINGS
list below with your own CSV filenames and labels, then run.

The trained models are saved to Osmograph/classifiers/ and appear in
the Osmograph classifier dropdown on next launch.
"""
import sys, pickle, warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import RepeatedStratifiedKFold

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "opensmell"))
sys.path.insert(0, str(ROOT.parent))
from Osmograph.viz.paradigm_features import compute_window_paradigms
from opensmell.preprocessing import expand_channels

HOME = Path.home()
RECS = HOME / "Osmograph_Recordings"
TRAIN_STRIDE = 5
WINDOW_SIZE = 100
CLASSIFIERS_DIR = ROOT / "classifiers"

MQ6_COLS = ["MQ135", "MQ3", "MQ6", "MQ7", "MQ4", "MQ8"]
RECORDER_COLS = ["VOC", "Alcohol", "LPG", "CO", "NO2", "C2H5OH"]
ALL_COL_SETS = [MQ6_COLS, RECORDER_COLS]
FW_MAPPING = [(0, 0), (1, 1), (0, 2), (2, 3), (1, 4)]

RECORDINGS = [
    ("warm_garlic", RECS / "20260613_180633_warm garlic.csv"),
    ("after_warm_garlic", RECS / "20260613_180921_after warm garlic.csv"),
    ("onion", RECS / "20260612_162028_onions.csv"),
    ("onion", RECS / "20260612_193500_onions2.csv"),
    ("room_air", RECS / "20260612_193318_room air.csv"),
    ("mosquito_coil", RECS / "20260614_182351_Mosquito coil.csv"),
    ("mosquito_coil", RECS / "20260614_182510_Mosquito coil.csv"),
    ("mosquito_coil", RECS / "20260615_190732_mosquito coil 15 jun.csv"),
    ("cinnamon", RECS / "20260615_200424_cinnamon stick.csv"),
    ("mosquito_coil", RECS / "20260616_113220_mosquito coil.csv"),
    ("mosquito_coil", RECS / "20260616_113359_mosquito coil2.csv"),
    ("lime", RECS / "20260616_123018_morning lime.csv"),
    ("cinnamon", RECS / "20260616_124023_cinnamon.csv"),
]


def load_osm_csv(path):
    df = pd.read_csv(str(path))
    raw = None
    for col_set in ALL_COL_SETS:
        avail = [c for c in col_set if c in df.columns]
        if avail:
            raw = df[avail].values.astype(np.float32)
            break
    if raw is None:
        raise ValueError(f"No known columns in {path}")
    if raw.shape[1] < 6:
        raw = expand_channels(raw[:, :raw.shape[1]])
    elif raw.shape[1] > 6:
        raw = raw[:, :6]
    return raw


def extract_features(window):
    return compute_window_paradigms(window, r0_samples=3)


def load_windows(path):
    raw = load_osm_csv(path)
    N = raw.shape[0]
    if N >= WINDOW_SIZE:
        return [raw[i:i+WINDOW_SIZE] for i in range(0, N - WINDOW_SIZE + 1, TRAIN_STRIDE)]
    return [np.pad(raw, ((0, WINDOW_SIZE - N), (0, 0)), mode="edge")]


# ── Load all recordings ──────────────────────────────────────────────
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("Osmograph Classifier Training")
print("=" * 60)
print(f"Recordings dir: {RECORDINGS_DIR}")
print()

X, y = [], []
for label, path in RECORDINGS:
    if not path.exists():
        print(f"  SKIP (missing): {path.name}")
        continue
    windows = load_windows(path)
    for w in windows:
        X.append(extract_features(w))
        y.append(label)
    print(f"  {path.stem}: {len(windows)} windows -> {label}")

X = np.array(X)
print(f"\nTotal: {X.shape[0]} windows, {len(set(y))} classes: {sorted(set(y))}")
print(f"Feature dim: {X.shape[1]}")

# ── Build merged-garlic label vector ─────────────────────────────────
merged_y = np.array(["garlic" if lbl in ("warm_garlic", "after_warm_garlic") else lbl for lbl in y])
unique_merged = sorted(set(merged_y))
print(f"Merged garlic → {len(unique_merged)} classes: {unique_merged}")

# ── Helper: train + save ────────────────────────────────────────────
def train_and_save(labels, scaler_X, name, clf_type="rf"):
    le = LabelEncoder()
    y_enc = le.fit_transform(labels)
    n_classes = len(le.classes_)

    if clf_type == "lr":
        clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=1.0)
    else:
        clf = RandomForestClassifier(n_estimators=200, class_weight="balanced", max_depth=8, random_state=42)

    clf.fit(scaler_X, y_enc)
    train_acc = clf.score(scaler_X, y_enc)

    # Cross-validation
    if n_classes > 1 and X.shape[0] >= 12:
        rskf = RepeatedStratifiedKFold(n_splits=3, n_repeats=3, random_state=42)
        scores = []
        for tr, te in rskf.split(scaler_X, y_enc):
            if clf_type == "lr":
                c = LogisticRegression(max_iter=3000, class_weight="balanced", C=1.0)
            else:
                c = RandomForestClassifier(n_estimators=200, class_weight="balanced", max_depth=8, random_state=42)
            c.fit(scaler_X[tr], y_enc[tr])
            scores.append(c.score(scaler_X[te], y_enc[te]))
        cv_acc = f"{np.mean(scores):.3f} +/- {np.std(scores):.3f}"
    else:
        cv_acc = "N/A"

    path = CLASSIFIERS_DIR / f"{name}.pkl"
    with open(path, "wb") as f:
        pickle.dump({
            "clf": clf, "label_encoder": le,
            "classes": le.classes_.tolist(),
            "scaler": scaler_X,
            "window_size": WINDOW_SIZE,
            "n_features": X.shape[1],
        }, f)
    print(f"  → {path.name}  |  train={train_acc:.3f}  cv={cv_acc}  |  {n_classes} classes: {le.classes_.tolist()}")
    return clf, le

CLASSIFIERS_DIR.mkdir(parents=True, exist_ok=True)

# Scale all features once (used for multi-class models)
scaler_all = StandardScaler()
X_scaled = scaler_all.fit_transform(X)

print("\n── Models ──")

# 1. Merged-garlic multi-class (all classes, RF)
train_and_save(merged_y, X_scaled, "user_multi_class_rf", "rf")

# 2. Merged-garlic multi-class (all classes, LR)
train_and_save(merged_y, X_scaled, "user_multi_class_lr", "lr")

# 3. Mosquito coil vs everything else (binary, RF)
mc_mask = merged_y == "mosquito_coil"
mc_y = np.array(["mosquito_coil" if m else "other" for m in mc_mask])
mc_scaler = StandardScaler()
mc_X = mc_scaler.fit_transform(X)
train_and_save(mc_y, mc_X, "mosquito_coil_detector", "rf")

# 4. Mosquito coil vs room air (binary, RF)
for cls_a, cls_b, out_name in [
    ("mosquito_coil", "room_air", "mosquito_coil_vs_room_air"),
]:
    m = np.isin(merged_y, [cls_a, cls_b])
    bx, by = X[m], merged_y[m]
    bs = StandardScaler()
    bxs = bs.fit_transform(bx)
    train_and_save(by.tolist(), bxs, out_name, "rf")

print("\nDone.")
