# Hound Coder

This is a project to run a local LLM stack for coding assistance. It runs a code completion server and an agent server on a DGX Spark. Clients that speak OpenAI-compatible APIs (Zed, OpenCode, Continue, and others) can use it with a personal API token.

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
ln -s $PWD/hound-coder-server.service /etc/systemd/system/hound-coder-server.service

# Register and enable the hound-coder vLLM service to start on boot
systemctl daemon-reload
systemctl enable --now docker
systemctl enable --now hound-coder-vllm.service

# Set up the Hound Coder server (JWT auth, admin, inference proxy + metrics)
cd server
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cd ..

# Seed the first admin user; save the printed JWT, it's your admin token (needed to reach /admin/)
HOUND_DATA_DIR=$PWD/data server/venv/bin/python server/bootstrap.py --email you@example.com

# Configure Google OAuth self-service registration (optional but recommended)
cp server/.env.example server/.env
# edit server/.env with a Google OAuth client id/secret and your allowed email domain

systemctl enable --now hound-coder-server.service

# Install nginx site config (edit server_name — and TLS when ready — in the copy under sites-available)
cp hound-coder.conf.example /etc/nginx/sites-available/hound-coder.conf
# edit /etc/nginx/sites-available/hound-coder.conf
ln -s /etc/nginx/sites-available/hound-coder.conf /etc/nginx/sites-enabled/hound-coder.conf
rm -f /etc/nginx/sites-enabled/default
systemctl enable nginx
nginx -t && systemctl restart nginx
```

If you ever see the stock "Welcome to nginx!" page instead of the Hound Coder pages, `/etc/nginx/sites-enabled/default` has come back (e.g. reinstated by an `nginx` package upgrade) and is winning as the `default_server` for port 80. Re-run `rm -f /etc/nginx/sites-enabled/default && systemctl reload nginx` — the example's `listen 80 default_server;` also guards against this once the site is enabled.

# Check it is working

```bash
# Does not require root
systemctl status hound-coder-vllm.service
systemctl status hound-coder-server.service
docker compose -f /opt/hound-coder/docker-compose.yaml ps
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/tab/models  # should return 401 (unauthorized)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" http://localhost/tab/models  # should return 200, $TOKEN from bootstrap.py or the /admin/ UI
```

## Managing allowed users

Visiting the server's root URL shows a welcome page from the Hound Coder server (templated from [server/templates/index.html](server/templates/index.html)) explaining what the service is and how to get access — no auth required. Set `SERVICE_NAME` and `ALLOWED_EMAIL_DOMAIN` in `server/.env` to customize the title and the spelled-out signup domain.

### Self-service registration (Google OAuth)

Users on the approved email domain can get a token from the homepage by signing in with Google, instead of waiting for
an admin. Set this up via [server/.env.example](server/.env.example):

1. Create an OAuth 2.0 client in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials), with
   authorized redirect URI `https://<your-host>/register/google/callback`.
2. Copy `server/.env.example` to `server/.env` and fill in `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and
   `ALLOWED_EMAIL_DOMAIN` (only Google accounts on this domain may register). `.env` is not tracked in git.
3. Restart `hound-coder-server.service` to pick up the new settings.

On sign-in, the server checks Google's `email_verified` claim and the account's domain, rejects blocked emails, and
then creates the user (non-admin) if needed. It reuses the user's most recently issued non-revoked token if one
exists, or issues a new one otherwise. The success page shows a (masked) copyable token and collapsible setup
sections defined as markdown under [server/setup-sections/](server/setup-sections/). Those files support
placeholders such as `<SERVER_BASE_URL>`, `<YOUR_API_KEY>`, and `<SERVICE_NAME>`; fenced code blocks marked
`download=<filename>` become downloadable configs (e.g. Continue). `<SERVER_BASE_URL>` comes from the
request's Host (and `X-Forwarded-Proto` when TLS terminates at nginx). When you enable HTTPS at nginx, also
set `COOKIE_SECURE=1` in `server/.env` so the OAuth session cookie is marked Secure.

Admins can block specific email addresses (whether or not they've registered yet) from the `/admin/` UI's
blocklist section; blocking revokes all of that email's existing tokens and prevents future self-registration or
token issuance for it.

### Admin UI

Open `http://localhost/admin/` in a browser and paste an admin JWT (e.g. the one printed by `bootstrap.py`) to add/remove users, toggle admin status, and issue or revoke tokens. The same operations are available directly via the `/admin/api/users` REST API using that bearer token.

## Usage metrics and audit

nginx forwards `/tab/` and `/chat/` to the Hound Coder server, which validates the JWT, proxies to the local vLLM OpenAI servers, and records each request.

**Durable audit / event store** (`$HOUND_DATA_DIR/usage.db`, separate from the auth DB): email, token `iat`, endpoint (`tab`|`chat`), method/path, status, request body, prompt/completion tokens, end-to-end latency, and time-to-first-byte. Rows older than `USAGE_RETENTION_DAYS` (default 182) are pruned on server startup.

**Prometheus metrics** (scrape `http://127.0.0.1:8003/metrics` on the host): `houndcoder_requests_total`, `houndcoder_prompt_tokens_total`, `houndcoder_completion_tokens_total`, `houndcoder_request_duration_seconds`, and `houndcoder_ttft_seconds` — ready for a later Grafana setup (system aggregates, per-user filter by `email`, admin view of all users).

**HTTP query API** (bearer JWT required; non-admins always see only their own data):

- `GET /usage/summary` — per-email aggregates (`request_count`, token totals, average latency/TTFT).
- `GET /usage/events` — recent request rows (newest first), including tokens and latency; `request_body` is omitted unless requested.

Shared query params:

| Param | Summary | Events | Notes |
|-------|---------|--------|-------|
| `email` | yes | yes | Admin only: filter to one user. Omit for all users (admin) or self (non-admin). |
| `endpoint` | yes | yes | `tab` or `chat`. |
| `since` / `until` | yes | yes | Unix timestamps (inclusive). |
| `group_by_endpoint` | yes | — | If `true`, break totals out by `tab`/`chat` (default `false`). |
| `limit` | — | yes | Page size, 1–1000 (default `100`). |
| `offset` | — | yes | Skip N rows (default `0`). |
| `include_body` | — | yes | If `true`, include prompt/message bodies (default `false`). |

```bash
curl -s -H "Authorization: Bearer $TOKEN" 'http://localhost/usage/summary?group_by_endpoint=true' | jq
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://localhost/usage/events?endpoint=chat&limit=20&include_body=true' | jq
# Admin: one user
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  'http://localhost/usage/summary?email=student@example.edu' | jq
```

## Updating the production server

```bash
# Note: run as root (or with sudo)
cd /opt/hound-coder
git pull   # systemd units are symlinked; nginx site under /etc/nginx/sites-available is a copy — merge from hound-coder.conf.example if it changed

# If upgrading from the old auth-server / local.conf layout:
#   systemctl disable --now hound-coder-auth.service
#   rm -f /etc/systemd/system/hound-coder-auth.service
#   ln -sf $PWD/hound-coder-server.service /etc/systemd/system/hound-coder-server.service
#   mv /opt/hound-coder/auth /opt/hound-coder/data   # if the old data dir still exists
#   # move venv/.env if you kept them under auth-server/: mv auth-server/venv server/ && mv auth-server/.env server/
#   cp hound-coder.conf.example /etc/nginx/sites-available/hound-coder.conf  # then re-apply server_name/TLS
#   rm -f /opt/hound-coder/local.conf

# Pick up systemd unit file changes, if any
systemctl daemon-reload

# Reload nginx config (no downtime)
nginx -t && systemctl reload nginx

# Pick up server code/dependency changes
server/venv/bin/pip install -r server/requirements.txt
systemctl enable --now hound-coder-server.service
systemctl restart hound-coder-server.service

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
