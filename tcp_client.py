"""TCP client for the SECOND laptop. Connects to the InstaWarehouse laptop over a plain TCP socket and talks to it.

    py tcp_client.py <server IP> [port]            interactive:  ping | stats | msg <text> | quit
    py tcp_client.py <server IP> 9000 --demo       runs 5 pings, asks for the stats, sends a message and stops

The server IP is the Tailscale address (100.x.x.x) printed by run_network.bat on the server laptop, or its Wi-Fi/LAN IP when both are on the same network.
The password is shown on the server laptop (terminal and Admin > TCP Link). Only the Python standard library is needed.
"""
import argparse, hashlib, hmac, json, socket, sys, threading, time


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("host"); ap.add_argument("port", nargs="?", type=int, default=9000)
    ap.add_argument("--password", "-p", default=""); ap.add_argument("--name", default=socket.gethostname()); ap.add_argument("--demo", action="store_true")
    a = ap.parse_args(); pw = a.password or input("TCP password (shown on the server laptop): ").strip()
    print(f"\n  Connecting to {a.host}:{a.port} ...")
    t0 = time.time()
    try: s = socket.create_connection((a.host, a.port), timeout=10)
    except OSError as e:
        print(f"  Could not connect: {e}\n  Check: the server laptop is running, the IP and port are right, both laptops are on Tailscale (or the same network), and the firewall allows Python.")
        sys.exit(1)
    print(f"  TCP connection established in {(time.time() - t0) * 1000:.0f} ms   (this laptop {s.getsockname()[0]}:{s.getsockname()[1]}  ->  server {a.host}:{a.port})")
    f = s.makefile("rwb", buffering=0); lock = threading.Lock()

    def send(o):
        with lock: s.sendall((json.dumps(o, separators=(",", ":")) + "\n").encode())

    def read(): return json.loads(f.readline().decode() or "null")
    ch = read()
    if not ch or ch.get("type") != "challenge": print("  This is not an InstaWarehouse TCP link."); sys.exit(1)
    send({"type": "hello", "name": a.name, "mac": hmac.new(pw.encode(), ch["nonce"].encode(), hashlib.sha256).hexdigest()})
    w = read()
    if not w or w.get("type") != "welcome": print("  Rejected:", (w or {}).get("text", "no answer"), "(wrong password?)"); sys.exit(1)
    print(f"  Handshake done. You are session #{w['session']} on server '{w['server']}'.\n")
    pend = {}; stop = threading.Event()

    def reader():
        try:
            while not stop.is_set():
                m = read()
                if m is None: break
                t = m.get("type")
                if t == "pong" and m.get("t") in pend:
                    rtt = (time.time() - pend.pop(m["t"])) * 1000; print(f"  pong from server: round trip {rtt:.1f} ms"); pend["last_rtt"] = rtt
                elif t == "stats": print("  server stats:", {k: v for k, v in m.items() if k != "type"})
                elif t == "msg": print(f"\n  >> message from {m.get('from', 'server')}: {m.get('text')}")
                elif t == "ack": print("  server:", m.get("text"))
                elif t == "error": print("  server error:", m.get("text"))
        except (OSError, ValueError): pass
        if not stop.is_set(): print("\n  The server closed the connection.")
        stop.set()
    threading.Thread(target=reader, daemon=True).start()

    def ping():
        tid = round(time.time(), 6); pend[tid] = time.time(); send({"type": "ping", "t": tid, "rtt_ms": pend.get("last_rtt")})
    try:
        if a.demo:
            for _ in range(5): ping(); time.sleep(0.5)
            send({"type": "stats"}); time.sleep(0.5); send({"type": "msg", "text": f"hello from {a.name}"}); time.sleep(0.8)
        else:
            print("  Commands:  ping   stats   msg <text>   quit\n")
            while not stop.is_set():
                try: line = input("tcp> ").strip()
                except EOFError: break
                if line == "ping": ping()
                elif line == "stats": send({"type": "stats"})
                elif line.startswith("msg "): send({"type": "msg", "text": line[4:]})
                elif line in ("quit", "exit", "q"): break
                elif line: print("  Unknown command. Use: ping | stats | msg <text> | quit")
                time.sleep(0.2)
    except KeyboardInterrupt: pass
    finally:
        try: send({"type": "bye"})
        except OSError: pass
        stop.set(); s.close(); print("  Disconnected.")


if __name__ == "__main__": main()
