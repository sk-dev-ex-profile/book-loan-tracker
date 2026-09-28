import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from web import create_app


class WebTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "book-tracker.db"
        self.app = create_app(
            {"TESTING": True, "DATABASE": str(self.db), "SECRET_KEY": "test-only"}
        )
        self.client = self.app.test_client()

    def token(self):
        self.client.get("/?view=add")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def post(self, url, **data):
        return self.client.post(
            url, data={"csrf_token": self.token(), **data}, follow_redirects=True
        )

    def rows(self, table):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            return conn.execute(f"SELECT * FROM {table}").fetchall()

    def test_empty_shelf_and_add(self):
        response = self.client.get("/")
        self.assertIn("На полке пока нет книг", response.text)
        self.assertEqual(self.post("/books", title="Учебная книга").status_code, 200)
        self.assertEqual(self.rows("books"), [(1, "Учебная книга", None)])

    def test_loan_return_and_history(self):
        self.post("/books", title="Книга")
        self.post("/books/1/lend", borrower="Анна")
        self.assertEqual(self.rows("books")[0][2], "Анна")
        # GET подтверждения ничего не меняет.
        response = self.client.get("/?book=1&view=return")
        self.assertIn("Да, отметить возврат", response.text)
        self.assertEqual(self.rows("books")[0][2], "Анна")
        self.assertEqual(self.post("/books/1/return", loan_id="1").status_code, 200)
        self.assertIsNone(self.rows("books")[0][2])
        self.assertEqual([r[2] for r in self.rows("events")], ["lend", "return"])

    def test_stale_loan_is_conflict_without_mutation(self):
        self.post("/books", title="Книга")
        self.post("/books/1/lend", borrower="Анна")
        response = self.post("/books/1/lend", borrower="Михаил")
        self.assertEqual(response.status_code, 409)
        self.assertIn("Книга уже выдана", response.text)
        self.assertEqual(self.rows("books")[0][2], "Анна")
        self.assertEqual(len(self.rows("events")), 1)

    def test_stale_return_is_conflict(self):
        self.post("/books", title="Книга")
        self.assertEqual(self.post("/books/1/return", loan_id="1").status_code, 409)
        self.assertEqual(self.rows("events"), [])

    def test_return_confirmation_cannot_return_a_newer_loan(self):
        self.post("/books", title="Книга")
        self.post("/books/1/lend", borrower="Анна")
        self.client.get("/?book=1&view=return")
        self.post("/books/1/return", loan_id="1")
        self.post("/books/1/lend", borrower="Борис")
        response = self.post("/books/1/return", loan_id="1")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.rows("books")[0][2], "Борис")
        self.assertEqual(len(self.rows("events")), 3)

    def test_book_ids_outside_sqlite_range_are_not_found(self):
        huge = 2**63
        self.assertEqual(self.client.get(f"/?book={huge}").status_code, 404)
        self.assertEqual(self.post(f"/books/{huge}/lend", borrower="Анна").status_code, 404)
        self.assertEqual(self.post(f"/books/{huge}/return", loan_id="1").status_code, 404)

    def test_invalid_input_keeps_database_unchanged(self):
        for value in ("   ", "к" * 201):
            with self.subTest(value=value):
                self.assertEqual(self.post("/books", title=value).status_code, 400)
        self.assertEqual(self.rows("books"), [])
        self.post("/books", title="Книга")
        for value in ("   ", "а" * 101):
            self.assertEqual(self.post("/books/1/lend", borrower=value).status_code, 400)
        self.assertIsNone(self.rows("books")[0][2])

        self.post("/books/1/lend", borrower="Анна")
        for value in ("", "not-a-number"):
            self.assertEqual(self.post("/books/1/return", loan_id=value).status_code, 400)
        self.assertEqual(self.rows("books")[0][2], "Анна")

    def test_missing_book_returns_not_found(self):
        self.assertEqual(self.client.get("/?book=999").status_code, 404)
        self.assertEqual(self.post("/books/999/lend", borrower="Анна").status_code, 404)
        self.assertEqual(self.post("/books/999/return").status_code, 404)

    def test_csrf_is_required_and_bound_to_session(self):
        self.client.get("/")
        self.assertEqual(self.client.post("/books", data={"title": "Книга"}).status_code, 400)
        other = self.app.test_client()
        response = other.post("/books", data={"title": "Книга", "csrf_token": self.token()})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows("books"), [])
        self.assertEqual(self.client.post("/books", data={"csrf_token": "я"}).status_code, 400)

    def test_cli_and_web_share_changes(self):
        root = Path(__file__).resolve().parents[1]
        subprocess.run(
            [
                sys.executable,
                str(root / "book_tracker.py"),
                "--db",
                str(self.db),
                "add",
                "Книга из CLI",
            ],
            check=True,
            capture_output=True,
        )
        self.assertIn("Книга из CLI", self.client.get("/").text)
        self.post("/books/1/lend", borrower="Анна")
        result = subprocess.run(
            [sys.executable, str(root / "book_tracker.py"), "--db", str(self.db), "list"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Анна", result.stdout)

    def test_user_text_is_escaped(self):
        response = self.post("/books", title='<script>alert("x")</script>')
        self.assertNotIn('<script>alert("x")</script>', response.text)
        self.assertIn("&lt;script&gt;", response.text)

    def test_database_failure_does_not_expose_details_or_keep_partial_loan(self):
        self.post("/books", title="Книга")
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("""CREATE TRIGGER fail_event BEFORE INSERT ON events
                         BEGIN SELECT RAISE(ABORT, 'private database detail'); END""")
        with self.assertLogs(self.app.logger, level="ERROR"):
            response = self.post("/books/1/lend", borrower="Анна")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private database detail", response.text)
        self.assertIsNone(self.rows("books")[0][2])

    def test_health_and_static_styles(self):
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})
        response = self.client.get("/")
        css = re.search(r'href="([^"]+\.css)"', response.text).group(1)
        with self.client.get(css) as response:
            self.assertEqual(response.status_code, 200)
