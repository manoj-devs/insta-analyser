# Connect two laptops on different networks (Tailscale)

Laptop A runs the website. Laptop B opens it by Laptop A's private IP. Nothing is public and nothing is hosted online.

## One time, on both laptops
1. Install Tailscale: https://tailscale.com/download (Windows: run the installer, then sign in from the tray icon).
2. Laptop A signs in. Then at login.tailscale.com > Machines > the A machine > Share, send the invite to your friend; they open it on Laptop B and sign in. (Testing alone: sign in to both laptops with the same account.)
3. Both show "Connected".

## One time, on Laptop A only
1. Install Python 3.10+ (tick "Add python.exe to PATH").
2. Unzip instawarehouse.zip, open the folder `iw` in File Explorer, type `cmd` in the address bar and press Enter.
3. `python -m pip install -r requirements.txt`
4. `python setup_email.py` (Gmail address + 16-letter App Password; needed so sign-up codes reach the user's inbox).

## Every time
1. Laptop A: double-click `run_network.bat`. It prints, for example, `http://100.101.22.7:8000/` and `http://100.101.22.7:8000/admin`. Keep the window open.
2. Laptop B: open that user address in a browser, sign up, enter the e-mailed code.
3. Admin: open the /admin address on either laptop. Sign in with the admin e-mail (the Gmail you typed in setup_email) and `Admin@12345`, enter the e-mailed code, then choose a new password.

If A says "Tailscale was not found": open Tailscale and wait for "Connected". If B cannot open the page: check that both show Connected and that the address matches exactly.

## On Render (tomorrow)
Tailscale is not used. Render gives one public address; both laptops simply open it (admin at /admin). See DEPLOY_RENDER_FREE.md.

## TCP link between the two laptops (faculty requirement)
Besides the website, the app opens a plain TCP port (default 9000) on Laptop A.
1. Laptop A: run `run_network.bat` (it prints the IP and the TCP command). Admin portal > TCP Link shows the port and password.
2. Laptop B: open the project folder in a terminal and run `py tcp_client.py <Laptop A IP> 9000` (it asks for the password shown on A: terminal and Admin > TCP Link).
3. Laptop B appears under "Connected laptops" on A within a second, with ping time and bytes. Use Message to send text to B; type in B's terminal to send to A.
Wrong password = refused. Works on the same Wi-Fi or over Tailscale. Allow Python through Windows Firewall on A when asked (Private networks).
