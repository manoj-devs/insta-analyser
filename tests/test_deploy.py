"""Hosting without SMTP ports (e-mail over HTTPS) and the compressed warehouse parts used for the GitHub copy."""
import gzip, json, os, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from fastapi.testclient import TestClient
import main
from app import config, otp, security
from tests.test_auth import H, post, SIGNUP
from tests.test_region import user
from tests.conftest import last_code


class Stub:
    """A tiny local web server that plays the part of the e-mail service."""
    def __init__(self, status=201):
        self.seen, self.status = [], status
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
                outer.seen.append({"headers": dict(self.headers), "body": body, "path": self.path})
                self.send_response(outer.status); self.send_header("content-type", "application/json"); self.end_headers()
                self.wfile.write(b'{"messageId":"x"}' if outer.status < 300 else b'{"message":"Key not found"}')
            def log_message(self, *a): pass
        self.srv = HTTPServer(("127.0.0.1", 0), Handler); self.url = f"http://127.0.0.1:{self.srv.server_port}/v3/smtp/email"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def close(self): self.srv.shutdown()


@pytest.fixture()
def api_mail(monkeypatch):
    s = Stub()
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test"); monkeypatch.setenv("MAIL_FROM", "InstaWarehouse <sender@example.com>"); monkeypatch.setenv("BREVO_URL", s.url)
    yield s
    s.close()


def test_api_mail_counts_as_real_delivery(api_mail):
    assert security.api_mail_configured() and security.smtp_configured()


def test_mail_goes_over_https_api_with_key_and_sender(api_mail):
    assert security.send_mail("someone@example.com", "Subject", "Your code is 123456")
    r = api_mail.seen[0]
    assert r["headers"]["api-key"] == "xkeysib-test" and r["path"] == "/v3/smtp/email"
    assert r["body"]["sender"] == {"name": "InstaWarehouse", "email": "sender@example.com"} and r["body"]["to"] == [{"email": "someone@example.com"}]
    assert r["body"]["subject"] == "Subject" and "123456" in r["body"]["textContent"]


def test_api_mail_failure_is_reported_not_hidden(monkeypatch):
    s = Stub(status=401)
    monkeypatch.setenv("BREVO_API_KEY", "bad"); monkeypatch.setenv("MAIL_FROM", "a@example.com"); monkeypatch.setenv("BREVO_URL", s.url)
    assert security.send_mail("x@example.com", "S", "B") is False and "401" in security.LAST_ERROR
    s.close()


def test_signup_in_production_works_with_api_mail_and_code_is_only_in_the_mail(api_mail, monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION", True); monkeypatch.setattr(otp, "PRODUCTION", True, raising=False)
    c = TestClient(main.app)
    r = post(c, "/api/auth/signup", **{**SIGNUP, "email": "prod@example.com"})
    assert r.status_code == 200 and "demo_otp" not in r.text
    code = json.dumps(api_mail.seen[-1]["body"]["textContent"]); import re
    num = re.search(r"\b(\d{6})\b", code).group(1)
    assert post(c, "/api/auth/verify", email="prod@example.com", code=num, ticket=r.json()["ticket"]).status_code == 200


def test_warehouse_is_rebuilt_from_compressed_parts(tmp_path, monkeypatch):
    data = os.urandom(300_000) + b"x" * 400_000
    blob = gzip.compress(data); cut = len(blob) // 2
    proc = tmp_path / "data" / "processed"; proc.mkdir(parents=True)
    (proc / "warehouse.db.gz.part1").write_bytes(blob[:cut]); (proc / "warehouse.db.gz.part2").write_bytes(blob[cut:])
    monkeypatch.setattr(config, "ROOT", str(tmp_path))
    config.unpack_warehouse()
    assert (proc / "warehouse.db").read_bytes() == data
    config.unpack_warehouse()                                         # second call does nothing and keeps the file
    assert (proc / "warehouse.db").read_bytes() == data
