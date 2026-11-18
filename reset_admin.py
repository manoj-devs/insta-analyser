"""Forgot the admin password?  python reset_admin.py  -> sets it back to Admin@12345 (you must change it at next sign-in)."""
from app import db, security
db.init(); c = db.conn()
n = c.execute("UPDATE users SET pw=?, must_change=1, status='active' WHERE role='admin' AND id=(SELECT MIN(id) FROM users WHERE role='admin')", (security.hash_pw("Admin@12345"),)).rowcount
c.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE role='admin')"); c.commit()
print("Admin password reset to Admin@12345" if n else "No admin account found; start the app once to create it.")
