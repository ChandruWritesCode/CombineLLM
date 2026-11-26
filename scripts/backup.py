"""Create a consistent SQLite backup, including committed WAL data."""

import argparse
import shutil
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
    key_source = source.with_suffix(".key")
    key_destination = args.destination.with_suffix(".key")
    if key_source.exists() and key_destination.exists():
        parser.error("Backup key destination already exists; use a unique backup name.")
    with args.destination.open("xb"):
        pass
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(args.destination) as backup:
            original.backup(backup)
    if key_source.exists():
        with key_source.open("rb") as original_key, key_destination.open("xb") as backup_key:
            shutil.copyfileobj(original_key, backup_key)
        key_destination.chmod(0o600)
    print(f"Backup created: {args.destination}")


if __name__ == "__main__":
    main()
