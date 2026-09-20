CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    borrower TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    book_id INTEGER NOT NULL REFERENCES books(id),
    action TEXT NOT NULL CHECK(action IN ('lend', 'return')),
    borrower TEXT NOT NULL
);
