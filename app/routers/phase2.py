import json
import os
import random
import sqlite3
import threading
import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Query
from app import config
from app.deps import require_admin, require_user
from app.services import etl

router = APIRouter(prefix="/api")
STATE = {"running": False, "log": [], "error": None, "started": None, "finished": None}
SUMMARY_TABLES = ["summary_year", "summary_category", "summary_tier", "summary_hour_weekday", "summary_hashtags"]
COLS = "combined_id, source, original_post_id, text, hashtags, hashtag_count, mention_count, text_length, likes, comments, engagement"


def _db():
    """Read-only connection to the warehouse."""
    if not os.path.exists(config.WAREHOUSE):
        raise HTTPException(404, "Warehouse not built yet. An admin must run the ETL first.")
    return sqlite3.connect(f"file:{config.WAREHOUSE}?mode=ro", uri=True)


def _worker():
    try:
        etl.run_etl(lambda m: STATE["log"].append(f"{dt.datetime.now():%H:%M:%S}  {m}"))
        try:                                                 # pre-build the cube cache for the new warehouse
            from app.routers import extra
            extra.cube_payload()
            from app.services import mining
            mining.start()                                   # retrain the mining models on the new warehouse
        except Exception:
            pass
    except Exception as e:                                   # shown to the admin
        STATE["error"] = str(e)
        STATE["log"].append("ERROR: " + str(e))
    finally:
        STATE["running"] = False
        STATE["finished"] = dt.datetime.now().isoformat(timespec="seconds")


# ---------------- ETL ----------------
def start():
    if STATE["running"]:
        raise HTTPException(409, "ETL is already running")
    STATE.update(running=True, log=[], error=None, started=dt.datetime.now().isoformat(timespec="seconds"), finished=None)
    threading.Thread(target=_worker, daemon=True).start()
    return {"started": True}


@router.post("/etl/run")
def run(_=Depends(require_admin)):
    return start()


@router.get("/etl/status")
def status(_=Depends(require_user)):
    return STATE


@router.get("/etl/lineage")
def lineage(_=Depends(require_user)):
    if not os.path.exists(config.LINEAGE):
        raise HTTPException(404, "No ETL run yet")
    with open(config.LINEAGE) as fh:
        return json.load(fh)


# ---------------- dataset viewer ----------------
@router.get("/data/sample")
def sample(_=Depends(require_user)):
    """100 random rows of the combined dataset (same sample all day)."""
    con = _db()
    n = con.execute("SELECT COUNT(*) FROM combined_posts").fetchone()[0]
    ids = random.Random(dt.date.today().toordinal()).sample(range(1, n + 1), min(100, n))
    cur = con.execute(f"SELECT {COLS} FROM combined_posts WHERE combined_id IN ({','.join('?' * len(ids))}) ORDER BY combined_id", ids)
    cols = [c[0] for c in cur.description]
    return {"columns": cols, "rows": cur.fetchall(), "total": n, "sample": True}


@router.get("/data/combined")
def combined(page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200), q: str = "", source: str = "",
             _=Depends(require_admin)):
    """Full combined dataset with search and paging (admin only)."""
    where, params = [], []
    if q:
        where.append("(text LIKE ? OR hashtags LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if source in ("posts_dataset", "reach_dataset"):
        where.append("source = ?")
        params.append(source)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    con = _db()
    total = con.execute(f"SELECT COUNT(*) FROM combined_posts {w}", params).fetchone()[0]
    cur = con.execute(f"SELECT {COLS} FROM combined_posts {w} ORDER BY combined_id LIMIT ? OFFSET ?", params + [size, (page - 1) * size])
    return {"columns": [c[0] for c in cur.description], "rows": cur.fetchall(), "total": total,
            "page": page, "size": size, "pages": max(1, -(-total // size))}


# ---------------- pre-calculated summary tables ----------------
@router.get("/summary")
def summary_list(_=Depends(require_user)):
    return SUMMARY_TABLES


@router.get("/summary/{name}")
def summary(name: str, _=Depends(require_user)):
    if name not in SUMMARY_TABLES:                           # whitelist: no SQL injection possible
        raise HTTPException(404, "Unknown summary table")
    cur = _db().execute(f"SELECT * FROM {name}")
    return {"columns": [c[0] for c in cur.description], "rows": cur.fetchall()}
