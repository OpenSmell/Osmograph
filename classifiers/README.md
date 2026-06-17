# Classifiers

Trained models for real-time substance identification. Models in this directory are trained by the user via the Osmograph Train tab.

## Model Format

Each `.pkl` file contains a dictionary:

```python
{
    "clf": RandomForestClassifier | LogisticRegression,
    "label_encoder": LabelEncoder,
    "classes": list[str],
    "scaler": StandardScaler | None,
    "classifier_name": str,
    "n_sensors": int,
    "n_features": int,
    "window_size": int,
    "training_accuracy": float,
}
```

## Feature Extraction

All models use **paradigm features** (5 per channel: delta_ratio, direction, mean_slope, auc, endpoint_delta) computed from R₀-normalized sensor data. This is device-agnostic.

## Included Reference Models

The following `.pkl` files are pre-trained on the [SmellNet](https://github.com/opensmell/SmellNet) dataset (44 food substances, 6-sensor reference hardware). They serve as examples but may not work on other hardware without adaptation.

- `smellnet_4class_paradigm.pkl` — 4-class (garlic, ginger, lemon, cinnamon). Trained on SmellNet data using paradigm features.

### Archive

- `archive/` — Legacy models using old 48-dim statistical features. Kept for backward compatibility.

## Training Your Own

Use the **Train** tab in Osmograph:
1. Connect your board and record 30+ seconds per substance
2. Open the Train tab, click **Discover Recordings**
3. Assign labels and click **Train Classifier**
4. The trained model appears in the classifier dropdown automatically

Or run from the command line:
```bash
python train_classifiers.py
```

Training uses RandomForest by default (test better on small e-nose datasets than logistic regression). See `train_classifiers.py` for the full pipeline.
