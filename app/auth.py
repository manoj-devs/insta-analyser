"""Authentication for TWO separate portals.

  user portal   /        cookie iw_user   endpoints /api/auth/*          role 'user' only
  admin portal  /admin   cookie iw_admin  endpoints /api/admin/auth/*    role 'admin' only (password + emailed code)

A user account can never sign in to the admin portal and an admin account can never sign in to the user portal.
"""
import os, secrets, time
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from app import db, otp, security

COOKIE = {"user": "iw_user", "admin": "iw_admin"}
SESSION_SECONDS = {"user": 8 * 3600, "admin": 4 * 3600}
IDLE_SECONDS = {"user": 4 * 3600, "admin": 30 * 60}         # admin is signed out after 30 minutes without activity
MAX_SESSIONS = 5
ADMIN_2FA = os.getenv("ADMIN_2FA", "1") != "0"              # admin sign-in needs password AND an emailed code
DEFAULT_ADMIN_PW = "Admin@12345"
router = APIRouter(prefix="/api")
now = time.time


def is_https(request):
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https" or os.getenv("COOKIE_SECURE") == "1"


def _info(request):
    return (request.client.host if request and request.client else ""), (request.headers.get("user-agent", "")[:200] if request else "")


def audit(event, user_id=None, email=None, request=None, detail=""):
    ip, ua = _info(request)
    c = db.conn()
    c.execute("INSERT INTO audit(ts,user_id,email,event,ip,ua,detail) VALUES (?,?,?,?,?,?,?)", (now(), user_id, email, event, ip, ua, detail))
    c.commit(); c.close()


def ensure_admin():
    c = db.conn()
    if not c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        email = os.getenv("ADMIN_EMAIL", "admin@instawarehouse.com").lower()
        env_pw = os.getenv("ADMIN_PASSWORD")
        c.execute("INSERT INTO users(email,name,pw,role,status,verified,created,must_change) VALUES (?,?,?,?,?,1,?,?)",
                  (email, "Administrator", security.hash_pw(env_pw or DEFAULT_ADMIN_PW), "admin", "active", now(), 0 if env_pw else 1))
        c.commit()
    c.close()


# ---------------- sessions ----------------
def current_user(request, kind=None):
    for k in ([kind] if kind else ["user", "admin"]):
        t = request.cookies.get(COOKIE[k])
        if not t: continue
        c = db.conn()
        r = c.execute("SELECT u.id,u.email,u.name,u.role,u.status,u.must_change,s.expires,s.last_seen,s.kind FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (t,)).fetchone()
        ok = bool(r) and r["kind"] == k and r["expires"] > now() and r["status"] == "active" \
            and now() - (r["last_seen"] or 0) <= IDLE_SECONDS[k] and (r["role"] == "admin") == (k == "admin")
        if not ok:
            if r: c.execute("DELETE FROM sessions WHERE token=?", (t,)); c.commit()
            c.close(); continue
        if not request.headers.get("x-background"):        # background refreshes must not keep an idle admin signed in
            c.execute("UPDATE sessions SET last_seen=? WHERE token=?", (now(), t)); c.commit()
        c.close()
        d = dict(r); d["token"] = t; d["portal"] = k
        return d
    return None


def require_user(request: Request):
    """Any signed-in person (user portal or admin portal). Used by the shared data endpoints."""
    u = current_user(request)
    if not u: raise HTTPException(401, "Please sign in.")
    if u["must_change"]: raise HTTPException(403, "Please change your password first.")
    return u


def require_portal_user(request: Request):
    u = current_user(request, "user")
    if not u: raise HTTPException(401, "Please sign in.")
    return u


def require_admin_nochange(request: Request):
    u = current_user(request, "admin")
    if not u: raise HTTPException(401, "Please sign in as an administrator.")
    return u


def require_admin(request: Request):
    u = require_admin_nochange(request)
    if u["must_change"]: raise HTTPException(403, "Please change the default password first.")
    return u


def _start_session(response, request, uid, kind):
    c = db.conn(); ip, ua = _info(request)
    old = request.cookies.get(COOKIE[kind])
    if old: c.execute("DELETE FROM sessions WHERE token=?", (old,))                # a new token on every sign-in
    c.execute("DELETE FROM sessions WHERE expires<?", (now(),))
    rows = c.execute("SELECT token FROM sessions WHERE user_id=? ORDER BY created DESC", (uid,)).fetchall()
    for r in rows[MAX_SESSIONS - 1:]: c.execute("DELETE FROM sessions WHERE token=?", (r["token"],))
    token = secrets.token_urlsafe(32)
    c.execute("INSERT INTO sessions(token,user_id,created,expires,last_seen,ip,ua,kind) VALUES (?,?,?,?,?,?,?,?)",
              (token, uid, now(), now() + SESSION_SECONDS[kind], now(), ip, ua, kind))
    c.execute("UPDATE users SET last_login=?, login_count=COALESCE(login_count,0)+1 WHERE id=?", (now(), uid))
    c.commit(); c.close()
    response.set_cookie(COOKIE[kind], token, httponly=True, samesite="strict", max_age=SESSION_SECONDS[kind], path="/", secure=is_https(request))


def _public(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "must_change": bool(u["must_change"])}


# ---------------- models ----------------
class SignupIn(BaseModel):
    name: str; email: str; password: str
    phone: str = ""; country: str = ""; user_type: str = "creator"; handle: str = ""; interests: str = ""; consent: bool = False
class LoginIn(BaseModel):
    email: str; password: str
class VerifyIn(BaseModel):
    email: str; code: str; ticket: str = ""
class ResendIn(BaseModel):
    email: str; ticket: str = ""
class EmailIn(BaseModel):
    email: str
class ResetIn(BaseModel):
    email: str; ticket: str = ""; password: str
class PwChangeIn(BaseModel):
    current: str; new: str
class ReasonIn(BaseModel):
    reason: str = ""


def _lockout(c, email, ip):
    if c.execute("SELECT COUNT(*) FROM audit WHERE event='login_fail' AND email=? AND ts>?", (email, now() - 600)).fetchone()[0] >= 5:
        raise HTTPException(429, "Too many failed attempts. This account is locked for 10 minutes.")
    if c.execute("SELECT COUNT(*) FROM audit WHERE event='login_fail' AND ip=? AND ts>?", (ip, now() - 600)).fetchone()[0] >= 15:
        raise HTTPException(429, "Too many failed attempts from this device. Try again in 10 minutes.")


def _status_check(u, request, portal):
    if u["status"] == "blocked":
        audit("login_denied", u["id"], u["email"], request, f"blocked ({portal})")
        raise HTTPException(403, f"Your account has been blocked by the administrator. Reason: {u['reason'] or 'not specified'}.")
    if u["status"] == "deleted":
        audit("login_denied", u["id"], u["email"], request, f"deleted ({portal})")
        raise HTTPException(403, f"Your account was removed by the administrator. Reason: {u['reason'] or 'not specified'}.")


# ================= USER PORTAL =================
@router.post("/auth/signup")
def signup(b: SignupIn, request: Request):
    email, name = b.email.strip().lower(), " ".join(b.name.split())
    if not (2 <= len(name) <= 60): raise HTTPException(400, "Please enter your name (2 to 60 characters).")
    if not security.EMAIL_RE.match(email): raise HTTPException(400, "Please enter a valid email address.")
    if email.split("@")[1] in security.DISPOSABLE: raise HTTPException(400, "Disposable email addresses are not allowed.")
    p = security.password_problem(b.password, email, name)
    if p: raise HTTPException(400, p)
    phone = b.phone.replace(" ", "").replace("-", "")
    if phone and not security.PHONE_RE.match(phone): raise HTTPException(400, "Phone number must have 8 to 15 digits (a leading + is allowed).")
    country = " ".join(b.country.split())
    if not (2 <= len(country) <= 60): raise HTTPException(400, "Please choose your country.")
    if b.user_type not in security.USER_TYPES: raise HTTPException(400, "Please choose what describes you best.")
    handle = b.handle.strip()
    if handle and not security.HANDLE_RE.match(handle): raise HTTPException(400, "Instagram handle may contain letters, numbers, dots and underscores only.")
    handle = ("@" + handle.lstrip("@").lower()) if handle else ""
    interests = " ".join(b.interests.split())[:120]
    if not b.consent: raise HTTPException(400, "Please accept the terms and the data-collection notice to continue.")
    ip, _ = _info(request); c = db.conn()
    if c.execute("SELECT COUNT(*) FROM audit WHERE event='signup' AND ip=? AND ts>?", (ip, now() - 3600)).fetchone()[0] >= 5:
        c.close(); raise HTTPException(429, "Too many sign-ups from this device. Try again later.")
    u = c.execute("SELECT id,verified FROM users WHERE email=?", (email,)).fetchone()
    if u and u["verified"]: c.close(); raise HTTPException(409, "This email is already registered. Please sign in.")
    vals = (name, security.hash_pw(b.password), phone or None, country, b.user_type, handle or None, interests or None, now(), ip)
    if u:
        c.execute("UPDATE users SET name=?, pw=?, phone=?, country=?, user_type=?, handle=?, interests=?, consent_at=?, signup_ip=? WHERE id=?", vals + (u["id"],))
    else:
        c.execute("INSERT INTO users(name,pw,phone,country,user_type,handle,interests,consent_at,signup_ip,email,role,status,verified,created) VALUES (?,?,?,?,?,?,?,?,?,?,'user','active',0,?)", vals + (email, now()))
    c.commit(); uid = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
    audit("signup", uid, email, request, f"{b.user_type}, {country}")
    try: return otp.issue(c, c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(), "verify", request)
    finally: c.close()


def _pending_user(c, email, ticket, purposes, role="user"):
    u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u or u["role"] != role or u["otp_purpose"] not in purposes or not otp.ticket_ok(u, ticket):
        raise otp.err(400, "There is no active code. Please start again.", "none")
    return u


@router.post("/auth/resend")
def resend(b: ResendIn, request: Request):
    email = b.email.strip().lower(); c = db.conn()
    try:
        u = _pending_user(c, email, b.ticket, ("verify", "login", "reset"))
        _status_check(u, request, "user")
        return otp.issue(c, u, u["otp_purpose"], request)           # sending a new code cancels the older one
    finally: c.close()


@router.post("/auth/verify")
def verify(b: VerifyIn, request: Request, response: Response):
    """Checks the code from the pop-up. Used for sign-up verification AND for sign-in from a new device."""
    email = b.email.strip().lower(); c = db.conn()
    try:
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u is not None and u["role"] != "user": u = None
        purpose = otp.check(c, u, b.code, b.ticket, ("verify", "login"), request)
        _status_check(u, request, "user")
        if purpose == "verify": c.execute("UPDATE users SET verified=1 WHERE id=?", (u["id"],)); c.commit()
        otp.trust_device(c, u, request, response)
    finally: c.close()
    _start_session(response, request, u["id"], "user")
    audit("verify" if purpose == "verify" else "otp_login", u["id"], email, request); audit("login_success", u["id"], email, request, f"user portal, code accepted ({purpose})")
    return {"ok": True, "user": _public(u)}


@router.post("/auth/login")
def login(b: LoginIn, request: Request, response: Response):
    email = b.email.strip().lower(); ip, _ = _info(request); c = db.conn()
    try: _lockout(c, email, ip)
    except HTTPException: c.close(); raise
    u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u or not security.check_pw(b.password, u["pw"]):
        c.close(); audit("login_fail", u["id"] if u else None, email, request, "user portal"); raise HTTPException(401, "Invalid email or password.")
    if u["role"] == "admin":
        c.close(); audit("login_denied", u["id"], email, request, "admin tried the user portal")
        raise HTTPException(403, "Administrators sign in on the admin portal: open /admin.")
    _status_check(u, request, "user")
    try:
        if not u["verified"]:                                     # finish verification instead of dead-ending
            out = otp.issue(c, u, "verify", request, soft=True); out["needs_verification"] = True; out["needs_otp"] = True; return out
        if otp.needs_login_otp(c, u, request):                    # new device (or OTP_LOGIN=always): ask for a code in the pop-up
            out = otp.issue(c, u, "login", request, soft=True); out["needs_otp"] = True; return out
        otp.trust_device(c, u, request, response) if otp.LOGIN_POLICY != "never" else None
    finally: c.close()
    _start_session(response, request, u["id"], "user"); audit("login_success", u["id"], email, request, "user portal")
    return {"ok": True, "user": _public(u)}


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    u = current_user(request, "user"); t = request.cookies.get(COOKIE["user"])
    if t:
        c = db.conn(); c.execute("DELETE FROM sessions WHERE token=?", (t,)); c.commit(); c.close()
    if u: audit("logout", u["id"], u["email"], request, "user portal")
    response.delete_cookie(COOKIE["user"], path="/"); return {"ok": True}


@router.get("/auth/me")
def me(request: Request):
    u = require_portal_user(request); return _public(u)


@router.post("/auth/forgot")
def forgot(b: EmailIn, request: Request):
    email = b.email.strip().lower(); ip, _ = _info(request); c = db.conn()
    try:
        if c.execute("SELECT COUNT(*) FROM audit WHERE event='reset_request' AND (ip=? OR email=?) AND ts>?", (ip, email, now() - 3600)).fetchone()[0] >= 5:
            raise HTTPException(429, "Too many reset requests. Try again in an hour.")
        audit("reset_request", None, email, request)
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u and u["verified"] and u["status"] == "active" and u["role"] == "user": return otp.issue(c, u, "reset", request)
        return otp.fake_info(email)                              # same answer: no account guessing
    finally: c.close()


@router.post("/auth/reset/verify")
def reset_verify(b: VerifyIn, request: Request):
    """Step 1 of a password reset: the pop-up checks the code. Step 2 (/auth/reset) sets the new password."""
    email = b.email.strip().lower(); c = db.conn()
    try:
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u is not None and u["role"] != "user": u = None
        otp.check(c, u, b.code, b.ticket, ("reset",), request)
    finally: c.close()
    return {"ok": True}


@router.post("/auth/reset")
def reset(b: ResetIn, request: Request):
    email = b.email.strip().lower(); c = db.conn()
    u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u or u["role"] != "user" or u["otp_purpose"] != "reset_ok" or not otp.ticket_ok(u, b.ticket) or (u["otp_exp"] or 0) < now():
        c.close(); raise otp.err(400, "Your reset session has ended. Please start again.", "none")
    p = security.password_problem(b.password, email, u["name"])
    if p: c.close(); raise HTTPException(400, p)
    c.execute("UPDATE users SET pw=?, pw_changed=?, otp=NULL, otp_purpose=NULL, otp_ticket=NULL, otp_exp=NULL WHERE id=?", (security.hash_pw(b.password), now(), u["id"]))
    c.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],)); c.execute("DELETE FROM devices WHERE user_id=?", (u["id"],)); c.commit(); c.close()
    audit("password_reset", u["id"], email, request, "all devices signed out"); return {"ok": True}


def change_password(request, u, b: PwChangeIn):
    c = db.conn(); row = c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
    if not security.check_pw(b.current, row["pw"]):
        c.close(); audit("password_change_fail", u["id"], u["email"], request); raise HTTPException(400, "Your current password is not correct.")
    p = security.password_problem(b.new, u["email"], u["name"])
    if p: c.close(); raise HTTPException(400, p)
    if security.check_pw(b.new, row["pw"]): c.close(); raise HTTPException(400, "The new password must be different from the current one.")
    c.execute("UPDATE users SET pw=?, pw_changed=?, must_change=0 WHERE id=?", (security.hash_pw(b.new), now(), u["id"]))
    c.execute("DELETE FROM sessions WHERE user_id=? AND token!=?", (u["id"], u["token"]))                     # every other device is signed out
    cur = request.cookies.get(otp.DEVICE_COOKIE)
    c.execute("DELETE FROM devices WHERE user_id=? AND token_hash!=?", (u["id"], otp._tick(cur or "")))       # and has to use a code again
    c.commit(); c.close()
    audit("password_changed", u["id"], u["email"], request, "other sessions closed"); return {"ok": True}


# ================= ADMIN PORTAL =================
@router.post("/admin/auth/login")
def admin_login(b: LoginIn, request: Request, response: Response):
    email = b.email.strip().lower(); ip, _ = _info(request); c = db.conn()
    try: _lockout(c, email, ip)
    except HTTPException: c.close(); raise
    u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u or not security.check_pw(b.password, u["pw"]) or u["role"] != "admin":
        c.close(); audit("login_fail", u["id"] if u else None, email, request, "admin portal"); raise HTTPException(401, "Invalid email or password.")
    _status_check(u, request, "admin")
    if ADMIN_2FA and not u["must_change"]:
        try: out = otp.issue(c, u, "2fa", request, soft=True)
        finally: c.close()
        out["step"] = "code"; out["needs_otp"] = True; return out
    c.close(); _start_session(response, request, u["id"], "admin"); audit("login_success", u["id"], email, request, "admin portal")
    return {"ok": True, "step": "done", "user": _public(u)}


@router.post("/admin/auth/resend")
def admin_resend(b: ResendIn, request: Request):
    email = b.email.strip().lower(); c = db.conn()
    try:
        u = _pending_user(c, email, b.ticket, ("2fa",), role="admin")
        return otp.issue(c, u, "2fa", request)
    finally: c.close()


@router.post("/admin/auth/verify")
def admin_verify(b: VerifyIn, request: Request, response: Response):
    email = b.email.strip().lower(); c = db.conn()
    u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if u is not None and u["role"] != "admin": u = None
    try: otp.check(c, u, b.code, b.ticket, ("2fa",), request)
    except HTTPException:
        c.close(); audit("login_fail", u["id"] if u else None, email, request, "admin portal, wrong code"); raise
    c.close(); _start_session(response, request, u["id"], "admin"); audit("login_success", u["id"], email, request, "admin portal, 2-step")
    return {"ok": True, "step": "done", "user": _public(u)}


@router.post("/admin/auth/logout")
def admin_logout(request: Request, response: Response):
    u = current_user(request, "admin"); t = request.cookies.get(COOKIE["admin"])
    if t:
        c = db.conn(); c.execute("DELETE FROM sessions WHERE token=?", (t,)); c.commit(); c.close()
    if u: audit("logout", u["id"], u["email"], request, "admin portal")
    response.delete_cookie(COOKIE["admin"], path="/"); return {"ok": True}


@router.get("/admin/auth/me")
def admin_me(request: Request):
    return _public(require_admin_nochange(request))


@router.post("/admin/auth/password")
def admin_password(b: PwChangeIn, request: Request):
    return change_password(request, require_admin_nochange(request), b)
