# InstaWarehouse – two portals: User and Admin

> **Which zip?** `instawarehouse.zip` is the complete project (data included, works on its own). `instawarehouse_code_only.zip` has no data: unzip it *on top of* a folder that already has `data/`, otherwise the dashboards stay empty.

## Run (Python 3.10+)
1. `pip install -r requirements.txt`
2. Put your three finished files in `data/raw/`:
   `clean_instagram_posts.csv`, `clean_instagram_reach.csv`, `combined_instagram_data.csv`
   (if they are missing, the app cleans `Instagram_data.csv` + `intsa_data2.csv` from scratch instead)
3. `python main.py`
   - User portal  : http://127.0.0.1:8000/
   - Admin portal : http://127.0.0.1:8000/admin

First start builds the warehouse automatically (about 30 s).

## Admin sign-in
- Default: `admin@instawarehouse.com` / `Admin@12345`. You are forced to choose a new password at first sign-in.
- To choose your own at the start: set `ADMIN_EMAIL` and `ADMIN_PASSWORD` before the first run.
- After the first password change every admin sign-in needs password + a 6-digit emailed code (`ADMIN_2FA=0` turns the code off).
- Forgot the admin password: `python reset_admin.py`.

## Email codes
Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` to send real emails (Gmail: smtp.gmail.com, 587, an app password).
Without them the code is shown on screen (demo mode), which is fine for a demonstration but not for real use.

## Authentication
| | User portal | Admin portal |
|---|---|---|
| URL / API | `/` , `/api/auth/*` | `/admin` , `/api/admin/auth/*` |
| Cookie | `iw_user` (8 h, 4 h idle) | `iw_admin` (4 h, 30 min idle) |
| Sign-in | email + password | email + password + emailed code |
| Sign-up | yes, email code, no admin approval | no; an admin creates admins |
| Extras | forgot / reset password, change password, profile, devices, data export | forced first password change, add admins |

An admin account cannot sign in to the user portal and a user can never reach admin pages or APIs.
Passwords: scrypt hashes, strength rules (length, upper/lower/number, common-password and name/email checks), 5 wrong tries lock an account for 10 minutes, new session token on every sign-in, changing a password signs out other devices, blocked/deleted users are signed out instantly.

## What is collected (shown to users at sign-up)
Profile (name, email, optional phone, country, type, handle, interests, consent time, sign-up IP), every analysed account and its result, page visits, feedback, sign-in history. Admins see it in **Collected Data**, **Users** (detail panel) and **Overview**, and can export CSVs. Users can download their own data and delete saved analyses.

## Data mining (new)
Models train automatically on the first start (about a minute) and after every ETL; admins can retrain in **Mining Lab**. Needs `scikit-learn` (in requirements.txt).
- **Engagement predictor** (gradient boosting, hold-out tested): next-post likes/comments and the 3 changes that help most.
- **Creator personas** (k-means), **caption text mining** (TF-IDF + logistic regression), **breakout detector** (admin list).
- **My Account Analyser**: forecast + persona + estimated fee per sponsored post. **Influencer Analyser**: type the public numbers of any celebrity or influencer, optionally a post, and get the forecast and estimated fee (USD and INR). No live Instagram access.
- **No celebrity dataset is needed.** The Influencer Analyser works for ANY public account (Kohli, Ronaldo, a tennis player, a local influencer) from three numbers: followers, category and, optionally, average likes and comments (if left empty, the typical engagement for that audience size is assumed). The "Quick pick" list only pre-fills approximate follower counts (Wikipedia, Sept 2026; tennis players from a May 2023 article) and can be edited.
- Fees are estimates: Influencer Marketing Hub 2026 benchmarks up to 10M followers; for 10M+ the curve is anchored on the Hopper HQ Instagram Rich List (2019 and 2024 agency-rate estimates, about $5 to $6 per 1,000 followers; Ronaldo 633M = $3.43M per post). The curve reproduces those published figures within about 10%. Beyond about 650M followers it is extrapolated. Set `INR_PER_USD` to change the exchange rate (default 88).

## OTP pop-up and multi-device use (faculty feedback)
- Sign-up, password reset, admin sign-in and sign-in from a **new browser** open a pop-up: 6 boxes, Verify, Resend (30 s wait), 5-minute countdown, works on phones.
- The code is created and checked **on the server**, stored only as a salted hash, expires after 5 minutes, a resend cancels the older code, 5 wrong tries lock the account for 5 minutes, and it is never shown on screen, in the URL or in logs. Clear messages for correct, wrong, expired, locked and failed delivery.
- Choose email / SMS / both with `OTP_CHANNELS`, and when a code is needed with `OTP_LOGIN` (see `.env.example`).
- Profile page: upload a profile picture (kept on the server) and see/remove trusted devices.
- Going online: see `DEPLOY.md`.

## Region influencer analyser (build 5.5)
- User portal > **Region Influencers**: choose continent / country / state, category and size band, then see **every influencer in that region** (paged, sortable, searchable), their **estimated** earnings per post, per month and per year (low - mid - high, INR or USD), and tap one to get **Steps to earn more** (ranked, with the extra yearly income each step could bring), a 3/6/12-month projection and a **what-if simulator**. Compare two regions, export CSV/Excel.
- The posts dataset has **no region column**, so regions come from an **influencer directory**. The zip ships **66 real public figures** (celebrities, cricketers, creators, Tamil Nadu) with the follower count, the date and the public page it came from. Instagram does not publish income, so the money columns are **estimates** from the fee model. Add more rows in Admin > Regions (CSV) or in `tools/make_real_directory.py`.
- Money is always an estimate (published rate curve x engagement x category x a region price level). Assumptions are listed at the bottom of the page and can be changed with `SPONSORED_SHARE`, `GROWTH_PCT_MONTH`, `OTHER_STREAMS_PCT` in `.env`.

## Creator Income Analyser (build 5.6)
Menu group "Creator Income": Post Analyzer, Income Planner, My Progress. It estimates what ordinary creators can earn from their OWN content (affiliate links, own products, services, subscriptions). Brand deals and sponsored posts are not part of it; those stay on the Influencer Analyser and Region Influencers pages. Every figure is an estimate shown as low / likely / high, and the assumptions are listed on the page.
Screenshot reading needs the free Tesseract program: Linux `sudo apt install tesseract-ocr`, macOS `brew install tesseract`, Windows https://github.com/UB-Mannheim/tesseract/wiki (tick "add to PATH"). Without it the page still works; the upload button is switched off and numbers are typed. The Docker image installs it for you. Screenshots are processed in memory and never saved.

## Admin and users on different networks (build 5.5)
Run `python share_online.py` (or double-click `share_online.bat`). It starts the server in public mode and a free Cloudflare Tunnel, then prints a public https link for users and one for the admin (plus a QR code). Needs `SECRET_KEY` and email set up (`python setup_email.py`). The default admin password must be changed on this computer first; until then the admin link is closed to the internet. The link works while the window is open and changes each run. For a permanent address see DEPLOY.md. Optional: `ADMIN_ALLOWED_IPS=1.2.3.4,10.0.0.0/8` and `ADMIN_PATH=my-secret-admin` limit the admin portal.

## Tests
`python -m pytest -q` (uses a temporary database).

## Notes
Income figures are illustrative estimates (fixed rates per 1,000 followers); the dataset has no real earnings. Handle ownership is not verified.

## Troubleshooting: "Please choose your country" with no country field, or a red banner at the top
That means the folder mixes files from two different zips (for example an old `static/index.html` with a new `static/js/user.js`).
The app now checks this itself (build 5.3) and shows a red banner. Fix: delete the old project folder, unzip the newest
`instawarehouse.zip` completely into a new folder, restart `python main.py`, and press Ctrl+F5 in the browser.

## Getting the codes by real email (instead of on the screen)
Out of the box the 6-digit codes are shown on the screen (demo mode), because a server cannot send email without an account to send from.
To send them to the person's inbox using Gmail:
1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an App password: https://myaccount.google.com/apppasswords (name it InstaWarehouse, copy the 16 letters)
3. Run `python setup_email.py` (or double-click `setup_email.bat`). It asks for the Gmail address, the App password and the admin email, sends a test email, then saves the settings in `.env`.
4. Restart `python main.py`. From now on sign-up, forgot-password and admin sign-in codes arrive by email and are never shown on screen. If sending fails the user sees an error, not the code.
Keep `.env` private (it holds the App password). To go back to demo mode, delete `.env`.

## Dashboard notes
The posts dataset ends on 14 Aug 2019, so there is no real data for 2020 to 2026. The yearly chart shows 2012 to 2026, and the 2020 to 2026 part is a dotted straight-line projection of the 2014 to 2018 trend with a range, clearly labelled as not real data.
