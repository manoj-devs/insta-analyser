"""User portal: profile, password, devices, analysis history, feedback, data export, usage tracking."""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
import os, secrets
from app import config
from pydantic import BaseModel, Field
from app import db, security
from app.auth import audit, change_password, now, require_portal_user, require_user, PwChangeIn

router = APIRouter(prefix="/api")
PAGES = {"dashboard", "cube", "schema", "pipeline", "analyser", "history", "account",
         "region", "regions", "creator", "creator_plan", "creator_hist", "overview", "users", "activity", "submissions", "admins", "influencer", "caption", "mining", "lab"}


class ProfileIn(BaseModel):
    name: str; phone: str = ""; country: str = ""; user_type: str = "creator"; handle: str = ""; interests: str = ""


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5); topic: str = "general"; message: str = Field(min_length=3, max_length=1000)


class TrackIn(BaseModel):
    page: str


def _profile(u):
    c = db.conn(); r = c.execute("SELECT name,email,phone,country,user_type,handle,interests,created,last_login,login_count,pw_changed,consent_at,avatar FROM users WHERE id=?", (u["id"],)).fetchone(); c.close()
    return dict(r)


@router.get("/account/profile")
def get_profile(u=Depends(require_portal_user)):
    return _profile(u)


@router.put("/account/profile")
def put_profile(b: ProfileIn, request: Request, u=Depends(require_portal_user)):
    name = " ".join(b.name.split())
    if not (2 <= len(name) <= 60): raise HTTPException(400, "Please enter your name (2 to 60 characters).")
    phone = b.phone.replace(" ", "").replace("-", "")
    if phone and not security.PHONE_RE.match(phone): raise HTTPException(400, "Phone number must have 8 to 15 digits.")
    country = " ".join(b.country.split())
    if not (2 <= len(country) <= 60): raise HTTPException(400, "Please choose your country.")
    if b.user_type not in security.USER_TYPES: raise HTTPException(400, "Please choose what describes you best.")
    handle = b.handle.strip()
    if handle and not security.HANDLE_RE.match(handle): raise HTTPException(400, "Instagram handle may contain letters, numbers, dots and underscores only.")
    handle = ("@" + handle.lstrip("@").lower()) if handle else None
    c = db.conn()
    c.execute("UPDATE users SET name=?, phone=?, country=?, user_type=?, handle=?, interests=? WHERE id=?",
              (name, phone or None, country, b.user_type, handle, " ".join(b.interests.split())[:120] or None, u["id"])); c.commit(); c.close()
    audit("profile_updated", u["id"], u["email"], request); return _profile(u)


@router.post("/account/password")
def password(b: PwChangeIn, request: Request, u=Depends(require_portal_user)):
    return change_password(request, u, b)


@router.get("/account/sessions")
def sessions(u=Depends(require_portal_user)):
    c = db.conn()
    rows = c.execute("SELECT token,ip,ua,created,last_seen FROM sessions WHERE user_id=? AND kind='user' AND expires>? ORDER BY last_seen DESC", (u["id"], now())).fetchall(); c.close()
    return [{"ip": r["ip"], "ua": r["ua"], "created": r["created"], "last_seen": r["last_seen"], "current": r["token"] == u["token"]} for r in rows]


@router.post("/account/sessions/revoke-others")
def revoke_others(request: Request, u=Depends(require_portal_user)):
    c = db.conn(); n = c.execute("DELETE FROM sessions WHERE user_id=? AND token!=?", (u["id"], u["token"])).rowcount; c.commit(); c.close()
    audit("sessions_revoked", u["id"], u["email"], request, f"{n} other device(s) signed out"); return {"ok": True, "closed": n}


@router.get("/account/history")
def history(u=Depends(require_portal_user)):
    c = db.conn()
    rows = c.execute("SELECT id,ts,handle,followers,tier,category,account_type,avg_likes,avg_comments,hashtags,posts_per_week,score,income_per_post,income_monthly FROM analyses WHERE user_id=? ORDER BY ts DESC LIMIT 100", (u["id"],)).fetchall(); c.close()
    return [dict(r) for r in rows]


@router.delete("/account/history/{aid}")
def delete_history(aid: int, request: Request, u=Depends(require_portal_user)):
    c = db.conn(); n = c.execute("DELETE FROM analyses WHERE id=? AND user_id=?", (aid, u["id"])).rowcount; c.commit(); c.close()
    if not n: raise HTTPException(404, "Not found.")
    return {"ok": True}


@router.post("/account/feedback")
def feedback(b: FeedbackIn, request: Request, u=Depends(require_portal_user)):
    if b.topic not in ("general", "analyser", "cube", "dashboard", "login", "other"): raise HTTPException(400, "Unknown topic.")
    c = db.conn(); c.execute("INSERT INTO feedback(ts,user_id,rating,topic,message) VALUES (?,?,?,?,?)", (now(), u["id"], b.rating, b.topic, b.message.strip())); c.commit(); c.close()
    audit("feedback", u["id"], u["email"], request, f"{b.rating}/5 {b.topic}"); return {"ok": True}


@router.get("/account/export")
def export(request: Request, u=Depends(require_portal_user)):
    """Everything the system stores about the signed-in user (transparency)."""
    c = db.conn(); rows = lambda s: [dict(r) for r in c.execute(s, (u["id"],))]
    data = {"profile": _profile(u),
            "analyses": rows("SELECT * FROM analyses WHERE user_id=?"), "feedback": rows("SELECT ts,rating,topic,message FROM feedback WHERE user_id=?"),
            "page_visits": rows("SELECT ts,name FROM events WHERE user_id=? AND kind='page'"),
            "sign_in_history": rows("SELECT ts,event,ip,ua,detail FROM audit WHERE user_id=? ORDER BY id DESC LIMIT 500")}
    c.close(); audit("data_export", u["id"], u["email"], request)
    return Response(json.dumps(data, indent=2, default=str), media_type="application/json", headers={"Content-Disposition": "attachment; filename=my_data.json"})


@router.post("/track")
def track(b: TrackIn, u=Depends(require_user)):
    if b.page in PAGES:
        c = db.conn(); c.execute("INSERT INTO events(ts,user_id,kind,name) VALUES (?,?,'page',?)", (now(), u["id"], b.page)); c.commit(); c.close()
    return {"ok": True}


# ---------------- trusted devices (browsers that may sign in without a new code) ----------------
@router.get("/account/devices")
def devices(request: Request, u=Depends(require_portal_user)):
    from app import otp
    c = db.conn(); cur = request.cookies.get(otp.DEVICE_COOKIE)
    cur_hash = otp._tick(cur) if cur else None
    rows = c.execute("SELECT id,token_hash,label,ip,first_seen,last_seen FROM devices WHERE user_id=? ORDER BY last_seen DESC", (u["id"],)).fetchall(); c.close()
    return [{"id": r["id"], "label": r["label"], "ip": r["ip"], "first_seen": r["first_seen"], "last_seen": r["last_seen"], "current": r["token_hash"] == cur_hash} for r in rows]


@router.delete("/account/devices/{did}")
def forget_device(did: int, request: Request, u=Depends(require_portal_user)):
    c = db.conn(); n = c.execute("DELETE FROM devices WHERE id=? AND user_id=?", (did, u["id"])).rowcount; c.commit(); c.close()
    if not n: raise HTTPException(404, "That device is not in your list.")
    audit("device_forgotten", u["id"], u["email"], request); return {"ok": True}


# ---------------- profile picture: stored on the server, so every device shows the same one ----------------
_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"RIFF", "webp"))
_MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


@router.post("/account/avatar")
async def upload_avatar(request: Request, u=Depends(require_portal_user)):
    data = await request.body()
    if not data: raise HTTPException(400, "Please choose a picture.")
    if len(data) > 1_000_000: raise HTTPException(400, "The picture is too big. Please use one under 1 MB.")
    ext = next((e for m, e in _MAGIC if data.startswith(m) and (e != "webp" or data[8:12] == b"WEBP")), None)
    if not ext: raise HTTPException(400, "Please upload a PNG, JPG or WebP picture.")
    name = f"u{u['id']}_{secrets.token_hex(6)}.{ext}"
    with open(os.path.join(config.UPLOAD_DIR, name), "wb") as f: f.write(data)
    c = db.conn(); old = c.execute("SELECT avatar FROM users WHERE id=?", (u["id"],)).fetchone()["avatar"]
    c.execute("UPDATE users SET avatar=? WHERE id=?", (name, u["id"])); c.commit(); c.close()
    if old and os.path.basename(old) == old:
        try: os.remove(os.path.join(config.UPLOAD_DIR, old))
        except OSError: pass
    audit("avatar_changed", u["id"], u["email"], request); return {"ok": True, "avatar": name}


@router.get("/account/avatar")
def get_avatar(u=Depends(require_portal_user)):
    c = db.conn(); r = c.execute("SELECT avatar FROM users WHERE id=?", (u["id"],)).fetchone(); c.close()
    name = r["avatar"] if r else None
    path = os.path.join(config.UPLOAD_DIR, os.path.basename(name)) if name else None
    if not path or not os.path.exists(path): raise HTTPException(404, "No picture.")
    return FileResponse(path, media_type=_MIME.get(name.rsplit(".", 1)[-1], "application/octet-stream"), headers={"Cache-Control": "private, max-age=60", "X-Content-Type-Options": "nosniff"})
