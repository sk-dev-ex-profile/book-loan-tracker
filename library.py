"""Общие операции с книгами для CLI и веб-интерфейса."""

import sqlite3
from pathlib import Path


class BookNotFound(ValueError):
    """Экземпляр не существует."""


class InvalidInput(ValueError):
    """Некорректные входные данные."""


SCHEMA = Path(__file__).parent / "migrations" / "001_initial.sql"


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    except Exception:
        conn.close()
        raise
    return conn


def nonempty(value, label, limit):
    value = value.strip()
    if not value:
        raise InvalidInput(f"{label} не может быть пустым")
    if len(value) > limit:
        raise InvalidInput(f"{label}: не больше {limit} символов")
    return value


def book(conn, book_id):
    if not 1 <= book_id <= 2**63 - 1:
        raise BookNotFound("Книга не найдена")
    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise BookNotFound("Книга не найдена")
    return row


def add(conn, title):
    title = nonempty(title, "Название", 200)
    with conn:
        cursor = conn.execute("INSERT INTO books(title) VALUES (?)", (title,))
    return cursor.lastrowid


def lend(conn, book_id, borrower):
    borrower = nonempty(borrower, "Имя читателя", 100)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = book(conn, book_id)
        if row["borrower"] is not None:
            raise ValueError("Книга уже выдана")
        conn.execute("UPDATE books SET borrower = ? WHERE id = ?", (borrower, book_id))
        conn.execute(
            "INSERT INTO events(book_id, action, borrower) VALUES (?, 'lend', ?)",
            (book_id, borrower),
        )


def give_back(conn, book_id, expected_loan_id=None):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = book(conn, book_id)
        if row["borrower"] is None:
            raise ValueError("Книга уже на полке")
        if expected_loan_id is not None:
            latest = conn.execute(
                "SELECT id FROM events WHERE book_id = ? ORDER BY id DESC LIMIT 1", (book_id,)
            ).fetchone()
            if latest is None or latest["id"] != expected_loan_id:
                raise ValueError(
                    "Выдача изменилась. Проверьте текущего читателя и повторите возврат."
                )
        conn.execute("UPDATE books SET borrower = NULL WHERE id = ?", (book_id,))
        conn.execute(
            "INSERT INTO events(book_id, action, borrower) VALUES (?, 'return', ?)",
            (book_id, row["borrower"]),
        )


def history(conn, book_id):
    book(conn, book_id)
    return [
        dict(row)
        for row in conn.execute(
            "SELECT id, action, borrower FROM events WHERE book_id = ? ORDER BY id", (book_id,)
        )
    ]


def all_books(conn):
    return [dict(row) for row in conn.execute("SELECT * FROM books ORDER BY id")]


def seed_demo(conn):
    """Заполнить только пустую базу; существующие книги не менять."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]:
            raise ValueError("База не пустая: учебные данные не добавлены")
        conn.executemany(
            "INSERT INTO books (id, title, borrower) VALUES (?, ?, ?)",
            [
                (1, "Путешествие к морю", "Анна"),
                (2, "Город за рекой", None),
                (3, "Истории старого дома", "Михаил"),
                (4, "Сад на подоконнике", None),
            ],
        )
        conn.executemany(
            "INSERT INTO events (book_id, action, borrower) VALUES (?, ?, ?)",
            [
                (1, "lend", "Михаил"),
                (1, "return", "Михаил"),
                (1, "lend", "Анна"),
                (3, "lend", "Михаил"),
                (4, "lend", "Анна"),
                (4, "return", "Анна"),
            ],
        )
