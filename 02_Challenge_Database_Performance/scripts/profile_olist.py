
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "olist"

FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "translation": "product_category_name_translation.csv",
}

PRIMARY_KEYS = {
    "customers": ["customer_id"],
    "orders": ["order_id"],
    "order_items": ["order_id", "order_item_id"],
    "payments": ["order_id", "payment_sequential"],
    "reviews": ["review_id"],
    "products": ["product_id"],
    "sellers": ["seller_id"],
    "translation": ["product_category_name"],
}

frames = {}

print("=" * 65)
print("OLIST DATA QUALITY AUDIT")
print("=" * 65)

# 1. Profile ordinary CSV files
for table, filename in FILES.items():

    path = DATA / filename

    if not path.exists():
        raise FileNotFoundError(path)

    if table == "geolocation":
        continue

    df = pd.read_csv(path, dtype="string")
    frames[table] = df

    print(f"\nTABLE: {table}")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    nulls = df.isna().sum()
    missing = nulls[nulls > 0]

    print("Missing values:")
    print(missing.to_dict() if len(missing) else "None")

    keys = PRIMARY_KEYS[table]
    duplicates = df.duplicated(subset=keys).sum()

    print(f"Candidate PK: {keys}")
    print(f"Duplicate PK rows: {duplicates:,}")


# 2. Geolocation: process in chunks
print("\n" + "=" * 65)
print("GEOLOCATION PROFILE")
print("=" * 65)

geo_path = DATA / FILES["geolocation"]

geo_rows = 0
geo_nulls = {}
zip_prefixes = set()

for chunk in pd.read_csv(
    geo_path,
    dtype="string",
    chunksize=100_000
):
    geo_rows += len(chunk)

    for column in chunk.columns:
        geo_nulls[column] = (
            geo_nulls.get(column, 0)
            + int(chunk[column].isna().sum())
        )

    zip_prefixes.update(
        chunk["geolocation_zip_code_prefix"].dropna().unique()
    )

print(f"Rows: {geo_rows:,}")
print(f"Distinct ZIP prefixes: {len(zip_prefixes):,}")
print("Missing values:", {
    k: v for k, v in geo_nulls.items() if v > 0
})


# 3. Foreign key integrity
print("\n" + "=" * 65)
print("FOREIGN KEY AUDIT")
print("=" * 65)

RELATIONS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_items", "seller_id", "sellers", "seller_id"),
    ("payments", "order_id", "orders", "order_id"),
    ("reviews", "order_id", "orders", "order_id"),
]

for child, child_col, parent, parent_col in RELATIONS:

    child_values = frames[child][child_col]
    parent_values = set(
        frames[parent][parent_col].dropna()
    )

    invalid = child_values.notna() & ~child_values.isin(
        parent_values
    )

    print(
        f"{child}.{child_col} -> "
        f"{parent}.{parent_col}: "
        f"{int(invalid.sum()):,} unmatched rows"
    )

    if invalid.any():
        print(
            "  Examples:",
            child_values[invalid].drop_duplicates().head(5).tolist()
        )


print("\n" + "=" * 65)
print("AUDIT COMPLETED")
print("=" * 65)
