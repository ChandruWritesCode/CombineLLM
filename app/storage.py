"""Small SQLite repository. Transactions never span network calls."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.schemas import ChatRequest, Message


def now():
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 7:
                raise RuntimeError("Database is newer than this application; do not downgrade.")
            if version == 0:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE conversations (
                        id TEXT PRIMARY KEY, title TEXT NOT NULL,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                    );
                    CREATE TABLE messages (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        id TEXT NOT NULL UNIQUE,
                        conversation_id TEXT NOT NULL
                            REFERENCES conversations(id) ON DELETE CASCADE,
                        role TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL, provider TEXT, model TEXT,
                        finish_reason TEXT, usage TEXT, error TEXT,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX messages_conversation ON messages(conversation_id, seq);
                    PRAGMA user_version=1;
                    COMMIT;
                """)
            if version < 2:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE model_connections (
                        id TEXT PRIMARY KEY, config TEXT NOT NULL, credential TEXT NOT NULL,
                        auth_method TEXT NOT NULL, created_at TEXT NOT NULL
                    );
                    CREATE TABLE preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    ALTER TABLE conversations ADD COLUMN model_id TEXT;
                    ALTER TABLE messages ADD COLUMN model_id TEXT;
                    CREATE TABLE usage_events (
                        id TEXT PRIMARY KEY, model_id TEXT, label TEXT, provider TEXT, model TEXT,
                        source TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
                        duration_ms INTEGER, input_tokens INTEGER, output_tokens INTEGER,
                        reasoning_tokens INTEGER, total_tokens INTEGER, error_code TEXT
                    );
                    CREATE INDEX usage_started ON usage_events(started_at);
                    UPDATE conversations SET model_id=NULL;
                    PRAGMA user_version=2;
                    COMMIT;
                """)
            if version < 3:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    ALTER TABLE usage_events ADD COLUMN input_price_per_million TEXT;
                    ALTER TABLE usage_events ADD COLUMN output_price_per_million TEXT;
                    ALTER TABLE usage_events ADD COLUMN estimated_cost_usd TEXT;
                    PRAGMA user_version=3;
                    COMMIT;
                """)
            if version < 4:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    ALTER TABLE usage_events ADD COLUMN attempt_group_id TEXT;
                    ALTER TABLE usage_events ADD COLUMN attempt_number INTEGER;
                    PRAGMA user_version=4;
                    COMMIT;
                """)
            if version < 5:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE cooldowns (pool TEXT PRIMARY KEY, until REAL NOT NULL);
                    ALTER TABLE usage_events ADD COLUMN usage_group TEXT;
                    ALTER TABLE messages ADD COLUMN attempt_group_id TEXT;
                    PRAGMA user_version=5;
                    COMMIT;
                """)
            if version < 6:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    ALTER TABLE messages ADD COLUMN coordination_mode TEXT;
                    ALTER TABLE messages ADD COLUMN coordination_stage TEXT;
                    ALTER TABLE messages ADD COLUMN rating INTEGER;
                    PRAGMA user_version=6;
                    COMMIT;
                """)
            if version < 7:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    ALTER TABLE messages ADD COLUMN selection_mode TEXT;
                    ALTER TABLE messages ADD COLUMN selection_reason TEXT;
                    PRAGMA user_version=7;
                    COMMIT;
                """)
            db.execute("UPDATE usage_events SET status='interrupted' WHERE status='running'")
            db.execute(
                "UPDATE messages SET status='interrupted', error=? WHERE status='streaming'",
                (
                    "The backend restarted before this response finished. "
                    "You can send the prompt again.",
                ),
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self.connect() as db:
            return [
                dict(r) for r in db.execute("SELECT * FROM conversations ORDER BY updated_at DESC")
            ]

    def create(self, title):
        item = {"id": str(uuid4()), "title": title, "created_at": now(), "updated_at": now()}
        with self.connect() as db:
            db.execute(
                "INSERT INTO conversations (id,title,created_at,updated_at) "
                "VALUES (:id,:title,:created_at,:updated_at)",
                item,
            )
        return item

    def get(self, conversation_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM conversations WHERE id=?", (conversation_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Conversation not found")
            result = dict(row)
            result["messages"] = [
                self.decode(r)
                for r in db.execute(
                    "SELECT * FROM messages WHERE conversation_id=? ORDER BY seq",
                    (conversation_id,),
                )
            ]
            for message in result["messages"]:
                message["attempts"] = self.attempts(db, message.get("attempt_group_id"))
            return result

    @staticmethod
    def decode(row):
        result = dict(row)
        result.pop("seq", None)
        result["usage"] = json.loads(result["usage"]) if result["usage"] else None
        return result

    def rename(self, conversation_id, title):
        self.get(conversation_id)
        with self.connect() as db:
            db.execute(
                "UPDATE conversations SET title=?,updated_at=? WHERE id=?",
                (title, now(), conversation_id),
            )
        return self.get(conversation_id)

    def delete(self, conversation_id):
        self.get(conversation_id)
        with self.connect() as db:
            db.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))

    def begin(self, conversation_id, content, max_output_tokens, provider):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            conversation = db.execute(
                "SELECT * FROM conversations WHERE id=?", (conversation_id,)
            ).fetchone()
            if conversation is None:
                raise HTTPException(404, "Conversation not found")
            rows = db.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY seq", (conversation_id,)
            ).fetchall()
            if any(r["status"] == "streaming" for r in rows):
                raise HTTPException(409, "A response is already running in this conversation")
            history = []
            # Failed/cancelled turns remain visible but never become model context.
            for previous, answer in zip(rows, rows[1:]):
                if (
                    previous["role"] == "user"
                    and answer["role"] == "assistant"
                    and answer["status"] == "complete"
                ):
                    history.extend(
                        [
                            Message(role="user", content=previous["content"]),
                            Message(role="assistant", content=answer["content"]),
                        ]
                    )
            history.append(Message(role="user", content=content))
            request = ChatRequest(
                messages=history,
                max_output_tokens=max_output_tokens,
                system=getattr(provider, "system_prompt", "") or None,
            )
            answer_id = str(uuid4())
            for role, text, status, message_id in [
                ("user", content, "complete", str(uuid4())),
                ("assistant", "", "streaming", answer_id),
            ]:
                db.execute(
                    """INSERT INTO messages
                    (id,conversation_id,role,content,status,provider,model,created_at)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        message_id,
                        conversation_id,
                        role,
                        text,
                        status,
                        provider.name if role == "assistant" else None,
                        provider.model if role == "assistant" else None,
                        now(),
                    ),
                )
            model_id = getattr(provider, "model_id", None)
            db.execute("UPDATE messages SET model_id=? WHERE id=?", (model_id, answer_id))
            if getattr(provider, "coordination_mode", None):
                db.execute(
                    "UPDATE messages SET coordination_mode=?,attempt_group_id=? WHERE id=?",
                    (provider.coordination_mode, provider.attempt_group_id, answer_id),
                )
            db.execute(
                "UPDATE messages SET selection_mode=?,selection_reason=? WHERE id=?",
                (
                    getattr(provider, "selection_mode", "manual"),
                    getattr(provider, "selection_reason", None),
                    answer_id,
                ),
            )
            if model_id:
                db.execute(
                    "UPDATE conversations SET model_id=? WHERE id=?", (model_id, conversation_id)
                )
            title = (
                content[:60]
                if not rows and conversation["title"] == "New conversation"
                else conversation["title"]
            )
            db.execute(
                "UPDATE conversations SET title=?,updated_at=? WHERE id=?",
                (title, now(), conversation_id),
            )
            return answer_id, request

    @staticmethod
    def attempts(db, group):
        return (
            [
                dict(r)
                for r in db.execute(
                    "SELECT label,model,source,status,error_code,attempt_number,"
                    "estimated_cost_usd,total_tokens FROM usage_events "
                    "WHERE attempt_group_id=? ORDER BY attempt_number",
                    (group,),
                )
            ]
            if group
            else []
        )

    def attribute_answer(self, message_id, provider):
        with self.connect() as db:
            db.execute(
                "UPDATE messages SET provider=?,model=?,model_id=?,attempt_group_id=? WHERE id=?",
                (
                    provider.name,
                    provider.model,
                    getattr(provider, "response_model_id", getattr(provider, "model_id", None)),
                    getattr(provider, "attempt_group_id", None),
                    message_id,
                ),
            )

    def save_answer(self, message_id, content, status, error=None, finish=None, usage=None):
        with self.connect() as db:
            db.execute(
                """UPDATE messages SET content=?,status=?,error=?,finish_reason=?,usage=?
                          WHERE id=? AND status='streaming'""",
                (
                    content,
                    status,
                    error,
                    finish,
                    json.dumps(usage) if usage is not None else None,
                    message_id,
                ),
            )

    def save_stage(self, message_id, stage):
        with self.connect() as db:
            db.execute(
                "UPDATE messages SET coordination_stage=? WHERE id=? AND status='streaming'",
                (stage, message_id),
            )

    def rate_answer(self, conversation_id, message_id, rating):
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE messages SET rating=? WHERE conversation_id=? AND id=? "
                "AND role='assistant' AND status='complete'",
                (rating, conversation_id, message_id),
            )
            if not cursor.rowcount:
                raise HTTPException(422, "Only completed assistant answers can be rated")
        return self.message(conversation_id, message_id)

    def message(self, conversation_id, message_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM messages WHERE id=? AND conversation_id=?",
                (message_id, conversation_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Message not found")
            result = self.decode(row)
            result["attempts"] = self.attempts(db, result.get("attempt_group_id"))
            return result
