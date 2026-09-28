import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "library.db"

    def run_cli(self, *args, ok=True):
        result = subprocess.run(
            [sys.executable, str(ROOT / "book_tracker.py"), "--db", str(self.db), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr)
        return result

    def test_loan_return_and_persistence(self):
        self.run_cli("add", "Учебная книга")
        self.run_cli("lend", "1", "Читатель А")
        rows = json.loads(self.run_cli("list").stdout)
        self.assertEqual(rows, [{"id": 1, "title": "Учебная книга", "borrower": "Читатель А"}])
        self.run_cli("return", "1")
        self.assertIsNone(json.loads(self.run_cli("list").stdout)[0]["borrower"])
        history = json.loads(self.run_cli("history", "1").stdout)
        self.assertEqual(
            [(r["action"], r["borrower"]) for r in history],
            [("lend", "Читатель А"), ("return", "Читатель А")],
        )

    def test_second_loan_does_not_overwrite_borrower_or_history(self):
        self.run_cli("add", "Учебная книга")
        self.run_cli("lend", "1", "Читатель А")
        self.run_cli("lend", "1", "Читатель Б", ok=False)
        self.assertEqual(json.loads(self.run_cli("list").stdout)[0]["borrower"], "Читатель А")
        self.assertEqual(len(json.loads(self.run_cli("history", "1").stdout)), 1)

    def test_invalid_operations_leave_no_events(self):
        self.run_cli("add", "   ", ok=False)
        self.run_cli("add", "Учебная книга")
        self.run_cli("lend", "1", "   ", ok=False)
        self.run_cli("lend", "99", "Читатель А", ok=False)
        self.run_cli("return", "1", ok=False)
        self.run_cli("return", "99", ok=False)
        self.run_cli("history", "99", ok=False)
        self.assertEqual(json.loads(self.run_cli("history", "1").stdout), [])
        self.assertIsNone(json.loads(self.run_cli("list").stdout)[0]["borrower"])

    def test_event_write_failure_rolls_back_loan(self):
        self.run_cli("add", "Учебная книга")
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("""CREATE TRIGGER reject_event BEFORE INSERT ON events
                          BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        self.run_cli("lend", "1", "Читатель А", ok=False)
        self.assertIsNone(json.loads(self.run_cli("list").stdout)[0]["borrower"])

    def test_demo_is_repeatable_and_does_not_touch_selected_database(self):
        self.run_cli("add", "Моя книга")
        before = self.db.read_bytes()
        first = self.run_cli("demo").stdout
        second = self.run_cli("demo").stdout
        self.assertEqual(first, second)
        self.assertIn("Повторная выдача отклонена", first)
        self.assertIn("Книга возвращена; событий в истории: 2", first)
        self.assertEqual(self.db.read_bytes(), before)

    def test_seed_only_initializes_empty_database(self):
        self.run_cli("seed")
        first = json.loads(self.run_cli("list").stdout)
        self.assertEqual(len(first), 4)
        self.assertEqual(first[0]["borrower"], "Анна")
        self.run_cli("seed", ok=False)
        self.assertEqual(json.loads(self.run_cli("list").stdout), first)

    def test_seed_refuses_to_change_personal_data(self):
        self.run_cli("add", "Личная книга")
        self.run_cli("seed", ok=False)
        self.assertEqual(
            json.loads(self.run_cli("list").stdout),
            [{"id": 1, "title": "Личная книга", "borrower": None}],
        )


if __name__ == "__main__":
    unittest.main()
