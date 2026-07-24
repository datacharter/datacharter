CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    kind VARCHAR(32) NOT NULL
);
INSERT INTO events VALUES
    (1, 1, 'login'),
    (2, 1, 'query'),
    (3, 2, 'login'),
    (4, 3, 'export');
