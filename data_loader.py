import shutil
import time
from pathlib import Path

import pandas as pd

import config


def memory_mb(df: pd.DataFrame) -> float:
    return df.memory_usage(deep=True).sum() / 1024 ** 2


def optimize_dtypes(df: pd.DataFrame, cat_ratio: float = 0.5) -> pd.DataFrame:
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_integer_dtype(s):
            df[col] = pd.to_numeric(s, downcast="integer")
        elif pd.api.types.is_float_dtype(s):
            df[col] = pd.to_numeric(s, downcast="float")
        elif s.dtype == object:
            n = len(s)
            if n and s.nunique(dropna=True) / n < cat_ratio:
                df[col] = s.astype("category")
    return df


def read_csv_chunked(name: str, chunksize: int = config.CHUNK_SIZE, optimize: bool = True) -> pd.DataFrame:
    path = config.RAW_DIR / config.RAW_FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Download the dataset first (menu item 1 / README).")
    parse_dates = config.DATE_COLS.get(name)
    chunks = []
    for chunk in pd.read_csv(path, chunksize=chunksize, parse_dates=parse_dates):
        chunks.append(optimize_dtypes(chunk) if optimize else chunk)
    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True)
    return optimize_dtypes(df) if optimize else df


def aggregate_geolocation_chunked(chunksize: int = config.CHUNK_SIZE) -> pd.DataFrame:
    path = config.RAW_DIR / config.RAW_FILES["geolocation"]
    if not path.exists():
        raise FileNotFoundError(f"{path} not found.")
    parts = []
    for chunk in pd.read_csv(path, chunksize=chunksize):
        g = chunk.groupby("geolocation_zip_code_prefix").agg(
            lat_sum=("geolocation_lat", "sum"),
            lng_sum=("geolocation_lng", "sum"),
            n=("geolocation_lat", "size"),
        )
        parts.append(g)
    total = pd.concat(parts).groupby(level=0).sum()
    out = pd.DataFrame({
        "zip_prefix": total.index.astype("int32"),
        "lat": (total["lat_sum"] / total["n"]).round(6).values,
        "lng": (total["lng_sum"] / total["n"]).round(6).values,
    })
    return out.reset_index(drop=True)


def memory_report() -> pd.DataFrame:
    rows = []
    for name in config.RAW_FILES:
        path = config.RAW_DIR / config.RAW_FILES[name]
        raw = pd.read_csv(path, parse_dates=config.DATE_COLS.get(name))
        before = memory_mb(raw)
        opt = optimize_dtypes(raw.copy())
        after = memory_mb(opt)
        rows.append({
            "table": name, "rows": len(raw),
            "mem_before_mb": round(before, 2), "mem_after_mb": round(after, 2),
            "saving_pct": round(100 * (1 - after / before), 1) if before else 0.0,
        })
        del raw, opt
    df = pd.DataFrame(rows)
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.OUT_DIR / "memory_report.csv", index=False)
    return df


def convert_all_to_parquet() -> None:
    config.PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    for name in config.RAW_FILES:
        df = read_csv_chunked(name)
        df.to_parquet(config.PARQUET_DIR / f"{name}.parquet", index=False)


def benchmark_csv_vs_parquet(repeats: int = 3) -> pd.DataFrame:
    rows = []
    for name, fname in config.RAW_FILES.items():
        csv_path = config.RAW_DIR / fname
        pq_path = config.PARQUET_DIR / f"{name}.parquet"
        if not pq_path.exists():
            df = read_csv_chunked(name)
            config.PARQUET_DIR.mkdir(parents=True, exist_ok=True)
            df.to_parquet(pq_path, index=False)
        t_csv = _best_time(lambda: pd.read_csv(csv_path), repeats)
        t_pq = _best_time(lambda: pd.read_parquet(pq_path), repeats)
        rows.append({
            "table": name,
            "csv_mb": round(csv_path.stat().st_size / 1024 ** 2, 2),
            "parquet_mb": round(pq_path.stat().st_size / 1024 ** 2, 2),
            "csv_read_s": round(t_csv, 3),
            "parquet_read_s": round(t_pq, 3),
        })
    df = pd.DataFrame(rows)
    df["size_ratio"] = (df["csv_mb"] / df["parquet_mb"]).round(2)
    df["speedup"] = (df["csv_read_s"] / df["parquet_read_s"]).round(2)
    df.to_csv(config.OUT_DIR / "csv_vs_parquet.csv", index=False)
    return df


def _best_time(fn, repeats: int) -> float:
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def load_all(prefer_parquet: bool = True) -> dict:
    out = {}
    for name in config.RAW_FILES:
        pq = config.PARQUET_DIR / f"{name}.parquet"
        if prefer_parquet and pq.exists():
            out[name] = pd.read_parquet(pq)
        else:
            out[name] = read_csv_chunked(name)
    return out


def download_dataset() -> bool:
    try:
        import kagglehub

        src = kagglehub.dataset_download("olistbr/brazilian-ecommerce")
        config.RAW_DIR.mkdir(parents=True, exist_ok=True)
        for f in Path(src).glob("*.csv"):
            shutil.copy(f, config.RAW_DIR / f.name)
        return True
    except Exception as exc:
        print(f"Automatic download failed: {exc}")
        print("Download manually: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce")
        print(f"and unzip the CSV files into: {config.RAW_DIR}")
        return False
