CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    tier TEXT NOT NULL
);
INSERT INTO customers VALUES
    (1, 'ada@example.com', 'pro'),
    (2, 'grace@example.com', 'free'),
    (3, 'edsger@example.com', 'pro');
