"""Verify a trusted backup and restore it to a new path without replacing live data."""

import argparse
import shutil
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def verify_backup(source: Path):
    if not source.is_file():
        raise ValueError("Backup database does not exist")
    try:
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if integrity != "ok":
                raise ValueError("Backup database failed SQLite integrity check")
            if not 1 <= version <= 8:
                raise ValueError("Backup database schema is unsupported")
            db.execute("SELECT COUNT(*) FROM conversations").fetchone()
            db.execute("SELECT COUNT(*) FROM messages").fetchone()
            credentials = (
                [row[0] for row in db.execute("SELECT credential FROM model_connections") if row[0]]
                if version >= 2
                else []
            )
    except sqlite3.DatabaseError as exc:
        raise ValueError("Backup is not a readable CombineLLM database") from exc

    key_path = source.with_suffix(".key")
    if credentials and not key_path.is_file():
        raise ValueError("The matching backup key is required for saved credentials")
    if key_path.is_file():
        try:
            cipher = Fernet(key_path.read_bytes())
            for credential in credentials:
                cipher.decrypt(credential.encode())
        except (ValueError, InvalidToken) as exc:
            raise ValueError("The backup key does not match the saved credentials") from exc
    return {"schema_version": version, "credential_key_present": key_path.is_file()}


def restore_backup(source: Path, destination: Path):
    result = verify_backup(source)
    if source.resolve() == destination.resolve():
        raise ValueError("Choose a different destination from the backup")
    key_source = source.with_suffix(".key")
    key_destination = destination.with_suffix(".key")
    if destination.exists() or key_destination.exists():
        raise FileExistsError("Destination database or key already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with source.open("rb") as original, destination.open("xb") as restored:
            created.append(destination)
            shutil.copyfileobj(original, restored)
        destination.chmod(0o600)
        if key_source.is_file():
            with key_source.open("rb") as original, key_destination.open("xb") as restored:
                created.append(key_destination)
                shutil.copyfileobj(original, restored)
            key_destination.chmod(0o600)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("destination", type=Path, nargs="?")
    args = parser.parse_args()
    try:
        result = (
            restore_backup(args.backup, args.destination)
            if args.destination
            else verify_backup(args.backup)
        )
    except (ValueError, FileExistsError, OSError) as exc:
        parser.error(str(exc))
    action = "Restored to a new path" if args.destination else "Verified backup"
    print(f"{action}: schema {result['schema_version']}; matching key checked")


if __name__ == "__main__":
    main()
