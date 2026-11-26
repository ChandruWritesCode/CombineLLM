"""Create a consistent SQLite backup, including committed WAL data."""

import argparse
import sqlite3
from pathlib import Path

from app.config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    source = Path(Settings().database_path).resolve()
    if not source.is_file():
        parser.error("Database does not exist; start the backend first.")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids silently overwriting another backup or the live database.
    with args.destination.open("xb"):
        pass
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(args.destination) as backup:
            original.backup(backup)
    print(f"Backup created: {args.destination}")


if __name__ == "__main__":
    main()
