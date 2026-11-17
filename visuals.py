import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

import config
import database
import queries

sns.set_theme(style="whitegrid")


def _run(n: int):
    return database.query_df(queries.QUERIES[n][1])


def _save(fig, name: str) -> str:
    config.FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FIG_DIR / name
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def fig_monthly_revenue() -> str:
    df = _run(1)
    df = df[(df["month"] >= "2017-01") & (df["month"] <= "2018-08")]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    sns.lineplot(data=df, x="month", y="revenue", marker="o", ax=ax)
    ax.set_title("Monthly revenue of delivered orders (BRL)")
    ax.set_xlabel("Month")
    ax.set_ylabel("Revenue, BRL")
    ax.tick_params(axis="x", rotation=60)
    return _save(fig, "01_monthly_revenue.png")


def fig_top_categories() -> str:
    df = _run(2).head(10)
    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(data=df, y="category", x="revenue", hue="category", legend=False, ax=ax)
    ax.set_title("Top-10 product categories by revenue")
    ax.set_xlabel("Revenue, BRL")
    ax.set_ylabel("Category")
    return _save(fig, "02_top_categories.png")


def fig_late_by_state() -> str:
    df = _run(3).sort_values("late_share_pct", ascending=False)
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=df, x="customer_state", y="late_share_pct", hue="customer_state", legend=False, ax=ax)
    ax.set_title("Share of late deliveries by customer state (states with 100+ orders)")
    ax.set_xlabel("Customer state")
    ax.set_ylabel("Late deliveries, %")
    return _save(fig, "03_late_by_state.png")


def fig_cohort_heatmap() -> str:
    df = _run(6)
    pivot = df.pivot(index="cohort", columns="month_offset", values="retention_pct")
    pivot = pivot.loc[pivot.index >= "2017-01"]
    pivot = pivot.drop(columns=[0])
    fig, ax = plt.subplots(figsize=(11, 7))
    sns.heatmap(pivot, annot=True, fmt=".1f", cmap="YlGnBu", cbar_kws={"label": "Retention, %"}, ax=ax)
    ax.set_title("Customer cohort retention (% of cohort that purchased again)")
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("Cohort (first purchase month)")
    return _save(fig, "04_cohort_retention.png")


def fig_review_vs_delay() -> str:
    df = _run(9)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    sns.barplot(data=df, x="delivery_bucket", y="avg_score", hue="delivery_bucket", legend=False, ax=ax)
    ax.set_ylim(1, 5)
    ax.set_title("Average review score vs delivery timeliness")
    ax.set_xlabel("Delivery vs estimated date")
    ax.set_ylabel("Average review score")
    ax.tick_params(axis="x", rotation=20)
    return _save(fig, "05_review_vs_delay.png")


def fig_seller_scatter() -> str:
    df = _run(4)
    fig, ax = plt.subplots(figsize=(8, 5.5))
    sns.scatterplot(data=df, x="late_share_pct", y="avg_review", size="revenue", alpha=0.7, ax=ax)
    ax.set_title("Seller performance: late share vs average review (top-50 sellers by revenue)")
    ax.set_xlabel("Late deliveries, %")
    ax.set_ylabel("Average review score")
    return _save(fig, "06_seller_performance.png")


def make_all() -> list:
    return [f() for f in (fig_monthly_revenue, fig_top_categories, fig_late_by_state,
                          fig_cohort_heatmap, fig_review_vs_delay, fig_seller_scatter)]
