import os, re, hashlib, hmac, secrets, smtplib
from email.message import EmailMessage

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?\d{8,15}$")
HANDLE_RE = re.compile(r"^@?[A-Za-z0-9._]{1,30}$")
DISPOSABLE = {"mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com", "yopmail.com",
              "trashmail.com", "sharklasers.com", "getnada.com", "dispostable.com", "throwawaymail.com",
              "temp-mail.org", "maildrop.cc", "fakeinbox.com", "mailnesia.com"}
COMMON = {"password", "password1", "password123", "passw0rd", "qwerty123", "qwertyuiop", "admin123", "admin@123",
          "admin@12345", "welcome1", "welcome123", "letmein123", "iloveyou1", "abc12345", "12345678", "123456789",
          "changeme1", "instagram1", "instagram123"}
USER_TYPES = ["creator", "influencer", "business", "brand_manager", "social_media_manager", "agency", "photographer", "celebrity", "athlete",
              "musician", "journalist", "student", "researcher", "teacher", "developer", "analyst", "freelancer", "ngo", "other"]


def hash_pw(pw):
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def check_pw(pw, stored):
    try:
        _, salt, dk = stored.split("$")
        new = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(new.hex(), dk)
    except Exception:
        return False


def password_problem(pw, email="", name=""):
    if len(pw) < 8: return "Password must be at least 8 characters."
    if len(pw) > 100: return "Password is too long (100 characters at most)."
    if not re.search(r"[a-z]", pw) or not re.search(r"[A-Z]", pw) or not re.search(r"\d", pw):
        return "Password needs an uppercase letter, a lowercase letter and a number."
    low = pw.lower()
    if low in COMMON: return "That password is too common. Please choose another."
    local = (email or "").split("@")[0].lower()
    if len(local) >= 4 and local in low: return "Password must not contain your email name."
    first = (name or "").split(" ")[0].lower()
    if len(first) >= 4 and first in low: return "Password must not contain your name."
    return None


def new_otp():
    return f"{secrets.randbelow(10**6):06d}"


SUBJECTS = {"verify": "Your InstaWarehouse verification code", "reset": "Your InstaWarehouse password reset code",
            "2fa": "Your InstaWarehouse admin sign-in code"}


LAST_ERROR = ""


def api_mail_configured():
    """E-mail over HTTPS (Brevo). Needed on hosts that block the SMTP ports, such as Render's free plan."""
    return bool(os.getenv("BREVO_API_KEY") and os.getenv("MAIL_FROM"))


def smtp_configured():
    """True when ANY real e-mail delivery is set up: SMTP (Gmail etc.) or the HTTPS e-mail API."""
    return api_mail_configured() or bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


def _send_api(to, subject, body):
    import httpx, re
    url = os.getenv("BREVO_URL", "https://api.brevo.com/v3/smtp/email")
    frm = os.getenv("MAIL_FROM", "")
    m = re.match(r"^\s*(.*?)\s*<([^<>]+)>\s*$", frm); name, addr = (m.group(1) or "InstaWarehouse", m.group(2)) if m else ("InstaWarehouse", frm.strip())
    r = httpx.post(url, headers={"api-key": os.getenv("BREVO_API_KEY", ""), "accept": "application/json", "content-type": "application/json"}, timeout=20,
                   json={"sender": {"name": name, "email": addr}, "to": [{"email": to}], "subject": subject, "textContent": body})
    if r.status_code >= 300:
        raise RuntimeError(f"mail service answered {r.status_code}: {r.text[:200]}")


def send_mail(to, subject, body):
    """Sends one plain-text email through SMTP. Returns True on success; the reason for a failure is kept in LAST_ERROR."""
    global LAST_ERROR
    if api_mail_configured():
        try:
            _send_api(to, subject, body); LAST_ERROR = ""; return True
        except Exception as e:
            LAST_ERROR = f"{type(e).__name__}: {e}"
            print(f"\n  !! Could not send email to {to} through the e-mail API: {LAST_ERROR}\n  !! Check BREVO_API_KEY and that MAIL_FROM is a verified sender in Brevo.\n")
            return False
    host, port = os.getenv("SMTP_HOST", ""), int(os.getenv("SMTP_PORT", "587"))
    mode = os.getenv("SMTP_SECURITY", "ssl" if port == 465 else "starttls").lower()
    try:
        m = EmailMessage(); m["Subject"] = subject
        m["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "no-reply@instawarehouse.local")); m["To"] = to
        m.set_content(body)
        if mode == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=20) as s: s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASS", "")); s.send_message(m)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                if mode == "starttls": s.starttls()
                if os.getenv("SMTP_USER"): s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASS", ""))
                s.send_message(m)
        LAST_ERROR = ""; return True
    except Exception as e:
        LAST_ERROR = f"{type(e).__name__}: {e}"
        print(f"\n  !! Could not send email to {to}: {LAST_ERROR}\n  !! Check SMTP_USER / SMTP_PASS in the .env file (Gmail needs an App Password, not your normal password).\n")
        return False
