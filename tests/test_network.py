import run_network as rn

WIN = "Ethernet adapter Tailscale:\n   IPv4 Address. . . . . . . . . . . : 100.101.22.7\nWireless LAN adapter Wi-Fi:\n   IPv4 Address. . . . . . . . . . . : 192.168.1.5\n"
LIN = "3: tailscale0    inet 100.88.9.1/32 scope global tailscale0\n2: eth0    inet 172.17.0.2/16 brd"


def test_only_tailscale_range_addresses_are_picked():
    assert rn.tailscale_addresses(WIN) == ["100.101.22.7"] and rn.tailscale_addresses(LIN) == ["100.88.9.1"]
    assert rn.tailscale_addresses("inet 100.200.1.1 and 10.0.0.3 and 100.63.255.255") == []        # 100.200 is outside 100.64-100.127
    assert rn.tailscale_addresses("") == [] and rn.tailscale_addresses(None) == []


def test_secret_key_is_created_once_and_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(rn, "ROOT", str(tmp_path)); monkeypatch.delenv("SECRET_KEY", raising=False)
    (tmp_path / ".env").write_text("SMTP_USER=a@b.com")
    rn.ensure_secret_key(); t = (tmp_path / ".env").read_text()
    assert "SMTP_USER=a@b.com\nSECRET_KEY=" in t
    rn.ensure_secret_key(); assert (tmp_path / ".env").read_text() == t
