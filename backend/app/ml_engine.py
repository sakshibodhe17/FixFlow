"""
FixFlow failure-prediction engine.

Goal: estimate the probability that each asset has a (non-preventive) failure reported
within the next 30 days.

Features (per asset, computed "as of" a point in time, using only data before it):
    asset_age_days, failure_count, failures_90d, days_since_last_failure,
    days_since_last_repair, avg_repair_cost, total_downtime_hours, warranty_active,
    + one-hot usage category (asset category)

Training set (no data leakage): we take snapshots every 14 days across the history.
For each snapshot date T and each asset, features use data before T and the label is
"did the asset get a failure report in [T, T + 30 days)?". The model is validated on the
most recent 25% of snapshots (time-based split), then refit on everything.

Algorithm: XGBoost if installed, otherwise scikit-learn RandomForest.
If there is not enough history to train, a transparent heuristic scorer is used so the
dashboard still works on a fresh install.

CLI:
    python -m app.ml_engine train      # train + save model
    python -m app.ml_engine predict    # score every asset and store Failure_Prediction rows
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except ImportError:  # pragma: no cover
    HAS_XGBOOST = False

log = logging.getLogger("fixflow.ml")

HORIZON_DAYS = 30
SNAPSHOT_STEP_DAYS = 14
NUMERIC_FEATURES = [
    "asset_age_days", "failure_count", "failures_90d", "days_since_last_failure",
    "days_since_last_repair", "avg_repair_cost", "total_downtime_hours", "warranty_active",
]
FEATURE_LABELS = {
    "asset_age_days": "Asset age", "failure_count": "Total past failures", "failures_90d": "Failures in last 90 days",
    "days_since_last_failure": "Days since last failure", "days_since_last_repair": "Days since last repair",
    "avg_repair_cost": "Average repair cost", "total_downtime_hours": "Total downtime",
    "warranty_active": "Under warranty",
}
MODEL_FILENAME = "failure_model.joblib"


class InsufficientDataError(Exception):
    pass


# =============================================================================
# Pure functions (no database) — easy to unit test
# =============================================================================
def _utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True)


def _days_since(ids: pd.Series, grp, col: str, as_of: pd.Timestamp) -> pd.Series:
    """Days between as_of and each asset's latest event (NaN if none). Mapping numbers,
    not datetimes, avoids a pandas quirk with empty datetime mappers."""
    if grp.ngroups == 0:
        return pd.Series(np.nan, index=ids.index)
    days = (as_of - grp[col].max()).dt.days.astype(float)
    return ids.map(days).astype(float)


def build_features(assets: pd.DataFrame, failures: pd.DataFrame, repairs: pd.DataFrame,
                   as_of: pd.Timestamp) -> pd.DataFrame:
    """
    assets:   asset_id, category, purchase_date, created_at, warranty_expiry
    failures: asset_id, reported_at                   (non-preventive requests)
    repairs:  asset_id, completed_at, repair_cost, downtime_hours
    Returns one row per asset that existed at `as_of`.
    """
    a = assets.copy()
    a["start"] = a["purchase_date"].fillna(a["created_at"])
    a = a[a["start"] <= as_of]
    if a.empty:
        return pd.DataFrame(columns=["asset_id", "category", *NUMERIC_FEATURES])

    age = (as_of - a["start"]).dt.days.clip(lower=0).astype(float)
    f = failures[failures["reported_at"] < as_of]
    r = repairs[repairs["completed_at"] < as_of]
    grp_f = f.groupby("asset_id")
    grp_r = r.groupby("asset_id")

    out = pd.DataFrame({"asset_id": a["asset_id"].values, "category": a["category"].values,
                        "asset_age_days": age.values})
    ids = out["asset_id"]
    out["failure_count"] = ids.map(grp_f.size()).fillna(0).astype(float)
    recent = f[f["reported_at"] >= as_of - pd.Timedelta(days=90)].groupby("asset_id").size()
    out["failures_90d"] = ids.map(recent).fillna(0).astype(float)
    out["days_since_last_failure"] = _days_since(ids, grp_f, "reported_at", as_of).fillna(out["asset_age_days"])
    out["days_since_last_repair"] = _days_since(ids, grp_r, "completed_at", as_of).fillna(out["asset_age_days"])
    out["avg_repair_cost"] = ids.map(grp_r["repair_cost"].mean()).fillna(0).astype(float)
    out["total_downtime_hours"] = ids.map(grp_r["downtime_hours"].sum()).fillna(0).astype(float)
    out["warranty_active"] = (a["warranty_expiry"] >= as_of).fillna(False).astype(float).values
    return out


def encode(df: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    X = df[NUMERIC_FEATURES].astype(float).copy()
    for c in categories:
        X[f"cat_{c}"] = (df["category"] == c).astype(float)
    return X


def build_training_set(assets: pd.DataFrame, failures: pd.DataFrame, repairs: pd.DataFrame,
                       now: pd.Timestamp | None = None) -> pd.DataFrame:
    now = now or pd.Timestamp.now(tz="UTC")
    if failures.empty or assets.empty:
        raise InsufficientDataError("No failure history yet.")
    earliest = min(failures["reported_at"].min(), assets["purchase_date"].fillna(assets["created_at"]).min())
    start = max(earliest + pd.Timedelta(days=60), failures["reported_at"].min())
    end = now - pd.Timedelta(days=HORIZON_DAYS)
    if start >= end:
        raise InsufficientDataError("Need at least ~3 months of maintenance history to train.")
    frames = []
    for T in pd.date_range(start, end, freq=f"{SNAPSHOT_STEP_DAYS}D"):
        feats = build_features(assets, failures, repairs, T)
        if feats.empty:
            continue
        window = failures[(failures["reported_at"] >= T) &
                          (failures["reported_at"] < T + pd.Timedelta(days=HORIZON_DAYS))]
        hit = set(window["asset_id"])
        feats["label"] = feats["asset_id"].isin(hit).astype(int)
        feats["cutoff"] = T
        frames.append(feats)
    if not frames:
        raise InsufficientDataError("Not enough snapshots to train.")
    return pd.concat(frames, ignore_index=True)


def make_model():
    if HAS_XGBOOST:
        return "xgboost", XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9,
            min_child_weight=2, eval_metric="logloss", random_state=42, n_jobs=2)
    return "random_forest", RandomForestClassifier(
        n_estimators=400, max_depth=8, min_samples_leaf=3, random_state=42, n_jobs=2)


def fit_and_evaluate(data: pd.DataFrame, categories: list[str]) -> dict:
    """Time-based validation, then refit on all data. Returns a model bundle dict."""
    if len(data) < 60 or data["label"].nunique() < 2:
        raise InsufficientDataError("Need more labelled history (both failures and failure-free periods).")
    X, y = encode(data, categories), data["label"].values

    cutoffs = np.sort(data["cutoff"].unique())
    split_at = cutoffs[int(len(cutoffs) * 0.75)] if len(cutoffs) >= 4 else None
    train_mask = (data["cutoff"] < split_at).values if split_at is not None else None
    if train_mask is not None and len(set(y[train_mask])) == 2 and len(set(y[~train_mask])) == 2:
        X_tr, X_te, y_tr, y_te = X[train_mask], X[~train_mask], y[train_mask], y[~train_mask]
        split = "time-based (last 25% of snapshots)"
    else:
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y, random_state=42)
        split = "stratified random 25%"

    algo, model = make_model()
    model.fit(X_tr, y_tr)
    proba = model.predict_proba(X_te)[:, 1]
    pred = (proba >= 0.5).astype(int)
    metrics = {
        "roc_auc": round(float(roc_auc_score(y_te, proba)), 4),
        "accuracy": round(float(accuracy_score(y_te, pred)), 4),
        "precision": round(float(precision_score(y_te, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_te, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_te, pred, zero_division=0)), 4),
        "test_samples": int(len(y_te)), "train_samples": int(len(y_tr)), "split": split,
    }

    _, final = make_model()
    final.fit(X, y)
    importance = {col: round(float(v), 4) for col, v in zip(X.columns, final.feature_importances_)}
    version = f"{'xgb' if algo == 'xgboost' else 'rf'}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    return {"model": final, "algorithm": algo, "version": version, "categories": categories,
            "feature_columns": list(X.columns), "metrics": metrics, "feature_importance": importance,
            "n_samples": int(len(y)), "positive_rate": round(float(y.mean()), 4),
            "trained_at": datetime.now(timezone.utc).isoformat()}


def heuristic_scores(feats: pd.DataFrame) -> np.ndarray:
    """Fallback when no trained model exists: a transparent logistic score."""
    z = (-3.0
         + 0.9 * feats["failures_90d"]
         + 0.15 * feats["failure_count"]
         + 0.35 * (feats["asset_age_days"] / 365.0)
         + 0.8 * (feats["days_since_last_failure"] < 45).astype(float)
         + 0.4 * (1 - feats["warranty_active"]))
    return 1 / (1 + np.exp(-z.values))


def risk_level(score: float, medium: float, high: float) -> str:
    return "High" if score >= high else "Medium" if score >= medium else "Low"


def explain(row: pd.Series, fleet: pd.DataFrame) -> list[str]:
    """Plain-language reasons shown next to a risk score."""
    reasons = []
    if row["failures_90d"] >= 2:
        reasons.append(f"{int(row['failures_90d'])} faults in the last 90 days")
    elif row["failures_90d"] == 1:
        reasons.append("1 fault in the last 90 days")
    if row["failure_count"] > 0 and row["days_since_last_failure"] <= 30:
        reasons.append(f"Last failed {int(row['days_since_last_failure'])} days ago")
    years = row["asset_age_days"] / 365
    if years >= 5:
        reasons.append(f"{years:.0f} years old")
    if row["warranty_active"] == 0:
        reasons.append("Out of warranty")
    q75 = fleet["avg_repair_cost"].quantile(0.75) if len(fleet) else 0
    if row["avg_repair_cost"] > 0 and row["avg_repair_cost"] >= q75:
        reasons.append("Repairs cost more than most assets")
    if row["failure_count"] >= 5:
        reasons.append(f"{int(row['failure_count'])} failures on record")
    return reasons[:4] or ["No warning signs in its history"]


# =============================================================================
# Database-facing functions
# =============================================================================
def load_frames(db) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from sqlalchemy import select
    from .models import Asset, MaintenanceRequest, RepairLog

    assets = pd.DataFrame(db.execute(select(
        Asset.asset_id, Asset.category, Asset.purchase_date, Asset.created_at, Asset.warranty_expiry,
        Asset.status)).all(), columns=["asset_id", "category", "purchase_date", "created_at",
                                        "warranty_expiry", "status"])
    failures = pd.DataFrame(db.execute(select(MaintenanceRequest.asset_id, MaintenanceRequest.reported_at)
                                       .where(MaintenanceRequest.is_preventive.is_(False))).all(),
                            columns=["asset_id", "reported_at"])
    repairs = pd.DataFrame(db.execute(
        select(MaintenanceRequest.asset_id, RepairLog.completed_at, RepairLog.repair_cost, RepairLog.downtime_hours)
        .join(MaintenanceRequest, RepairLog.request_id == MaintenanceRequest.request_id)
        .where(RepairLog.completed_at.is_not(None))).all(),
        columns=["asset_id", "completed_at", "repair_cost", "downtime_hours"])

    for col in ("purchase_date", "created_at", "warranty_expiry"):
        assets[col] = _utc(assets[col])
    failures["reported_at"] = _utc(failures["reported_at"])
    repairs["completed_at"] = _utc(repairs["completed_at"])
    repairs["repair_cost"] = pd.to_numeric(repairs["repair_cost"], errors="coerce").fillna(0.0)
    repairs["downtime_hours"] = pd.to_numeric(repairs["downtime_hours"], errors="coerce").fillna(0.0)
    return assets, failures, repairs


def model_path():
    from .config import settings
    return settings.MODEL_DIR / MODEL_FILENAME


def load_bundle() -> dict | None:
    p = model_path()
    if not p.exists():
        return None
    try:
        return joblib.load(p)
    except Exception:
        log.exception("Could not load model file %s", p)
        return None


def train_model(db, trained_by: int | None = None) -> dict:
    from sqlalchemy import update
    from .models import ModelRun

    assets, failures, repairs = load_frames(db)
    data = build_training_set(assets, failures, repairs)
    categories = sorted(assets["category"].dropna().unique().tolist())
    bundle = fit_and_evaluate(data, categories)

    path = model_path()
    joblib.dump(bundle, path)
    joblib.dump(bundle, path.with_name(f"failure_model_{bundle['version']}.joblib"))  # keep history

    db.execute(update(ModelRun).values(is_active=False))
    run = ModelRun(model_version=bundle["version"], algorithm=bundle["algorithm"], n_samples=bundle["n_samples"],
                   positive_rate=bundle["positive_rate"], metrics=bundle["metrics"],
                   feature_importance=bundle["feature_importance"], is_active=True, trained_by=trained_by)
    db.add(run)
    db.commit()
    log.info("Trained %s on %d samples: %s", bundle["version"], bundle["n_samples"], bundle["metrics"])
    return {k: v for k, v in bundle.items() if k != "model"}


def current_features(db) -> pd.DataFrame:
    assets, failures, repairs = load_frames(db)
    active = assets[assets["status"] != "Retired"]
    return build_features(active, failures, repairs, pd.Timestamp.now(tz="UTC"))


def predict_all(db, notify_new_high: bool = True) -> dict:
    """Score every active asset, store Failure_Prediction rows, flag new High-risk assets."""
    from decimal import Decimal
    from sqlalchemy import select
    from .models import Asset, FailurePrediction
    from .services.notify import notify_roles
    from .services.settings_store import get_setting

    bundle = load_bundle()
    if bundle is None:
        try:
            train_model(db)
            bundle = load_bundle()
        except InsufficientDataError as e:
            log.info("Using heuristic scorer: %s", e)

    feats = current_features(db)
    if feats.empty:
        return {"model_version": None, "scored": 0, "high": 0, "medium": 0, "low": 0, "newly_high": []}

    if bundle:
        X = encode(feats, bundle["categories"]).reindex(columns=bundle["feature_columns"], fill_value=0.0)
        scores = bundle["model"].predict_proba(X)[:, 1]
        version = bundle["version"]
    else:
        scores = heuristic_scores(feats)
        version = "heuristic-v1"

    medium = get_setting(db, "risk_medium_threshold")
    high = get_setting(db, "risk_high_threshold")

    previous = {p.asset_id: p.risk_level for p in db.scalars(
        select(FailurePrediction).distinct(FailurePrediction.asset_id)
        .order_by(FailurePrediction.asset_id, FailurePrediction.predicted_at.desc()))}

    now = datetime.now(timezone.utc)
    counts = {"High": 0, "Medium": 0, "Low": 0}
    newly_high = []
    for asset_id, score in zip(feats["asset_id"], scores):
        s = float(np.clip(score, 0, 1))
        level = risk_level(s, medium, high)
        counts[level] += 1
        db.add(FailurePrediction(asset_id=int(asset_id), risk_score=Decimal(f"{s:.4f}"), risk_level=level,
                                 model_version=version, predicted_at=now))
        if level == "High" and previous.get(int(asset_id)) != "High":
            newly_high.append(int(asset_id))

    if notify_new_high and newly_high:
        names = [a.asset_name for a in db.scalars(select(Asset).where(Asset.asset_id.in_(newly_high)))]
        notify_roles(db, ("Manager",), f"{len(newly_high)} asset(s) now at high failure risk",
                     "Consider preventive maintenance for: " + ", ".join(names[:10]) +
                     ("…" if len(names) > 10 else ""), link="/manager/risk")
    db.commit()
    log.info("Scored %d assets with %s: %s", len(feats), version, counts)
    return {"model_version": version, "scored": int(len(feats)), "high": counts["High"],
            "medium": counts["Medium"], "low": counts["Low"], "newly_high": newly_high}


if __name__ == "__main__":  # python -m app.ml_engine train|predict
    logging.basicConfig(level=logging.INFO)
    from .database import SessionLocal

    cmd = sys.argv[1] if len(sys.argv) > 1 else "predict"
    with SessionLocal() as session:
        if cmd == "train":
            print(train_model(session))
        else:
            print(predict_all(session))
