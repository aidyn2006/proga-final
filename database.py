import sqlite3
from contextlib import closing

import pandas as pd

import config
import data_loader


def connect() -> sqlite3.Connection:
    if not config.DB_PATH.exists():
        raise FileNotFoundError(f"Database {config.DB_PATH} not found. Build it first (menu item 4).")
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query_df(sql: str, params=None, parse_dates=None) -> pd.DataFrame:
    with closing(connect()) as conn:
        return pd.read_sql_query(sql, conn, params=params, parse_dates=parse_dates)


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if isinstance(df[col].dtype, pd.CategoricalDtype):
            df[col] = df[col].astype(object)
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def build_zip_codes(dfs: dict, geo: pd.DataFrame) -> pd.DataFrame:
    c = dfs["customers"][["customer_zip_code_prefix", "customer_city", "customer_state"]]
    c.columns = ["zip_prefix", "city", "state"]
    s = dfs["sellers"][["seller_zip_code_prefix", "seller_city", "seller_state"]]
    s.columns = ["zip_prefix", "city", "state"]
    both = pd.concat([c.astype(object), s.astype(object)], ignore_index=True)
    counts = both.groupby(["zip_prefix", "city", "state"], dropna=False).size().reset_index(name="n")
    best = counts.sort_values("n", ascending=False).drop_duplicates("zip_prefix").drop(columns="n")
    best["zip_prefix"] = best["zip_prefix"].astype("int64")
    geo = geo.copy()
    geo["zip_prefix"] = geo["zip_prefix"].astype("int64")
    return best.merge(geo, on="zip_prefix", how="left").sort_values("zip_prefix")


def build_database(dfs: dict | None = None) -> dict:
    config.ensure_dirs()
    dfs = dfs or data_loader.load_all()
    geo = data_loader.aggregate_geolocation_chunked()

    if config.DB_PATH.exists():
        config.DB_PATH.unlink()

    zips = build_zip_codes(dfs, geo)
    customers = dfs["customers"].rename(columns={"customer_zip_code_prefix": "zip_prefix"})[
        ["customer_id", "customer_unique_id", "zip_prefix"]]
    sellers = dfs["sellers"].rename(columns={"seller_zip_code_prefix": "zip_prefix"})[
        ["seller_id", "zip_prefix"]]

    products = dfs["products"].rename(columns={
        "product_category_name": "category_name",
        "product_name_lenght": "name_length",
        "product_description_lenght": "description_length",
        "product_photos_qty": "photos_qty",
        "product_weight_g": "weight_g",
        "product_length_cm": "length_cm",
        "product_height_cm": "height_cm",
        "product_width_cm": "width_cm",
    })

    tr = dfs["category_translation"].astype(object)
    cats = pd.DataFrame({"category_name": pd.concat(
        [tr["product_category_name"], products["category_name"].astype(object)]).dropna().unique()})
    cats = cats.merge(tr.rename(columns={"product_category_name": "category_name",
                                         "product_category_name_english": "category_name_en"}),
                      on="category_name", how="left")
    cats["category_name_en"] = cats["category_name_en"].fillna(cats["category_name"])

    orders = dfs["orders"]
    items = dfs["order_items"]
    pays = dfs["order_payments"]
    rev = dfs["order_reviews"].drop_duplicates(subset=["review_id", "order_id"])
    rev = rev[rev["order_id"].isin(orders["order_id"])]

    tables = [
        ("zip_codes", zips), ("customers", customers), ("sellers", sellers),
        ("product_categories", cats), ("products", products), ("orders", orders),
        ("order_items", items), ("order_payments", pays), ("order_reviews", rev),
    ]

    counts = {}
    with closing(sqlite3.connect(config.DB_PATH)) as conn:
        conn.executescript((config.ROOT / "schema.sql").read_text(encoding="utf-8"))
        for name, df in tables:
            _prep(df).to_sql(name, conn, if_exists="append", index=False, chunksize=10_000)
            counts[name] = len(df)
        conn.commit()
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        counts["foreign_key_violations"] = len(bad)
    return counts
