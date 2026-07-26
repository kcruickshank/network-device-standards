"""
Network Device Standards - shared backend API
==============================================

A small FastAPI + SQLite service that lets multiple people share one catalogue,
as an alternative to SharePoint. The HTML app's "API server" storage mode talks
to this service.

WHAT IT DOES
  - Stores each kind of record (devices, accessories, links, golden images,
    bills of materials, sites, change log) in its own SQLite table.
  - Stores the single config/taxonomy blob in a one-row table.
  - Every record carries a "version" number. Saves must send the version they
    last saw; if someone else changed it first, the save is rejected with HTTP
    409 (Conflict). This is the same protection the SharePoint mode has, so two
    people editing the same device never silently overwrite each other.
  - Serves the app's index.html itself, so users just open one URL.

HOW TO RUN (development / small team)
  1. Install Python 3.9+.
  2. pip install fastapi "uvicorn[standard]"
  3. Put your app file next to this script and name it  index.html
  4. python server.py
  5. Open http://<this-machine>:8000  in a browser.
     In the app: Settings -> "API server (shared)" -> the URL is pre-filled ->
     Connect.

HOW TO RUN (as a proper service)
  Run behind a real host so others can reach it, e.g.:
     uvicorn server:app --host 0.0.0.0 --port 8000
  Then point colleagues at  http://<server-name-or-ip>:8000
  For production, put it behind a reverse proxy (IIS/nginx) with HTTPS, and
  consider restricting access to your internal network.

DATA / BACKUP
  All data lives in one file:  nds.db  (next to this script).
  Back it up by copying that file. That's your entire catalogue.
"""

import os
import json
import sqlite3
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

HERE = os.path.dirname(os.path.abspath(__file__))
# DB path can be overridden (e.g. to a mounted volume in Docker) via NDS_DB_PATH.
DB_PATH = os.environ.get("NDS_DB_PATH") or os.path.join(HERE, "nds.db")
# The app's single HTML file. In the repo it lives in ../app/index.html; when
# containerised it is copied to /app/app/index.html. Fall back to beside the script.
INDEX_HTML = os.environ.get("NDS_INDEX_HTML") or (
    os.path.join(HERE, "..", "app", "index.html")
    if os.path.exists(os.path.join(HERE, "..", "app", "index.html"))
    else os.path.join(HERE, "index.html")
)

# The record collections. Each becomes a table of (id, version, data-json).
COLLECTIONS = [
    "devices", "accessories", "links", "goldenImages",
    "boms", "sites", "changelog",
]

_lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")  # better concurrent reads
    return conn


def init_db():
    with db() as conn:
        for c in COLLECTIONS:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {c} ("
                "  id TEXT PRIMARY KEY,"
                "  version INTEGER NOT NULL DEFAULT 1,"
                "  data TEXT NOT NULL"
                ")"
            )
        # single-row config table
        conn.execute(
            "CREATE TABLE IF NOT EXISTS config ("
            "  id INTEGER PRIMARY KEY CHECK (id = 1),"
            "  version INTEGER NOT NULL DEFAULT 1,"
            "  data TEXT NOT NULL"
            ")"
        )
        conn.commit()


init_db()

app = FastAPI(title="Network Device Standards API")

# Allow the page to call the API when it's opened from a different origin
# (e.g. hosted on SharePoint but using the API for data, or opened as a file).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _valid(collection: str):
    if collection not in COLLECTIONS:
        raise HTTPException(status_code=404, detail="Unknown collection")


# ---------------------------------------------------------------- bulk load
@app.get("/api/v1/all")
def get_all():
    """Return the entire catalogue in one call (used on connect/reload)."""
    out = {}
    with db() as conn:
        for c in COLLECTIONS:
            rows = conn.execute(f"SELECT id, version, data FROM {c}").fetchall()
            items = []
            for r in rows:
                obj = json.loads(r["data"])
                obj["id"] = r["id"]
                obj["_version"] = r["version"]
                items.append(obj)
            out[c] = items
        cfg = conn.execute("SELECT version, data FROM config WHERE id = 1").fetchone()
        if cfg:
            meta = json.loads(cfg["data"])
            meta["_version"] = cfg["version"]
            out["meta"] = meta
        else:
            out["meta"] = None
    return out


# ---------------------------------------------------------------- per-record save
@app.put("/api/v1/{collection}/{item_id}")
def upsert(collection: str, item_id: str, payload: dict = Body(...)):
    """
    Create or update one record.
    Body: the record object. It may include "_version" = the version the client
    last saw. If the stored version differs, we return 409 (someone else changed
    it first). New records omit _version or send 0.
    """
    _valid(collection)
    client_version = int(payload.get("_version") or 0)
    data = dict(payload)
    data.pop("_version", None)
    data.pop("id", None)
    body = json.dumps(data)

    with _lock, db() as conn:
        row = conn.execute(
            f"SELECT version FROM {collection} WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            # new record
            conn.execute(
                f"INSERT INTO {collection} (id, version, data) VALUES (?, 1, ?)",
                (item_id, body),
            )
            conn.commit()
            return {"id": item_id, "_version": 1}
        # existing record - check version
        current = row["version"]
        if client_version and client_version != current:
            raise HTTPException(
                status_code=409,
                detail={"message": "Version conflict", "currentVersion": current},
            )
        new_version = current + 1
        conn.execute(
            f"UPDATE {collection} SET version = ?, data = ? WHERE id = ?",
            (new_version, body, item_id),
        )
        conn.commit()
        return {"id": item_id, "_version": new_version}


# ---------------------------------------------------------------- per-record delete
@app.delete("/api/v1/{collection}/{item_id}")
def delete(collection: str, item_id: str, version: Optional[int] = None):
    _valid(collection)
    with _lock, db() as conn:
        row = conn.execute(
            f"SELECT version FROM {collection} WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return {"deleted": True}  # already gone
        if version is not None and int(version) != row["version"]:
            raise HTTPException(
                status_code=409,
                detail={"message": "Version conflict", "currentVersion": row["version"]},
            )
        conn.execute(f"DELETE FROM {collection} WHERE id = ?", (item_id,))
        conn.commit()
        return {"deleted": True}


# ---------------------------------------------------------------- config (single row)
@app.put("/api/v1/config")
def save_config(payload: dict = Body(...)):
    """Config is small and edited frequently from many places; last-write-wins."""
    data = dict(payload)
    data.pop("_version", None)
    body = json.dumps(data)
    with _lock, db() as conn:
        row = conn.execute("SELECT version FROM config WHERE id = 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO config (id, version, data) VALUES (1, 1, ?)", (body,))
            conn.commit()
            return {"_version": 1}
        new_version = row["version"] + 1
        conn.execute("UPDATE config SET version = ?, data = ? WHERE id = 1", (new_version, body))
        conn.commit()
        return {"_version": new_version}


# ---------------------------------------------------------------- health + app
@app.get("/api/v1/ping")
def ping():
    return {"service": "nds", "ok": True, "collections": COLLECTIONS}


@app.get("/")
def root():
    if os.path.exists(INDEX_HTML):
        return FileResponse(INDEX_HTML)
    return JSONResponse(
        {"message": "NDS API is running. Place index.html next to server.py to serve the app here."}
    )


if __name__ == "__main__":
    import uvicorn
    print("Network Device Standards API")
    print(f"  Database: {DB_PATH}")
    print(f"  App file: {INDEX_HTML}  ({'found' if os.path.exists(INDEX_HTML) else 'MISSING - copy your index.html here'})")
    print("  Open http://localhost:8000 in a browser, or share the machine's address with your team.")
    uvicorn.run(app, host="0.0.0.0", port=8000)
