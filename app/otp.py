"""One-time codes (OTP) for sign-up, new-device sign-in, password reset and admin sign-in.

Rules (from the faculty feedback):
  * a random 6-digit code that expires after 5 minutes (OTP_TTL_SECONDS)
  * delivered by email and/or SMS, NEVER shown on the page, never put in a URL or in the server log
  * stored only as a salted HMAC hash; checked on the server; sending a new code cancels the older one
  * at most 5 wrong tries, then the code is cancelled and the account is locked for 5 minutes
  * a 30 second wait between codes and 5 codes per hour per account
  * every flow carries a one-time "ticket" that only the browser which started the flow holds
Settings (environment or .env):  OTP_CHANNELS=email|sms|both   OTP_LOGIN=new_device|always|never   APP_ENV=production
"""
import base64, collections, hashlib, hmac, json, os, re, secrets, time, urllib.parse, urllib.request
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from app import config, db, security

TTL = int(os.getenv("OTP_TTL_SECONDS", "300"))
MAX_TRIES = int(os.getenv("OTP_MAX_TRIES", "5"))
LOCK_SECONDS = int(os.getenv("OTP_LOCK_SECONDS", "300"))
COOLDOWN = int(os.getenv("OTP_RESEND_SECONDS", "30"))
MAX_SENDS = int(os.getenv("OTP_MAX_PER_HOUR", "5"))
CHANNELS = os.getenv("OTP_CHANNELS", "email").lower()               # email | sms | both
LOGIN_POLICY = os.getenv("OTP_LOGIN", "new_device").lower()          # new_device | always | never
PRODUCTION = config.PRODUCTION
OUTBOX = collections.deque(maxlen=25)                                # development only, in memory, never written to a file or log
now = time.time
router = APIRouter()

SUBJECT = {"verify": "Your InstaWarehouse verification code", "login": "Your InstaWarehouse sign-in code",
           "reset": "Your InstaWarehouse password reset code", "2fa": "Your InstaWarehouse admin sign-in code"}
INTRO = {"verify": "Your InstaWarehouse verification code is", "login": "Your InstaWarehouse sign-in code is (we ask because this looks like a new device)",
         "reset": "Your InstaWarehouse password reset code is", "2fa": "Your InstaWarehouse admin sign-in code is"}


# ---------------- hashing ----------------
def _secret():
    k = os.getenv("SECRET_KEY")
    if k: return k.encode()
    path = os.path.join(config.DATA_DIR, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f: f.write(secrets.token_hex(32))
        try: os.chmod(path, 0o600)
        except OSError: pass
    return open(path).read().strip().encode()


def _h(code, email, salt):
    return hmac.new(_secret(), f"{salt}:{email}:{code}".encode(), hashlib.sha256).hexdigest()


def make_hash(code, email):
    salt = secrets.token_hex(8); return f"{salt}${_h(code, email, salt)}"


def hash_ok(code, email, stored):
    try:
        salt, h = (stored or "").split("$"); return hmac.compare_digest(_h(code, email, salt), h)
    except Exception:
        return False


def _tick(t): return hashlib.sha256((t or "").encode()).hexdigest()


def ticket_ok(u, ticket):
    return bool(u and u["otp_ticket"] and ticket and hmac.compare_digest(u["otp_ticket"], _tick(ticket)))


def err(status, msg, state, retry=None):
    h = {"X-Otp-State": state}
    if retry: h["Retry-After"] = str(int(max(1, retry)))
    return HTTPException(status, msg, headers=h)


def mask_email(e):
    n, _, d = (e or "").partition("@"); return (n[:1] + "***" + (n[-1:] if len(n) > 2 else "")) + "@" + d


def mask_phone(p): return "•••• " + (p or "")[-4:]


# ---------------- delivery channels ----------------
def sms_configured():
    return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN") and (os.getenv("TWILIO_FROM") or os.getenv("TWILIO_MESSAGING_SERVICE")))


DIAL = {"india": "+91", "united states": "+1", "canada": "+1", "united kingdom": "+44", "australia": "+61", "singapore": "+65",
        "united arab emirates": "+971", "sri lanka": "+94", "malaysia": "+60"}


def e164(phone, country=""):
    p = re.sub(r"[^\d+]", "", phone or "")
    if not p: return None
    if p.startswith("+"): return p if re.fullmatch(r"\+\d{8,15}", p) else None
    if p.startswith("00"): return "+" + p[2:]
    cc = DIAL.get((country or "").lower())
    if cc == "+91" and len(p) == 10: return cc + p
    if cc and cc != "+91" and 8 <= len(p) <= 11: return cc + p.lstrip("0")
    return None


def send_sms(to, text):
    """Twilio REST API (no extra package). Returns True on success."""
    try:
        sid, tok = os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
        data = {"To": to, "Body": text}
        if os.getenv("TWILIO_MESSAGING_SERVICE"): data["MessagingServiceSid"] = os.environ["TWILIO_MESSAGING_SERVICE"]
        else: data["From"] = os.environ["TWILIO_FROM"]
        req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", urllib.parse.urlencode(data).encode(), method="POST")
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{tok}".encode()).decode())
        with urllib.request.urlopen(req, timeout=20) as r: return 200 <= r.status < 300
    except Exception as e:
        print(f"\n  !! SMS could not be sent: {type(e).__name__}\n"); return False


def plan(u):
    """Which channels to use for this person: (list, phone)."""
    phone = e164(u["phone"], u["country"])
    have = {"email": security.smtp_configured(), "sms": sms_configured() and bool(phone)}
    want = {"email": ["email"], "sms": ["sms"], "both": ["email", "sms"]}.get(CHANNELS, ["email"])
    use = [c for c in want if have[c]]
    if not use: use = [c for c in ("email", "sms") if have[c]][:1]          # fall back to whatever works
    return use, phone


def _audit(event, u, request, detail=""):
    from app import auth
    auth.audit(event, u["id"], u["email"], request, detail)                     # never contains the code


# ---------------- issue / check ----------------
def issue(c, u, purpose, request=None, soft=False):
    """Create and send a new code. Returns the public information for the pop-up (never the code)."""
    t = now()
    if (u["otp_lock"] or 0) > t:
        raise err(429, f"Too many wrong codes. This account is locked for {int((u['otp_lock'] - t) // 60) + 1} more minute(s).", "locked", u["otp_lock"] - t)
    use, phone = plan(u)
    if not use and PRODUCTION:
        raise err(503, "Email delivery is not set up on this server yet. The administrator must configure SMTP (see setup_email.py).", "undeliverable")
    info = {"ok": True, "email": u["email"], "purpose": purpose, "ttl": TTL, "cooldown": COOLDOWN, "max_tries": MAX_TRIES}
    if u["otp_sent"] and t - u["otp_sent"] < COOLDOWN and u["otp_purpose"] == purpose:
        if not soft: raise err(429, f"Please wait {int(COOLDOWN - (t - u['otp_sent'])) + 1} seconds before asking for another code.", "cooldown", COOLDOWN - (t - u["otp_sent"]))
        ticket = secrets.token_urlsafe(16)                                    # a code was just sent: keep it, only hand this browser a ticket
        c.execute("UPDATE users SET otp_ticket=? WHERE id=?", (_tick(ticket), u["id"])); c.commit()
        return {**info, "ticket": ticket, "already_sent": True, "sent_to": [], "remaining": max(1, int(u["otp_exp"] - t)), "retry": int(COOLDOWN - (t - u["otp_sent"])) + 1}
    win, sends = u["otp_win"] or 0, u["otp_sends"] or 0
    if t - win > 3600: win, sends = t, 0
    if sends >= MAX_SENDS:
        raise err(429, f"Too many codes were requested. Please try again in {int((win + 3600 - t) // 60) + 1} minutes.", "limit", win + 3600 - t)
    code, ticket = security.new_otp(), secrets.token_urlsafe(16)
    c.execute("UPDATE users SET otp=?, otp_exp=?, otp_tries=0, otp_purpose=?, otp_ticket=?, otp_sent=?, otp_win=?, otp_sends=? WHERE id=?",
              (make_hash(code, u["email"]), t + TTL, purpose, _tick(ticket), t, win, sends + 1, u["id"]))
    c.commit()
    body_tail = f"\n\nIt expires in {TTL // 60} minutes. Never share this code with anyone. If you did not ask for it, ignore this message."
    sent_to, dev = [], False
    if use:
        for ch in use:
            ok = (security.send_mail(u["email"], SUBJECT[purpose], f"{INTRO[purpose]} {code}.{body_tail}") if ch == "email"
                  else send_sms(phone, f"InstaWarehouse code: {code}. Expires in {TTL // 60} min. Do not share it."))
            if ok: sent_to.append(f"your email {mask_email(u['email'])}" if ch == "email" else f"your phone {mask_phone(phone)}")
        if not sent_to:
            c.execute("UPDATE users SET otp=NULL, otp_exp=NULL WHERE id=?", (u["id"],)); c.commit()
            raise err(502, "We could not send the code just now. Please check your email address and try again in a minute.", "delivery_failed")
    else:                                                                    # development only: a local "inbox" instead of real email
        OUTBOX.appendleft({"ts": t, "to": u["email"], "subject": SUBJECT[purpose], "body": f"{INTRO[purpose]} {code}.{body_tail}"})
        sent_to, dev = [f"the local development inbox (no email service is set up)"], True
    if request is not None: _audit("otp_sent", u, request, f"{purpose} via {'+'.join(use) or 'dev-outbox'}")
    return {**info, "ticket": ticket, "sent_to": sent_to, "dev_outbox": dev, "remaining": TTL}


def check(c, u, code, ticket, purposes, request=None):
    """Validate a code on the server. Returns the purpose it was issued for. Raises clear, plain errors."""
    t = now()
    if u is None: raise err(400, "There is no active code. Please ask for a new one.", "none")
    if (u["otp_lock"] or 0) > t:
        raise err(429, f"Too many wrong codes. For your safety this account is locked for {int((u['otp_lock'] - t) // 60) + 1} more minute(s).", "locked", u["otp_lock"] - t)
    if not ticket_ok(u, ticket) or u["otp_purpose"] not in purposes:
        raise err(400, "There is no active code. Please ask for a new one.", "none")
    if not u["otp"]:
        raise err(400, "This code has expired. Tap Resend to get a new one.", "expired")
    if (u["otp_exp"] or 0) < t:
        c.execute("UPDATE users SET otp=NULL WHERE id=?", (u["id"],)); c.commit()
        if request is not None: _audit("otp_expired", u, request, u["otp_purpose"])
        raise err(400, "This code has expired. Tap Resend to get a new one.", "expired")
    if not hash_ok((code or "").strip(), u["email"], u["otp"]):
        tries = (u["otp_tries"] or 0) + 1
        if tries >= MAX_TRIES:
            c.execute("UPDATE users SET otp=NULL, otp_tries=0, otp_lock=? WHERE id=?", (t + LOCK_SECONDS, u["id"])); c.commit()
            if request is not None: _audit("otp_locked", u, request, f"{u['otp_purpose']}, {MAX_TRIES} wrong codes")
            raise err(429, f"Too many wrong codes. For your safety this account is locked for {LOCK_SECONDS // 60} minutes.", "locked", LOCK_SECONDS)
        c.execute("UPDATE users SET otp_tries=? WHERE id=?", (tries, u["id"])); c.commit()
        if request is not None: _audit("otp_wrong", u, request, f"{u['otp_purpose']}, try {tries}")
        left = MAX_TRIES - tries
        raise err(400, f"That code is not correct. {left} {'try' if left == 1 else 'tries'} left.", "wrong")
    purpose = u["otp_purpose"]
    if purpose == "reset":                                                   # code accepted: allow ONE password change in the next 10 minutes
        c.execute("UPDATE users SET otp=NULL, otp_tries=0, otp_purpose='reset_ok', otp_exp=? WHERE id=?", (t + 600, u["id"]))
    else:
        c.execute("UPDATE users SET otp=NULL, otp_tries=0, otp_purpose=NULL, otp_ticket=NULL, otp_exp=NULL WHERE id=?", (u["id"],))
    c.commit()
    return purpose


def fake_info(email, purpose="reset"):
    """Same shape as a real answer, for e-mail addresses that have no account (so the page cannot be used to find out who is registered)."""
    return {"ok": True, "email": email, "purpose": purpose, "ttl": TTL, "cooldown": COOLDOWN, "max_tries": MAX_TRIES, "ticket": secrets.token_urlsafe(16),
            "sent_to": [f"your email {mask_email(email)}"], "dev_outbox": False, "remaining": TTL}


# ---------------- trusted devices ("new device" sign-in) ----------------
DEVICE_COOKIE = "iw_dev"


def device_label(ua):
    ua = ua or ""
    br = "Edge" if "Edg/" in ua else "Chrome" if "Chrome/" in ua else "Firefox" if "Firefox/" in ua else "Safari" if "Safari/" in ua else "Browser"
    os_ = "Android" if "Android" in ua else "iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Windows" if "Windows" in ua else "Mac" if "Mac OS" in ua else "Linux" if "Linux" in ua else "unknown"
    return f"{br} on {os_}"


def is_trusted(c, u, request):
    tok = request.cookies.get(DEVICE_COOKIE)
    return bool(tok and c.execute("SELECT 1 FROM devices WHERE user_id=? AND token_hash=?", (u["id"], _tick(tok))).fetchone())


def needs_login_otp(c, u, request):
    if LOGIN_POLICY == "never": return False
    if LOGIN_POLICY == "always": return True
    return not is_trusted(c, u, request)


def trust_device(c, u, request, response):
    """Remember this browser so the next sign-in from it does not need a code (only for OTP_LOGIN=new_device)."""
    tok = request.cookies.get(DEVICE_COOKIE); t = now()
    if tok and c.execute("UPDATE devices SET last_seen=? WHERE user_id=? AND token_hash=?", (t, u["id"], _tick(tok))).rowcount:
        c.commit(); return
    tok = secrets.token_urlsafe(32)
    c.execute("INSERT INTO devices(user_id,token_hash,label,ip,first_seen,last_seen) VALUES (?,?,?,?,?,?)",
              (u["id"], _tick(tok), device_label(request.headers.get("user-agent", "")), request.client.host if request.client else "", t, t)); c.commit()
    from app import auth
    response.set_cookie(DEVICE_COOKIE, tok, httponly=True, samesite="strict", max_age=90 * 86400, path="/", secure=auth.is_https(request))


# ---------------- development inbox (localhost only, only when no real email/SMS is configured) ----------------
@router.get("/dev/outbox", include_in_schema=False)
def dev_outbox(request: Request):
    host = request.client.host if request.client else ""
    if PRODUCTION or security.smtp_configured() or sms_configured() or host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(404, "Not found")
    rows = "".join(f"<tr><td>{time.strftime('%H:%M:%S', time.localtime(m['ts']))}</td><td>{m['to']}</td><td><pre style='margin:0;white-space:pre-wrap'>{m['body']}</pre></td></tr>" for m in OUTBOX) or "<tr><td colspan=3>No messages yet.</td></tr>"
    return HTMLResponse(f"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=5><title>Development inbox</title>
<body style="font:15px system-ui;background:#0b1020;color:#eef1ff;padding:24px"><h2>Development inbox</h2>
<p style="color:#9aa3c7">Email is not configured, so the codes land here instead (this page only opens on this computer and is empty after a restart). To send real email run <code>python setup_email.py</code>.</p>
<table cellpadding=8 style="border-collapse:collapse;width:100%"><tr style="text-align:left;color:#9aa3c7"><th>Time</th><th>To</th><th>Message</th></tr>{rows}</table></body>""", headers={"Cache-Control": "no-store"})
