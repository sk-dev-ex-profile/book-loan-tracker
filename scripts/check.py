"""Запуск проверок одним интерпретатором из любого каталога."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    ["ruff", "check", "."],
    ["ruff", "format", "--check", "."],
    ["djlint", "templates", "--lint"],
    ["djlint", "templates", "--check"],
    ["unittest", "discover", "-s", "tests", "-v"],
]


def main():
    for command in COMMANDS:
        print("\n→", " ".join(command), flush=True)
        result = subprocess.run([sys.executable, "-m", *command], cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
