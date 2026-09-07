# Shantini Crackers

Flask and MySQL application for browsing fireworks, creating customer estimates,
and managing products through an admin dashboard.

## Requirements

- Python 3.10 or newer
- MySQL 8 or compatible MySQL server
- Git, if cloning the project
- A mail account with an app password, if estimate emails are required

## Project Setup

Open a terminal in the project directory:

```powershell
cd D:\fireworks
```

Create and activate a virtual environment on Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

## Environment Configuration

Copy `.env.example` to `.env` and replace the example values:

```powershell
Copy-Item .env.example .env
```

Important settings:

```dotenv
SECRET_KEY=use-a-long-random-value
MYSQL_HOST=127.0.0.1
MYSQL_USER=fireworks_app
MYSQL_PASSWORD=your-mysql-password
MYSQL_DB=fireworks_db
ADMIN_EMAIL=admin@example.com
ADMIN_PHONE=+911234567890
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-gmail-app-password
MAIL_USE_TLS=true
MAIL_FROM=your-email@example.com
```

Do not commit `.env`. It contains database, mail, and session secrets.

## Initialize MySQL

Make sure MySQL is running and that the configured MySQL user can create the
`fireworks_db` database. Then run:

```powershell
python init_db.py
```

The initializer creates the database tables and loads the catalog seed data.
It also creates the first admin using `ADMIN_EMAIL` and `ADMIN_PHONE` from
`.env`. The current initializer uses `ananthi` as the initial admin password;
change that password before using the application remotely.

The application server and MySQL server may be on different machines. In that
case, set `MYSQL_HOST` to the private IP or DNS name of the MySQL server and
allow MySQL traffic only from the application server on port `3306`.

## Run Locally

Start the development server:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

Admin login:

```text
http://127.0.0.1:5000/admin/login
```

The development server is intended for local testing only.

## Use From Another Device on the Same Network

Run Flask on all network interfaces:

```powershell
flask --app app run --host 0.0.0.0 --port 5000
```

Find the host computer's private IP address:

```powershell
ipconfig
```

On another device connected to the same network, open:

```text
http://YOUR_HOST_IP:5000/
```

For example:

```text
http://192.168.1.25:5000/
```

If the page cannot be reached, check that:

1. The Flask process is still running.
2. Both devices are on the same network.
3. Windows Firewall allows inbound TCP traffic on port `5000`.
4. The URL uses the host computer's IP address, not `localhost`.
5. The router or network does not isolate wireless clients.

Do not port-forward the Flask development server directly to the public
internet.

## Remote Deployment

For a server or public deployment:

1. Use a Linux server or a managed Python hosting service.
2. Store `.env` values in the hosting provider's secret/environment settings.
3. Run the application with a production WSGI server such as Gunicorn or
	Waitress instead of `python app.py`.
4. Put Nginx, Apache, or the hosting provider's HTTPS proxy in front of it.
5. Allow inbound HTTP/HTTPS traffic only through the reverse proxy.
6. Keep MySQL private and restrict port `3306` to the application server.
7. Set `SECRET_KEY` to a long random value and use a strong database password.
8. Disable debug mode in production.

Example Gunicorn command on Linux after installing Gunicorn:

```bash
gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
```

The reverse proxy should forward requests to `127.0.0.1:8000` and provide
HTTPS for users.

## Email Estimates

Gmail and other providers generally require an app password rather than the
normal mailbox password. If `MAIL_USERNAME` or `MAIL_PASSWORD` is empty, the
application still saves estimate PDFs locally but does not send email.

Generated estimate PDFs are stored under:

```text
downloads/estimates/
```

## Tests

Run the existing tests with:

```powershell
python -m unittest tests.test_user_login_flow -v
```

## Useful URLs

| Page | URL |
| --- | --- |
| Home | `/` |
| Products | `/products` |
| Customer account | `/account` |
| Cart / estimate | `/cart` |
| Admin login | `/admin/login` |
| Admin dashboard | `/admin/dashboard` |
