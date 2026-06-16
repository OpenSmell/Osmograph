"""
paradigm_features.py

Paradigm-based feature extraction for MOX sensor time series.
Replaces the statistical feature extraction (mean, std, skew, kurtosis, etc.)
with physically meaningful paradigm features.

The four paradigms:
1. AMPLITUDE: delta_ratio = max deviation from R0, normalized by R0
2. SELECTIVITY: (cross-channel) relative delta_ratios across channels
3. TEMPORAL: mean_slope (rate of change) and auc (integrated response)
4. RATIO STABILITY: all features are normalized by local R0

These features are device-agnostic: R0 normalization cancels baseline drift
and manufacturing variance.
"""

import numpy as np

N_CHANNELS = 6


def compute_window_paradigms(window: np.ndarray, r0_samples: int = 3) -> np.ndarray:
    """
    Extract paradigm features from a (T, C) sensor window.
    
    For each channel:
      - delta_ratio: |extreme - R0| / R0 (amplitude)
      - direction: +1 (increase), -1 (decrease), 0 (flat)
      - mean_slope: mean(|diff|) / R0 (temporal dynamics)
      - auc: sum(|R - R0| / R0) (integrated response)
      - endpoint_delta: (last - first) / R0 (trend)
    
    Returns:
        (5 * C,) feature vector
    """
    n_ch = window.shape[1]
    feats = []
    
    for c in range(n_ch):
        ch = window[:, c].astype(np.float64)
        ch = np.nan_to_num(ch, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Check for dead channel (all same value, or all zero)
        if np.std(ch) < 1e-8 or np.all(ch == 0):
            feats.extend([0.0, 0.0, 0.0, 0.0, 0.0])
            continue
        
        # Ratio Stability: estimate local baseline
        n_base = min(r0_samples, len(ch))
        R0 = np.mean(ch[:n_base])
        if R0 <= 0:
            R0 = np.mean(ch[ch > 0]) if np.any(ch > 0) else 1.0
        
        # Amplitude: find extreme relative to R0
        delta_ratio = float(np.max(np.abs(ch - R0)) / R0)
        
        # Direction: which way did the signal go
        last_mean = np.mean(ch[-3:]) if len(ch) >= 3 else ch[-1]
        direction = 1 if last_mean > R0 * 1.02 else (-1 if last_mean < R0 * 0.98 else 0)
        
        # Temporal: rate of change
        diffs = np.diff(ch)
        mean_slope = float(np.mean(np.abs(diffs)) / R0) if len(diffs) > 0 else 0.0
        
        # Temporal: integrated response
        normalized = np.abs(ch - R0) / R0
        auc = float(np.trapezoid(normalized)) if len(normalized) > 1 else float(normalized[0])
        
        # Endpoint delta (trend across window)
        n_first = min(3, len(ch))
        n_last = min(3, len(ch))
        first_mean = np.mean(ch[:n_first])
        endpoint_delta = float((np.mean(ch[-n_last:]) - first_mean) / R0) if R0 > 0 else 0.0
        
        feats.extend([delta_ratio, direction, mean_slope, auc, endpoint_delta])
    
    feats = [0.0 if np.isnan(f) or np.isinf(f) else f for f in feats]
    return np.array(feats, dtype=np.float32)


def extract_features(window: np.ndarray) -> np.ndarray:
    """
    Drop-in replacement for the old extract_features in realtime_classifier.py.
    Uses paradigm features instead of statistical features.
    
    Old: 8 features/channel (mean, std, range, RMS, mean_diff, endpoint, skew, kurtosis)
    New: 5 features/channel (delta_ratio, direction, mean_slope, auc, endpoint_delta)
    
    Returns:
        (30,) feature vector for 6 channels (5 features * 6 channels)
    """
    return compute_window_paradigms(window, r0_samples=3)


# Feature names for interpretability
FEATURE_NAMES = []
for ch in range(N_CHANNELS):
    for feat in ['delta_ratio', 'direction', 'mean_slope', 'auc', 'endpoint_delta']:
        FEATURE_NAMES.append(f'ch{ch}_{feat}')
