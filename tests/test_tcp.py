"""The TCP link between two computers: handshake, ping, stats, messages both ways, wrong password, admin view. Uses this computer's real (non-loopback) IP when it has one."""
import json, os, socket, subprocess, sys, time
import pytest
from fastapi.testclient import TestClient
import main
from app.services import tcplink
from tests.test_region import admin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(("10.255.255.255", 1)); return s.getsockname()[0]
    except OSError: return "127.0.0.1"
    finally: s.close()


@pytest.fixture()
def link(monkeypatch):
    monkeypatch.setenv("TCP_PASSWORD", "abc123")
    tcplink.stop(); tcplink.STATE.update(running=False); ip = my_ip(); r = tcplink.start(ip, 19050); assert r, tcplink.STATE["error"]
    yield r; tcplink.stop(); tcplink.STATE.update(running=False)


def talk(host, port, pw):
    s = socket.create_connection((host, port), timeout=5); f = s.makefile("rwb", buffering=0)
    ch = json.loads(f.readline()); import hmac, hashlib
    f.write((json.dumps({"type": "hello", "name": "testlap", "mac": hmac.new(pw.encode(), ch["nonce"].encode(), hashlib.sha256).hexdigest()}) + "\n").encode())
    return s, f, json.loads(f.readline())


def test_wrong_password_is_refused_and_right_one_works(link):
    host, port = link
    s, f, w = talk(host, port, "nope"); assert w["type"] == "error"; s.close()
    s, f, w = talk(host, port, "abc123"); assert w["type"] == "welcome" and w["session"] >= 1
    f.write(b'{"type":"ping","t":1}\n'); assert json.loads(f.readline())["type"] == "pong"
    f.write(b'{"type":"stats"}\n'); st = json.loads(f.readline()); assert st["type"] == "stats" and "time" in st
    f.write(b'{"type":"msg","text":"hi from test"}\n'); assert json.loads(f.readline())["type"] == "ack"
    assert any(c["name"] == "testlap" for c in tcplink.status()["connections"]) and any("hi from test" in l["text"] for l in tcplink.status()["log"])
    assert tcplink.send_to(w["session"], "hello laptop"); m = json.loads(f.readline()); assert m == {"type": "msg", "from": "admin", "text": "hello laptop"}
    f.write(b'{"type":"bye"}\n'); s.close(); time.sleep(0.3); assert not tcplink.status()["connections"]


def test_client_script_demo_against_the_real_ip(link):
    host, port = link
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tcp_client.py"), host, str(port), "--password", "abc123", "--demo"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TCP connection established" in r.stdout and "Handshake done" in r.stdout and r.stdout.count("pong from server") == 5 and "server stats" in r.stdout
    assert any("hello from" in l["text"] for l in tcplink.status()["log"])
    bad = subprocess.run([sys.executable, os.path.join(ROOT, "tcp_client.py"), host, str(port), "--password", "wrong", "--demo"], capture_output=True, text=True, timeout=30)
    assert bad.returncode == 1 and "Rejected" in bad.stdout


def test_admin_api_is_admin_only_and_shows_the_link(link):
    with TestClient(main.app) as c:
        assert c.get("/api/admin/tcp/status").status_code in (401, 403)
        admin(c); st = c.get("/api/admin/tcp/status").json()
        assert st["running"] and st["port"] == link[1] and st["password"] == "abc123"
