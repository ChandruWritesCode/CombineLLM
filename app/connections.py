"""Model connection configuration and encrypted server-side credential storage."""

import ipaddress
import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.costs import Money
from app.storage import now


class Connection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["gemini", "openai", "anthropic", "openrouter", "ollama", "compatible"]
    model: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9_./:@+-]+$")
    base_url: str = ""
    api_key: SecretStr | None = None
    clear_key: bool = False
    enabled: bool = True
    allow_fallback: bool = True
    usage_group: str = Field(default="", max_length=100)
    timeout_seconds: float = Field(default=60, ge=1, le=300)
    max_output_tokens: int = Field(default=2048, ge=1, le=8192)
    context_limit_chars: int | None = Field(default=None, ge=1000, le=1000000)
    task_tags: list[Literal["general", "code", "writing", "analysis"]] = Field(
        default_factory=list, max_length=4
    )
    temperature: float | None = Field(default=None, ge=0, le=2)
    system_prompt: str = Field(default="", max_length=10000)
    input_price_per_million: Money | None = None
    output_price_per_million: Money | None = None
    monthly_budget_usd: Money | None = None
    monthly_request_limit: int | None = Field(default=None, ge=1, le=1000000)
    include_usage: bool = True
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value):
        if value and (
            len(value.get_secret_value()) > 8192
            or any(ord(c) < 32 for c in value.get_secret_value())
        ):
            raise ValueError("Credential has invalid characters or length")
        return value

    @field_validator("task_tags")
    @classmethod
    def distinct_tags(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Task strengths must be distinct")
        return value

    @model_validator(mode="after")
    def endpoint(self):
        defaults = {
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        if self.kind in defaults:
            if self.base_url and self.base_url.rstrip("/") != defaults[self.kind]:
                raise ValueError("Use the compatible type for custom endpoints")
            self.base_url = defaults[self.kind]
        else:
            self.base_url = self.base_url.rstrip("/")
            parts = urlsplit(self.base_url)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.query
                or parts.fragment
                or any(c.isspace() for c in self.base_url)
            ):
                raise ValueError("Use an HTTP(S) base URL without credentials, query, or fragment")
            if parts.scheme == "http":
                local = parts.hostname in {"localhost", "host.docker.internal"}
                try:
                    address = ipaddress.ip_address(parts.hostname)
                    local = local or address.is_loopback or address.is_private
                except ValueError:
                    pass
                if not local:
                    raise ValueError("Public endpoints must use HTTPS; HTTP is for local servers")
        if self.kind == "gemini" and ("/" in self.model or ":" in self.model):
            raise ValueError("Gemini requires a model ID without the models/ prefix")
        if self.kind == "anthropic" and self.temperature is not None and self.temperature > 1:
            raise ValueError("Claude temperature must be between 0 and 1")
        return self


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_model_id: str | None = None
    fallback_model_ids: list[str] = Field(default_factory=list, max_length=3)
    monthly_budget_usd: Money | None = None
    monthly_request_limit: int | None = Field(default=None, ge=1, le=1000000)
    budget_warning_percent: int = Field(default=80, ge=1, le=100)
    max_output_tokens: int = Field(default=2048, ge=1, le=8192)
    system_prompt: str = Field(default="", max_length=10000)


class Connections:
    def __init__(self, store):
        self.store = store
        key_path = Path(store.path).with_suffix(".key")
        if not key_path.exists():
            with store.connect() as db:
                existing = db.execute(
                    "SELECT 1 FROM model_connections WHERE credential != ''"
                ).fetchone()
            if existing:
                raise RuntimeError("Credential key is missing. Restore the matching .key backup.")
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as file:
                file.write(Fernet.generate_key())
        self.cipher = Fernet(key_path.read_bytes())

    def preferences(self):
        with self.store.connect() as db:
            row = db.execute("SELECT value FROM preferences WHERE key='workspace'").fetchone()
        return Preferences.model_validate_json(row[0]) if row else Preferences()

    def save_preferences(self, prefs):
        if len(set(prefs.fallback_model_ids)) != len(prefs.fallback_model_ids):
            raise HTTPException(422, "Fallback models must be distinct")
        for model_id in prefs.fallback_model_ids:
            if not self.get(model_id)["enabled"]:
                raise HTTPException(422, "Fallback models must be enabled")
        if prefs.default_model_id:
            model = self.get(prefs.default_model_id)
            if not model["enabled"]:
                raise HTTPException(422, "Default model must be enabled")
        with self.store.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO preferences VALUES ('workspace',?)",
                (prefs.model_dump_json(),),
            )
        return prefs

    def list(self):
        with self.store.connect() as db:
            return [
                self.public(row)
                for row in db.execute("SELECT * FROM model_connections ORDER BY created_at,id")
            ]

    @staticmethod
    def public(row):
        return {
            **json.loads(row["config"]),
            "id": row["id"],
            "has_key": bool(row["credential"]),
            "auth_method": row["auth_method"],
            "created_at": row["created_at"],
        }

    def get(self, model_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM model_connections WHERE id=?", (model_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Model connection not found")
        return self.public(row)

    def secret(self, model_id):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT credential FROM model_connections WHERE id=?", (model_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(404, "Model connection not found")
        try:
            return self.cipher.decrypt(row[0].encode()).decode() if row[0] else ""
        except InvalidToken as exc:
            raise HTTPException(
                503, "Stored credential cannot be unlocked; restore its key file"
            ) from exc

    def save(self, body, model_id=None, auth_method=None):
        if model_id:
            previous = self.get(model_id)
            # Changing destinations must never silently forward an existing secret.
            if (
                (previous["kind"] != body.kind or previous["base_url"] != body.base_url)
                and not (body.api_key and body.api_key.get_secret_value())
                and not body.clear_key
            ):
                raise HTTPException(
                    422, "Changing provider or endpoint requires a new or cleared key"
                )
            key = "" if body.clear_key else self.secret(model_id)
            auth = auth_method or previous["auth_method"]
        else:
            model_id = str(uuid4())
            key = ""
            auth = auth_method or "api_key"
        if body.api_key and body.api_key.get_secret_value():
            key = body.api_key.get_secret_value()
            auth = auth_method or "api_key"
        if body.clear_key:
            key = ""
            auth = "none"
        config = body.model_dump(mode="json", exclude={"api_key", "clear_key"})
        credential = self.cipher.encrypt(key.encode()).decode() if key else ""
        with self.store.connect() as db:
            db.execute(
                """INSERT INTO model_connections (id,config,credential,auth_method,created_at)
                VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config,
                credential=excluded.credential,auth_method=excluded.auth_method""",
                (model_id, json.dumps(config), credential, auth if key else "none", now()),
            )
        return self.get(model_id)

    def delete(self, model_id):
        self.get(model_id)
        with self.store.connect() as db:
            db.execute("DELETE FROM model_connections WHERE id=?", (model_id,))
        prefs = self.preferences()
        if prefs.default_model_id == model_id:
            prefs.default_model_id = None
        prefs.fallback_model_ids = [mid for mid in prefs.fallback_model_ids if mid != model_id]
        # Deleting a connection must also work when another saved choice was disabled.
        with self.store.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO preferences VALUES ('workspace',?)",
                (prefs.model_dump_json(),),
            )

    def import_environment(self, settings):
        # Import once; later edits are made through Settings rather than overwritten on restart.
        with self.store.connect() as db:
            imported = db.execute("SELECT 1 FROM preferences WHERE key='env_imported'").fetchone()
        if imported or not settings.gemini_model or not settings.gemini_api_key.get_secret_value():
            return
        entry = self.save(
            Connection(
                name="Gemini (imported)",
                kind="gemini",
                model=settings.gemini_model,
                api_key=settings.gemini_api_key,
                timeout_seconds=settings.provider_timeout_seconds,
            )
        )
        prefs = self.preferences()
        if not prefs.default_model_id:
            prefs.default_model_id = entry["id"]
            self.save_preferences(prefs)
        with self.store.connect() as db:
            db.execute("INSERT INTO preferences VALUES ('env_imported','true')")
