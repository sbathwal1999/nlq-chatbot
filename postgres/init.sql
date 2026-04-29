-- init.sql — Demo schema + seed data
--
-- This script runs automatically when the PostgreSQL container starts for the
-- first time (mounted via docker-compose into /docker-entrypoint-initdb.d/).
--
-- Schema models a minimal retail dataset: customers, products, orders, order_items.
-- Designed to answer the example questions from the requirements doc.

-- -----------------------------------------------------------------------
-- Tables
-- -----------------------------------------------------------------------

CREATE TABLE customers (
    id          SERIAL PRIMARY KEY,
    name        TEXT        NOT NULL,
    email       TEXT        UNIQUE NOT NULL,
    region      TEXT        NOT NULL,          -- e.g. North, South, East, West
    created_at  TIMESTAMP   DEFAULT NOW()
);

CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        TEXT        NOT NULL,
    category    TEXT        NOT NULL,
    price       NUMERIC(10, 2) NOT NULL
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER     NOT NULL REFERENCES customers(id),
    status      TEXT        NOT NULL,          -- pending | shipped | delivered | cancelled
    ordered_at  TIMESTAMP   NOT NULL
);

CREATE TABLE order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER     NOT NULL REFERENCES orders(id),
    product_id  INTEGER     NOT NULL REFERENCES products(id),
    quantity    INTEGER     NOT NULL,
    unit_price  NUMERIC(10, 2) NOT NULL        -- snapshot of price at time of order
);

-- -----------------------------------------------------------------------
-- Seed data
-- -----------------------------------------------------------------------

INSERT INTO customers (name, email, region) VALUES
    ('Alice Martin',  'alice@example.com',  'North'),
    ('Bob Chen',      'bob@example.com',    'South'),
    ('Carol Davis',   'carol@example.com',  'East'),
    ('Dan Okafor',    'dan@example.com',    'North'),
    ('Eva Singh',     'eva@example.com',    'West'),
    ('Frank Lee',     'frank@example.com',  'South'),
    ('Grace Kim',     'grace@example.com',  'East'),
    -- Last two haven't ordered in >90 days (no orders seeded for them)
    ('Harry Brown',   'harry@example.com',  'North'),
    ('Isla White',    'isla@example.com',   'West');

INSERT INTO products (name, category, price) VALUES
    ('Wireless Mouse',      'Electronics',  29.99),
    ('Mechanical Keyboard', 'Electronics',  89.99),
    ('USB-C Hub',           'Electronics',  49.99),
    ('Desk Lamp',           'Office',       34.99),
    ('Notebook (A5)',       'Stationery',    8.99),
    ('Ballpoint Pens x10',  'Stationery',    5.49),
    ('Laptop Stand',        'Electronics',  59.99),
    ('Webcam HD',           'Electronics',  79.99);

-- Orders within the last month
INSERT INTO orders (customer_id, status, ordered_at) VALUES
    (1, 'delivered', NOW() - INTERVAL '5 days'),
    (2, 'shipped',   NOW() - INTERVAL '8 days'),
    (3, 'pending',   NOW() - INTERVAL '2 days'),
    (4, 'pending',   NOW() - INTERVAL '1 day'),
    (5, 'delivered', NOW() - INTERVAL '15 days'),
    (6, 'cancelled', NOW() - INTERVAL '20 days'),
    (7, 'pending',   NOW() - INTERVAL '3 days');

-- Older orders (2–4 months ago) — customers 1–3 ordered before, so they're active
INSERT INTO orders (customer_id, status, ordered_at) VALUES
    (1, 'delivered', NOW() - INTERVAL '60 days'),
    (2, 'delivered', NOW() - INTERVAL '75 days'),
    (3, 'delivered', NOW() - INTERVAL '50 days');

-- Order items — spread across products to make top-5 queries interesting
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1, 1, 2, 29.99),   -- Alice bought 2x Wireless Mouse
    (1, 3, 1, 49.99),   -- Alice bought 1x USB-C Hub
    (2, 2, 1, 89.99),   -- Bob bought 1x Mechanical Keyboard
    (2, 7, 1, 59.99),   -- Bob bought 1x Laptop Stand
    (3, 1, 1, 29.99),   -- Carol bought 1x Wireless Mouse
    (3, 4, 2, 34.99),   -- Carol bought 2x Desk Lamp
    (4, 8, 1, 79.99),   -- Dan bought 1x Webcam HD
    (5, 2, 2, 89.99),   -- Eva bought 2x Mechanical Keyboard
    (5, 5, 3,  8.99),   -- Eva bought 3x Notebook
    (6, 6, 5,  5.49),   -- Frank bought 5x Pens (cancelled)
    (7, 1, 3, 29.99),   -- Grace bought 3x Wireless Mouse
    (7, 3, 2, 49.99),   -- Grace bought 2x USB-C Hub
    (8, 2, 1, 89.99),
    (9, 1, 1, 29.99),
    (10, 7, 1, 59.99);
