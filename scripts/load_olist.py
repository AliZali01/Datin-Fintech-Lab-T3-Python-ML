
import os
import time
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "olist"

load_dotenv(ROOT / ".env")

# Source CSV -> PostgreSQL table and columns
TABLES = {
    "customers": (
        "olist_customers_dataset.csv",
        [
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
        ],
    ),
    "geolocation": (
        "olist_geolocation_dataset.csv",
        [
            "geolocation_zip_code_prefix",
            "geolocation_lat",
            "geolocation_lng",
            "geolocation_city",
            "geolocation_state",
        ],
    ),
    "product_category_translation": (
        "product_category_name_translation.csv",
        [
            "product_category_name",
            "product_category_name_english",
        ],
    ),
    "products": (
        "olist_products_dataset.csv",
        [
            "product_id",
            "product_category_name",
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ],
    ),
    "sellers": (
        "olist_sellers_dataset.csv",
        [
            "seller_id",
            "seller_zip_code_prefix",
            "seller_city",
            "seller_state",
        ],
    ),
    "orders": (
        "olist_orders_dataset.csv",
        [
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    ),
    "order_items": (
        "olist_order_items_dataset.csv",
        [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
        ],
    ),
    "order_payments": (
        "olist_order_payments_dataset.csv",
        [
            "order_id",
            "payment_sequential",
            "payment_type",
            "payment_installments",
            "payment_value",
        ],
    ),
    "order_reviews": (
        "olist_order_reviews_dataset.csv",
        [
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
            "review_creation_date",
            "review_answer_timestamp",
        ],
    ),
}


def main():

    start = time.perf_counter()

    connection_settings = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }

    if not all([
        connection_settings["dbname"],
        connection_settings["user"],
        connection_settings["password"],
    ]):
        raise RuntimeError("Database credentials are missing from .env")

    # Verify all source files before modifying database
    for filename, _ in TABLES.values():
        if not (DATA_DIR / filename).exists():
            raise FileNotFoundError(DATA_DIR / filename)

    print("Connecting to PostgreSQL...")

    with psycopg.connect(**connection_settings) as conn:

        with conn.cursor() as cur:

            # Reset previous Olist data.
            # All related tables are truncated together.
            cur.execute("""
                TRUNCATE TABLE
                    olist.order_reviews,
                    olist.order_payments,
                    olist.order_items,
                    olist.orders,
                    olist.products,
                    olist.sellers,
                    olist.customers,
                    olist.geolocation,
                    olist.product_category_translation
                RESTART IDENTITY;
            """)

            results = {}

            for table, (filename, columns) in TABLES.items():

                path = DATA_DIR / filename

                print(f"\nLoading {table}...")

                copy_command = sql.SQL("""
                    COPY {} ({})
                    FROM STDIN
                    WITH (
                        FORMAT CSV,
                        HEADER TRUE,
                        ENCODING 'UTF8'
                    )
                """).format(
                    sql.Identifier("olist", table),
                    sql.SQL(", ").join(
                        sql.Identifier(column)
                        for column in columns
                    ),
                )

                with cur.copy(copy_command) as copy:
                    with path.open("rb") as source:
                        while chunk := source.read(1024 * 1024):
                            copy.write(chunk)

                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(
                        sql.Identifier("olist", table)
                    )
                )

                count = cur.fetchone()[0]
                results[table] = count

                print(f"Loaded: {count:,} records")

                # Preserve categories without English translations.
                if table == "product_category_translation":
                    cur.execute("""
                        INSERT INTO olist.product_category_translation
                            (product_category_name,
                             product_category_name_english)
                        VALUES
                            ('pc_gamer', NULL),
                            ('portateis_cozinha_e_preparadores_de_alimentos',
                             NULL)
                        ON CONFLICT (product_category_name)
                        DO NOTHING;
                    """)

                    print("Untranslated categories preserved.")

    # Transaction has been committed successfully here.
    elapsed = time.perf_counter() - start

    print("\n" + "=" * 55)
    print("OLIST DATA LOADING COMPLETED")
    print("=" * 55)

    for table, count in results.items():
        print(f"{table:35} {count:>12,}")

    print("\nGeolocation and all source tables loaded.")
    print(f"Duration: {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()
