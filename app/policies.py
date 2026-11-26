"""Local routing policy and persistent shared cooldowns."""

import ipaddress
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit


def retry_delay(value):
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 60
    if seconds != seconds or seconds == float("inf"):
        return 60
    return max(1, min(86400, seconds))


def is_local(config):
    if config["kind"] not in {"compatible", "ollama"}:
        return False
    host = urlsplit(config["base_url"]).hostname
    if host in {"localhost", "host.docker.internal"}:
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_loopback
    except ValueError:
        return False


def remaining(store, group):
    with store.connect() as db:
        row = db.execute("SELECT until FROM cooldowns WHERE pool=?", (group,)).fetchone()
    return max(0, row[0] - time.time()) if row else 0


def cool_down(store, group, seconds):
    with store.connect() as db:
        db.execute(
            "INSERT INTO cooldowns VALUES (?,?) ON CONFLICT(pool) "
            "DO UPDATE SET until=max(until,excluded.until)",
            (group, time.time() + seconds),
        )
