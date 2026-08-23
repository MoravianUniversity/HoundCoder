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
cp hound-coder-vllm.service /etc/systemd/system/hound-coder-vllm.service
cp hound-coder-auth.service /etc/systemd/system/hound-coder-auth.service

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
AUTH_DATA_DIR=/opt/hound-coder/auth auth-server/venv/bin/python auth-server/bootstrap.py --email you@example.com
systemctl enable --now hound-coder-auth.service

# Copy nginx config
cp hound-coder.conf /etc/nginx/sites-available/hound-coder.conf
ln -s /etc/nginx/sites-available/hound-coder.conf /etc/nginx/sites-enabled/hound-coder.conf
rm -f /etc/nginx/sites-enabled/default
systemctl enable nginx
systemctl restart nginx
```

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

Open `http://localhost/admin/` in a browser and paste an admin JWT (e.g. the one printed by `bootstrap.py`) to add/remove users, toggle admin status, and issue or revoke tokens. The same operations are available directly via the `/admin/api/users` REST API using that bearer token.

# Benchmarking

To benchmark the individual servers: (takes about 45 seconds for the tab-complete one and 6 minutes for the agent one; should run twice as the first time is definitely slower)

```bash
docker exec -it vllm-inline vllm bench serve --base-url http://localhost:8001 --endpoint /v1/completions --model Qwen/Qwen2.5-Coder-7B --dataset-name random --random-input-len 800 --random-output-len 64 --max-concurrency 30 --num-prompts 300 --request-rate inf
docker exec -it vllm-agent  vllm bench serve --base-url http://localhost:8002 --endpoint /v1/chat/completions --backend openai-chat --model Intel/Qwen3-Coder-30B-A3B-Instruct-int4-AutoRound --dataset-name random --random-input-len 4000 --random-output-len 500 --max-concurrency 6 --num-prompts 60 --request-rate inf
```

Can also run both at the same time (in different terminals, reducing max-concurrency to 15/5 and num-prompts to 150/10 to simulate them at the same time).
