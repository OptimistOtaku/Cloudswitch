"""Atomic plan versions and an outbox for reliable Switch replies."""

import copy
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .planner import forecasts, plan, validate, minute, calculate


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / "state.sqlite"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER, version INTEGER, config TEXT, approved TEXT);
            CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, revision INTEGER, room TEXT, thread TEXT, result TEXT, config TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, request TEXT, response TEXT, delivered INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS closing (version INTEGER PRIMARY KEY, report TEXT);
            CREATE TABLE IF NOT EXISTS inbox (id TEXT PRIMARY KEY, event TEXT, processed INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS cursors (room TEXT PRIMARY KEY, position INTEGER);
            """)
            config = json.loads(
                (self.folder / "kitchen.json").read_text(encoding="utf-8")
            )
            validate(config)
            db.execute(
                "INSERT OR IGNORE INTO state VALUES (1,0,0,?,NULL)",
                (json.dumps(config),),
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def snapshot(self):
        with self.connect() as db:
            row = dict(db.execute("SELECT * FROM state").fetchone())
            row["config"] = json.loads(row["config"])
            row["approved"] = json.loads(row["approved"]) if row["approved"] else None
            row["proposals"] = [
                dict(p) | {"result": json.loads(p["result"])}
                for p in db.execute(
                    "SELECT id,revision,status,result FROM proposals ORDER BY rowid DESC LIMIT 5"
                )
            ]
            row["closing"] = [
                json.loads(p[0]) for p in db.execute("SELECT report FROM closing")
            ]
            return row

    def handle(self, message_id, room, thread, sender, action, owner):
        request = json.dumps(
            dict(room=room, thread=thread, sender=sender, action=action), sort_keys=True
        )
        with self.connect() as db:
            old = db.execute(
                "SELECT request,response FROM messages WHERE id=?", (message_id,)
            ).fetchone()
            if old:
                if old["request"] != request:
                    raise ValueError("Message ID reused with different contents")
                return json.loads(old["response"])
            state = db.execute("SELECT * FROM state").fetchone()
            config = json.loads(state["config"])
            kind = action["kind"]
            if kind == "approve":
                if sender != owner:
                    raise ValueError("Only the configured owner may approve")
                proposal = db.execute(
                    "SELECT * FROM proposals WHERE id=?", (action["proposal_id"],)
                ).fetchone()
                if (
                    not proposal
                    or proposal["room"] != room
                    or proposal["thread"] != thread
                ):
                    raise ValueError("Proposal belongs to a different room or thread")
                if (
                    proposal["status"] != "pending"
                    or proposal["revision"] != state["revision"]
                ):
                    raise ValueError(
                        "Proposal is stale or already approved; request a fresh plan"
                    )
                result = json.loads(proposal["result"])
                alternative = action.get("alternative", 0)
                if type(alternative) is not int or not 0 <= alternative <= len(
                    result["alternatives"]
                ):
                    raise ValueError("Invalid alternative number")
                if alternative:
                    original = result
                    result = calculate(
                        config,
                        forecasts(self.folder / "orders.csv", config),
                        original["alternatives"][alternative - 1]["portions"],
                    )
                    for field in (
                        "baseline_blockers",
                        "baseline_ingredient_commitment",
                        "questions",
                        "alternatives",
                    ):
                        result[field] = original[field]
                    result["selected_alternative"] = alternative
                result["version"] = state["version"] + 1
                result["approved_by"] = sender
                result["source_message"] = message_id
                db.execute(
                    "UPDATE state SET version=?,approved=?,revision=revision+1 WHERE id=1",
                    (result["version"], json.dumps(result)),
                )
                db.execute(
                    "UPDATE proposals SET status='superseded' WHERE status='pending'"
                )
                db.execute(
                    "UPDATE proposals SET status='approved' WHERE id=?",
                    (proposal["id"],),
                )
                response = {"kind": "approved", "plan": result}
            elif kind == "close":
                if sender != owner or not state["approved"]:
                    raise ValueError("Owner and approved plan required for closing")
                approved = json.loads(state["approved"])
                rows = action["rows"]
                expected = {row["dish"]: row["portions"] for row in approved["prep"]}
                if set(rows) != set(expected):
                    raise ValueError("Closing must account for every prepared dish")
                for dish, counts in rows.items():
                    if (
                        set(counts) != {"sold", "carried", "discarded"}
                        or any(type(n) is not int or n < 0 for n in counts.values())
                        or sum(counts.values()) != expected[dish]
                    ):
                        raise ValueError(
                            "Sold + carried + discarded must equal prepared portions"
                        )
                if db.execute(
                    "SELECT 1 FROM closing WHERE version=?", (state["version"],)
                ).fetchone():
                    raise ValueError("Shift version already closed")
                report = {
                    "version": state["version"],
                    "recorded_portions": rows,
                    "recorded_by": sender,
                    "projected_contribution": approved["economics"][
                        "expected_contribution"
                    ],
                    "note": "Actual margin requires settlement and purchase receipts. Carryover requires kitchen safety checks.",
                }
                db.execute(
                    "INSERT INTO closing VALUES (?,?)",
                    (state["version"], json.dumps(report)),
                )
                response = {"kind": "closed", "report": report}
            elif kind in ("plan", "update"):
                if kind == "update":
                    config = self.apply(config, action["changes"])
                    validate(config)
                    db.execute(
                        "UPDATE state SET config=?,revision=revision+1 WHERE id=1",
                        (json.dumps(config),),
                    )
                    db.execute(
                        "UPDATE proposals SET status='superseded' WHERE status='pending'"
                    )
                revision = state["revision"] + (kind == "update")
                result = plan(config, forecasts(self.folder / "orders.csv", config))
                identity = hashlib.sha256(message_id.encode()).hexdigest()[:10]
                db.execute(
                    "INSERT INTO proposals VALUES (?,?,?,?,?,?, 'pending')",
                    (
                        identity,
                        revision,
                        room,
                        thread,
                        json.dumps(result),
                        json.dumps(config),
                    ),
                )
                response = {
                    "kind": "proposal",
                    "proposal_id": identity,
                    "revision": revision,
                    "plan": result,
                }
            elif kind == "clarify":
                response = {"kind": "clarify", "question": action["question"]}
            else:
                raise ValueError("Unsupported action")
            db.execute(
                "INSERT INTO messages(id,request,response) VALUES (?,?,?)",
                (message_id, request, json.dumps(response)),
            )
            return response

    @staticmethod
    def apply(config, changes):
        result = copy.deepcopy(config)
        if not changes:
            raise ValueError("Update needs explicit changes")
        allowed = {
            "cooks": {"available"},
            "markets": {"closes", "arrival"},
            "dishes": {"confirmed"},
            "ingredients": {"stock"},
        }
        for change in changes:
            group, name, field, value = (
                change[k] for k in ("group", "name", "field", "value")
            )
            if group == "quotes":
                ingredient, market = name.split("/")
                if (
                    field != "available"
                    or value is not None
                    and type(value) is not bool
                ):
                    raise ValueError("Supplier stock must be true, false, or unknown")
                result["ingredients"][ingredient]["quotes"][market][field] = value
            else:
                if group not in allowed or field not in allowed[group]:
                    raise ValueError("Unsupported update")
                if field == "available" and type(value) is not bool:
                    raise ValueError("Availability must be boolean")
                if field in ("stock", "confirmed") and (
                    type(value) is not int or value < 0
                ):
                    raise ValueError("Quantity must be a nonnegative integer")
                if field in ("arrival", "closes"):
                    minute(value)
                result[group][name][field] = value
        return result

    def pending(self):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute("SELECT * FROM messages WHERE delivered=0")
            ]

    def enqueue(self, identity, event):
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO inbox(id,event) VALUES (?,?)",
                (identity, json.dumps(event)),
            )

    def incoming(self):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM inbox WHERE processed=0 ORDER BY rowid"
                )
            ]

    def cursor(self, room, position=None):
        with self.connect() as db:
            if position is not None:
                db.execute(
                    "INSERT INTO cursors VALUES (?,?) ON CONFLICT(room) DO UPDATE SET position=excluded.position",
                    (room, position),
                )
            row = db.execute(
                "SELECT position FROM cursors WHERE room=?", (room,)
            ).fetchone()
            return row[0] if row else None

    def processed(self, identity):
        with self.connect() as db:
            db.execute("UPDATE inbox SET processed=1 WHERE id=?", (identity,))

    def delivered(self, identity):
        with self.connect() as db:
            db.execute("UPDATE messages SET delivered=1 WHERE id=?", (identity,))
