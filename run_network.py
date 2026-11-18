"""Run InstaWarehouse so a second laptop on ANOTHER network can use it through a private network (Tailscale). No public link, no localhost.

    python run_network.py            (on Windows: double-click run_network.bat)

This laptop becomes the server. It gets a private Tailscale IP (like 100.101.22.7). The other laptop, once it is also on Tailscale,
opens  http://<that IP>:8000/  (users)  or  http://<that IP>:8000/admin  (admin). Only devices on your Tailscale network can reach it.
"""
import ipaddress, os, re, shutil, subprocess, sys, secrets

ROOT = os.path.dirname(os.path.abspath(__file__)); os.chdir(ROOT); sys.path.insert(0, ROOT)
PORT = int(os.getenv("PORT", "8000"))
TS_NET = ipaddress.ip_network("100.64.0.0/10")                     # the address range Tailscale uses
CLI = [shutil.which("tailscale") or "", r"C:\Program Files\Tailscale\tailscale.exe", "/Applications/Tailscale.app/Contents/MacOS/Tailscale", "/usr/bin/tailscale"]


def say(m=""): print(m, flush=True)


def tailscale_addresses(text):
    """every Tailscale-range IPv4 address found in some command output"""
    out = []
    for m in re.finditer(r"\b(100\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", text or ""):
        try:
            if ipaddress.ip_address(m.group(1)) in TS_NET and m.group(1) not in out: out.append(m.group(1))
        except ValueError: pass
    return out


def run(cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
    except Exception: return ""


def find_ip():
    if os.getenv("NETWORK_IP"): return os.getenv("NETWORK_IP")                               # manual override
    for exe in CLI:
        if exe and os.path.exists(exe):
            ips = tailscale_addresses(run([exe, "ip", "-4"]))
            if ips: return ips[0]
    for cmd in (["ipconfig"], ["ip", "-4", "addr"], ["ifconfig"]):                              # fallback: look at this computer's network adapters
        if shutil.which(cmd[0]):
            ips = tailscale_addresses(run(cmd))
            if ips: return ips[0]
    return None


def ensure_secret_key():
    """the one-time codes are signed with SECRET_KEY: create one in .env if there is none (never overwrites)"""
    p = os.path.join(ROOT, ".env"); text = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    if re.search(r"^\s*SECRET_KEY\s*=\s*\S", text, re.M) or os.getenv("SECRET_KEY"): return
    with open(p, "a", encoding="utf-8") as f: f.write(("\n" if text and not text.endswith("\n") else "") + "SECRET_KEY=" + secrets.token_urlsafe(32) + "\n")
    say("  Created a SECRET_KEY in .env (needed to sign the e-mail codes).")


def main():
    ip = find_ip()
    if not ip:
        say("\n  Tailscale was not found or is not connected on this computer.\n   1. Install it from https://tailscale.com/download and sign in.\n   2. Wait until the Tailscale icon shows 'Connected'.\n   3. Run this again.\n"); sys.exit(2)
    ensure_secret_key()
    from app import security, otp                                  # also loads .env
    if not (security.smtp_configured() or otp.sms_configured()):
        say("\n  E-mail codes are not set up yet, and the other laptop cannot read this computer's screen.\n  Run  python setup_email.py  first (Gmail address + App password), then run this again.\n"); sys.exit(2)
    os.environ.update(HOST=ip, APP_ENV="production", PORT=str(PORT))
    say("\n  ============================================================")
    say(f"  This laptop's private (Tailscale) address:  {ip}")
    say(f"  Other laptop, user portal :  http://{ip}:{PORT}/")
    say(f"  Other laptop, admin portal:  http://{ip}:{PORT}/admin")
    say(f"  TCP link (2nd laptop, in the project folder):  py tcp_client.py {ip} 9000")
    say("  (the TCP password is shown in the admin portal > TCP Link)")
    say("  The other laptop must have Tailscale installed and connected.")
    say("  Keep this window open. Closing it stops the site.")
    say("  ============================================================\n")
    os.execv(sys.executable, [sys.executable, "main.py"])


if __name__ == "__main__": main()
