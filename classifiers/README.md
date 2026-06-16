# Classifiers

Trained LogisticRegression models for real-time substance identification.

## Model Format

Each `.pkl` file contains a dictionary:

```python
{
    "clf": LogisticRegression,        # Trained classifier
    "label_encoder": LabelEncoder,    # Label → integer encoding
    "classes": list[str],             # Class names
    "scaler": StandardScaler,         # Feature scaler
    "classifier_name": str,           # User-given name
    "n_sensors": int,                 # Sensor channels used during training
    "n_features": int,                # Feature dimensions (30 for paradigm)
    "window_size": int,               # Window size in samples
    "training_accuracy": float,       # Training accuracy
}
```

## Feature Extraction

All models use **paradigm features** (5 per channel: delta_ratio, direction, mean_slope, auc, endpoint_delta) computed from R₀-normalized sensor data. This is device-agnostic.

## Included Models

- `garlic_ginger_onion_air.pkl` — 4-class (garlic, ginger, onion, room_air)
- `garlic_ginger_onion.pkl` — 3-class (garlic, ginger, onion)
- `garlic_ginger.pkl` — 2-class (garlic, ginger)

### Archive

- `archive/all_substances_(4).pkl` — Legacy model, uses old 48-dim statistical features (z-score + 8 per channel). Kept for backward compatibility.

## Training Your Own

Use the Train tab in Osmograph, or run:
```bash
python train_classifiers.py
```
