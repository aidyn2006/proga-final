from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
PARQUET_DIR = ROOT / "data" / "parquet"
DB_PATH = ROOT / "data" / "olist.db"
OUT_DIR = ROOT / "outputs"
FIG_DIR = OUT_DIR / "figures"
QUERY_DIR = OUT_DIR / "query_results"

RAW_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

DATE_COLS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}

CHUNK_SIZE = 100_000
RANDOM_STATE = 42


def ensure_dirs() -> None:
    for d in (RAW_DIR, PARQUET_DIR, DB_PATH.parent, FIG_DIR, QUERY_DIR):
        d.mkdir(parents=True, exist_ok=True)
