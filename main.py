import sys

import pandas as pd

import audit
import benchmark
import config
import data_loader
import database
import ml_models
import queries
import visuals

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

_state = {"dfs": None}


def get_data() -> dict:
    if _state["dfs"] is None:
        _state["dfs"] = data_loader.load_all()
    return _state["dfs"]


def action_download() -> None:
    present = [f for f in config.RAW_FILES.values() if (config.RAW_DIR / f).exists()]
    print(f"{len(present)}/{len(config.RAW_FILES)} CSV files found in {config.RAW_DIR}")
    if len(present) < len(config.RAW_FILES):
        data_loader.download_dataset()


def action_optimize() -> None:
    print("Memory before/after dtype optimisation:")
    print(data_loader.memory_report().to_string(index=False))
    data_loader.convert_all_to_parquet()
    print("\nCSV vs Parquet:")
    print(data_loader.benchmark_csv_vs_parquet().to_string(index=False))
    _state["dfs"] = None


def action_audit() -> None:
    print(audit.run_audit(get_data())["text"])


def action_build_db() -> None:
    counts = database.build_database(get_data())
    for k, v in counts.items():
        print(f"  {k}: {v:,}")


def choose_query() -> None:
    for n, (title, _) in queries.QUERIES.items():
        print(f"  {n:>2}. {title}")
    raw = input("Query number (or 'a' for all): ").strip().lower()
    if raw == "a":
        numbers = list(queries.QUERIES)
    else:
        try:
            numbers = [int(raw)]
        except ValueError:
            print("Please enter a number or 'a'.")
            return
    for n in numbers:
        if n not in queries.QUERIES:
            print(f"No query #{n}.")
            continue
        title, sql = queries.QUERIES[n]
        df = database.query_df(sql)
        out = config.QUERY_DIR / f"query_{n:02d}.csv"
        config.QUERY_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        print(f"\n=== Q{n}: {title} === ({len(df)} rows, saved to {out.name})")
        print(df.head(15).to_string(index=False))


def action_compare_sql_pandas() -> None:
    print(benchmark.compare_sql_vs_pandas())


def action_visuals() -> None:
    for p in visuals.make_all():
        print("saved", p)


def action_models() -> None:
    print(ml_models.run_comparison().to_string(index=False))


def predict_interactive() -> None:
    df = ml_models.load_dataset()
    train, _ = ml_models.time_split(df)
    model = ml_models.build_models()["Random Forest"]
    model.fit(train[ml_models.NUM + ml_models.CAT], train["is_late"])
    row = train[ml_models.NUM + ml_models.CAT].median(numeric_only=True).to_dict()
    for col in ml_models.CAT:
        row[col] = train[col].mode().iat[0]
    prompts = {"promised_days": "Promised delivery time, days", "price_sum": "Order price, BRL",
               "freight_sum": "Freight, BRL"}
    for key, text in prompts.items():
        raw = input(f"{text} [{row[key]:.1f}]: ").strip()
        if raw:
            try:
                row[key] = float(raw)
            except ValueError:
                print("  not a number - default kept")
    for key, text in {"customer_state": "Customer state (e.g. SP)", "seller_state": "Seller state"}.items():
        raw = input(f"{text} [{row[key]}]: ").strip().upper()
        if raw:
            row[key] = raw
    row["same_state"] = int(row["customer_state"] == row["seller_state"])
    proba = model.predict_proba(pd.DataFrame([row]))[0, 1]
    print(f"Estimated probability of late delivery: {proba:.1%}")


def run_all() -> None:
    steps = [("Memory + Parquet", action_optimize), ("Audit", action_audit), ("Build DB", action_build_db),
             ("SQL vs Pandas", action_compare_sql_pandas), ("Visuals", action_visuals), ("Models", action_models)]
    for title, fn in steps:
        print(f"\n##### {title} #####")
        fn()
    print("\n##### SQL queries #####")
    config.QUERY_DIR.mkdir(parents=True, exist_ok=True)
    for n, (title, sql) in queries.QUERIES.items():
        df = database.query_df(sql)
        df.to_csv(config.QUERY_DIR / f"query_{n:02d}.csv", index=False)
        print(f"Q{n}: {title} -> {len(df)} rows")


MENU = {
    "1": ("Check / download dataset", action_download),
    "2": ("Optimise memory + CSV vs Parquet benchmark", action_optimize),
    "3": ("Data quality audit", action_audit),
    "4": ("Build SQLite database (3NF)", action_build_db),
    "5": ("Run SQL queries", choose_query),
    "6": ("SQL vs Pandas comparison", action_compare_sql_pandas),
    "7": ("Create visualisations", action_visuals),
    "8": ("Late-delivery models (baseline vs LR vs RF)", action_models),
    "9": ("Predict late delivery for a custom order", predict_interactive),
    "a": ("Run full pipeline", run_all),
    "0": ("Exit", None),
}


def main() -> None:
    config.ensure_dirs()
    if "--all" in sys.argv:
        run_all()
        return
    while True:
        print("\n=== Olist E-commerce Marketplace Analytics ===")
        for key, (title, _) in MENU.items():
            print(f"  {key} - {title}")
        choice = input("Choose: ").strip().lower()
        if choice == "0":
            print("Bye!")
            break
        if choice not in MENU:
            print("Unknown option.")
            continue
        try:
            MENU[choice][1]()
        except FileNotFoundError as exc:
            print(f"File problem: {exc}")
        except Exception as exc:
            print(f"Error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
