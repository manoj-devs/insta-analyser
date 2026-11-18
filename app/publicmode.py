"""Safety rules for when the site is reachable from the internet (PUBLIC_MODE=1, set by share_online.py, or APP_ENV=production)."""
import ipaddress, os, time
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from app import config, db, otp, security

ADMIN_ALLOWED_IPS = [x.strip() for x in os.getenv("ADMIN_ALLOWED_IPS", "").split(",") if x.strip()]
ADMIN_PATH = os.getenv("ADMIN_PATH", "").strip("/ ")
_NETS = []
for _x in ADMIN_ALLOWED_IPS:
    try: _NETS.append(ipaddress.ip_network(_x, strict=False))
    except ValueError: print(f"  !! ADMIN_ALLOWED_IPS: '{_x}' is not an IP address or network and is ignored")
_DEF = {"t": 0, "v": False}


def problems():
    """what must be set before the site may be opened to the internet. Returns a list of plain-English lines."""
    out = []
    if not os.getenv("SECRET_KEY"): out.append("SECRET_KEY is not set. Add a long random text as SECRET_KEY in the .env file (it signs the one-time codes).")
    if not (security.smtp_configured() or otp.sms_configured()):
        out.append("Email (or SMS) delivery is not set up, so sign-up codes cannot be sent. Run  python setup_email.py  first.")
    return out


def client_ip(request: Request):
    return request.client.host if request.client else ""


def is_remote(request: Request):
    ip = client_ip(request)
    if request.headers.get("cf-connecting-ip"): return True
    try: return not ipaddress.ip_address(ip).is_loopback
    except ValueError: return True


def ip_allowed(request: Request):
    if not _NETS: return True
    try: ip = ipaddress.ip_address(client_ip(request))
    except ValueError: return False
    return ip.is_loopback or any(ip in n for n in _NETS)


def default_admin_password_unchanged():
    if time.time() - _DEF["t"] > 5:
        c = db.conn(); _DEF["v"] = bool(c.execute("SELECT 1 FROM users WHERE role='admin' AND must_change=1 LIMIT 1").fetchone()); c.close(); _DEF["t"] = time.time()
    return _DEF["v"]


def is_admin_path(path):
    return path.startswith("/api/admin") or path == "/admin" or path.startswith("/admin/") or (ADMIN_PATH and path.strip("/") == ADMIN_PATH)


def admin_gate(request: Request):
    """returns a Response when this request to the admin portal must be refused, else None"""
    path = request.url.path
    if not is_admin_path(path): return None
    if not ip_allowed(request): return JSONResponse({"detail": "Not found"}, status_code=404)
    if ADMIN_PATH and (path == "/admin" or path == "/admin/"): return JSONResponse({"detail": "Not found"}, status_code=404)
    if config.PUBLIC_MODE and is_remote(request) and default_admin_password_unchanged():
        msg = "The administrator must first sign in on the computer that runs the server (http://127.0.0.1:8000/admin) and change the default password. Until then the admin portal is closed to the internet."
        if path.startswith("/api"): return JSONResponse({"detail": msg}, status_code=403)
        return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>Admin closed</title><body style='font:16px system-ui;background:#0b1020;color:#eef1ff;padding:40px'><h2>Admin portal is closed for now</h2><p>{msg}</p>", status_code=403)
    return None
