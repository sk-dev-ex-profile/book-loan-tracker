# Запуск и разработка

## Требования

Python 3.14 с `sqlite3` или Docker Engine с Compose. Проверены Python 3.14.6 на macOS ARM64
и Linux ARM64 внутри образа `python:3.14.6-slim`. Установка пакетов и загрузка образа требуют интернета.
База и само приложение работают локально. Отдельный Node.js и сборка JavaScript не нужны.

## macOS и Linux

Из корня проекта:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -c "from pathlib import Path; Path('data').mkdir(exist_ok=True)"
python book_tracker.py --db data/book-tracker.db seed
python web.py
```

Откройте http://localhost:8000. Остановка — Ctrl+C. Для повторного запуска активируйте
окружение и выполните `python web.py`. `seed` рассчитан только на пустую базу;
пустая полка без учебных записей тоже работает.

Для запуска без инструментов разработки достаточно установить `requirements.txt`.
`requirements-dev.txt` включает его и добавляет линтеры с их зависимостями.

## Windows PowerShell

Этот вариант приведён как инструкция, но на Windows не проверялся.
Активация окружения не требуется — команды обращаются к его интерпретатору напрямую:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -c "from pathlib import Path; Path('data').mkdir(exist_ok=True)"
.\.venv\Scripts\python.exe book_tracker.py --db data/book-tracker.db seed
.\.venv\Scripts\python.exe web.py
```

## Настройки

| Настройка | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `BOOK_TRACKER_DB` | `data/book-tracker.db` | Файл базы веб-приложения; путь относительно текущего каталога |
| `BOOK_TRACKER_HOST` | `127.0.0.1` | Адрес прослушивания локального сервера |
| `BOOK_TRACKER_PORT` | `8000` | Порт сервера при запуске `python web.py` |
| `BOOK_TRACKER_SECRET_KEY` | Случайное значение при запуске | Подпись сессионной cookie; необязательна для локального примера |
| `BOOK_TRACKER_WEB_PORT` | `8000` | Только Compose: порт на компьютере, перенаправленный в контейнер |

Файл `.env` приложение автоматически не читает. Переменные передаются через окружение.
При новом случайном ключе после перезапуска старая форма становится недействительной:
обновите страницу. В репозитории нет секретного ключа, который нужно копировать.

Пример другого порта и отдельной базы в macOS/Linux:

```bash
BOOK_TRACKER_DB=data/another.db BOOK_TRACKER_PORT=8001 python web.py
```

**CLI не читает `BOOK_TRACKER_DB`.** Для общей с веб-приложением базы явно указывайте путь:

```bash
python book_tracker.py --db data/book-tracker.db list
```

Без `--db` CLI использует `book-tracker.db` в текущем каталоге. Веб-приложение создаёт каталог базы
самостоятельно; перед `seed` из CLI каталог нужно создать явно.

## Автоматические проверки

```bash
python scripts/check.py
```

Либо отдельно:

```bash
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m djlint templates --lint
python -m djlint templates --check
```

20 тестов: 7 для CLI и 13 для HTTP-интерфейса. Они проверяют выдачу, возврат, сохранение,
повторные операции, пустой и слишком длинный ввод, отсутствующие книги, CSRF-защиту,
экранирование текста, откат при ошибке и совместную работу CLI с веб-интерфейсом.
Тесты используют временные базы; специально внесённый отказ SQLite не затрагивает личные данные.

Для исправления форматирования:

```bash
python -m ruff format .
python -m djlint templates --reformat
```

Ruff проверяет Python, djLint — Jinja-шаблоны. Это не линтер CSS и не проверка доступности интерфейса.
Правила находятся в `pyproject.toml`. Работа с [Ruff](https://docs.astral.sh/ruff/linter/)
и [djLint для Jinja](https://djlint.com/docs/languages/jinja/) описана в документации инструментов.

## Docker

```bash
docker compose up --build -d
docker compose exec web python book_tracker.py --db /app/data/book-tracker.db seed
docker compose ps
docker compose logs web
```

Откройте http://localhost:8000. Проверка доступности: GET `/health` возвращает
`{"status":"ok"}`. В контейнере работает Waitress, от пользователя `book-loan-tracker`, без прав root.
Waitress запускает Flask-приложение; это поддерживаемый [вариант запуска Flask](https://flask.palletsprojects.com/en/stable/deploying/waitress/).

База находится в `/app/data/book-tracker.db`, каталог подключён как именованный volume.
Обычное пересоздание контейнера и `docker compose down` сохраняют базу.
`docker compose down -v` удаляет volume вместе с книгами — это сброс данных, не обычная остановка.

Другой внешний порт:

```bash
BOOK_TRACKER_WEB_PORT=8001 docker compose up --build -d
```

Проверки в отдельном этапе сборки:

```bash
docker build --target checks -t book-loan-tracker-checks .
```

Сборка приложения:

```bash
docker build --target runtime -t book-loan-tracker .
```

`runtime` не запускает проверки автоматически: для них предназначен отдельный этап `checks`.
Файл `.github/workflows/checks.yml` запускает проверки и сборку после публикации репозитория
на GitHub. Наличие файла не означает, что удалённый CI уже выполнялся.

## Что делать при проблемах

- `Address already in use`: остановите другой процесс на порту 8000 или выберите другой порт.
- `База не пустая`: это ожидаемый отказ повторного `seed`; запускайте приложение с существующими данными.
- `Форма устарела`: обновите страницу после перезапуска сервера.
- `unable to open database file`: проверьте каталог и права записи; для CLI создайте каталог заранее.
- Изменения из CLI не видны в браузере: сравните `--db` и `BOOK_TRACKER_DB`, затем обновите страницу.
