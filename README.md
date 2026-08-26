# Hound Coder

This is a project to run a local LLM stack for coding assistance. It runs a a code completion server and an agent server on a DGX Spark. These can be accessed utilizing the Continue extension in VS Code.

```bash
# Note: all commands should be run as root (or with sudo)

# Install dependencies
apt install nginx docker-compose git python3-venv

# Clone the repo to /opt/hound-coder
cd /opt
git clone git@github.com:MoravianUniversity/HoundCoder.git hound-coder
cd hound-coder

# 'Install' files
ln -s $PWD/hound-coder-vllm.service /etc/systemd/system/hound-coder-vllm.service
ln -s $PWD/hound-coder-auth.service /etc/systemd/system/hound-coder-auth.service
ln -s $PWD/hound-coder-logrotate.conf /etc/logrotate.d/hound-coder

# Register and enable the hound-coder vLLM service to start on boot
systemctl daemon-reload
systemctl enable --now docker
systemctl enable --now hound-coder-vllm.service

# Set up the auth server (token validation + admin API)
cd auth-server
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cd ..

# Seed the first admin user; save the printed JWT, it's your admin token (needed to reach /admin/)
AUTH_DATA_DIR=$PWD/auth auth-server/venv/bin/python auth-server/bootstrap.py --email you@example.com

# Configure Google OAuth self-service registration (optional but recommended)
cp auth-server/.env.example auth-server/.env
# edit auth-server/.env with a Google OAuth client id/secret and your allowed email domain

systemctl enable --now hound-coder-auth.service

# Set the host-specific nginx settings (server_name, and eventually TLS)
cp local.conf.example /opt/hound-coder/local.conf
# edit /opt/hound-coder/local.conf to set the real server_name

# Copy nginx config
ln -s $PWD/hound-coder.conf /etc/nginx/sites-available/hound-coder.conf
ln -s /etc/nginx/sites-available/hound-coder.conf /etc/nginx/sites-enabled/hound-coder.conf
rm -f /etc/nginx/sites-enabled/default
systemctl enable nginx
systemctl restart nginx
```

If you ever see the stock "Welcome to nginx!" page instead of the Hound Coder pages, `/etc/nginx/sites-enabled/default` has come back (e.g. reinstated by an `nginx` package upgrade) and is winning as the `default_server` for port 80. Re-run `rm -f /etc/nginx/sites-enabled/default && systemctl reload nginx` — `local.conf.example`'s `listen 80 default_server;` also guards against this as long as `local.conf` was copied from it.

# Check it is working

```bash
# Does not require root
systemctl status hound-coder-vllm.service
systemctl status hound-coder-auth.service
docker compose -f /opt/hound-coder/docker-compose.yaml ps
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/tab/models  # should return 401 (unauthorized)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" http://localhost/tab/models  # should return 200, $TOKEN from bootstrap.py or the /admin/ UI
```

## Managing allowed users

Visiting the server's root URL shows a static welcome page (served straight from [www/index.html](www/index.html) by nginx) explaining what the service is and how to get access — no auth required, since it's just informational.

### Self-service registration (Google OAuth)

Users on the approved email domain can register themselves at `/auth/info` by signing in with Google, instead of
waiting for an admin. Set this up via [auth-server/.env.example](auth-server/.env-example):

1. Create an OAuth 2.0 client in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials), with
   authorized redirect URI `https://<your-host>/auth/google/callback`.
2. Copy `auth-server/.env.example` to `auth-server/.env` and fill in `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and
   `ALLOWED_EMAIL_DOMAIN` (only Google accounts on this domain may register). `.env` is not tracked in git.
3. Restart `hound-coder-auth.service` to pick up the new settings.

On sign-in, the server checks Google's `email_verified` claim and the account's domain, rejects blocked emails, and
then creates the user (non-admin) if needed. It reuses the user's most recently issued non-revoked token if one
exists, or issues a new one otherwise, then lets them download their Continue config from a success page — same
template and token format as the admin-issued ones below.

Admins can block specific email addresses (whether or not they've registered yet) from the `/admin/` UI's
blocklist section; blocking revokes all of that email's existing tokens and prevents future self-registration or
token issuance for it.

### Admin UI

Open `http://localhost/admin/` in a browser and paste an admin JWT (e.g. the one printed by `bootstrap.py`) to add/remove users, toggle admin status, and issue or revoke tokens. The same operations are available directly via the `/admin/api/users` REST API using that bearer token.

Each token row also has a "Continue config" button that downloads [continue-config-template.yaml](continue-config-template.yaml) with that token filled in, ready to drop into a user's Continue extension config. The `apiBase` (scheme, host, and port) in that config is derived from `/opt/hound-coder/local.conf`: the `server_name`, and whichever `listen` directive is found first (an SSL one wins over a plain one), so it only needs to be set in one place.

## Usage logging

Every request to `/tab/` or `/chat/` is logged to `/opt/hound-coder/usage.log` with the requester's email, token issue date, the request line (method + path), the response status, and the request body (the prompt/messages sent, not the model's response) — useful for auditing student assignment usage. The body is dropped from a log entry if it's larger than `client_body_buffer_size` (1 MB) since nginx then spills it to a temp file instead of keeping it available to log; bump that value in [hound-coder.conf](hound-coder.conf) if you expect larger prompts.

[hound-coder-logrotate.conf](hound-coder-logrotate.conf) rotates `usage.log` weekly (keeping 26 compressed archives) via the system's `logrotate` cron job, and signals nginx to reopen the file afterward so logging continues uninterrupted.

## Updating the production server

```bash
# Note: run as root (or with sudo)
cd /opt/hound-coder
git pull   # nginx config, systemd units, and docker-compose.yaml are symlinked, so this updates them in place

# Pick up systemd unit file changes, if any
systemctl daemon-reload

# Reload nginx config (no downtime)
nginx -t && systemctl reload nginx

# Pick up auth-server code/dependency changes
auth-server/venv/bin/pip install -r auth-server/requirements.txt
systemctl restart hound-coder-auth.service

# Pick up docker-compose.yaml changes (only recreates containers whose config actually changed)
docker compose -f docker-compose.yaml up -d
```

# Benchmarking

To benchmark the individual servers: (takes about 45 seconds for the tab-complete one and 6 minutes for the agent one; should run twice as the first time is definitely slower)

```bash
docker exec -it vllm-inline vllm bench serve --base-url http://localhost:8001 --endpoint /v1/completions --model Qwen/Qwen2.5-Coder-7B --dataset-name random --random-input-len 800 --random-output-len 64 --max-concurrency 30 --num-prompts 300 --request-rate inf
docker exec -it vllm-agent  vllm bench serve --base-url http://localhost:8002 --endpoint /v1/chat/completions --backend openai-chat --model Intel/Qwen3-Coder-30B-A3B-Instruct-int4-AutoRound --dataset-name random --random-input-len 4000 --random-output-len 500 --max-concurrency 6 --num-prompts 60 --request-rate inf
```

Can also run both at the same time (in different terminals, reducing max-concurrency to 15/5 and num-prompts to 150/10 to simulate them at the same time).
