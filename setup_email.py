"""One-time email setup:  python setup_email.py

Makes InstaWarehouse send the 6-digit sign-up / password-reset / admin codes to the person's real inbox.
It works with a normal Gmail account:
  1. Turn on 2-Step Verification:  https://myaccount.google.com/security
  2. Create an App password:       https://myaccount.google.com/apppasswords   (name it InstaWarehouse, copy the 16 letters)
  3. Run this script, paste the Gmail address and the App password. It sends you a test email and saves the settings in
     the file  .env  (keep that file private, never share it or upload it).
"""
import getpass, os, sqlite3, sys
ROOT = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ROOT)
from app import config, security          # noqa: E402  (loading app.config also reads any existing .env)

print(__doc__)
smtp_user = input("Your Gmail address (the one that SENDS the codes): ").strip()
smtp_pass = getpass.getpass("Gmail App password (16 letters, typing is hidden): ").replace(" ", "").strip()
host = input("SMTP server [smtp.gmail.com]: ").strip() or "smtp.gmail.com"
port = input("SMTP port [587]: ").strip() or "587"
admin = input(f"Admin email, where the ADMIN sign-in codes are sent [{smtp_user}]: ").strip() or smtp_user

os.environ.update(SMTP_HOST=host, SMTP_PORT=port, SMTP_USER=smtp_user, SMTP_PASS=smtp_pass, SMTP_FROM=f"InstaWarehouse <{smtp_user}>")
print("\nSending a test email to", smtp_user, "...")
if not security.send_mail(smtp_user, "InstaWarehouse email test", "If you can read this, InstaWarehouse can send your sign-up codes by email."):
    print("\nFAILED:", security.LAST_ERROR)
    print("Most common reasons: (a) you used your normal Gmail password instead of an App password, (b) 2-Step Verification is not on,")
    print("(c) a typo in the 16 letters. Nothing was saved. Fix it and run this script again.")
    sys.exit(1)

lines = [f"SMTP_HOST={host}", f"SMTP_PORT={port}", f"SMTP_USER={smtp_user}", f"SMTP_PASS={smtp_pass}", f"SMTP_FROM=InstaWarehouse <{smtp_user}>", f"ADMIN_EMAIL={admin}"]
with open(os.path.join(ROOT, ".env"), "w", encoding="utf-8") as f: f.write("# written by setup_email.py - private, do not share\n" + "\n".join(lines) + "\n")
print("Test email sent. Settings saved in .env")

# if an admin account already exists with another email, move it to the new admin email so the codes reach you
if os.path.exists(config.AUTH_DB):
    c = sqlite3.connect(config.AUTH_DB)
    r = c.execute("SELECT id,email FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    if r and r[1].lower() != admin.lower():
        taken = c.execute("SELECT 1 FROM users WHERE email=? AND id<>?", (admin.lower(), r[0])).fetchone()
        if taken: print(f"The admin email {admin} is already used by a normal user account, so the admin account keeps {r[1]}. Use another email or delete that user.")
        else:
            c.execute("UPDATE users SET email=? WHERE id=?", (admin.lower(), r[0])); c.commit()
            print(f"The admin account email was changed from {r[1]} to {admin.lower()}.")
    c.close()
print("\nDone. Restart the server (python main.py). New sign-ups will now get their code in their inbox, and nothing is shown on the screen.")
