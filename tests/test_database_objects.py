
import os
import unittest
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import DBAPIError


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def create_database_engine():

    required = [
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ]

    missing = [key for key in required if not os.getenv(key)]

    if missing:
        raise RuntimeError(f"Missing environment variables: {missing}")

    database_url = URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("DB_HOST") or "localhost",
        port=int(os.getenv("DB_PORT") or "5432"),
        database=os.getenv("POSTGRES_DB"),
    )

    return create_engine(database_url, pool_pre_ping=True)


class TestDatabaseObjects(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_database_engine()

        with cls.engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_top_sellers_function_matches_snapshot(self):

        with self.engine.connect() as conn:

            actual = conn.execute(
                text("""
                    SELECT seller_id, total_revenue
                    FROM olist.get_top_sellers(:limit)
                """),
                {"limit": 20},
            ).all()

            expected = conn.execute(
                text("""
                    SELECT seller_id, total_revenue
                    FROM olist.seller_performance_snapshot
                    ORDER BY total_revenue DESC
                    LIMIT :limit
                """),
                {"limit": 20},
            ).all()

        self.assertEqual(len(actual), 20)
        self.assertEqual(
            {(r.seller_id, r.total_revenue) for r in actual},
            {(r.seller_id, r.total_revenue) for r in expected},
        )

    def test_category_sales_function_respects_date_range(self):

        params = {
            "start_date": date(2017, 1, 1),
            "end_date": date(2017, 3, 31),
        }

        with self.engine.connect() as conn:

            actual = conn.execute(
                text("""
                    SELECT *
                    FROM olist.get_category_sales(
                        :start_date,
                        :end_date
                    )
                    ORDER BY sales_month, category
                """),
                params,
            ).all()

            expected = conn.execute(
                text("""
                    SELECT *
                    FROM olist.monthly_category_sales_snapshot
                    WHERE sales_month >= :start_date
                      AND sales_month <= :end_date
                    ORDER BY sales_month, category
                """),
                params,
            ).all()

        self.assertGreater(len(actual), 0)
        self.assertEqual(actual, expected)

    def test_payment_distribution_function_filters_type(self):

        with self.engine.connect() as conn:

            payment_type = conn.scalar(
                text("""
                    SELECT payment_type
                    FROM olist.payment_distribution_snapshot
                    ORDER BY payment_type
                    LIMIT 1
                """)
            )

            actual = conn.execute(
                text("""
                    SELECT *
                    FROM olist.get_payment_distribution(
                        :payment_type
                    )
                    ORDER BY payment_type, payment_installments
                """),
                {"payment_type": payment_type},
            ).all()

            expected = conn.execute(
                text("""
                    SELECT *
                    FROM olist.payment_distribution_snapshot
                    WHERE payment_type = :payment_type
                    ORDER BY payment_type, payment_installments
                """),
                {"payment_type": payment_type},
            ).all()

        self.assertIsNotNone(payment_type)
        self.assertGreater(len(actual), 0)
        self.assertEqual(actual, expected)

    def test_views_match_source_data(self):

        with self.engine.connect() as conn:

            delivered_view = conn.scalar(
                text("SELECT COUNT(*) FROM olist.v_delivered_orders")
            )

            delivered_source = conn.scalar(
                text("""
                    SELECT COUNT(*)
                    FROM olist.orders
                    WHERE order_status = 'delivered'
                      AND order_delivered_customer_date IS NOT NULL
                """)
            )

            live_sellers = conn.execute(
                text("""
                    SELECT
                        COUNT(*),
                        ROUND(COALESCE(SUM(total_revenue), 0), 2)
                    FROM olist.v_seller_performance_live
                """)
            ).one()

            snapshot_sellers = conn.execute(
                text("""
                    SELECT
                        COUNT(*),
                        ROUND(COALESCE(SUM(total_revenue), 0), 2)
                    FROM olist.seller_performance_snapshot
                """)
            ).one()

        self.assertEqual(delivered_view, delivered_source)
        self.assertEqual(live_sellers, snapshot_sellers)

    def test_monthly_procedure_is_idempotent(self):

        month = date(2017, 1, 1)

        with self.engine.connect() as conn:

            transaction = conn.begin()

            try:
                counts = []

                for _ in range(2):

                    conn.execute(
                        text("""
                            CALL olist.refresh_monthly_sales(
                                CAST(:month AS date)
                            )
                        """),
                        {"month": month},
                    )

                    count = conn.scalar(
                        text("""
                            SELECT COUNT(*)
                            FROM olist.monthly_sales_cache
                            WHERE sales_month = :month
                        """),
                        {"month": month},
                    )

                    counts.append(count)

                self.assertEqual(counts[0], counts[1])
                self.assertGreater(counts[0], 0)

            finally:
                transaction.rollback()

    def test_monthly_procedure_rejects_null_month(self):

        with self.engine.connect() as conn:

            transaction = conn.begin()

            before = conn.scalar(
                text("""
                    SELECT COUNT(*)
                    FROM olist.monthly_sales_cache
                    WHERE sales_month = DATE '2017-01-01'
                """)
            )

            try:
                with self.assertRaises(DBAPIError):

                    conn.execute(
                        text("""
                            CALL olist.refresh_monthly_sales(
                                CAST(:month AS date)
                            )
                        """),
                        {"month": None},
                    )

            finally:
                transaction.rollback()

        with self.engine.connect() as conn:

            after = conn.scalar(
                text("""
                    SELECT COUNT(*)
                    FROM olist.monthly_sales_cache
                    WHERE sales_month = DATE '2017-01-01'
                """)
            )

        self.assertEqual(before, after)

    def test_delivery_delay_query_on_controlled_data(self):

        query = text("""
            WITH sample_orders (
                order_id,
                customer_state,
                order_month,
                delivered_at,
                estimated_at
            ) AS (
                VALUES
                (
                    'A', 'SP', DATE '2024-01-01',
                    TIMESTAMP '2024-01-05 00:00:00',
                    TIMESTAMP '2024-01-04 00:00:00'
                ),
                (
                    'B', 'SP', DATE '2024-01-01',
                    TIMESTAMP '2024-01-04 00:00:00',
                    TIMESTAMP '2024-01-04 00:00:00'
                ),
                (
                    'C', 'RJ', DATE '2024-01-01',
                    TIMESTAMP '2024-01-03 00:00:00',
                    TIMESTAMP '2024-01-04 00:00:00'
                )
            )

            SELECT
                customer_state,
                order_month,
                COUNT(*) AS total_orders,
                COUNT(*) FILTER (
                    WHERE delivered_at > estimated_at
                ) AS delayed_orders,
                ROUND(
                    100.0 * COUNT(*) FILTER (
                        WHERE delivered_at > estimated_at
                    ) / COUNT(*),
                    2
                ) AS delayed_percentage

            FROM sample_orders

            GROUP BY customer_state, order_month
            ORDER BY customer_state
        """)

        with self.engine.connect() as conn:
            rows = conn.execute(query).all()

        actual = [
            (
                row.customer_state,
                row.order_month,
                row.total_orders,
                row.delayed_orders,
                float(row.delayed_percentage),
            )
            for row in rows
        ]

        expected = [
            ("RJ", date(2024, 1, 1), 1, 0, 0.0),
            ("SP", date(2024, 1, 1), 2, 1, 50.0),
        ]

        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
