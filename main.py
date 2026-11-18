"""InstaWarehouse:  python main.py  ->  http://127.0.0.1:8000"""
import collections, glob, os, time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app import auth, config, db, otp, publicmode
from app.routers import account, admin, creator, extra, ops, phase2, region, reports, tcp as tcp_api
from app.routers import mining as mining_api
from app.services import mining as mining_svc

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    startup()                                   # defined below; runs once when the server starts
    yield


app = FastAPI(title="InstaWarehouse API", description="Instagram data warehouse, OLAP and analytics", lifespan=lifespan)
BUILD = "5.7"                     # bump when the front-end changes; the pages compare it with their own copy
HITS = collections.defaultdict(collections.deque)
SENSITIVE = collections.defaultdict(collections.deque)          # stricter limit for sign-in and code endpoints when the site is public
SENS_PATHS = ("/api/admin/auth", "/api/auth/login", "/api/auth/signup", "/api/auth/verify", "/api/auth/resend", "/api/auth/forgot", "/api/auth/reset", "/api/creator/ocr")


@app.middleware("http")
async def guard(request: Request, call_next):
    blocked = publicmode.admin_gate(request)
    if blocked is not None: return blocked
    if config.PUBLIC_MODE and request.method == "POST" and request.url.path.startswith(SENS_PATHS):
        q, t = SENSITIVE[publicmode.client_ip(request)], time.time()
        while q and t - q[0] > 60: q.popleft()
        q.append(t)
        if len(q) > 20:
            if len(q) == 21: auth.audit("rate_limited", None, None, request, "more than 20 sign-in/code requests in 60 s (public mode)")
            return JSONResponse({"detail": "Too many attempts. Please wait a minute and try again."}, status_code=429, headers={"Retry-After": "60"})
    if request.url.path.startswith("/api"):
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "fetch":
            return JSONResponse({"detail": "Missing request header."}, status_code=403)
        key = request.cookies.get(auth.COOKIE['user']) or request.cookies.get(auth.COOKIE['admin']) or (request.client.host if request.client else "?")
        q, t = HITS[key], time.time()
        while q and t - q[0] > 10: q.popleft()
        q.append(t)
        if len(q) > 120:
            if len(q) == 121: auth.audit("rate_limited", None, None, request, "more than 120 requests in 10 s")
            return JSONResponse({"detail": "Too many requests. Please slow down."}, status_code=429)
    resp = await call_next(request)
    if request.url.path.startswith("/static/"): resp.headers["Cache-Control"] = "no-cache"      # always re-check, so an updated zip is never shown from an old cache
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    resp.headers["Content-Security-Policy"] = "frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'"
    if config.PRODUCTION and auth.is_https(request): resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp


app.include_router(auth.router)
app.include_router(otp.router)
app.include_router(admin.router)
app.include_router(account.router)
app.include_router(region.router)
app.include_router(creator.router)
app.include_router(ops.router)
app.include_router(mining_api.router)
app.include_router(phase2.router)
app.include_router(extra.router)
app.include_router(reports.router)
app.include_router(tcp_api.router)
app.mount("/static", StaticFiles(directory=os.path.join(config.ROOT, "static")), name="static")


STALE_MARKS = {"index.html": f'name="iw-build" content="{BUILD}"', "admin.html": f'name="iw-build" content="{BUILD}"', "css/app.css": f'"{BUILD}"',
               "js/common.js": f'BUILD="{BUILD}"', "js/user.js": f'PAGE_JS_BUILD="{BUILD}"', "js/admin.js": f'PAGE_JS_BUILD="{BUILD}"'}


def stale_files():
    """front-end files that are missing or come from a different zip than main.py (e.g. an old index.html next to a new main.py)"""
    bad = []
    for rel, mark in STALE_MARKS.items():
        try:
            with open(os.path.join(config.ROOT, "static", rel), encoding="utf-8") as f: ok = mark in f.read()
        except OSError: ok = False
        if not ok: bad.append("static/" + rel)
    return bad


def _stale_page(bad):
    items = "".join(f"<li><code>{b}</code></li>" for b in bad)
    return HTMLResponse(f"""<!doctype html><meta charset=utf-8><title>Old files in your folder</title><meta name=viewport content="width=device-width,initial-scale=1">
<body style="font:16px/1.6 system-ui,sans-serif;background:#0b1020;color:#eef1ff;margin:0;display:grid;place-items:center;min-height:100vh"><div style="max-width:640px;padding:28px">
<h1 style="margin:0 0 8px">Your project folder has old files</h1>
<p>The server (main.py, build <b>{BUILD}</b>) is new, but these web files are from an older zip, so the sign-up page would not work:</p><ul>{items}</ul>
<p><b>How to fix (2 minutes):</b></p><ol><li>Stop the server (press Ctrl+C in the terminal).</li>
<li>Create a <b>new empty folder</b> and unzip the newest <code>instawarehouse.zip</code> into it. Do not copy single files over the old folder.</li>
<li>Open a terminal in the new <code>iw</code> folder and run <code>pip install -r requirements.txt</code>, then <code>python main.py</code>.</li>
<li>Press Ctrl+F5 in the browser.</li></ol></div></body>""", status_code=503, headers={"Cache-Control": "no-store"})


def _page(name):
    bad = stale_files()
    if bad: return _stale_page(bad)
    r = FileResponse(os.path.join(config.ROOT, "static", name))
    r.headers["Cache-Control"] = "no-store"
    return r


@app.get("/api/version", include_in_schema=False)
def version():
    return {"build": BUILD}


@app.get("/", include_in_schema=False)
def home():
    return _page("index.html")                      # USER portal


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_home():
    return _page("admin.html")                      # ADMIN portal (separate sign-in)


if publicmode.ADMIN_PATH:                           # optional secret address for the admin portal (the guard hides /admin)
    app.add_api_route("/" + publicmode.ADMIN_PATH, lambda: _page("admin.html"), include_in_schema=False)


def startup():
    bad = stale_files()
    if bad: print("\n  !! WARNING: these web files are from an older version and will be refused:", ", ".join(bad), "\n  !! Unzip the newest instawarehouse.zip into a NEW empty folder and run it from there.\n")
    if config.PUBLIC_MODE:
        miss = publicmode.problems()
        if miss:
            print("\n  !! The site cannot be opened to the internet yet:"); [print("  !!  - " + m) for m in miss]; print()
            raise SystemExit(2)
    db.init(); auth.ensure_admin()
    from app.services import tcplink
    _t = tcplink.start()
    if _t: print(f"  TCP link   : listening on {_t[0]}:{_t[1]}  (other laptop: py tcp_client.py {_t[0] if _t[0] not in ('0.0.0.0', '127.0.0.1') else '<this laptop IP>'} {_t[1]} ; password {tcplink.password()})")
    from app.services import directory
    seeded = directory.ensure_seed()
    if seeded: print(f"  Influencer directory: loaded {seeded['accepted']} real public influencers (names, follower counts and sources). Add more from Admin > Regions.")
    import threading
    from app.services import creator as _creator
    from app import security
    real = security.smtp_configured() or otp.sms_configured()
    print(f"  OTP: code length 6, valid {otp.TTL // 60} min, {otp.MAX_TRIES} tries then {otp.LOCK_SECONDS // 60} min lock | channels={otp.CHANNELS} | user sign-in code: {otp.LOGIN_POLICY}")
    print("  OTP delivery: " + ("real email/SMS" if real else ("NOT CONFIGURED (production: sign-up is refused until you run setup_email.py)" if config.PRODUCTION else "development inbox at /dev/outbox (this computer only). Run setup_email.py for real email.")))
    have = lambda n: any(glob.glob(os.path.join(config.RAW_DIR, n + e)) for e in (".csv", ".xlsx", ".xls"))
    from app.services import etl
    if (etl.clean_files_present() or (have("Instagram_data") and have("intsa_data2"))) and not os.path.exists(config.WAREHOUSE):
        print("Raw files found and no warehouse yet: running the ETL in the background...")
        phase2.start()
    if not os.path.exists(config.WAREHOUSE) and not (etl.clean_files_present() or (have("Instagram_data") and have("intsa_data2"))):
        print("\n  !! NO DATA FOUND. Put clean_instagram_reach.csv, clean_instagram_posts.csv and combined_instagram_data.csv in " + config.RAW_DIR)
        print("  !! (or unzip the FULL instawarehouse.zip, which already contains them). The code-only zip has no data, so the dashboards stay empty.\n")
    if os.path.exists(config.WAREHOUSE) and not mining_svc.available():
        print("Training the data mining models in the background (about a minute) ...")
        mining_svc.start()
    if os.path.exists(config.WAREHOUSE):          # warm the cube cache so the first visit is instant
        import threading
        def _warm():                                   # one after the other, so the peak memory stays low on a 512 MB host
            try: extra.cube_payload()
            except Exception: pass
            try: _creator.available()
            except Exception: pass
        threading.Thread(target=_warm, daemon=True).start()


if __name__ == "__main__":
    import socket

    def free(port, host="127.0.0.1"):
        with socket.socket() as sk: return sk.connect_ex((host, port)) != 0
    host = os.getenv("HOST") or ("127.0.0.1" if config.PUBLIC_MODE else "0.0.0.0" if config.PRODUCTION else "127.0.0.1")   # public mode = a tunnel on this computer
    port = int(os.getenv("PORT", "8000"))
    if not free(port):
        print(f"\n  !! Port {port} is ALREADY IN USE, almost certainly by an OLD copy of this project that is still running.")
        print("  !! That is why the browser keeps showing the old page. Close the old terminal window (or press Ctrl+C in it).")
        alt = next((q for q in range(port + 1, port + 20) if free(q)), None)
        if alt is None: raise SystemExit("No free port found.")
        print(f"  !! The NEW version will start on port {alt} instead."); port = alt
    show = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"\n  InstaWarehouse build {BUILD} is starting.  Open this address in your browser:")
    print(f"  User portal : http://{show}:{port}/")
    print(f"  Admin portal: http://{show}:{port}/admin   (admin@instawarehouse.com / Admin@12345, you must change it at first sign-in)")
    print(f"  Check       : http://{show}:{port}/api/version  must show build {BUILD}")
    if config.PUBLIC_MODE: print("  PUBLIC MODE is ON: HTTPS-only cookies, stricter sign-in limits" + (", admin limited to " + ", ".join(publicmode.ADMIN_ALLOWED_IPS) if publicmode.ADMIN_ALLOWED_IPS else "") + ".")
    if host == "0.0.0.0": print("  Other devices on your Wi-Fi can open  http://<this computer's IP>:%d/" % port)
    print("  Set ADMIN_EMAIL / ADMIN_PASSWORD before the first start to choose your own. ADMIN_2FA=0 turns off the admin email code.\n")
    uvicorn.run(app, host=host, port=port, proxy_headers=True, forwarded_allow_ips="*" if (config.PRODUCTION and not config.PUBLIC_MODE) else "127.0.0.1")
