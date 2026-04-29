# 06 — PostgreSQL & Data Modelling

## Table of Contents

1. [What is a Relational Database?](#1-what-is-a-relational-database)
2. [Why PostgreSQL?](#2-why-postgresql)
3. [Core SQL Concepts](#3-core-sql-concepts)
4. [Schema Design Principles](#4-schema-design-principles)
5. [The Retail Data Model](#5-the-retail-data-model)
6. [Entity-Relationship Diagram](#6-entity-relationship-diagram)
7. [The init.sql File](#7-the-initsql-file)
8. [Common Query Patterns](#8-common-query-patterns)
9. [PostgreSQL-Specific Features We Use](#9-postgresql-specific-features-we-use)

---

## 1. What is a Relational Database?

A **relational database** stores data in tables. Each table has:

- **Rows** (also called records or tuples) — one entry per entity instance
- **Columns** (also called fields or attributes) — one property per column
- **Primary key** — a column (or combination) that uniquely identifies each row

Tables relate to each other through **foreign keys** — a column in one table that
references the primary key of another.

### Why "Relational"?

The name comes from the mathematical concept of a **relation** — a set of tuples
with named attributes. In practice, it means the data is organised into tables and
tables are connected through shared keys.

```
customers table          orders table
─────────────────        ─────────────────────────
id  name    region       id  customer_id  status
─────────────────        ─────────────────────────
1   Alice   North        1   3            delivered
2   Bob     South        2   1            pending
3   Carol   East         3   1            shipped
```

The `orders.customer_id` column references `customers.id`. This is how we know that
order #1 belongs to Carol (customer 3) and orders #2 and #3 belong to Alice (customer 1).

### Relational vs Non-Relational

| Relational (SQL) | Non-Relational (NoSQL) |
|---|---|
| Tables with fixed schema | Documents, key-value, graphs, etc. |
| Strong consistency | Often eventual consistency |
| ACID transactions | Variable (depends on system) |
| SQL query language | Varies by system |
| Best for structured, related data | Best for flexible or high-scale data |
| PostgreSQL, MySQL, SQLite | MongoDB, Redis, Cassandra |

For business analytics on structured data with relationships, relational databases
are still the dominant choice.

---

## 2. Why PostgreSQL?

PostgreSQL (often called "Postgres") is an open-source relational database with
30+ years of development. It is the most feature-rich free SQL database available.

### Why We Chose It

1. **Industry standard for analytics** — widely used in production, well understood
2. **Rich SQL dialect** — CTEs, window functions, JSON support, full-text search
3. **Excellent LLM familiarity** — Llama and other models have seen enormous amounts
   of PostgreSQL syntax in their training data
4. **Official Docker image** — `postgres:16-alpine` just works
5. **LangChain native support** — `postgresql+psycopg2` dialect is well-tested

### PostgreSQL vs SQLite

SQLite is simpler and requires no server. We chose PostgreSQL because:

- It matches what real production systems use (the learning value is higher)
- It requires Docker, which is the point of the exercise
- It has a richer SQL dialect (more realistic queries)
- LangChain's SQL agent was built primarily for server-based databases

---

## 3. Core SQL Concepts

### SELECT — Reading Data

```sql
SELECT column1, column2
FROM table_name
WHERE condition
ORDER BY column1 DESC
LIMIT 10;
```

- `SELECT` — which columns to return
- `FROM` — which table to read
- `WHERE` — filter rows (optional)
- `ORDER BY` — sort the results (optional)
- `LIMIT` — cap the number of rows returned (optional)

### JOIN — Combining Tables

JOINs let you query multiple tables at once by matching rows on shared keys.

```sql
SELECT customers.name, orders.status
FROM orders
INNER JOIN customers ON orders.customer_id = customers.id;
```

**Types of JOINs:**

```
Table A    Table B
────────   ────────
1          1
2          2
3          (no match)
           4 (no match)

INNER JOIN: rows with matches in BOTH tables → 1, 2
LEFT JOIN:  all rows from A + matches from B → 1, 2, 3 (3 has NULL for B columns)
RIGHT JOIN: all rows from B + matches from A → 1, 2, 4 (4 has NULL for A columns)
FULL JOIN:  all rows from both → 1, 2, 3, 4
```

For our queries, we almost always use `INNER JOIN` because we only want orders that
have matching customers and products.

### Aggregate Functions

Aggregate functions compute a single value from a group of rows.

```sql
SELECT
    COUNT(*)                          AS total_orders,
    SUM(quantity)                     AS total_units,
    AVG(unit_price)                   AS avg_price,
    MAX(ordered_at)                   AS most_recent,
    MIN(ordered_at)                   AS earliest
FROM order_items
JOIN orders ON order_items.order_id = orders.id
WHERE orders.status != 'cancelled';
```

### GROUP BY — Aggregating by Category

`GROUP BY` splits rows into groups before applying aggregate functions.

```sql
-- Revenue by product category
SELECT
    products.category,
    SUM(order_items.quantity * order_items.unit_price) AS revenue
FROM order_items
JOIN orders   ON order_items.order_id   = orders.id
JOIN products ON order_items.product_id = products.id
WHERE orders.status != 'cancelled'
GROUP BY products.category
ORDER BY revenue DESC;
```

**Rule:** Any column in `SELECT` that is not inside an aggregate function must appear
in `GROUP BY`.

### WHERE vs HAVING

```sql
-- WHERE filters rows BEFORE aggregation
-- HAVING filters groups AFTER aggregation

SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE status != 'cancelled'     -- filter individual rows first
GROUP BY customer_id
HAVING COUNT(*) > 3;            -- then filter groups with fewer than 3 orders
```

### CTEs — Common Table Expressions

CTEs (introduced with `WITH`) let you name a subquery and reference it later.
They improve readability for complex queries.

```sql
WITH monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', ordered_at) AS month,
        SUM(oi.quantity * oi.unit_price) AS revenue
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    WHERE o.status != 'cancelled'
    GROUP BY DATE_TRUNC('month', ordered_at)
)
SELECT month, revenue
FROM monthly_revenue
ORDER BY month DESC
LIMIT 6;
```

CTEs are especially important for the SQL agent — it often generates CTEs to break
complex queries into readable steps.

---

## 4. Schema Design Principles

### Normalisation

**Normalisation** is the process of organising data to reduce redundancy. The goal
is to store each piece of information in exactly one place.

**Unnormalised (bad):**
```
orders
──────────────────────────────────────────────────
order_id  customer_name  customer_email  product_name  price  qty
1         Alice          alice@co.com    Laptop         999    1
2         Alice          alice@co.com    Mouse          29     2
3         Bob            bob@co.com      Keyboard       79     1
```

Problems: if Alice changes her email, we must update multiple rows. If we delete all
of Bob's orders, we lose his contact info.

**Normalised (good):**
```
customers: id=1 name=Alice email=alice@co.com
           id=2 name=Bob   email=bob@co.com

products:  id=1 name=Laptop   price=999
           id=2 name=Mouse    price=29
           id=3 name=Keyboard price=79

orders: id=1 customer_id=1
        id=2 customer_id=1
        id=3 customer_id=2

order_items: order_id=1 product_id=1 qty=1 unit_price=999
             order_id=2 product_id=2 qty=2 unit_price=29
             order_id=3 product_id=3 qty=1 unit_price=79
```

Each fact is in one place. Changing Alice's email updates exactly one row.

### Primary Keys

Every table has a **primary key** — a column that uniquely identifies each row.

```sql
CREATE TABLE customers (
    id         SERIAL PRIMARY KEY,   -- auto-incrementing integer
    name       TEXT NOT NULL,
    ...
);
```

`SERIAL` is PostgreSQL shorthand for "auto-incrementing integer". Each new row gets
the next available integer automatically.

### Foreign Keys

**Foreign keys** enforce referential integrity — they prevent orphaned records.

```sql
CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),  -- foreign key
    ...
);
```

With this constraint, you cannot insert an order with `customer_id=999` if customer
999 does not exist. The database enforces consistency.

### NOT NULL Constraints

Columns marked `NOT NULL` cannot be left empty. This prevents "accidental null" bugs.

```sql
name  TEXT NOT NULL,   -- name is required
email TEXT NOT NULL    -- email is required
```

---

## 5. The Retail Data Model

Our database has four tables modelling a simplified e-commerce operation.

### customers

```sql
CREATE TABLE customers (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    region     TEXT NOT NULL,        -- 'North', 'South', 'East', 'West'
    created_at TIMESTAMP DEFAULT NOW()
);
```

Represents people who have registered on the platform. The `region` field is used
for geographic breakdowns. `created_at` allows cohort analysis (new vs old customers).

### products

```sql
CREATE TABLE products (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,   -- e.g. 'Electronics', 'Stationery'
    price    NUMERIC(10,2) NOT NULL
);
```

The product catalogue. `price` here is the list price — the actual price charged at
order time is stored in `order_items.unit_price`. This distinction matters: if a
product's price changes, historical orders should reflect what was charged, not the
current price.

### orders

```sql
CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    status      TEXT NOT NULL DEFAULT 'pending',
    ordered_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
```

One row per order. An order can have multiple items (stored in `order_items`).

`status` is an enum-like text field with four valid values:
- `pending` — order placed, not yet shipped
- `shipped` — dispatched, in transit
- `delivered` — received by customer
- `cancelled` — order was cancelled (important: excluded from sales figures)

### order_items

```sql
CREATE TABLE order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL
);
```

The "line items" of each order. One row per product per order. If an order contains
three different products, there are three rows in `order_items`.

`unit_price` records the price at the time of purchase — essential for accurate
historical revenue calculation.

---

## 6. Entity-Relationship Diagram

```
customers               orders                  order_items             products
─────────────           ───────────────         ───────────────         ────────────
id (PK)  ◄──────────┐   id (PK)  ◄──────────┐  id (PK)                 id (PK)
name                 └── customer_id (FK)     └─ order_id (FK)   ┌────► id (PK)
email                    status                  product_id (FK) ─┘      name
region                   ordered_at              quantity                category
created_at                                       unit_price              price
```

### Reading the Diagram

- Each `customer` can have many `orders` (one-to-many)
- Each `order` can have many `order_items` (one-to-many)
- Each `product` can appear in many `order_items` (one-to-many)
- `order_items` is a **junction table** connecting `orders` and `products`
  (many-to-many relationship resolved into two one-to-many relationships)

### Why a Junction Table?

An order can contain multiple products. A product can appear in multiple orders.
This is a **many-to-many** relationship. Relational databases represent this with
a junction (bridge) table:

```
orders ←── order_items ──► products
```

Without the junction table, you would need to store multiple product IDs in a single
order row — violating normalisation and making queries very difficult.

---

## 7. The init.sql File

The `postgres/init.sql` file runs automatically when the PostgreSQL container starts
for the first time. It creates the schema and seeds data.

### Schema Creation

```sql
CREATE TABLE customers (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    region     TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE products (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,
    price    NUMERIC(10,2) NOT NULL
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    status      TEXT NOT NULL DEFAULT 'pending',
    ordered_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL
);
```

### Seed Data

The seed data includes a deliberately **cancelled order** — Frank Lee ordering
Ballpoint Pens. This is used to verify that the business rule "exclude cancelled orders"
is working correctly. If a query returns 5 units for Ballpoint Pens, the cancelled
order is being wrongly included.

```sql
-- Frank Lee's order is cancelled
INSERT INTO orders (customer_id, status, ordered_at)
VALUES (10, 'cancelled', NOW() - INTERVAL '5 days');

-- 5 Ballpoint Pens on the cancelled order
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (11, 7, 5, 1.99);
```

### Why Seed Data Matters

Testing with realistic, edge-case data catches bugs that pass simple tests. The
cancelled order exists specifically to verify correctness, not just to fill rows.

---

## 8. Common Query Patterns

These are the query patterns our SQL agent generates most frequently.

### Top N by Volume

```sql
SELECT p.name, SUM(oi.quantity) AS units_sold
FROM order_items oi
JOIN orders   o ON oi.order_id   = o.id
JOIN products p ON oi.product_id = p.id
WHERE o.status != 'cancelled'
GROUP BY p.name
ORDER BY units_sold DESC
LIMIT 5;
```

### Revenue by Category

```sql
SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue
FROM order_items oi
JOIN orders   o ON oi.order_id   = o.id
JOIN products p ON oi.product_id = p.id
WHERE o.status != 'cancelled'
GROUP BY p.category
ORDER BY revenue DESC;
```

### Date Range Filter

```sql
-- Last 30 days
WHERE o.ordered_at >= NOW() - INTERVAL '30 days'

-- Last 7 days
WHERE o.ordered_at >= NOW() - INTERVAL '7 days'

-- Yesterday
WHERE DATE(o.ordered_at) = CURRENT_DATE - 1
```

### Customers with No Orders (Inactive)

```sql
SELECT c.name, c.email
FROM customers c
LEFT JOIN orders o ON c.id = o.customer_id
WHERE o.id IS NULL
   OR o.ordered_at < NOW() - INTERVAL '90 days';
```

### Orders by Region

```sql
SELECT c.region, COUNT(DISTINCT o.id) AS order_count
FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE o.status != 'cancelled'
GROUP BY c.region
ORDER BY order_count DESC;
```

---

## 9. PostgreSQL-Specific Features We Use

### NUMERIC(10,2) for Money

```sql
price NUMERIC(10,2)   -- up to 10 digits total, 2 decimal places
```

Never use `FLOAT` for money. Floating point arithmetic has rounding errors.
`NUMERIC` is exact decimal arithmetic — 1.10 + 2.20 = 3.30, always.

### SERIAL for Auto-increment IDs

```sql
id SERIAL PRIMARY KEY
```

`SERIAL` is PostgreSQL shorthand for:
```sql
id INTEGER NOT NULL DEFAULT nextval('table_id_seq')
```

It creates a sequence object and uses it to generate unique IDs automatically.

### TIMESTAMP and Date Arithmetic

PostgreSQL has rich date/time support:

```sql
NOW()                          -- current timestamp with time zone
CURRENT_DATE                   -- today's date (no time)
NOW() - INTERVAL '30 days'     -- 30 days ago
DATE_TRUNC('month', timestamp) -- round down to start of month
EXTRACT(YEAR FROM timestamp)   -- extract year component
```

### DEFAULT Values

```sql
status     TEXT      NOT NULL DEFAULT 'pending',
ordered_at TIMESTAMP NOT NULL DEFAULT NOW(),
created_at TIMESTAMP          DEFAULT NOW()
```

`DEFAULT` values are applied when `INSERT` omits the column. This simplifies
application code — you don't need to explicitly set `ordered_at` on every insert.

### UNIQUE Constraint

```sql
email TEXT NOT NULL UNIQUE
```

`UNIQUE` creates an index and prevents duplicate values in that column. Attempting
to insert two customers with the same email will fail with a constraint violation.
