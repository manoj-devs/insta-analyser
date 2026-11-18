"""Admin operations: recent admin sign-ins, database backup and restore."""
import os, shutil, sqlite3, tempfile, time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from app import config, db, publicmode
from app.auth import audit, require_admin

router = APIRouter(prefix="/api/admin")


@router.get("/logins")
def logins(u=Depends(require_admin)):
    c = db.conn()
    rows = c.execute("""SELECT ts,email,event,ip,ua,detail FROM audit WHERE event IN ('login_success','login_fail','login_denied','otp_locked','rate_limited')
                        AND (detail LIKE 'admin portal%' OR detail LIKE '%admin%') ORDER BY ts DESC LIMIT 20""").fetchall(); c.close()
    return {"public": config.PUBLIC_MODE, "allowed_ips": publicmode.ADMIN_ALLOWED_IPS, "rows": [dict(r) for r in rows]}


@router.get("/backup")
def backup(request: Request, u=Depends(require_admin)):
    """a consistent copy of the user/auth database (users, devices, analyses, directory). Contains personal data: keep it private."""
    fd, tmp = tempfile.mkstemp(suffix=".db"); os.close(fd)
    src = sqlite3.connect(config.AUTH_DB); dst = sqlite3.connect(tmp)
    try: src.backup(dst)
    finally: dst.close(); src.close()
    audit("backup_download", u["id"], u["email"], request, "auth database")
    return FileResponse(tmp, media_type="application/octet-stream", filename=f"instawarehouse_backup_{time.strftime('%Y%m%d_%H%M')}.db",
                        background=BackgroundTask(lambda: os.path.exists(tmp) and os.remove(tmp)), headers={"Cache-Control": "no-store"})


@router.post("/restore")
async def restore(request: Request, confirm: str = "", u=Depends(require_admin)):
    if confirm != "RESTORE": raise HTTPException(400, "Type RESTORE to confirm.")
    data = await request.body()
    if len(data) < 4096 or not data.startswith(b"SQLite format 3\x00"): raise HTTPException(400, "That is not an InstaWarehouse backup file.")
    if len(data) > 300_000_000: raise HTTPException(400, "The file is too large.")
    fd, tmp = tempfile.mkstemp(suffix=".db"); os.close(fd)
    with open(tmp, "wb") as f: f.write(data)
    try:
        t = sqlite3.connect(tmp)
        ok = t.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        names = {r[0] for r in t.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        admins = t.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] if "users" in names else 0
        t.close()
    except sqlite3.Error: ok, names, admins = False, set(), 0
    if not ok or not {"users", "sessions", "audit"} <= names or admins < 1:
        os.remove(tmp); raise HTTPException(400, "The file is damaged or is not a backup of this system (it must contain the users and at least one administrator).")
    keep = config.AUTH_DB + ".before_restore"
    shutil.copyfile(config.AUTH_DB, keep); shutil.copyfile(tmp, config.AUTH_DB); os.remove(tmp)
    db.init()                                   # adds any table the older backup does not have yet
    from app.services import directory; directory._CACHE["ver"] += 1
    audit("restore", None, u["email"], request, "database restored; previous copy kept as auth.db.before_restore")
    return {"ok": True, "note": "Restored. Everyone, including you, has to sign in again if their session is not in the backup."}
