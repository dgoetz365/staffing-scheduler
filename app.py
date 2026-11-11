"""A local, single-user volunteer scheduling demonstration. Python 3.12+."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "schedule.sqlite3"
MAX_BODY = 16_384


class Problem(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def integer(value, name):
    if type(value) is not int or not 1 <= value <= 2_147_483_647:
        raise Problem(f"{name} must be an integer between 1 and 2147483647.", 400)
    return value


def text_field(value, name, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise Problem(f"{name} must contain 1–{limit} characters.", 400)
    if any((ord(c) < 32 and c not in "\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise Problem(f"{name} contains unsupported characters.", 400)
    return value.strip()


def connect(path):
    conn = sqlite3.connect(path, timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA = """
CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL);
CREATE TABLE volunteers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, roles TEXT NOT NULL, windows TEXT NOT NULL);
CREATE TABLE shifts (id INTEGER PRIMARY KEY, station TEXT NOT NULL, role TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL, capacity INTEGER NOT NULL CHECK(capacity>0));
CREATE TABLE assignments (shift_id INTEGER REFERENCES shifts(id), volunteer_id INTEGER REFERENCES volunteers(id), PRIMARY KEY(shift_id,volunteer_id));
CREATE TABLE publications (id INTEGER PRIMARY KEY, draft_version INTEGER NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE requests (id INTEGER PRIMARY KEY, shift_id INTEGER REFERENCES shifts(id), from_id INTEGER REFERENCES volunteers(id), to_id INTEGER REFERENCES volunteers(id), reason TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','approved','declined')), created TEXT NOT NULL, reviewed TEXT);
CREATE TABLE events (id INTEGER PRIMARY KEY, created TEXT NOT NULL, version INTEGER NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TRIGGER immutable_publication_update BEFORE UPDATE ON publications BEGIN SELECT RAISE(ABORT,'Published schedules are immutable'); END;
CREATE TRIGGER immutable_publication_delete BEFORE DELETE ON publications BEGIN SELECT RAISE(ABORT,'Published schedules are immutable'); END;
"""


def seed(path):
    """Create exactly once, refusing even an empty existing file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb"):
            pass
    except FileExistsError as exc:
        raise Problem("Database already exists. Seed refused; choose a new --db path.", 409) from exc
    try:
        with closing(connect(path)) as db:
            db.executescript("BEGIN IMMEDIATE;" + SCHEMA)
            db.execute("INSERT INTO meta VALUES(1,1)")
            volunteers = [
                (1, "Mira Chen", ["Guide"], [[540, 660]]),
                (2, "Theo Park", ["Facilitator"], [[540, 660]]),
                (3, "Ellis Rowan", ["Facilitator", "Maker"], [[540, 720]]),
                (4, "Noor Patel", ["Guide"], [[600, 720]]),
                (5, "Bea Flores", ["Maker"], [[540, 660]]),
                (6, "Sam Reed", ["Guide", "Facilitator"], [[540, 600]]),
            ]
            db.executemany("INSERT INTO volunteers VALUES(?,?,?,?)", [(i, n, json.dumps(r), json.dumps(w)) for i, n, r, w in volunteers])
            db.executemany("INSERT INTO shifts VALUES(?,?,?,?,?,?)", [
                (1, "Welcome desk", "Guide", 540, 600, 1),
                (2, "Light lab", "Facilitator", 540, 600, 1),
                (3, "Water lab", "Facilitator", 600, 660, 1),
                (4, "Welcome desk", "Guide", 600, 660, 1),
                (5, "Build bench", "Maker", 570, 630, 1),
            ])
            db.executemany("INSERT INTO assignments VALUES(?,?)", [(1, 1), (2, 2), (3, 3), (4, 4)])
            db.execute("INSERT INTO events(created,version,kind,detail) VALUES(?,1,'seed','Fictional exhibition prepared; Build bench needs one Maker.')", (now(),))
            db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise


def roster(db):
    return [dict(row, roles=json.loads(row["roles"]), windows=json.loads(row["windows"])) for row in db.execute("SELECT * FROM volunteers ORDER BY id")]


def draft(db):
    assignments = [dict(r) for r in db.execute("SELECT * FROM assignments ORDER BY shift_id,volunteer_id")]
    return {"volunteers": roster(db), "shifts": [dict(r) for r in db.execute("SELECT * FROM shifts ORDER BY start,id")], "assignments": assignments}


def state(path):
    with closing(connect(path)) as db:
        db.execute("BEGIN")
        result = draft(db)
        result["version"] = db.execute("SELECT version FROM meta WHERE id=1").fetchone()[0]
        result["publications"] = [dict(r, payload=json.loads(r["payload"])) for r in db.execute("SELECT * FROM publications ORDER BY id DESC")]
        result["requests"] = [dict(r) for r in db.execute("SELECT * FROM requests ORDER BY id DESC")]
        result["events"] = [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]
        db.commit()
        return result


def get_row(db, table, row_id, label):
    # table is supplied only by fixed call sites, never by request data.
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    if row is None:
        raise Problem(f"{label} does not exist.", 404)
    return row


def validate_assignment(db, shift_id, volunteer_id, replacing=None):
    shift = get_row(db, "shifts", shift_id, "Shift")
    volunteer = get_row(db, "volunteers", volunteer_id, "Volunteer")
    if shift["role"] not in json.loads(volunteer["roles"]):
        raise Problem(f"{volunteer['name']} is not eligible for the {shift['role']} role.")
    if not any(start <= shift["start"] and end >= shift["end"] for start, end in json.loads(volunteer["windows"])):
        raise Problem(f"{volunteer['name']} is unavailable for the full shift.")
    existing = list(db.execute("SELECT * FROM assignments WHERE shift_id=?", (shift_id,)))
    if any(r["volunteer_id"] == volunteer_id for r in existing):
        raise Problem("This volunteer is already assigned to this shift.")
    occupancy = sum(r["volunteer_id"] != replacing for r in existing)
    if occupancy >= shift["capacity"]:
        raise Problem("This shift is full. Remove an assignment or submit a reassignment request.")
    overlap = db.execute("""SELECT s.station FROM assignments a JOIN shifts s ON s.id=a.shift_id
        WHERE a.volunteer_id=? AND s.start < ? AND s.end > ? LIMIT 1""", (volunteer_id, shift["end"], shift["start"])).fetchone()
    if overlap:
        raise Problem(f"{volunteer['name']} already has an overlapping shift at {overlap['station']}.")


def validate_publication(db):
    data = draft(db)
    people = {p["id"]: p for p in data["volunteers"]}
    shifts = {s["id"]: s for s in data["shifts"]}
    for shift in data["shifts"]:
        assigned = [a for a in data["assignments"] if a["shift_id"] == shift["id"]]
        if len(assigned) != shift["capacity"]:
            raise Problem(f"Cannot publish: {shift['station']} must have all {shift['capacity']} place(s) filled.")
    for assignment in data["assignments"]:
        person, shift = people[assignment["volunteer_id"]], shifts[assignment["shift_id"]]
        if shift["role"] not in person["roles"] or not any(a <= shift["start"] and b >= shift["end"] for a, b in person["windows"]):
            raise Problem("Cannot publish: a role or availability conflict exists.")
        for other in data["assignments"]:
            if other != assignment and other["volunteer_id"] == person["id"]:
                other_shift = shifts[other["shift_id"]]
                if shift["start"] < other_shift["end"] and shift["end"] > other_shift["start"]:
                    raise Problem("Cannot publish: overlapping assignments exist.")
    return data


FIELDS = {
    "assign": {"version", "shift_id", "volunteer_id"},
    "remove": {"version", "shift_id", "volunteer_id"},
    "publish": {"version"},
    "request": {"version", "shift_id", "from_id", "to_id", "reason"},
    "review": {"version", "request_id", "decision"},
}


def mutate(path, action, data):
    if action not in FIELDS:
        raise Problem("Route not found.", 404)
    if not isinstance(data, dict) or set(data) != FIELDS[action]:
        raise Problem("Request fields do not match this action.", 400)
    for key in FIELDS[action] - {"reason", "decision"}:
        integer(data[key], key)
    if action == "request":
        data["reason"] = text_field(data["reason"], "Reason")
    if action == "review" and data["decision"] not in ("approve", "decline"):
        raise Problem("Decision must be approve or decline.", 400)
    with closing(connect(path)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            version = db.execute("SELECT version FROM meta WHERE id=1").fetchone()[0]
            if version != data["version"]:
                raise Problem("This workspace changed. Refresh, check the current draft, then try again.", 409)
            detail = ""
            if action in ("assign", "remove"):
                shift_id, person_id = data["shift_id"], data["volunteer_id"]
                shift = get_row(db, "shifts", shift_id, "Shift")
                person = get_row(db, "volunteers", person_id, "Volunteer")
                if action == "assign":
                    validate_assignment(db, shift_id, person_id)
                    db.execute("INSERT INTO assignments VALUES(?,?)", (shift_id, person_id))
                    detail = f"Assigned {person['name']} to {shift['station']}."
                else:
                    deleted = db.execute("DELETE FROM assignments WHERE shift_id=? AND volunteer_id=?", (shift_id, person_id)).rowcount
                    if not deleted:
                        raise Problem("That assignment no longer exists.", 409)
                    detail = f"Removed {person['name']} from {shift['station']}."
            elif action == "publish":
                payload = validate_publication(db)
                cursor = db.execute("INSERT INTO publications(draft_version,created,payload) VALUES(?,?,?)", (version, now(), json.dumps(payload, ensure_ascii=False)))
                detail = f"Published snapshot {cursor.lastrowid} from workspace version {version}."
            elif action == "request":
                if data["from_id"] == data["to_id"]:
                    raise Problem("Choose a different replacement volunteer.")
                if not db.execute("SELECT 1 FROM assignments WHERE shift_id=? AND volunteer_id=?", (data["shift_id"], data["from_id"])).fetchone():
                    raise Problem("The original assignment no longer exists.", 409)
                validate_assignment(db, data["shift_id"], data["to_id"], replacing=data["from_id"])
                duplicate = db.execute("SELECT 1 FROM requests WHERE shift_id=? AND from_id=? AND status='pending'", (data["shift_id"], data["from_id"])).fetchone()
                if duplicate:
                    raise Problem("This assignment already has a pending request.", 409)
                cursor = db.execute("INSERT INTO requests(shift_id,from_id,to_id,reason,status,created) VALUES(?,?,?,?,'pending',?)", (data["shift_id"], data["from_id"], data["to_id"], data["reason"], now()))
                detail = f"Reassignment request {cursor.lastrowid} submitted for review."
            elif action == "review":
                request = get_row(db, "requests", data["request_id"], "Request")
                if request["status"] != "pending":
                    raise Problem("This request has already been reviewed.", 409)
                if data["decision"] == "approve":
                    original = db.execute("SELECT 1 FROM assignments WHERE shift_id=? AND volunteer_id=?", (request["shift_id"], request["from_id"])).fetchone()
                    if not original:
                        raise Problem("Approval blocked: the original assignment changed. Decline this request.", 409)
                    validate_assignment(db, request["shift_id"], request["to_id"], replacing=request["from_id"])
                    db.execute("DELETE FROM assignments WHERE shift_id=? AND volunteer_id=?", (request["shift_id"], request["from_id"]))
                    db.execute("INSERT INTO assignments VALUES(?,?)", (request["shift_id"], request["to_id"]))
                status = "approved" if data["decision"] == "approve" else "declined"
                db.execute("UPDATE requests SET status=?,reviewed=? WHERE id=?", (status, now(), request["id"]))
                detail = f"Request {request['id']} {status}; published snapshots unchanged."
            version += 1
            db.execute("UPDATE meta SET version=? WHERE id=1", (version,))
            db.execute("INSERT INTO events(created,version,kind,detail) VALUES(?,?,?,?)", (now(), version, action, detail))
            db.commit()
            return {"version": version, "message": detail}
        except Exception:
            db.rollback()
            raise


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Non-finite JSON number")

    def check(value):
        if isinstance(value, str) and any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Surrogate Unicode is unsupported")
        if isinstance(value, dict):
            for key, item in value.items():
                check(key)
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject_constant)
        check(value)
        if not isinstance(value, dict):
            raise ValueError("Expected JSON object")
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Problem("Body must be a UTF-8 JSON object without duplicate keys, non-finite numbers or surrogate characters.", 400) from exc


class Handler(BaseHTTPRequestHandler):
    server_version = "FieldworkLocal/1"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, *_args):
        pass  # No request bodies, headers or user text are logged.

    def respond(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def check_headers(self):
        names = [name.lower() for name in self.headers.keys()]
        if len(names) != len(set(names)):
            raise Problem("Duplicate headers are not accepted.", 400)
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected:
            raise Problem("Use the printed 127.0.0.1 URL.", 403)
        if "Transfer-Encoding" in self.headers:
            raise Problem("Transfer-Encoding is not supported.", 400)
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{expected}":
            raise Problem("Origin does not match this local server.", 403)
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            raise Problem("Cross-site requests are not accepted.", 403)

    def body(self):
        # Consume bounded input before policy rejection, avoiding unread-body TCP resets.
        lengths = self.headers.get_all("Content-Length", [])
        if not lengths and "Transfer-Encoding" in self.headers:
            raise Problem("Transfer-Encoding is not supported.", 400)
        if not lengths or not all(re.fullmatch(r"[0-9]{1,8}", item) for item in lengths):
            raise Problem("A valid Content-Length is required.", 411)
        length = max(map(int, lengths))
        if length > MAX_BODY:
            self.connection.settimeout(0.1)
            try:
                self.rfile.read(min(length, MAX_BODY * 2))
            except TimeoutError:
                pass
            finally:
                self.connection.settimeout(3)
            raise Problem("Request body exceeds 16 KiB.", 413)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise Problem("Incomplete request body.", 400)
        return raw

    def do_GET(self):
        try:
            self.check_headers()
            if self.headers.get("Content-Length", "0") != "0":
                self.body()
                raise Problem("GET requests cannot contain a body.", 400)
            if self.path == "/api/state":
                self.respond(200, state(self.server.db_path))
                return
            assets = {"/": ("index.html", "text/html; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8")}
            if self.path not in assets:
                raise Problem("Route not found.", 404)
            name, mime = assets[self.path]
            self.respond(200, (ROOT / "static" / name).read_bytes(), mime)
        except Problem as exc:
            self.respond(exc.status, {"error": str(exc)})
        except (sqlite3.Error, OSError):
            self.respond(500, {"error": "Local storage is unavailable. Check the server and database path."})

    def do_POST(self):
        try:
            raw = self.body()
            self.check_headers()
            if self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}":
                raise Problem("A matching Origin header is required.", 403)
            if self.headers.get("Content-Type", "").lower() not in ("application/json", "application/json; charset=utf-8"):
                raise Problem("Content-Type must be application/json.", 415)
            routes = {f"/api/{name}": name for name in FIELDS}
            if self.path not in routes:
                raise Problem("Route not found.", 404)
            self.respond(200, mutate(self.server.db_path, routes[self.path], strict_json(raw)))
        except Problem as exc:
            self.respond(exc.status, {"error": str(exc)})
        except TimeoutError:
            self.respond(408, {"error": "Request body timed out."})
        except sqlite3.Error:
            self.respond(503, {"error": "Local storage is busy or unavailable. Refresh and retry."})


def make_server(path, port=8766):
    path = Path(path)
    if not path.is_file():
        raise Problem("Database not found. Run the seed command first.", 404)
    state(path)  # Fail at startup for an incompatible database.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.db_path = path
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seed", "serve"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    try:
        if args.command == "seed":
            seed(args.db)
            print("Seeded fictional exhibition. Existing databases are never overwritten.")
        else:
            if not 0 <= args.port <= 65535:
                raise Problem("Port must be between 0 and 65535.", 400)
            with make_server(args.db, args.port) as server:
                print(f"Fieldwork Scheduler: http://127.0.0.1:{server.server_port}", flush=True)
                server.serve_forever()
    except (Problem, sqlite3.Error, OSError) as exc:
        parser.exit(1, f"Cannot start: {exc}\n")
    except KeyboardInterrupt:
        print("\nServer stopped. Your local schedule is saved.")


if __name__ == "__main__":
    main()
