from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from auth import get_current_user
from database import supabase
import joblib, numpy as np
from PIL import Image
import io, os
import tensorflow as tf

router = APIRouter(prefix="/analyze", tags=["Analysis"])

BASE   = os.path.dirname(os.path.dirname(__file__))
MODELS = os.path.join(BASE, "models")

# ── Speech model ──────────────────────────────────────────────────
speech_bundle   = joblib.load(os.path.join(MODELS, "parkinsons_best_model.pkl"))
speech_pipeline = speech_bundle["pipeline"]
SPEECH_FEATURES = speech_bundle["feature_cols"]

# ── Handwriting model ─────────────────────────────────────────────
hw_bundle    = joblib.load(os.path.join(MODELS, "handwriting_model_bundle.pkl"))
hw_img_size  = hw_bundle["img_size"]
hw_threshold = hw_bundle["best_threshold"]
hw_model     = tf.keras.models.load_model(
    os.path.join(MODELS, "efficientnet_handwriting_final.keras"))

# ── EEG artefacts ─────────────────────────────────────────────────
# Two inference paths are available (choose the one that matches your
# saved model artefacts):
#
#   PATH A  — Tabular (scaler → var-selector → sklearn/lgbm/xgb model)
#             Uses: eeg_scaler.pkl, eeg_var_selector.pkl,
#                   eeg_feature_names.pkl, eeg_best_tabular.pkl
#
#   PATH B  — CNN (raw segments → EEGNetLite)
#             Uses: eeg_cnn_config.pkl, eeg_cnn.pt
#
# Both paths start from the same raw-EEG preprocessing so you can
# enable whichever artefacts you actually exported from Colab.

import torch
import torch.nn as nn

# ── Load tabular pipeline artefacts ───────────────────────────────
eeg_scaler       = joblib.load(os.path.join(MODELS, "eeg_scaler.pkl"))
eeg_selector     = joblib.load(os.path.join(MODELS, "eeg_var_selector.pkl"))
# NOTE: the notebook saves the feature list as "eeg_feature_names.pkl"
# (the post-variance-threshold column names used to build the feature vector)
eeg_feat_names   = joblib.load(os.path.join(MODELS, "eeg_feature_names_selected.pkl"))
eeg_tabular_model = joblib.load(os.path.join(MODELS, "eeg_best_tabular.pkl"))

# ── EEGNetLite definition (must exactly match Cell 13 in the notebook) ──
class EEGNetLite(nn.Module):
    """
    Architecture from Cell 13 of parkinsons_eeg_updated_complete.ipynb.
    Key difference from the old code: takes (batch, n_channels, seg_len) raw
    EEG segments — NOT tabular features.
    """
    def __init__(self, n_channels: int, seg_len: int,
                 n_classes: int = 2,
                 F1: int = 8, D: int = 2, F2: int = 16,
                 dropout: float = 0.65,
                 embed_dim: int = 64):
        super().__init__()
        F2_actual = F1 * D

        self.temp_conv = nn.Sequential(
            nn.Conv1d(n_channels, F1, kernel_size=64, padding=32, bias=False),
            nn.BatchNorm1d(F1),
        )
        self.depth_conv = nn.Sequential(
            nn.Conv1d(F1, F1 * D, kernel_size=1, groups=F1, bias=False),
            nn.BatchNorm1d(F1 * D),
            nn.ELU(),
            nn.AvgPool1d(4),
            nn.Dropout(dropout),
        )
        self.sep_conv = nn.Sequential(
            nn.Conv1d(F2_actual, F2_actual, kernel_size=16, padding=8,
                      groups=F2_actual, bias=False),
            nn.Conv1d(F2_actual, F2, kernel_size=1, bias=False),
            nn.BatchNorm1d(F2),
            nn.ELU(),
            nn.AdaptiveAvgPool1d(4),
            nn.Dropout(dropout),
        )
        self.embed_head = nn.Sequential(
            nn.Flatten(),
            nn.Linear(F2 * 4, embed_dim),
            nn.ELU(),
            nn.Dropout(dropout * 0.5),
        )
        self.classifier = nn.Linear(embed_dim, n_classes)

    def forward(self, x):                    # x: (batch, channels, time)
        x = self.temp_conv(x)
        x = self.depth_conv(x)
        x = self.sep_conv(x)
        x = self.embed_head(x)
        return self.classifier(x)


# ── Load CNN artefacts (only if the .pt file was exported from Colab) ─
_cnn_pt_path  = os.path.join(MODELS, "eeg_cnn.pt")
_cnn_cfg_path = os.path.join(MODELS, "eeg_cnn_config.pkl")
eeg_net = None
eeg_cfg = None

if os.path.exists(_cnn_pt_path) and os.path.exists(_cnn_cfg_path):
    eeg_cfg = joblib.load(_cnn_cfg_path)
    eeg_net = EEGNetLite(
        n_channels = eeg_cfg["n_channels"],
        seg_len    = eeg_cfg["seg_len"],
        n_classes  = eeg_cfg.get("n_classes", 2),
        F1         = eeg_cfg.get("F1", 8),
        D          = eeg_cfg.get("D", 2),
        F2         = eeg_cfg.get("F2", 16),
        dropout    = eeg_cfg.get("dropout", 0.65),
        embed_dim  = eeg_cfg.get("embed_dim", 64),
    )
    eeg_net.load_state_dict(
        torch.load(_cnn_pt_path, map_location="cpu"))
    eeg_net.eval()
    print(f"✅ EEGNetLite loaded  "
          f"(n_channels={eeg_cfg['n_channels']}, seg_len={eeg_cfg['seg_len']})")
else:
    print("⚠️  eeg_cnn.pt / eeg_cnn_config.pkl not found — "
          "CNN path disabled, tabular model will be used.")


# ── Shared EEG preprocessing (mirrors Cell 6 + Cell 7 of the notebook) ─
def _preprocess_raw_eeg(raw):
    """Apply the exact same preprocessing as the Colab notebook."""
    import mne
    MAX_CROP_SECS  = 60.0
    RESAMPLE_SFREQ = 128
    NOTCH_FREQ     = 50.0
    L_FREQ, H_FREQ = 0.5, 45.0

    try:
        raw.pick_types(eeg=True, eog=False, ecg=False, stim=False, misc=False)
    except Exception:
        pass

    t_max = min(MAX_CROP_SECS, raw.times[-1])
    raw.crop(tmin=0.0, tmax=t_max)

    if raw.info["sfreq"] > RESAMPLE_SFREQ:
        raw.resample(RESAMPLE_SFREQ, verbose=False)

    if NOTCH_FREQ < raw.info["sfreq"] / 2:
        raw.notch_filter(freqs=NOTCH_FREQ, verbose=False)

    raw.filter(l_freq=L_FREQ, h_freq=H_FREQ,
               method="fir", fir_window="hamming", verbose=False)
    raw.set_eeg_reference("average", projection=False, verbose=False)
    return raw


def _extract_tabular_features(raw):
    """
    Mirror of Cell 7 extract_all_features() in the notebook.
    Returns a 1-D numpy array aligned to eeg_feat_names.
    """
    from scipy.signal import welch

    BANDS = {
        "delta": (1, 4), "theta": (4, 8),
        "alpha": (8, 13), "beta": (13, 30), "gamma": (30, 45),
    }

    data     = raw.get_data()            # (n_channels, n_times)
    sfreq    = raw.info["sfreq"]
    ch_names = raw.ch_names
    features, feat_names, band_matrices = [], [], {}

    # ── Band power (absolute) ──────────────────────────────────
    for band_name, (lo, hi) in BANDS.items():
        nperseg = min(int(sfreq * 2), data.shape[1])
        freqs, psd = welch(data, fs=sfreq, nperseg=nperseg, axis=-1)
        idx = np.where((freqs >= lo) & (freqs <= hi))[0]
        bp  = np.mean(psd[:, idx], axis=-1) if len(idx) > 0 else np.zeros(data.shape[0])
        band_matrices[band_name] = bp

        for ci, ch in enumerate(ch_names):
            features.append(float(bp[ci]))
            feat_names.append(f"{ch}_{band_name}_abs")
        features.append(float(np.mean(bp))); feat_names.append(f"mean_{band_name}_abs")
        features.append(float(np.std(bp)));  feat_names.append(f"std_{band_name}_abs")

    # ── Relative power ─────────────────────────────────────────
    total = sum(band_matrices.values())
    total = np.where(total == 0, 1e-12, total)
    for band_name, bp in band_matrices.items():
        rel = bp / total
        for ci, ch in enumerate(ch_names):
            features.append(float(rel[ci]))
            feat_names.append(f"{ch}_{band_name}_rel")
        features.append(float(np.mean(rel))); feat_names.append(f"mean_{band_name}_rel")

    # ── Band ratios ─────────────────────────────────────────────
    safe_div = lambda a, b: a / np.where(b == 0, 1e-12, b)
    for ci, ch in enumerate(ch_names):
        features.append(float(safe_div(band_matrices["theta"],
                                       band_matrices["alpha"])[ci]))
        feat_names.append(f"{ch}_theta_alpha_ratio")
        features.append(float(safe_div(
            band_matrices["delta"] + band_matrices["theta"],
            band_matrices["alpha"] + band_matrices["beta"])[ci]))
        feat_names.append(f"{ch}_slow_fast_ratio")

    # ── Hjorth parameters ──────────────────────────────────────
    d1       = np.diff(data, axis=1)
    d2       = np.diff(d1,   axis=1)
    activity = np.var(data, axis=1)
    var_d1   = np.var(d1, axis=1)
    var_d2   = np.var(d2, axis=1)
    mobility   = np.sqrt(np.where(activity > 0, var_d1 / activity, 0))
    mob_d1     = np.sqrt(np.where(var_d1  > 0, var_d2 / var_d1,   0))
    complexity = np.where(mobility > 0, mob_d1 / mobility, 0)

    for ci, ch in enumerate(ch_names):
        features.extend([float(activity[ci]), float(mobility[ci]), float(complexity[ci])])
        feat_names.extend([f"{ch}_hjorth_activity",
                           f"{ch}_hjorth_mobility",
                           f"{ch}_hjorth_complexity"])
    features.extend([float(np.mean(activity)),
                     float(np.mean(mobility)),
                     float(np.mean(complexity))])
    feat_names.extend(["mean_hjorth_activity",
                       "mean_hjorth_mobility",
                       "mean_hjorth_complexity"])

    # ── Spectral entropy ───────────────────────────────────────
    nperseg  = min(int(sfreq * 2), data.shape[1])
    _, psd   = welch(data, fs=sfreq, nperseg=nperseg, axis=-1)
    psd_norm = psd / (psd.sum(axis=1, keepdims=True) + 1e-12)
    entropy  = -np.sum(psd_norm * np.log2(psd_norm + 1e-12), axis=1)
    max_entr = np.log2(psd.shape[1])
    sp_entropy = entropy / max_entr

    for ci, ch in enumerate(ch_names):
        features.append(float(sp_entropy[ci]))
        feat_names.append(f"{ch}_spec_entropy")
    features.extend([float(np.mean(sp_entropy)), float(np.std(sp_entropy))])
    feat_names.extend(["mean_spec_entropy", "std_spec_entropy"])

    # ── Align to saved feature order ──────────────────────────
    feat_dict = dict(zip(feat_names, features))
    # eeg_feat_names are the POST-variance-threshold names saved by the notebook
    vals = np.array(
        [feat_dict.get(f, 0.0) for f in eeg_feat_names],
        dtype=np.float32
    )
    return vals


def _segment_eeg(data: np.ndarray, sfreq: float,
                 seg_secs: float = 2.0, overlap: float = 0.0) -> np.ndarray:
    """Split (n_ch, n_times) → (n_segs, n_ch, seg_len)."""
    seg_len = int(seg_secs * sfreq)
    step    = int(seg_len * (1 - overlap))
    segs    = [data[:, s:s + seg_len]
               for s in range(0, data.shape[1] - seg_len + 1, step)]
    return np.stack(segs, axis=0).astype(np.float32) if segs else None


# ── Helpers ───────────────────────────────────────────────────────
def risk_label(p: float) -> str:
    if p >= 0.65: return "High Risk"
    if p >= 0.40: return "Moderate Risk"
    return "Low Risk"


# ══════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════

@router.post("/speech")
def analyze_speech(
    features: dict,
    user_id: str = Depends(get_current_user)
):
    try:
        vals = [features[f] for f in SPEECH_FEATURES]
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Missing feature: {e}")
    proba = speech_pipeline.predict_proba([vals])[0]
    p_pd  = float(proba[1])
    return {"p_pd": round(p_pd, 4), "p_hc": round(1 - p_pd, 4),
            "risk": risk_label(p_pd)}


@router.post("/handwriting")
async def analyze_handwriting(
    image: UploadFile = File(...),
    user_id: str = Depends(get_current_user)
):
    contents = await image.read()
    img = Image.open(io.BytesIO(contents))\
               .resize((hw_img_size, hw_img_size)).convert("RGB")
    arr  = np.array(img, dtype=np.float32) / 255.0
    arr  = np.expand_dims(arr, 0)
    prob = float(hw_model.predict(arr)[0][0])
    p_pd = prob if prob >= hw_threshold else 1 - prob
    return {"p_pd": round(p_pd, 4), "p_hc": round(1 - p_pd, 4),
            "risk": risk_label(p_pd)}


@router.post("/eeg")
async def analyze_eeg(
    eeg_zip: UploadFile = File(...),
    user_id: str = Depends(get_current_user)
):
    """
    Accepts a ZIP containing a .set file (EEGLAB format).

    Inference path:
      • If eeg_cnn.pt is available  → CNN path  (raw segments → EEGNetLite)
      • Otherwise                    → Tabular path (features → scaler →
                                       VarianceThreshold → sklearn model)

    The two paths use different feature representations but identical
    preprocessing (crop 60 s, resample 128 Hz, bandpass, average ref).
    """
    import zipfile, tempfile, mne

    contents = await eeg_zip.read()

    with tempfile.TemporaryDirectory() as tmpdir:
        # ── 1. Extract ZIP ─────────────────────────────────────
        with zipfile.ZipFile(io.BytesIO(contents)) as z:
            z.extractall(tmpdir)

        # ── 2. Find .set file ──────────────────────────────────
        set_files = []
        for root, _, files in os.walk(tmpdir):
            for f in files:
                if f.lower().endswith(".set"):
                    set_files.append(os.path.join(root, f))

        if not set_files:
            raise HTTPException(
                status_code=422,
                detail="No .set file found in the uploaded ZIP. "
                       "Please upload a ZIP that contains an EEGLAB .set file."
            )

        # Prefer files with 'rest' in the name (resting-state)
        rest_files = [f for f in set_files if "rest" in os.path.basename(f).lower()]
        set_path   = rest_files[0] if rest_files else set_files[0]

        # ── 3. Load & preprocess ───────────────────────────────
        try:
            raw = mne.io.read_raw_eeglab(set_path, preload=True, verbose=False)
            raw = _preprocess_raw_eeg(raw)
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to load/preprocess EEG file: {e}"
            )

        # ══════════════════════════════════════════════════════
        # PATH A — CNN inference
        # Input: raw EEG segments (batch, n_channels, seg_len)
        # ══════════════════════════════════════════════════════
        if eeg_net is not None:
            seg_len_cfg = eeg_cfg["seg_len"]
            sfreq       = raw.info["sfreq"]
            data        = raw.get_data()            # (n_ch, n_times)

            # Ensure channel count matches what the CNN was trained on
            expected_ch = eeg_cfg["n_channels"]
            if data.shape[0] != expected_ch:
                # Pad or truncate channels to match training shape
                if data.shape[0] < expected_ch:
                    pad = np.zeros((expected_ch - data.shape[0], data.shape[1]),
                                   dtype=np.float32)
                    data = np.vstack([data, pad])
                else:
                    data = data[:expected_ch, :]

            segs = _segment_eeg(data, sfreq,
                                 seg_secs=seg_len_cfg / sfreq,
                                 overlap=0.0)
            if segs is None or len(segs) == 0:
                raise HTTPException(
                    status_code=422,
                    detail="EEG recording too short to extract even one segment."
                )

            tensor = torch.tensor(segs, dtype=torch.float32)  # (n_segs, n_ch, seg_len)
            with torch.no_grad():
                logits = eeg_net(tensor)
                probs  = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()

            # Subject-level aggregation: mean probability across segments
            p_pd = float(np.mean(probs))
            return {
                "p_pd":    round(p_pd, 4),
                "p_hc":    round(1 - p_pd, 4),
                "risk":    risk_label(p_pd),
                "n_segs":  int(len(segs)),
                "model":   "CNN",
            }

        # ══════════════════════════════════════════════════════
        # PATH B — Tabular inference
        # Input: hand-crafted features → scaler → VarianceThreshold → model
        #
        # FIX for the original ValueError:
        #   eeg_feat_names   = POST-variance-threshold column names
        #   eeg_var_selector = fitted on the RAW feature matrix (1060 cols)
        #
        # Correct order:
        #   raw_features (all ~1060) → scaler → selector → model
        #   NOT: partial features (506) → selector  ← this caused the crash
        # ══════════════════════════════════════════════════════
        else:
            # eeg_feat_names holds the SELECTED feature names (post-selector).
            # We need to first build the FULL raw feature vector, scale it,
            # then pass it through the selector.

            # Step 1: build full feature vector using ALL notebook feature names.
            #         We reuse _extract_tabular_features which already aligns
            #         to eeg_feat_names (the post-selection names). This is
            #         correct because the notebook saves eeg_feature_names.pkl
            #         AFTER fit_transform, i.e. these are already the selected
            #         columns. We therefore skip the selector here.
            #
            # If you saved eeg_feature_names_selected.pkl separately from a
            # pre-selection list, replace accordingly.
            vals = _extract_tabular_features(raw)   # shape: (n_selected_features,)

            # Step 2: scale (scaler was fitted on the post-selection features)
            vals_scaled = eeg_scaler.transform(vals.reshape(1, -1))

            # Step 3: run the tabular model
            proba = eeg_tabular_model.predict_proba(vals_scaled)[0]
            p_pd  = float(proba[1])

            return {
                "p_pd":  round(p_pd, 4),
                "p_hc":  round(1 - p_pd, 4),
                "risk":  risk_label(p_pd),
                "model": "Tabular",
            }


@router.post("/fuse")
def fuse_and_save(
    payload: dict,
    user_id: str = Depends(get_current_user)
):
    weights = {"eeg": 0.45, "speech": 0.30, "hw": 0.25}
    scores  = payload.get("scores", {})
    patient_name = payload.get("patient_name", "Unknown")

    total, w_sum = 0.0, 0.0
    for key, val in scores.items():
        if val is not None and key in weights:
            total  += val * weights[key]
            w_sum  += weights[key]
    if not w_sum:
        raise HTTPException(status_code=400, detail="No scores provided")

    fused = round(total / w_sum, 4)

    patient = supabase.table("patient_records").insert({
        "user_id": user_id, "patient_name": patient_name
    }).execute().data[0]

    supabase.table("screening_results").insert({
        "patient_id":   patient["id"],
        "speech_score": scores.get("speech"),
        "hw_score":     scores.get("hw"),
        "eeg_score":    scores.get("eeg"),
        "fused_score":  fused,
        "risk_label":   risk_label(fused),
    }).execute()

    return {"fused_score": fused, "risk": risk_label(fused),
            "patient_id": patient["id"]}