"""A plain TCP link between two computers (separate from the website's HTTP).

The server laptop listens on a TCP port. The other laptop connects with  tcp_client.py  using the server's IP address.
Messages are one JSON object per line. Every connection starts with a password handshake (HMAC), so a stranger who finds the port gets nothing.

  server -> {"type":"challenge","nonce":...}
  client -> {"type":"hello","name":...,"mac":HMAC-SHA256(password, nonce)}
  server -> {"type":"welcome","session":N,"server":hostname}
  then:  ping -> pong,  stats -> stats,  msg -> ack,  bye.   The admin can also push {"type":"msg"} to a connected laptop.

Settings (.env or environment):  TCP_ENABLED=1  TCP_HOST=<ip to listen on, default = HOST or 127.0.0.1>  TCP_PORT=9000  TCP_PASSWORD=<text, otherwise one is created in data/tcp.key>
"""
import collections, hmac, hashlib, json, os, secrets, socket, threading, time
from app import config

MAX_LINE = 4096
MAX_CONNS = 20
IDLE_SECONDS = 180
LOG = collections.deque(maxlen=200)
CONNS = {}
_FAILS = {}
_LOCK = threading.Lock()
STATE = {"running": False, "host": None, "port": None, "started": None, "next_id": 1, "total": 0, "error": ""}
_SERVER = {"sock": None}


def log(kind, text, who=""):
    LOG.appendleft({"ts": time.time(), "kind": kind, "who": who, "text": text})


def password():
    p = os.getenv("TCP_PASSWORD", "").strip()
    if p: return p
    path = os.path.join(config.DATA_DIR, "tcp.key")
    try:
        if os.path.exists(path): return open(path).read().strip()
        os.makedirs(config.DATA_DIR, exist_ok=True)
        p = secrets.token_hex(3)                                    # short, to type on the other laptop
        with open(path, "w") as f: f.write(p)
        return p
    except OSError:
        return secrets.token_hex(3)


def mac(pw, nonce): return hmac.new(pw.encode(), nonce.encode(), hashlib.sha256).hexdigest()


class Conn:
    def __init__(self, sock, addr, cid):
        self.sock, self.addr, self.id = sock, addr, cid
        self.name = "?"; self.since = time.time(); self.last = self.since; self.bytes_in = self.bytes_out = 0; self.rtt_ms = None; self.pings = 0
        self.lock = threading.Lock(); self.buf = b""; self.local = sock.getsockname()

    def send(self, obj):
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode()
        with self.lock: self.sock.sendall(data); self.bytes_out += len(data)

    def readline(self, timeout):
        self.sock.settimeout(timeout)
        while b"\n" not in self.buf:
            if len(self.buf) > MAX_LINE: raise ValueError("line too long")
            chunk = self.sock.recv(1024)
            if not chunk: raise ConnectionError("closed")
            self.buf += chunk; self.bytes_in += len(chunk)
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8", "replace"))

    def info(self):
        return {"id": self.id, "name": self.name, "peer": f"{self.addr[0]}:{self.addr[1]}", "local": f"{self.local[0]}:{self.local[1]}", "since": self.since, "last": self.last,
                "bytes_in": self.bytes_in, "bytes_out": self.bytes_out, "rtt_ms": self.rtt_ms, "pings": self.pings}


def _stats():
    out = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "host": socket.gethostname()}
    try:
        import sqlite3
        if os.path.exists(config.WAREHOUSE):
            c = sqlite3.connect(f"file:{config.WAREHOUSE}?mode=ro", uri=True)
            out["posts"] = c.execute("SELECT SUM(posts) FROM summary_year").fetchone()[0]; out["accounts"] = c.execute("SELECT COUNT(*) FROM dim_user").fetchone()[0]; c.close()
        from app import db
        d = db.conn(); out["directory_rows"] = d.execute("SELECT COUNT(*) FROM directory").fetchone()[0]; out["reports_made"] = (d.execute("SELECT name FROM sqlite_master WHERE name='reports'").fetchone() and
                                                                                                                                  d.execute("SELECT COUNT(*) FROM reports").fetchone()[0]) or 0; d.close()
    except Exception as e: out["note"] = type(e).__name__
    return out


def _handle(sock, addr):
    ip = addr[0]
    if _FAILS.get(ip, (0, 0))[1] > time.time():
        sock.close(); return
    with _LOCK:
        if len(CONNS) >= MAX_CONNS: sock.close(); return
        cid = STATE["next_id"]; STATE["next_id"] += 1
    cn = Conn(sock, addr, cid); authed = False
    try:
        nonce = secrets.token_hex(8); cn.send({"type": "challenge", "nonce": nonce, "server": socket.gethostname()})
        h = cn.readline(10)
        if h.get("type") != "hello" or not hmac.compare_digest(str(h.get("mac", "")), mac(password(), nonce)):
            n = _FAILS.get(ip, (0, 0))[0] + 1; _FAILS[ip] = (n, time.time() + (60 if n >= 3 else 0))
            log("warn", f"wrong password from {ip}", ip)
            try: cn.send({"type": "error", "text": "wrong password"})
            except OSError: pass
            return
        _FAILS.pop(ip, None); cn.name = str(h.get("name", "laptop"))[:40] or "laptop"; authed = True
        with _LOCK: CONNS[cid] = cn; STATE["total"] += 1
        cn.send({"type": "welcome", "session": cid, "server": socket.gethostname()}); log("connect", f"{cn.name} connected from {ip}:{addr[1]}", cn.name)
        while True:
            m = cn.readline(IDLE_SECONDS); cn.last = time.time(); t = m.get("type")
            if t == "ping":
                cn.pings += 1; cn.send({"type": "pong", "t": m.get("t"), "server_time": time.time()})
                if isinstance(m.get("rtt_ms"), (int, float)): cn.rtt_ms = round(float(m["rtt_ms"]), 1)
            elif t == "stats": cn.send({"type": "stats", **_stats()})
            elif t == "msg":
                txt = str(m.get("text", ""))[:500]; log("message", txt, cn.name); cn.send({"type": "ack", "text": "received"})
            elif t == "bye": break
            else: cn.send({"type": "error", "text": "unknown message type"})
    except (ConnectionError, OSError, ValueError, json.JSONDecodeError, socket.timeout):
        pass
    finally:
        if authed:
            with _LOCK: CONNS.pop(cid, None)
            log("disconnect", f"{cn.name} disconnected", cn.name)
        try: sock.close()
        except OSError: pass


def _serve(srv):
    while STATE["running"]:
        try: s, a = srv.accept()
        except OSError: break
        threading.Thread(target=_handle, args=(s, a), daemon=True).start()


def start(host=None, port=None):
    """start the listener once (safe to call again). Returns the (host, port) or None when disabled / not possible."""
    if STATE["running"]: return STATE["host"], STATE["port"]
    if os.getenv("TCP_ENABLED", "1") == "0": return None
    host = host or os.getenv("TCP_HOST") or os.getenv("HOST") or "127.0.0.1"; base = int(port or os.getenv("TCP_PORT", "9000"))
    for p in range(base, base + 20):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try: srv.bind((host, p))
        except OSError: srv.close(); continue
        srv.listen(16); _SERVER["sock"] = srv; STATE.update(running=True, host=host, port=p, started=time.time(), error="")
        threading.Thread(target=_serve, args=(srv,), daemon=True).start(); log("server", f"TCP link listening on {host}:{p}"); return host, p
    STATE["error"] = f"no free TCP port from {base} to {base + 19} on {host}"; return None


def stop():
    STATE["running"] = False
    s = _SERVER.get("sock")
    if s:
        try: s.close()
        except OSError: pass
    _SERVER["sock"] = None
    for c in list(CONNS.values()):
        try: c.sock.close()
        except OSError: pass


def status():
    return {"running": STATE["running"], "host": STATE["host"], "port": STATE["port"], "error": STATE["error"], "password": password(), "total": STATE["total"],
            "connections": [c.info() for c in CONNS.values()], "log": list(LOG)[:60], "server_name": socket.gethostname()}


def send_to(cid, text):
    c = CONNS.get(cid)
    if not c: return False
    try: c.send({"type": "msg", "from": "admin", "text": text[:500]}); log("sent", f"to {c.name}: {text[:200]}", "admin"); return True
    except OSError: return False


def drop(cid):
    c = CONNS.get(cid)
    if not c: return False
    try: c.sock.close()
    except OSError: pass
    return True
