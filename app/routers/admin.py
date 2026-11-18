"""Admin portal API: overview, users, activity, collected submissions, feedback, admin accounts."""
import csv, io, time, datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app import db, security
from app.auth import audit, require_admin, ReasonIn, now

router = APIRouter(prefix="/api/admin")


def _csv(name, header, rows):
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(header)
    for r in rows: w.writerow(list(r))
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename={name}"})


def _days(c, sql, params=(), n=14):
    """Zero-filled per-day counts for the last n days. sql must return (day, count)."""
    got = {r[0]: r[1] for r in c.execute(sql, params)}
    out = []
    for i in range(n - 1, -1, -1):
        d = (dt.date.today() - dt.timedelta(days=i)).isoformat()
        out.append([d[5:], got.get(d, 0)])
    return out


# ---------------- overview ----------------
@router.get("/overview")
def overview(request: Request, _=Depends(require_admin)):
    c = db.conn(); q = lambda s, p=(): c.execute(s, p).fetchone()[0]; t = now()
    day, week, since14 = t - 86400, t - 7 * 86400, t - 14 * 86400
    kpi = {
        "users": q("SELECT COUNT(*) FROM users WHERE role='user' AND status!='deleted' AND verified=1"),
        "pending": q("SELECT COUNT(*) FROM users WHERE role='user' AND verified=0"),
        "blocked": q("SELECT COUNT(*) FROM users WHERE status='blocked'"),
        "deleted": q("SELECT COUNT(*) FROM users WHERE status='deleted'"),
        "admins": q("SELECT COUNT(*) FROM users WHERE role='admin'"),
        "online": q("SELECT COUNT(DISTINCT user_id) FROM sessions WHERE expires>? AND last_seen>?", (t, t - 300)),
        "signups_7d": q("SELECT COUNT(*) FROM users WHERE role='user' AND verified=1 AND created>?", (week,)),
        "logins_24h": q("SELECT COUNT(*) FROM audit WHERE event='login_success' AND ts>?", (day,)),
        "failed_24h": q("SELECT COUNT(*) FROM audit WHERE event='login_fail' AND ts>?", (day,)),
        "analyses": q("SELECT COUNT(*) FROM analyses"), "analyses_7d": q("SELECT COUNT(*) FROM analyses WHERE ts>?", (week,)),
        "avg_score": round(q("SELECT COALESCE(AVG(score),0) FROM analyses"), 1),
        "feedback": q("SELECT COUNT(*) FROM feedback"), "avg_rating": round(q("SELECT COALESCE(AVG(rating),0) FROM feedback"), 2)}
    d = "date(ts,'unixepoch','localtime')"
    series = {
        "signups": _days(c, f"SELECT date(created,'unixepoch','localtime'), COUNT(*) FROM users WHERE role='user' AND verified=1 AND created>? GROUP BY 1", (since14,)),
        "logins": _days(c, f"SELECT {d}, COUNT(*) FROM audit WHERE event='login_success' AND ts>? GROUP BY 1", (since14,)),
        "analyses": _days(c, f"SELECT {d}, COUNT(*) FROM analyses WHERE ts>? GROUP BY 1", (since14,))}
    rows = lambda s, p=(): [list(r) for r in c.execute(s, p)]
    dist = {
        "user_type": rows("SELECT COALESCE(user_type,'unknown'), COUNT(*) FROM users WHERE role='user' AND verified=1 GROUP BY 1 ORDER BY 2 DESC"),
        "country": rows("SELECT COALESCE(country,'unknown'), COUNT(*) FROM users WHERE role='user' AND verified=1 GROUP BY 1 ORDER BY 2 DESC LIMIT 8"),
        "tier": rows("SELECT tier, COUNT(*) FROM analyses GROUP BY 1 ORDER BY 2 DESC"),
        "category": rows("SELECT category, COUNT(*) FROM analyses GROUP BY 1 ORDER BY 2 DESC LIMIT 8"),
        "pages": rows("SELECT name, COUNT(*) FROM events WHERE kind='page' AND ts>? GROUP BY 1 ORDER BY 2 DESC LIMIT 10", (t - 30 * 86400,)),
        "score": rows("SELECT CASE WHEN score<40 THEN 'Below 40' WHEN score<70 THEN '40 to 69' ELSE '70 and above' END, COUNT(*) FROM analyses GROUP BY 1")}
    c.close(); return {"kpi": kpi, "series": series, "dist": dist}


# ---------------- users ----------------
USER_SQL = """SELECT u.id,u.email,u.name,u.role,u.status,u.reason,u.verified,u.created,u.last_login,u.login_count,u.country,u.user_type,u.handle,
    (SELECT COUNT(*) FROM sessions s WHERE s.user_id=u.id AND s.expires>?) sessions,
    (SELECT COUNT(*) FROM analyses a WHERE a.user_id=u.id) analyses FROM users u"""


@router.get("/users")
def users(q: str = "", status: str = "", _=Depends(require_admin)):
    c = db.conn(); where, p = ["u.role='user'"], [now()]
    if q: where.append("(u.email LIKE ? OR u.name LIKE ? OR u.handle LIKE ?)"); p += [f"%{q}%"] * 3
    if status in ("active", "blocked", "deleted"): where.append("u.status=?"); p.append(status)
    if status == "pending": where.append("u.verified=0")
    rows = c.execute(USER_SQL + " WHERE " + " AND ".join(where) + " ORDER BY u.id DESC LIMIT 1000", p).fetchall(); c.close()
    return [dict(r) for r in rows]


@router.get("/users.csv")
def users_csv(_=Depends(require_admin)):
    c = db.conn()
    rows = c.execute("""SELECT id,email,name,phone,country,user_type,handle,interests,status,reason,verified,
        datetime(created,'unixepoch','localtime'),datetime(last_login,'unixepoch','localtime'),login_count,signup_ip,datetime(consent_at,'unixepoch','localtime')
        FROM users WHERE role='user' ORDER BY id""").fetchall(); c.close()
    return _csv("users.csv", ["id", "email", "name", "phone", "country", "type", "instagram handle", "interests", "status", "reason", "verified",
                              "created", "last login", "logins", "signup ip", "consent given"], rows)


@router.get("/users/{uid}")
def user_detail(uid: int, _=Depends(require_admin)):
    c = db.conn(); u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u: c.close(); raise HTTPException(404, "User not found.")
    keep = ["id", "email", "name", "role", "status", "reason", "verified", "created", "last_login", "login_count", "phone", "country",
            "user_type", "handle", "interests", "signup_ip", "consent_at", "pw_changed"]
    out = {"profile": {k: u[k] for k in keep}}
    out["sessions"] = [dict(r) for r in c.execute("SELECT kind,ip,ua,created,last_seen,expires FROM sessions WHERE user_id=? AND expires>? ORDER BY last_seen DESC", (uid, now()))]
    out["history"] = [dict(r) for r in c.execute("SELECT ts,event,ip,ua,detail FROM audit WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,))]
    out["analyses"] = [dict(r) for r in c.execute("SELECT ts,handle,followers,tier,category,score,income_per_post,income_monthly FROM analyses WHERE user_id=? ORDER BY ts DESC LIMIT 10", (uid,))]
    out["pages"] = [list(r) for r in c.execute("SELECT name, COUNT(*) FROM events WHERE user_id=? AND kind='page' GROUP BY 1 ORDER BY 2 DESC", (uid,))]
    c.close(); return out


def _set_status(request, uid, status, reason, event):
    me_ = require_admin(request); c = db.conn()
    u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u: c.close(); raise HTTPException(404, "User not found.")
    if u["role"] == "admin" or u["id"] == me_["id"]: c.close(); raise HTTPException(400, "Admin accounts cannot be blocked or deleted.")
    if status in ("blocked", "deleted") and len(reason.strip()) < 3: c.close(); raise HTTPException(400, "Please give a reason (at least 3 characters).")
    c.execute("UPDATE users SET status=?, reason=? WHERE id=?", (status, reason.strip() or None, uid))
    c.execute("DELETE FROM sessions WHERE user_id=?", (uid,)); c.commit(); c.close()      # instant sign-out everywhere
    audit(event, uid, u["email"], request, f"by {me_['email']}: {reason.strip()}"); return {"ok": True}


@router.post("/users/{uid}/block")
def block(uid: int, b: ReasonIn, request: Request): return _set_status(request, uid, "blocked", b.reason, "blocked")
@router.post("/users/{uid}/unblock")
def unblock(uid: int, request: Request): return _set_status(request, uid, "active", "", "unblocked")
@router.post("/users/{uid}/delete")
def delete(uid: int, b: ReasonIn, request: Request): return _set_status(request, uid, "deleted", b.reason, "deleted")


@router.post("/users/{uid}/logout")
def force_logout(uid: int, request: Request):
    me_ = require_admin(request); c = db.conn()
    u = c.execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()
    if not u: c.close(); raise HTTPException(404, "User not found.")
    n = c.execute("DELETE FROM sessions WHERE user_id=?", (uid,)).rowcount; c.commit(); c.close()
    audit("forced_logout", uid, u["email"], request, f"by {me_['email']}, {n} session(s)"); return {"ok": True, "closed": n}


# ---------------- activity ----------------
@router.get("/online")
def online(_=Depends(require_admin)):
    c = db.conn()
    rows = c.execute("""SELECT u.id,u.name,u.email,u.role,s.kind,s.ip,s.ua,s.created,s.last_seen FROM sessions s JOIN users u ON u.id=s.user_id
        WHERE s.expires>? AND s.last_seen>? ORDER BY s.last_seen DESC""", (now(), now() - 300)).fetchall(); c.close()
    seen, out = set(), []
    for r in rows:
        k = (r["id"], r["ua"], r["kind"])
        if k not in seen: seen.add(k); out.append(dict(r))
    return out


@router.get("/alerts")
def alerts(_=Depends(require_admin)):
    c = db.conn(); out = []
    def ids(emails):
        q = ",".join("?" * len(emails)) or "''"
        return [r[0] for r in c.execute(f"SELECT id FROM users WHERE role!='admin' AND status='active' AND email IN ({q})", list(emails)).fetchall()]
    for r in c.execute("SELECT email, COUNT(*) n FROM audit WHERE event='login_fail' AND ts>? AND email IS NOT NULL GROUP BY email HAVING n>=5", (now() - 900,)):
        out.append({"type": "Many failed logins", "severity": "high", "detail": f"{r['n']} failed sign-ins for {r['email']} in 15 minutes", "user_ids": ids([r["email"]])})
    for r in c.execute("SELECT ip, COUNT(*) n, GROUP_CONCAT(DISTINCT email) es FROM audit WHERE event='signup' AND ts>? GROUP BY ip HAVING n>=3", (now() - 3600,)):
        es = (r["es"] or "").split(","); out.append({"type": "Several sign-ups from one device", "severity": "medium", "detail": f"{r['n']} sign-ups from {r['ip']} in the last hour: {', '.join(es)}", "user_ids": ids(es)})
    for r in c.execute("SELECT ip, COUNT(*) n FROM audit WHERE event='rate_limited' AND ts>? GROUP BY ip", (now() - 3600,)):
        out.append({"type": "Very fast repeated requests", "severity": "medium", "detail": f"Device {r['ip']} was rate-limited {r['n']} time(s) in the last hour", "user_ids": []})
    for r in c.execute("SELECT ip, COUNT(*) n FROM audit WHERE event='login_fail' AND ts>? GROUP BY ip HAVING n>=8", (now() - 900,)):
        out.append({"type": "Many failed logins from one device", "severity": "high", "detail": f"{r['n']} failed sign-ins from {r['ip']} in 15 minutes", "user_ids": []})
    for r in c.execute("SELECT detail, COUNT(*) n FROM audit WHERE event='login_denied' AND detail LIKE 'admin tried%' AND ts>? GROUP BY 1", (now() - 86400,)):
        out.append({"type": "Admin account used on the user portal", "severity": "medium", "detail": f"{r['n']} attempt(s) in the last 24 hours", "user_ids": []})
    c.close(); return out


@router.get("/audit")
def audit_list(limit: int = 300, event: str = "", email: str = "", _=Depends(require_admin)):
    c = db.conn(); sql, p, w = "SELECT * FROM audit", [], []
    if event: w.append("event=?"); p.append(event)
    if email: w.append("email LIKE ?"); p.append(f"%{email}%")
    if w: sql += " WHERE " + " AND ".join(w)
    rows = c.execute(sql + " ORDER BY id DESC LIMIT ?", p + [min(limit, 2000)]).fetchall(); c.close()
    return [dict(r) for r in rows]


@router.get("/audit.csv")
def audit_csv(_=Depends(require_admin)):
    c = db.conn()
    rows = c.execute("SELECT id,datetime(ts,'unixepoch','localtime'),email,event,ip,ua,detail FROM audit ORDER BY id DESC").fetchall(); c.close()
    return _csv("login_history.csv", ["id", "time", "email", "event", "ip", "device", "detail"], rows)


# ---------------- collected submissions ----------------
@router.get("/analyses")
def analyses(limit: int = 200, _=Depends(require_admin)):
    c = db.conn()
    rows = c.execute("""SELECT a.id,a.ts,a.handle,a.followers,a.tier,a.category,a.account_type,a.avg_likes,a.avg_comments,a.hashtags,a.posts_per_week,
        a.score,a.income_per_post,a.income_monthly,a.best_hashtags,u.name,u.email FROM analyses a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT ?""", (min(limit, 1000),)).fetchall()
    one = lambda s: c.execute(s).fetchone()
    tot, sc, fo, inc = one("SELECT COUNT(*), COALESCE(AVG(score),0), COALESCE(AVG(followers),0), COALESCE(AVG(income_monthly),0) FROM analyses")
    agg = {"total": tot, "avg_score": round(sc, 1), "avg_followers": round(fo), "avg_monthly_income": round(inc),
           "unique_users": one("SELECT COUNT(DISTINCT user_id) FROM analyses")[0],
           "by_type": [list(r) for r in c.execute("SELECT account_type, COUNT(*), ROUND(AVG(score),1) FROM analyses GROUP BY 1")],
           "by_tier": [list(r) for r in c.execute("SELECT tier, COUNT(*), ROUND(AVG(score),1), ROUND(AVG(income_monthly)) FROM analyses GROUP BY 1 ORDER BY 2 DESC")],
           "by_category": [list(r) for r in c.execute("SELECT category, COUNT(*), ROUND(AVG(score),1), ROUND(AVG(avg_likes),1) FROM analyses GROUP BY 1 ORDER BY 2 DESC LIMIT 12")]}
    c.close(); return {"rows": [dict(r) for r in rows], "agg": agg}


@router.get("/lookups")
def lookups(_=Depends(require_admin)):
    c = db.conn()
    rows = c.execute("""SELECT l.id,l.ts,l.name,l.kind,l.category,l.followers,l.avg_likes,l.avg_comments,l.tier,l.persona,l.next_likes,l.fee_low_usd,l.fee_mid_usd,l.fee_high_usd,
        l.fee_mid_inr,u.email FROM lookups l LEFT JOIN users u ON u.id=l.user_id ORDER BY l.id DESC LIMIT 300""").fetchall(); c.close()
    return [dict(r) for r in rows]


@router.get("/analyses.csv")
def analyses_csv(_=Depends(require_admin)):
    c = db.conn()
    rows = c.execute("""SELECT a.id,datetime(a.ts,'unixepoch','localtime'),u.email,a.handle,a.followers,a.tier,a.category,a.account_type,a.avg_likes,a.avg_comments,
        a.hashtags,a.posts_per_week,a.score,a.income_per_post,a.income_monthly,a.best_hashtags FROM analyses a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id""").fetchall(); c.close()
    return _csv("account_submissions.csv", ["id", "time", "user email", "handle", "followers", "tier", "category", "account type", "avg likes", "avg comments",
                                            "hashtags per post", "posts per week", "score", "income per post (est.)", "income monthly (est.)", "best hashtag count"], rows)


@router.get("/feedback")
def feedback(_=Depends(require_admin)):
    c = db.conn()
    rows = c.execute("SELECT f.id,f.ts,f.rating,f.topic,f.message,u.name,u.email FROM feedback f LEFT JOIN users u ON u.id=f.user_id ORDER BY f.id DESC LIMIT 300").fetchall(); c.close()
    return [dict(r) for r in rows]


# ---------------- admin accounts ----------------
class AdminIn(BaseModel):
    name: str; email: str; password: str


@router.get("/admins")
def admins(_=Depends(require_admin)):
    c = db.conn()
    rows = c.execute("SELECT id,name,email,status,created,last_login,login_count,must_change FROM users WHERE role='admin' ORDER BY id").fetchall(); c.close()
    return [dict(r) for r in rows]


@router.post("/admins")
def create_admin(b: AdminIn, request: Request):
    me_ = require_admin(request); email, name = b.email.strip().lower(), " ".join(b.name.split())
    if not (2 <= len(name) <= 60): raise HTTPException(400, "Please enter a name.")
    if not security.EMAIL_RE.match(email): raise HTTPException(400, "Please enter a valid email address.")
    p = security.password_problem(b.password, email, name)
    if p: raise HTTPException(400, p)
    c = db.conn()
    if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone(): c.close(); raise HTTPException(409, "That email is already registered.")
    c.execute("INSERT INTO users(email,name,pw,role,status,verified,created,must_change) VALUES (?,?,?,'admin','active',1,?,1)", (email, name, security.hash_pw(b.password), now()))
    c.commit(); c.close(); audit("admin_created", None, email, request, f"by {me_['email']}"); return {"ok": True}
