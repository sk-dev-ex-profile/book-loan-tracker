"""Веб-интерфейс Book Loan Tracker: HTML-страницы и формы, общая логика в library.py."""

import os
import secrets
import sqlite3
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

import library


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get("BOOK_TRACKER_DB", "data/book-tracker.db"),
        SECRET_KEY=os.environ.get("BOOK_TRACKER_SECRET_KEY") or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=16_384,
    )
    if config:
        app.config.update(config)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    def db():
        if "db" not in g:
            g.db = library.connect(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.before_request
    def protect_forms():
        if request.method == "POST":
            expected = session.get("csrf_token", "")
            received = request.form.get("csrf_token", "")
            if not expected or not secrets.compare_digest(expected.encode(), received.encode()):
                return render_template(
                    "error.html",
                    message="Форма устарела. Откройте страницу заново и повторите действие.",
                ), 400
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return None

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'none'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response

    def shelf(book_id=None, view="detail", error=None, status=200):
        books = library.all_books(db())
        selected = (
            library.book(db(), book_id) if book_id is not None else (books[0] if books else None)
        )
        events = library.history(db(), selected["id"]) if selected else []
        return render_template(
            "index.html",
            books=books,
            selected=selected,
            events=events[::-1],
            view=view,
            error=error,
        ), status

    @app.get("/")
    def index():
        return shelf(request.args.get("book", type=int), request.args.get("view", "detail"))

    @app.post("/books")
    def add_book():
        try:
            book_id = library.add(db(), request.form.get("title", ""))
        except library.InvalidInput as error:
            return shelf(view="add", error=str(error), status=400)
        flash("Книга добавлена на полку.")
        return redirect(url_for("index", book=book_id), code=303)

    @app.post("/books/<int:book_id>/lend")
    def lend_book(book_id):
        try:
            library.lend(db(), book_id, request.form.get("borrower", ""))
        except library.BookNotFound:
            raise
        except library.InvalidInput as error:
            return shelf(book_id, error=str(error), status=400)
        except ValueError as error:
            return shelf(book_id, error=str(error), status=409)
        flash("Выдача записана.")
        return redirect(url_for("index", book=book_id), code=303)

    @app.post("/books/<int:book_id>/return")
    def return_book(book_id):
        library.book(db(), book_id)
        loan_id = request.form.get("loan_id", type=int)
        if loan_id is None:
            return shelf(book_id, error="Откройте подтверждение возврата заново.", status=400)
        try:
            library.give_back(db(), book_id, expected_loan_id=loan_id)
        except library.BookNotFound:
            raise
        except ValueError as error:
            return shelf(book_id, error=str(error), status=409)
        flash("Возврат отмечен. Книга снова на полке.")
        return redirect(url_for("index", book=book_id), code=303)

    @app.get("/health")
    def health():
        db().execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.errorhandler(library.BookNotFound)
    def missing_book(error):
        return render_template("error.html", message=str(error)), 404

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        app.logger.error("Ошибка SQLite", exc_info=error)
        return render_template(
            "error.html",
            message="Не удалось сохранить или прочитать данные. Повторите действие позже.",
        ), 503

    @app.errorhandler(404)
    def missing_page(_error):
        return render_template("error.html", message="Страница не найдена."), 404

    return app


if __name__ == "__main__":
    from waitress import serve

    serve(
        create_app(),
        host=os.environ.get("BOOK_TRACKER_HOST", "127.0.0.1"),
        port=int(os.environ.get("BOOK_TRACKER_PORT", "8000")),
        threads=4,
    )
