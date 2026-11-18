# Putting InstaWarehouse online (one server, one database, every device)

Everyone must reach the **same running server**; that is what makes a post or saved analysis made on a phone appear on a laptop.

1. **Host**: any service that runs a Docker container with a persistent disk (Render, Railway, Fly.io, a VPS). `render.yaml` is ready for Render.
2. **Database**: SQLite file `auth.db` on the persistent disk (`DATA_DIR`). This is fine for one server and a class demo. For many simultaneous users move `app/db.py` to PostgreSQL (future work).
3. **Uploaded pictures**: saved in `DATA_DIR/uploads` on the same disk (not in the browser). For cloud storage, swap `UPLOAD_DIR` handling in `app/routers/account.py` for S3/Cloudinary.
4. **HTTPS**: the host terminates TLS; the app trusts `X-Forwarded-Proto`, marks cookies `Secure` and sends HSTS when `APP_ENV=production`.
5. **Secrets**: set `SECRET_KEY`, SMTP (and Twilio) values as environment variables on the host. They are never sent to the browser.
6. **Codes**: with `APP_ENV=production` sign-up is refused unless real delivery is configured, so a code is never shown on screen.
7. **First admin**: see README ("Admin sign-in"); change the password at first login.

## Decisions for the team (defaults chosen)
| Question | Default | Change with |
|---|---|---|
| OTP by email, SMS or both | email | `OTP_CHANNELS` |
| When is a code needed | sign-up, password reset, admin sign-in, and sign-in from a new browser | `OTP_LOGIN=always|new_device|never` |
| Hosting / database | one Docker server + SQLite on a persistent disk | `render.yaml` |

## Test checklist
- Correct code, wrong code, expired code (5 min), resend (old code stops working), 5 wrong tries -> 5-minute lock, failed delivery message: automated in `tests/test_otp.py`.
- Sign in on a second browser: asks for a code; trusted browser later skips it; picture/history seen on both.
- Phone, tablet, laptop widths (360, 414, 768, 1024, 1440): no sideways scroll, buttons at least 44 px.
- Open the hosted URL on two real devices and confirm the same data appears.


## Different networks without a server (quick demo): `share_online.py`
1. Put `SECRET_KEY=...` in `.env` and run `python setup_email.py` (codes must be e-mailed, never shown on screen).
2. Run `python share_online.py`. It starts the app in PUBLIC MODE (HTTPS-only cookies, 20 sign-in/code requests a minute per address, security headers) and a Cloudflare Tunnel (or ngrok if `NGROK_AUTHTOKEN` is set and ngrok is installed).
3. Open the first sign-in of the admin on THIS computer (`http://127.0.0.1:8000/admin`) and change the default password. Until then the admin link answers "closed" to the internet.
4. Share the printed user link. Admin and users can now be on different Wi-Fi or mobile data and see the same data, because there is still one server and one database (this computer).
5. Close the window to stop sharing. Anyone with the link can open the sign-up page while it is open.

Optional hardening: `ADMIN_ALLOWED_IPS` (comma list of IPs or networks) and `ADMIN_PATH` (a secret address instead of /admin).
Admin > Admins & Security has **Download backup / Restore** for the user database; Admin > Overview lists the last 20 admin sign-ins.

### Manual test checklist (different networks)
- Phone on mobile data opens the user link, signs up, receives the e-mailed code, verifies, opens Region Influencers.
- Laptop on Wi-Fi opens the admin link, signs in (password + e-mailed code) and sees the new user under Users.
- A saved analysis made on the phone appears in My History on the laptop (same account).
- Admin portal from a non-allowed address (if ADMIN_ALLOWED_IPS is set) shows "Not found".

## Hosting size (measured in the build 5.5 test report)
The server uses about 410 MB of memory when idle and about 465 MB after all the pages have been used. A 512 MB plan is therefore too small: choose a plan with at least 1 GB (Render "Standard" has 2 GB). The data disk needs about 700 MB (warehouse, models and CSV copies); the blueprint asks for 2 GB.
On the first start with an empty disk the app copies the bundled warehouse and CSV files onto it (about a minute). Free plans without a disk lose all users on every redeploy.

## Screenshot reading on the host (build 5.6)
The Dockerfile installs `tesseract-ocr`, so Render needs nothing extra when it builds from the Dockerfile. If you deploy without Docker, install Tesseract on the host or leave it out: the Creator Income pages still work with typed numbers. Check `GET /api/creator/meta` after deploying: `"ocr": true` means screenshot reading is on. Add to the test checklist: upload a real Insights screenshot, check every highlighted box, analyze, save, open My Progress, download the PDF.


## Two laptops on different networks by IP (Tailscale): `run_network.py`
Install Tailscale on both laptops and sign in. On the laptop that runs the app: `python setup_email.py` once, then double-click `run_network.bat`. It prints `http://100.x.x.x:8000/` (users) and `/admin`; the other laptop opens that address. Not needed on Render: there both laptops just open the Render address.
