import pickle
import time

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import config
import database
import queries

NUM = ["promised_days", "purchase_hour", "purchase_dow", "purchase_month", "n_items",
       "price_sum", "freight_sum", "weight_g", "volume_cm3", "installments", "same_state"]
CAT = ["category", "payment_type", "customer_state", "seller_state"]


def load_dataset() -> pd.DataFrame:
    return database.query_df(queries.ML_FEATURES_SQL, parse_dates=["purchase_ts"])


def time_split(df: pd.DataFrame, train_frac: float = 0.8):
    df = df.sort_values("purchase_ts").reset_index(drop=True)
    cut = int(len(df) * train_frac)
    return df.iloc[:cut], df.iloc[cut:]


def _preprocess(scale: bool) -> ColumnTransformer:
    num_steps = [("imp", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("sc", StandardScaler()))
    return ColumnTransformer([
        ("num", Pipeline(num_steps), NUM),
        ("cat", Pipeline([("imp", SimpleImputer(strategy="constant", fill_value="unknown")),
                          ("ohe", OneHotEncoder(handle_unknown="ignore", min_frequency=50))]), CAT),
    ])


def build_models() -> dict:
    return {
        "Baseline (majority class)": DummyClassifier(strategy="most_frequent"),
        "Logistic Regression": Pipeline([
            ("prep", _preprocess(scale=True)),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))]),
        "Random Forest": Pipeline([
            ("prep", _preprocess(scale=False)),
            ("clf", RandomForestClassifier(n_estimators=150, max_depth=14, min_samples_leaf=5,
                                           class_weight="balanced_subsample", n_jobs=-1,
                                           random_state=config.RANDOM_STATE))]),
    }


def run_comparison() -> pd.DataFrame:
    df = load_dataset()
    train, test = time_split(df)
    assert train["purchase_ts"].max() <= test["purchase_ts"].min()
    assert not set(train["order_id"]) & set(test["order_id"])

    X_tr, y_tr = train[NUM + CAT], train["is_late"]
    X_te, y_te = test[NUM + CAT], test["is_late"]

    rows = []
    for name, model in build_models().items():
        t0 = time.perf_counter()
        model.fit(X_tr, y_tr)
        fit_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        pred = model.predict(X_te)
        pred_s = time.perf_counter() - t0
        proba = model.predict_proba(X_te)[:, 1] if hasattr(model, "predict_proba") else pred
        tn, fp, fn, tp = confusion_matrix(y_te, pred, labels=[0, 1]).ravel()
        rows.append({
            "model": name,
            "f1_late": round(f1_score(y_te, pred, zero_division=0), 4),
            "precision_late": round(precision_score(y_te, pred, zero_division=0), 4),
            "recall_late": round(recall_score(y_te, pred, zero_division=0), 4),
            "roc_auc": round(roc_auc_score(y_te, proba), 4),
            "fit_s": round(fit_s, 2),
            "predict_s": round(pred_s, 3),
            "model_size_mb": round(len(pickle.dumps(model)) / 1024 ** 2, 2),
            "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
            "train_rows": len(train), "test_rows": len(test),
            "late_share_test": round(float(y_te.mean()), 4),
        })
    res = pd.DataFrame(rows)
    res.to_csv(config.OUT_DIR / "model_comparison.csv", index=False)
    return res
