from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import psycopg


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://telacta:telacta@localhost:5432/telacta"
)
RANDOM_SEED = 20250629


@dataclass(frozen=True)
class ProductLine:
    product_line_id: int
    name: str


@dataclass(frozen=True)
class Product:
    product_id: int
    product_line_id: int
    sku: str
    name: str
    base_price: Decimal
    base_cost: Decimal


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generate_dim_date(start: date, end: date) -> list[tuple[int, date, int, int, int, int]]:
    rows = []
    current = start
    while current <= end:
        rows.append(
            (
                int(current.strftime("%Y%m%d")),
                current,
                current.year,
                current.month,
                current.isocalendar().week,
                current.day,
            )
        )
        current += timedelta(days=1)
    return rows


def create_schema(cur: psycopg.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_date (
            date_id INTEGER PRIMARY KEY,
            full_date DATE NOT NULL UNIQUE,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            week INTEGER NOT NULL,
            day INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dim_region (
            region_id INTEGER PRIMARY KEY,
            region_name TEXT NOT NULL,
            country TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dim_retailer (
            retailer_id INTEGER PRIMARY KEY,
            retailer_name TEXT NOT NULL,
            retailer_type TEXT NOT NULL,
            region_id INTEGER NOT NULL REFERENCES dim_region(region_id)
        );

        CREATE TABLE IF NOT EXISTS dim_product_line (
            product_line_id INTEGER PRIMARY KEY,
            product_line_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS dim_product (
            product_id INTEGER PRIMARY KEY,
            product_line_id INTEGER NOT NULL REFERENCES dim_product_line(product_line_id),
            sku TEXT NOT NULL UNIQUE,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            base_price NUMERIC(12, 2) NOT NULL,
            base_cost NUMERIC(12, 2) NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dim_order_method (
            order_method_id INTEGER PRIMARY KEY,
            order_method_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS fact_sales (
            sales_id BIGSERIAL PRIMARY KEY,
            order_id TEXT NOT NULL,
            order_line_number INTEGER NOT NULL,
            order_date DATE NOT NULL,
            date_id INTEGER NOT NULL REFERENCES dim_date(date_id),
            product_id INTEGER NOT NULL REFERENCES dim_product(product_id),
            retailer_id INTEGER NOT NULL REFERENCES dim_retailer(retailer_id),
            region_id INTEGER NOT NULL REFERENCES dim_region(region_id),
            order_method_id INTEGER NOT NULL REFERENCES dim_order_method(order_method_id),
            quantity INTEGER NOT NULL,
            unit_price NUMERIC(12, 2) NOT NULL,
            revenue NUMERIC(12, 2) NOT NULL,
            cost NUMERIC(12, 2) NOT NULL,
            gross_profit NUMERIC(12, 2) NOT NULL
        );
        """
    )


def truncate_tables(cur: psycopg.Cursor) -> None:
    cur.execute(
        """
        TRUNCATE TABLE
            fact_sales,
            dim_product,
            dim_product_line,
            dim_retailer,
            dim_region,
            dim_order_method,
            dim_date
        RESTART IDENTITY CASCADE;
        """
    )


def build_dimensions() -> tuple[
    list[tuple[int, str, str]],
    list[tuple[int, str, str, int]],
    list[tuple[int, str]],
    list[Product],
    list[tuple[int, str]],
]:
    regions = [
        (1, "Hokkaido", "Japan"),
        (2, "Kanto", "Japan"),
        (3, "Kansai", "Japan"),
        (4, "California", "United States"),
        (5, "Colorado", "United States"),
        (6, "British Columbia", "Canada"),
    ]

    retailers = [
        (1, "Trailhead Sapporo", "Flagship Store", 1),
        (2, "Summit Tokyo", "Urban Store", 2),
        (3, "Camp Base Osaka", "Outlet Store", 3),
        (4, "Pacific Ridge SF", "Flagship Store", 4),
        (5, "Alpine Denver", "Partner Store", 5),
        (6, "North Shore Vancouver", "Urban Store", 6),
    ]

    product_lines = [
        ProductLine(1, "Camping Equipment"),
        ProductLine(2, "Mountaineering Equipment"),
        ProductLine(3, "Outdoor Protection"),
        ProductLine(4, "Personal Accessories"),
        ProductLine(5, "Golf Equipment"),
    ]

    products = [
        Product(1, 1, "CMP-TENT-001", "North Peak Tent", money(320), money(190)),
        Product(2, 1, "CMP-BAG-001", "Aurora Sleeping Bag", money(180), money(108)),
        Product(3, 1, "CMP-STV-001", "Trail Mini Stove", money(95), money(54)),
        Product(4, 2, "MNT-BOOT-001", "Granite Climb Boots", money(210), money(132)),
        Product(5, 2, "MNT-ROPE-001", "Ascent Dynamic Rope", money(260), money(166)),
        Product(6, 2, "MNT-AXE-001", "Ridge Ice Axe", money(145), money(89)),
        Product(7, 3, "PRT-JKT-001", "Storm Guard Jacket", money(240), money(150)),
        Product(8, 3, "PRT-GLV-001", "Thermal Grip Gloves", money(65), money(34)),
        Product(9, 4, "ACC-BTL-001", "Insulated Trail Bottle", money(38), money(16)),
        Product(10, 4, "ACC-LMP-001", "Camp Lantern Pro", money(82), money(43)),
        Product(11, 5, "GLF-SET-001", "Range Iron Set", money(510), money(352)),
        Product(12, 5, "GLF-BAG-001", "Fairway Carry Bag", money(199), money(126)),
    ]

    order_methods = [
        (1, "Online"),
        (2, "Retail Store"),
        (3, "Phone"),
        (4, "Distributor"),
    ]

    return (
        regions,
        retailers,
        [(line.product_line_id, line.name) for line in product_lines],
        products,
        order_methods,
    )


def weighted_choice(rand: random.Random, items: list[tuple[object, int]]) -> object:
    values = [item for item, _ in items]
    weights = [weight for _, weight in items]
    return rand.choices(values, weights=weights, k=1)[0]


def generate_fact_sales(
    products: list[Product],
    retailers: list[tuple[int, str, str, int]],
    order_methods: list[tuple[int, str]],
) -> list[
    tuple[str, int, date, int, int, int, int, int, int, Decimal, Decimal, Decimal, Decimal]
]:
    rand = random.Random(RANDOM_SEED)
    start = date(2024, 1, 1)
    end = date(2025, 12, 31)
    day_count = (end - start).days + 1
    orders = 3200
    rows = []

    product_weights = [
        (products[0], 8),
        (products[1], 7),
        (products[2], 9),
        (products[3], 6),
        (products[4], 4),
        (products[5], 5),
        (products[6], 6),
        (products[7], 10),
        (products[8], 11),
        (products[9], 8),
        (products[10], 3),
        (products[11], 4),
    ]
    retailer_weights = [(retailer, 5 if retailer[2] != "Partner Store" else 3) for retailer in retailers]
    method_weights = [
        (1, 45),
        (2, 35),
        (3, 10),
        (4, 10),
    ]

    for order_number in range(1, orders + 1):
        order_date = start + timedelta(days=rand.randrange(day_count))
        order_id = f"ORD-{order_date:%Y%m%d}-{order_number:05d}"
        line_count = rand.randint(1, 4)

        for line_number in range(1, line_count + 1):
            product = weighted_choice(rand, product_weights)
            retailer = weighted_choice(rand, retailer_weights)
            order_method_id = weighted_choice(rand, method_weights)

            seasonal_multiplier = 1.0
            if product.product_line_id in {1, 2} and order_date.month in {5, 6, 7, 8}:
                seasonal_multiplier = 1.12
            if product.product_line_id == 5 and order_date.month in {3, 4, 5, 9, 10}:
                seasonal_multiplier = 1.08
            if product.product_line_id == 3 and order_date.month in {11, 12, 1, 2}:
                seasonal_multiplier = 1.1

            unit_price = money(float(product.base_price) * rand.uniform(0.93, 1.18) * seasonal_multiplier)
            quantity = rand.randint(1, 5 if product.product_line_id != 5 else 2)
            revenue = money(float(unit_price) * quantity)
            cost = money(float(product.base_cost) * quantity * rand.uniform(0.97, 1.05))
            gross_profit = money(float(revenue - cost))

            rows.append(
                (
                    order_id,
                    line_number,
                    order_date,
                    int(order_date.strftime("%Y%m%d")),
                    product.product_id,
                    retailer[0],
                    retailer[3],
                    order_method_id,
                    quantity,
                    unit_price,
                    revenue,
                    cost,
                    gross_profit,
                )
            )

    return rows


def insert_dimensions(cur: psycopg.Cursor) -> tuple[list[Product], list[tuple[int, str, str, int]], list[tuple[int, str]]]:
    regions, retailers, product_lines, products, order_methods = build_dimensions()
    dim_date_rows = generate_dim_date(date(2024, 1, 1), date(2026, 12, 31))

    cur.executemany(
        "INSERT INTO dim_date (date_id, full_date, year, month, week, day) VALUES (%s, %s, %s, %s, %s, %s)",
        dim_date_rows,
    )
    cur.executemany(
        "INSERT INTO dim_region (region_id, region_name, country) VALUES (%s, %s, %s)",
        regions,
    )
    cur.executemany(
        "INSERT INTO dim_retailer (retailer_id, retailer_name, retailer_type, region_id) VALUES (%s, %s, %s, %s)",
        retailers,
    )
    cur.executemany(
        "INSERT INTO dim_product_line (product_line_id, product_line_name) VALUES (%s, %s)",
        product_lines,
    )
    cur.executemany(
        """
        INSERT INTO dim_product (
            product_id,
            product_line_id,
            sku,
            product_name,
            category,
            base_price,
            base_cost
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                product.product_id,
                product.product_line_id,
                product.sku,
                product.name,
                product.name.split()[-1],
                product.base_price,
                product.base_cost,
            )
            for product in products
        ],
    )
    cur.executemany(
        "INSERT INTO dim_order_method (order_method_id, order_method_name) VALUES (%s, %s)",
        order_methods,
    )

    return products, retailers, order_methods


def insert_fact_sales(cur: psycopg.Cursor, products: list[Product], retailers, order_methods) -> int:
    rows = generate_fact_sales(products, retailers, order_methods)
    cur.executemany(
        """
        INSERT INTO fact_sales (
            order_id,
            order_line_number,
            order_date,
            date_id,
            product_id,
            retailer_id,
            region_id,
            order_method_id,
            quantity,
            unit_price,
            revenue,
            cost,
            gross_profit
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    return len(rows)


def main() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            create_schema(cur)
            truncate_tables(cur)
            products, retailers, order_methods = insert_dimensions(cur)
            fact_count = insert_fact_sales(cur, products, retailers, order_methods)
        conn.commit()

    print(f"Seed completed. Inserted {fact_count} fact rows into fact_sales.")


if __name__ == "__main__":
    main()
