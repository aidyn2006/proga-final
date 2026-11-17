import pandas as pd

import config


def audit_table(name: str, df: pd.DataFrame) -> dict:
    n = len(df)
    missing = df.isna().sum()
    return {
        "table": name,
        "rows": n,
        "cols": df.shape[1],
        "full_duplicate_rows": int(df.duplicated().sum()),
        "columns_with_missing": {c: int(v) for c, v in missing.items() if v > 0},
    }


def logical_checks(dfs: dict) -> list:
    orders, items = dfs["orders"], dfs["order_items"]
    pays, rev = dfs["order_payments"], dfs["order_reviews"]
    res = []

    def add(check, mask):
        res.append({"check": check, "violations": int(mask.sum())})

    delivered = orders["order_status"] == "delivered"
    add("delivered order without delivery date",
        delivered & orders["order_delivered_customer_date"].isna())
    add("delivery date before purchase date",
        orders["order_delivered_customer_date"] < orders["order_purchase_timestamp"])
    add("approved before purchase",
        orders["order_approved_at"] < orders["order_purchase_timestamp"])
    add("carrier date before approval",
        orders["order_delivered_carrier_date"] < orders["order_approved_at"])
    add("non-delivered order with delivery date",
        ~delivered & orders["order_delivered_customer_date"].notna())
    add("order without any item", ~orders["order_id"].isin(items["order_id"]))
    add("item price <= 0", items["price"] <= 0)
    add("negative freight", items["freight_value"] < 0)
    add("payment value <= 0", pays["payment_value"] <= 0)
    add("review score outside 1..5", ~rev["review_score"].between(1, 5))
    add("duplicate review_id", rev["review_id"].duplicated())
    add("order_id in items but not in orders", ~items["order_id"].isin(orders["order_id"]))
    return res


def run_audit(dfs: dict) -> dict:
    report = {
        "tables": [audit_table(n, d) for n, d in dfs.items()],
        "logical_checks": logical_checks(dfs),
    }
    lines = []
    for t in report["tables"]:
        lines.append(f"[{t['table']}] rows={t['rows']:,} dup_rows={t['full_duplicate_rows']}")
        for c, v in t["columns_with_missing"].items():
            lines.append(f"    missing {c}: {v:,} ({100 * v / t['rows']:.1f}%)")
    lines.append("--- logical checks ---")
    for c in report["logical_checks"]:
        lines.append(f"  {c['check']}: {c['violations']:,}")
    report["text"] = "\n".join(lines)
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    (config.OUT_DIR / "data_quality_report.txt").write_text(report["text"], encoding="utf-8")
    return report
