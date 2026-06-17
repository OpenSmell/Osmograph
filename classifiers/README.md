# Classifiers

Trained models for real-time substance identification. Models in this directory are trained by the user via the Osmograph Train tab.

Classifiers are stored as `.pkl` files and are local to your machine (listed in `.gitignore` — not pushed to the repo). Each contains the trained model, label encoder, and metadata for Osmograph to load and run predictions.

## Model Format

```python
{
    "clf": RandomForestClassifier | LogisticRegression,
    "label_encoder": LabelEncoder,
    "classes": list[str],
    "scaler": StandardScaler | None,
    "classifier_name": str,
    "n_sensors": int,       # stored at training time; actual sensor count detected at runtime
    "n_features": int,
    "window_size": int,
    "training_accuracy": float,
}
```

## Feature Extraction

All models use **paradigm features** (5 per channel: delta_ratio, direction, mean_slope, auc, endpoint_delta) computed from R₀-normalized sensor data. These features are device-agnostic — a model trained on one board can transfer to another with the same sensor types.

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
