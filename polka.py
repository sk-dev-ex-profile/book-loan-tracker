"""CLI учебного приложения «Полка»."""

import argparse
import json
import sqlite3
import sys
from contextlib import closing

from library import add, all_books, connect, give_back, history, lend, seed_demo


def demo():
    # Отдельная база в памяти: выбранный пользователем файл не открывается.
    with closing(connect(":memory:")) as conn:
        book_id = add(conn, "Учебная книга")
        print(f"Добавлена книга: {book_id}")
        lend(conn, book_id, "Читатель А")
        print("Книга выдана: Читатель А")
        try:
            lend(conn, book_id, "Читатель Б")
        except ValueError as error:
            print(f"Повторная выдача отклонена: {error}")
        else:
            raise RuntimeError("Повторная выдача неожиданно разрешена")
        give_back(conn, book_id)
        print(f"Книга возвращена; событий в истории: {len(history(conn, book_id))}")


def main():
    parser = argparse.ArgumentParser(description="Полка: учёт выданных книг")
    parser.add_argument("--db", default="polka.db", help="файл SQLite; по умолчанию polka.db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="учебный сценарий в отдельной базе в памяти")
    commands.add_parser("list", help="список книг и текущих читателей")
    commands.add_parser("seed", help="добавить учебные данные в пустую базу")
    commands.add_parser("add", help="добавить экземпляр книги").add_argument("title")
    loan = commands.add_parser("lend", help="выдать книгу")
    loan.add_argument("id", type=int)
    loan.add_argument("borrower")
    for name in ("return", "history"):
        commands.add_parser(name).add_argument("id", type=int)
    args = parser.parse_args()
    try:
        if args.command == "demo":
            demo()
            return 0
        with closing(connect(args.db)) as conn:
            if args.command == "seed":
                seed_demo(conn)
                print("Добавлены 4 учебные книги")
            elif args.command == "add":
                print(f"Добавлена книга: {add(conn, args.title)}")
            elif args.command == "list":
                rows = all_books(conn)
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            elif args.command == "lend":
                lend(conn, args.id, args.borrower)
                print(f"Книга выдана: {args.borrower.strip()}")
            elif args.command == "return":
                give_back(conn, args.id)
                print("Книга возвращена")
            elif args.command == "history":
                print(json.dumps(history(conn, args.id), ensure_ascii=False, indent=2))
    except (ValueError, sqlite3.Error, OSError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
