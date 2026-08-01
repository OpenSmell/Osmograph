"""
paradigm_features.py

Feature extraction for MOX sensor time series.

Three methods:
  1. paradigm_features (30-dim, legacy) — simple 5-feature-per-channel extraction
  2. framework_features (145+ dim, preferred) — full paper taxonomy features
     including device-agnostic, absolute, temporal, health, hardware,
     advanced (saturation index, multi-exp decay constants),
     cross-channel selectivity ratios, and global metrics

Framework features are the recommended approach. Paradigm features are kept
for backward compatibility with existing trained models.
"""

import numpy as np
from pathlib import Path

N_CHANNELS = 6

def _num_trapz(y: np.ndarray) -> float:
    try:
        return float(np.trapezoid(y))
    except AttributeError:
        return float(np.trapz(y))


def compute_window_paradigms(window: np.ndarray, r0_samples: int = 3) -> np.ndarray:
    n_ch = window.shape[1]
    feats = []
    for c in range(n_ch):
        ch = window[:, c].astype(np.float64)
        ch = np.nan_to_num(ch, nan=0.0, posinf=0.0, neginf=0.0)
        if np.std(ch) < 1e-8 or np.all(ch == 0):
            feats.extend([0.0, 0.0, 0.0, 0.0, 0.0])
            continue
        n_base = min(r0_samples, len(ch))
        R0 = np.mean(ch[:n_base])
        if R0 <= 0:
            R0 = np.mean(ch[ch > 0]) if np.any(ch > 0) else 1.0
        delta_ratio = float(np.max(np.abs(ch - R0)) / R0)
        last_mean = np.mean(ch[-3:]) if len(ch) >= 3 else ch[-1]
        direction = 1 if last_mean > R0 * 1.02 else (-1 if last_mean < R0 * 0.98 else 0)
        diffs = np.diff(ch)
        mean_slope = float(np.mean(np.abs(diffs)) / R0) if len(diffs) > 0 else 0.0
        normalized = np.abs(ch - R0) / R0
        auc = _num_trapz(normalized) if len(normalized) > 1 else float(normalized[0])
        n_first = min(3, len(ch))
        n_last = min(3, len(ch))
        first_mean = np.mean(ch[:n_first])
        endpoint_delta = float((np.mean(ch[-n_last:]) - first_mean) / R0) if R0 > 0 else 0.0
        feats.extend([delta_ratio, direction, mean_slope, auc, endpoint_delta])
    feats = [0.0 if np.isnan(f) or np.isinf(f) else f for f in feats]
    return np.array(feats, dtype=np.float32)


def compute_framework_features(window: np.ndarray) -> np.ndarray:
    """Extract framework features using the opensmell SDK.

    Returns 145+ dimensional feature vector covering:
    - Device-agnostic (6 per channel): relative_amplitude, direction,
      rise_time, decay_time, auc, endpoint_delta
    - Absolute (4 per channel): raw_resistance, baseline_resistance,
      voltage, calibrated_concentration
    - Temporal (4 per channel): hf_transient, oscillation_freq,
      oscillation_amp, response_latency
    - Health (4 per channel): drift_rate, sensitivity_decay,
      noise_floor, hysteresis
    - Hardware (3 per channel): circuit_response, thermal_profile, adc_noise
    - Advanced (7 per channel): saturation_index, tau1, tau2, tau3,
      a1, a2, a3 (multi-exp decay constants)
    - Cross-channel: selectivity_ratios for all sensor pairs
    - Global: max/mean_delta_ratio, n_active_channels, total_auc
    """
    from opensmell import features as _f
    feat_dict = _f.extract_all_framework_features(window)
    keys = sorted(feat_dict.keys())
    return np.array([feat_dict[k] for k in keys], dtype=np.float32)


def extract_features(window: np.ndarray, method: str = "framework") -> np.ndarray:
    if method == "framework" and window.shape[0] >= 15:
        return compute_framework_features(window)
    return compute_window_paradigms(window, r0_samples=3)


FEATURE_NAMES = []
for ch in range(N_CHANNELS):
    for feat in ['delta_ratio', 'direction', 'mean_slope', 'auc', 'endpoint_delta']:
        FEATURE_NAMES.append(f'ch{ch}_{feat}')
