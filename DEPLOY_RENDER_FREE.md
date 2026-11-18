# Put InstaWarehouse on Render (free) so two laptops on different networks use one website

Result: a public address like https://instawarehouse-xxxx.onrender.com. Laptop 1 opens it as a user; Laptop 2 opens it + /admin as admin. No localhost, no laptop acts as the server.

Free plan limits (be honest in the demo): it sleeps after 15 minutes idle (first visit then takes about a minute), and users/posts are lost when it restarts or redeploys. The admin account is rebuilt from the settings below each time.

## A. E-mail codes (Render free blocks Gmail/SMTP ports, so use Brevo over HTTPS, free 300 mails/day)
1. Sign up at brevo.com (no card). 2. Senders: add your Gmail address as a sender and click the link Brevo mails you. 3. Settings > SMTP & API > API Keys > generate a key (starts xkeysib-).

## B. GitHub
1. Run:  python tools/make_deploy_repo.py ../deploy   (makes a copy whose warehouse is 3 small parts; nothing over 40 MB)
2. Create an empty GitHub repository, then in the folder `deploy`:  git init, git add ., git commit -m "deploy", git remote add origin <your repo url>, git push -u origin main

## C. Render
1. New > Web Service (or Blueprint) > connect the repository > Language: Docker, Instance type: Free.
2. Environment variables: APP_ENV=production, DATA_DIR=/app/data, SECRET_KEY=<long random text>, OTP_CHANNELS=email, OTP_LOGIN=new_device, BREVO_API_KEY=<key>, MAIL_FROM=InstaWarehouse <your gmail>, ADMIN_EMAIL=<your gmail>, ADMIN_PASSWORD=<a strong password, 10+ chars, not your name>.
   (Using the Blueprint option with render.yaml fills the first ones for you; you type the secret ones.)
3. Deploy. The first build takes several minutes (it installs Tesseract and unpacks the data).

## D. Use it
Laptop 1: open the address, sign up, enter the e-mailed code. Laptop 2: open the address + /admin, sign in with ADMIN_EMAIL and ADMIN_PASSWORD, enter the e-mailed code.
