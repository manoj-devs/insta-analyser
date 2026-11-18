"""Open InstaWarehouse to the internet so the admin and the users can be on DIFFERENT networks (different Wi-Fi, mobile data).

    python share_online.py

It (1) checks that email codes and a secret key are set up, (2) starts the server in PUBLIC MODE on this computer, (3) starts a free
Cloudflare Tunnel (or ngrok) that gives a public https link, (4) prints the user link, the admin link and a QR code.
The link works only while this window stays open and this computer is on. The free link changes every time.
Press Ctrl+C to stop both.
"""
import os, platform, re, shutil, signal, socket, stat, subprocess, sys, tarfile, threading, time, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__)); os.chdir(ROOT); sys.path.insert(0, ROOT)
PORT = int(os.getenv("PORT", "8000"))
URL_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")
BIN = os.path.join(ROOT, "bin"); os.makedirs(BIN, exist_ok=True)


def extract_url(line):
    m = URL_RE.search(line or ""); return m.group(0) if m else None


def say(msg=""): print(msg, flush=True)


def check_ready():
    os.environ["PUBLIC_MODE"] = "1"
    from app import publicmode                       # also reads the .env file
    miss = publicmode.problems()
    if miss:
        say("\n  The site is not ready to be opened to the internet yet:")
        for m in miss: say("   - " + m)
        say("\n  Fix these, then run this again.\n"); sys.exit(2)


def default_admin_password_unchanged():
    try:
        from app import db, config
        if not os.path.exists(config.AUTH_DB): return True
        c = db.conn(); r = c.execute("SELECT 1 FROM users WHERE role='admin' AND must_change=1 LIMIT 1").fetchone(); c.close(); return bool(r)
    except Exception: return False


def port_free(p):
    with socket.socket() as s: return s.connect_ex(("127.0.0.1", p)) != 0


def find_cloudflared():
    env = os.getenv("CLOUDFLARED_BIN")
    if env: return env
    w = shutil.which("cloudflared")
    if w: return w
    exe = os.path.join(BIN, "cloudflared.exe" if os.name == "nt" else "cloudflared")
    if os.path.exists(exe): return exe
    sysn, mach = platform.system().lower(), platform.machine().lower()
    arch = "arm64" if mach in ("arm64", "aarch64") else "amd64" if mach in ("x86_64", "amd64") else "386"
    base = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    if sysn == "windows": url, tgz = base + f"cloudflared-windows-{arch}.exe", False
    elif sysn == "darwin": url, tgz = base + f"cloudflared-darwin-{arch}.tgz", True
    else: url, tgz = base + f"cloudflared-linux-{arch}", False
    say(f"  Downloading the free Cloudflare Tunnel program once ({url.split('/')[-1]}) ...")
    try:
        tmp = exe + (".tgz" if tgz else ".part"); urllib.request.urlretrieve(url, tmp)
        if tgz:
            with tarfile.open(tmp) as t: t.extract("cloudflared", BIN)
            os.remove(tmp)
        else: os.replace(tmp, exe)
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC); return exe
    except Exception as e:
        say(f"\n  Could not download the tunnel program ({e}).")
        say("  Your network may block GitHub. Download 'cloudflared' by hand from https://github.com/cloudflare/cloudflared/releases")
        say("  and put it in the 'bin' folder next to this file (or install it so that 'cloudflared' works in a terminal), then run this again.")
        say("  Or set NGROK_AUTHTOKEN in the .env file and install ngrok (https://ngrok.com/download).\n"); sys.exit(3)


def start_server(port):
    env = dict(os.environ, PUBLIC_MODE="1", HOST="127.0.0.1", PORT=str(port))
    p = subprocess.Popen([sys.executable, "main.py"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    threading.Thread(target=lambda: [print("   [server] " + l.rstrip(), flush=True) for l in p.stdout if "GET /" not in l and "POST /" not in l], daemon=True).start()
    for _ in range(180):
        if p.poll() is not None: say("\n  The server stopped. See the [server] lines above for the reason.\n"); sys.exit(4)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=2); return p
        except Exception: time.sleep(1)
    p.terminate(); say("  The server did not start in 3 minutes."); sys.exit(4)


def start_tunnel(port):
    """returns (process, public_url)"""
    tok = os.getenv("NGROK_AUTHTOKEN")
    if tok and shutil.which("ngrok"):
        subprocess.run(["ngrok", "config", "add-authtoken", tok], capture_output=True)
        p = subprocess.Popen(["ngrok", "http", str(port), "--log=stdout"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            time.sleep(1)
            try:
                import json
                for t in json.load(urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2))["tunnels"]:
                    if t["public_url"].startswith("https"): return p, t["public_url"]
            except Exception: pass
        p.terminate(); say("  ngrok did not give a link. Check the token."); sys.exit(5)
    exe = find_cloudflared()
    proto = os.getenv("TUNNEL_PROTOCOL", "http2")             # http2 (TCP 443) passes school/office/ISP firewalls that block the default QUIC (UDP 7844)
    p = subprocess.Popen([exe, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate", "--protocol", proto, "--edge-ip-version", "4"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    found, tail = {}, []
    def pump():
        for line in p.stdout:
            tail.append(line.rstrip()); del tail[:-25]
            u = extract_url(line)
            if u and "url" not in found: found["url"] = u
            if "Registered tunnel connection" in line: found["up"] = True
    threading.Thread(target=pump, daemon=True).start()
    for _ in range(120):                                       # the link is printed BEFORE the tunnel is connected: wait until Cloudflare confirms it
        if found.get("url") and found.get("up"): return p, found["url"]
        if p.poll() is not None: break
        time.sleep(1)
    say("\n  The tunnel could not connect to Cloudflare. Last lines from the tunnel program:")
    for l in tail[-12:]: say("   [tunnel] " + l)
    say("\n  Usually your Wi-Fi/firewall blocks it. Try a mobile hotspot, or set TUNNEL_PROTOCOL=quic in .env, then run this again.\n")
    p.terminate(); sys.exit(5)


def qr(url):
    try:
        import qrcode
        q = qrcode.QRCode(border=1); q.add_data(url); q.print_ascii(invert=True)
    except Exception: say("   (Install 'qrcode' with  pip install qrcode  to also show a QR code here.)")


def main():
    def _stop(*_): raise KeyboardInterrupt()
    for name in ("SIGTERM", "SIGBREAK", "SIGHUP"):               # closing the window must stop the server and the tunnel too
        if hasattr(signal, name):
            try: signal.signal(getattr(signal, name), _stop)
            except (ValueError, OSError): pass
    check_ready()
    port = PORT
    if not port_free(port):
        alt = next((q for q in range(port + 1, port + 20) if port_free(q)), None)
        if alt is None: say("No free port found."); sys.exit(1)
        say(f"  Port {port} is busy (an old copy may be running). Using {alt} instead."); port = alt
    say("\n  Starting the server in PUBLIC MODE ...")
    srv = start_server(port)
    tun = None
    try:
        say("  Starting the tunnel ...")
        tun, url = start_tunnel(port)
        admin = os.getenv("ADMIN_PATH", "").strip("/ ") or "admin"
        say("\n" + "=" * 66)
        say("  YOUR SITE IS ONLINE. Anyone with the link can open it, from any network.")
        say(f"\n  Users :  {url}/")
        say(f"  Admin :  {url}/{admin}")
        say(f"\n  Local :  http://127.0.0.1:{port}/   (this computer)")
        say("=" * 66); qr(url + "/")
        if default_admin_password_unchanged():
            say(f"\n  !! The admin password is still the default. The admin link stays CLOSED to the internet until you sign in on THIS computer at")
            say(f"  !!   http://127.0.0.1:{port}/admin   and change it.")
        say("\n  Keep this window open. Press Ctrl+C to stop sharing.\n")
        while srv.poll() is None and tun.poll() is None: time.sleep(1)
        say("  The server or the tunnel stopped.")
    except KeyboardInterrupt:
        say("\n  Stopping ...")
    finally:
        for p in (tun, srv):
            if p and p.poll() is None:
                p.terminate()
                try: p.wait(8)
                except Exception: p.kill()


if __name__ == "__main__":
    main()
