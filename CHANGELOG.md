## 5.7.1
- Reports redesigned to be colourful and visual: dark cover with coloured contents chips, coloured section banners per group, multi-colour bars, solid colour KPI tiles, colour-ramp heat maps, charts on soft cards, rainbow page strip. Text kept to one short caption per chart.

## 5.7
- NEW Reports page (user and admin): pick any dashboard items from a grouped drop-down (KPIs, yearly/category/tier/hour charts, star and snowflake schema, OLAP cube, ETL, mining models, personas, regions, earnings, admin usage) and get a mostly graphical PDF. A "Previous reports" tab keeps earlier ones to download or delete.
- NEW TCP link (tcp_client.py, app/services/tcplink.py, Admin > TCP Link): a raw TCP connection between two laptops with a password handshake (HMAC), ping/RTT, byte counts, messages both ways and a live log. Needs a reachable IP (same Wi-Fi or Tailscale); a Cloudflare public link carries only web traffic, not raw TCP.
- run_network.py prints the TCP command for the second laptop.

## 5.6.3
- Real directory grown from 66 to 566 named public creators/celebrities (follower counts and date printed by the public page named in each row). Delhi, Maharashtra, Karnataka, Gujarat, Telangana, Tamil Nadu and Uttar Pradesh have 30+; West Bengal 28; other states are thinner. No names are invented to fill a state: add rows in Admin > Regions or tools/make_real_directory.py.
- tools/make_real_directory.py now also reads app/seed/creators_socialveins.txt.

## 5.6.2
- The 720 synthetic demo influencers and every 'demo' label are removed; old sample rows are deleted on start.
- Directory now holds 66 real public figures with sourced, dated follower counts (tools/make_real_directory.py). Engagement is not published for them, so the typical rate for the size is used; earnings stay labelled estimates.
- NEW run_network.py / run_network.bat: runs the app on the laptop's Tailscale IP so a second laptop on another network connects by IP (no public link, no localhost). Creates SECRET_KEY if missing.

## 5.6.1
- E-mail can be sent over HTTPS (Brevo, BREVO_API_KEY + MAIL_FROM) for hosts that block SMTP ports, such as Render free.
- Warehouse can ship as gzip parts (tools/make_deploy_repo.py) so a GitHub push needs no Git LFS; rebuilt at image build.
- render.yaml is now the free blueprint; render-paid.yaml keeps data on a disk.
- Start-up warm-ups run one after another and the cube streams rows: peak memory about 470 MB instead of 850 MB.

# Changelog

## 5.6 - Creator Income Analyser (organic income, no sponsorship)
- NEW menu group "Creator Income" (separate from the brand-deal pages): Post Analyzer, Income Planner, My Progress.
- NEW Post Analyzer: engagement rate, rank against 605K warehouse posts of the same account size, estimated organic income for the post (low / likely / high), tips from what worked (hashtags, caption length, weekday).
- NEW screenshot reader: upload a screenshot of Insights, a post or a profile; numbers are read with Tesseract, filled into the form and highlighted for the user to check. The picture is never stored and its text is never returned.
- NEW Income Planner: four organic streams (affiliate, own product, services, subscription), readiness score out of 100, ranked steps (each re-runs the same model with one change), what-if sliders, 12-month projection, one-page PDF report card, plan saved per user across devices.
- NEW My Progress: saved posts per user, trend, best post, and warehouse insights by account size.
- Separate code: app/services/creator.py never uses the sponsorship fee engine (a test checks this).
- Deployment: Dockerfile installs tesseract-ocr; requirements add pillow, pytesseract, reportlab. If Tesseract is missing the page asks for typed numbers.
- Tests: tests/test_creator.py (16 tests). Memory: benchmarks are built once and the working memory is released (about 150 MB resident after loading).

## 5.5 - region analyser, public access, phone menu
- NEW Region Influencers page (user) and Regions & Directory page (admin): region tree, paged/sortable/searchable influencer table, estimated earnings per post/month/year (low-mid-high, INR/USD), ranked Steps to earn more with uplift, 3/6/12-month projection, what-if simulator, region comparison, CSV/Excel export.
- NEW influencer directory (table in auth.db) with CSV upload, validation and rejected-row report; 720 synthetic demo rows bundled (badged, never presented as real).
- NEW share_online.py / .bat: public https link through Cloudflare Tunnel or ngrok, QR code, readiness checks, public mode.
- NEW public-mode safety: refuses to start without SECRET_KEY and e-mail delivery; admin closed to the internet until the default password is changed; optional ADMIN_ALLOWED_IPS / ADMIN_PATH; stricter sign-in rate limit; CSP/Referrer/Permissions headers; last 20 admin sign-ins on the overview.
- NEW admin backup download and restore (typed confirmation, safety copy kept).
- NEW slide-in menu on phones (the menu no longer pushes the page down).
- Tests: tests/test_region.py (engine, steps, simulator, CSV validation, API paging/filters/access, export, upload, backup/restore, public mode, allow-list, headers).

## 5.4 - OTP pop-up, multi-device sessions, profile picture, trusted devices, deploy files
