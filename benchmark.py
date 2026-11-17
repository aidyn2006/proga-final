import time
from contextlib import closing

import numpy as np
import pandas as pd

import config
import database
import queries


def pandas_delay_by_state(orders: pd.DataFrame, customers: pd.DataFrame, zips: pd.DataFrame) -> pd.DataFrame:
    df = (orders[(orders["order_status"] == "delivered") & orders["order_delivered_customer_date"].notna()]
          .merge(customers[["customer_id", "zip_prefix"]], on="customer_id")
          .merge(zips[["zip_prefix", "state"]], on="zip_prefix"))
    delay = (df["order_delivered_customer_date"] - df["order_estimated_delivery_date"]).dt.total_seconds() / 86400
    df = df.assign(delay=delay, late=delay > 0)
    out = (df.groupby("state")
             .agg(delivered_orders=("order_id", "size"),
                  avg_delay_days=("delay", "mean"),
                  late_share_pct=("late", "mean"))
             .reset_index().rename(columns={"state": "customer_state"}))
    out = out[out["delivered_orders"] >= 100].copy()
    out["avg_delay_days"] = out["avg_delay_days"].round(4)
    out["late_share_pct"] = (100 * out["late_share_pct"]).round(2)
    return out.sort_values("late_share_pct", ascending=False).reset_index(drop=True)


def _time(fn, repeats=5):
    times, result = [], None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t0)
    return result, min(times)


def compare_sql_vs_pandas(repeats: int = 5) -> dict:
    date_cols = config.DATE_COLS["orders"]
    with closing(database.connect()) as conn:
        t0 = time.perf_counter()
        orders = pd.read_sql_query("SELECT * FROM orders", conn, parse_dates=date_cols)
        customers = pd.read_sql_query("SELECT * FROM customers", conn)
        zips = pd.read_sql_query("SELECT * FROM zip_codes", conn)
        load_s = time.perf_counter() - t0

        sql_res, t_sql = _time(lambda: pd.read_sql_query(queries.BENCH_SQL, conn), repeats)
    pd_res, t_pd = _time(lambda: pandas_delay_by_state(orders, customers, zips), repeats)

    a = sql_res.sort_values("customer_state").reset_index(drop=True)
    b = pd_res.sort_values("customer_state").reset_index(drop=True)
    same_shape = a.shape == b.shape and a["customer_state"].tolist() == b["customer_state"].tolist()
    match = same_shape and all(
        np.allclose(a[c].astype(float), b[c].astype(float), atol=1e-2)
        for c in ["delivered_orders", "avg_delay_days", "late_share_pct"]
    )
    result = {
        "sql_time_s": round(t_sql, 4),
        "pandas_time_s": round(t_pd, 4),
        "pandas_table_load_s": round(load_s, 4),
        "results_match": bool(match),
        "rows": len(a),
    }
    pd.DataFrame([result]).to_csv(config.OUT_DIR / "sql_vs_pandas.csv", index=False)
    return result
