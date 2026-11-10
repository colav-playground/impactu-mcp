# Deploying the ImpactU MCP server at mcp.impactu.colav.co

This guide publishes the server at **`https://mcp.impactu.colav.co/mcp`**, so that anyone can add ImpactU to Claude
as a custom connector. It takes about an hour for someone with root access to a Colav server and to the `colav.co` DNS.

```
Claude (Anthropic's cloud)                 Colav server
  ──HTTPS──►  mcp.impactu.colav.co:443  ──►  nginx (TLS, rate limit)  ──►  impactu-mcp :8000  ──►  api.dev.impactu.colav.co
```

Claude connects **from Anthropic's cloud**, not from the user's computer, so the server must be reachable from the
public internet over HTTPS with a valid certificate. The server keeps no data and no secrets: it only calls the public
ImpactU API.

## 0. What you need

- A Linux server with a public IP. The machine that serves the ImpactU API is a good choice: the MCP traffic ends there
  anyway. 1 vCPU and 512 MB RAM are enough to start.
- Ports **80** and **443** open to the internet (80 is only for the certificate challenge and the redirect).
- Root or sudo on that server.
- Access to the DNS of `colav.co`.
- Either **Docker** with the Compose plugin (recommended), or **Python 3.11+** (then use systemd, step 4b).
- **nginx** and **certbot**, or **Caddy** instead of both (step 5b).

## 1. DNS

Create a record for `mcp.impactu.colav.co` pointing to the server:

| Type | Name | Value |
| --- | --- | --- |
| `A` | `mcp.impactu` | the server's IPv4 address |
| `AAAA` (if the server has IPv6) | `mcp.impactu` | the server's IPv6 address |

or a `CNAME` to the name of the API server, if it already has one. Check it from any computer:

```bash
dig +short mcp.impactu.colav.co
```

It must print the server's IP before you request the certificate in step 5.

## 2. Get the code onto the server

The code is in the public repository [colav-playground/impactu-mcp](https://github.com/colav-playground/impactu-mcp). Clone it:

```bash
sudo mkdir -p /opt/impactu-mcp && sudo chown $USER /opt/impactu-mcp
git clone https://github.com/colav-playground/impactu-mcp.git /opt/impactu-mcp/src
cd /opt/impactu-mcp/src
```

Without a repository, copy the folder with `scp -r impactu-mcp server:/opt/impactu-mcp/src`.

## 3. Configure

```bash
cp .env.example .env
```

Edit `.env`. The two settings that matter:

- `MCP_PUBLIC_HOSTS=mcp.impactu.colav.co`: requests whose `Host` header is not this name are refused with 421.
  If you change the domain, change it here too.
- `IMPACTU_API_BASE`: the API the tools call. Keep `https://api.dev.impactu.colav.co` while the documented routes
  (help.impactu.colav.co) exist only on dev. Once production serves them, set `https://api.impactu.colav.co` and
  restart (step 8). If the MCP server runs on the same machine or network as the API, you can point it at the
  API's internal address (for example `http://127.0.0.1:5000`) to skip the public round trip.

`WORKERS=2` suits a small server; use about 2 per CPU core.

## 4a. Run it with Docker (recommended)

```bash
cd /opt/impactu-mcp/src
docker compose up -d --build
docker compose ps                       # STATUS should become "healthy" after ~30 s
curl -s http://127.0.0.1:8000/healthz   # {"status":"ok","version":"0.1.0","api_base":"https://api.dev.impactu.colav.co"}
```

The container listens only on `127.0.0.1:8000`, runs as an unprivileged user with a read-only file system, restarts
on failure and on reboot (`restart: unless-stopped`), and rotates its logs.

## 4b. Or run it with systemd (no Docker)

```bash
sudo useradd --system --home /opt/impactu-mcp --shell /usr/sbin/nologin impactu-mcp
sudo cp /opt/impactu-mcp/src/.env /opt/impactu-mcp/.env
sudo python3 -m venv /opt/impactu-mcp/venv
sudo /opt/impactu-mcp/venv/bin/pip install /opt/impactu-mcp/src
sudo chown -R impactu-mcp: /opt/impactu-mcp
sudo cp /opt/impactu-mcp/src/deploy/systemd/impactu-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now impactu-mcp
systemctl status impactu-mcp
curl -s http://127.0.0.1:8000/healthz
```

The unit forces `HOST=127.0.0.1`, so only nginx can reach it.

## 5a. HTTPS with nginx and Let's Encrypt

Install them (Debian/Ubuntu):

```bash
sudo apt install nginx certbot python3-certbot-nginx
```

**Get the certificate first**, with a plain HTTP site (the full configuration refers to certificate files that don't
exist yet):

```bash
sudo tee /etc/nginx/sites-available/mcp.impactu.colav.co >/dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name mcp.impactu.colav.co;
    location /.well-known/acme-challenge/ { root /var/www/html; }
}
EOF
sudo ln -sf /etc/nginx/sites-available/mcp.impactu.colav.co /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/html -d mcp.impactu.colav.co \
     --deploy-hook "systemctl reload nginx"
```

certbot also installs the `options-ssl-nginx.conf` and `ssl-dhparams.pem` files that the full configuration includes.
If they are missing, `sudo certbot --nginx -d mcp.impactu.colav.co` once creates them.

**Then install the full configuration**, which adds TLS, the HTTP→HTTPS redirect, a rate limit of 5 requests per second
per IP (bursts of 20), and the proxy settings MCP needs (no buffering, 300 s timeouts):

```bash
sudo cp /opt/impactu-mcp/src/deploy/nginx/mcp.impactu.colav.co.conf /etc/nginx/sites-available/mcp.impactu.colav.co
sudo nginx -t && sudo systemctl reload nginx
```

Renewal is automatic (certbot's systemd timer); the deploy hook reloads nginx after each renewal. Test it with
`sudo certbot renew --dry-run`.

If Colav's nginx already has a `server` block for other `*.impactu.colav.co` names, add this one as a separate
file; it only answers to `server_name mcp.impactu.colav.co`.

## 5b. Or HTTPS with Caddy (simpler)

Caddy obtains and renews the certificate by itself. Instead of nginx and certbot:

```bash
sudo apt install caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
mcp.impactu.colav.co {
    reverse_proxy 127.0.0.1:8000 {
        flush_interval -1
        transport http {
            read_timeout 300s
        }
    }
}
EOF
sudo systemctl reload caddy
```

Caddy has no built-in rate limit; add one at the firewall or a CDN if needed.

## 6. Check it from outside

From any computer (not the server):

```bash
curl -s https://mcp.impactu.colav.co/healthz
```

```bash
curl -s -X POST https://mcp.impactu.colav.co/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"check","version":"0"}}}'
```

The second command must answer with `"serverInfo":{"name":"ImpactU",...}`. Then run the full test suite against the
public URL, from a clone of the repository:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
IMPACTU_MCP_URL=https://mcp.impactu.colav.co/mcp .venv/bin/pytest -m live
```

All 12 tests should pass. For an interactive check, run `npx @modelcontextprotocol/inspector`, choose
"Streamable HTTP" and the URL `https://mcp.impactu.colav.co/mcp`, then list and call the tools.

## 7. Add it to Claude

Each user does this once:

1. Open [claude.ai](https://claude.ai) (or the Claude desktop app) → **Settings → Connectors**.
2. Click **Add custom connector**.
3. Name: `ImpactU`. URL: `https://mcp.impactu.colav.co/mcp`. Leave the OAuth fields empty.
4. Click **Add**. In a chat, open the tools menu and make sure ImpactU is enabled.
5. Ask, for example: *"Using ImpactU, how many articles did the Universidad de Antioquia publish in Q1 journals?"*

Notes for users:

- **Free plan:** one custom connector is allowed, and ImpactU would take that slot.
- **Team and Enterprise:** an owner adds the connector once in the organization's settings; members then enable it.
- **Claude Code:** `claude mcp add --transport http impactu https://mcp.impactu.colav.co/mcp`.

Publish these steps on help.impactu.colav.co (in Spanish and English), so users find them.

## 8. Operate it

| Task | Docker | systemd |
| --- | --- | --- |
| Logs | `docker compose logs -f --tail 100` | `journalctl -u impactu-mcp -f` |
| Restart after editing `.env` | `docker compose up -d` | `sudo systemctl restart impactu-mcp` |
| Update the code | `git pull && docker compose up -d --build` | `git pull && sudo /opt/impactu-mcp/venv/bin/pip install /opt/impactu-mcp/src && sudo systemctl restart impactu-mcp` |
| Stop | `docker compose down` | `sudo systemctl stop impactu-mcp` |

nginx logs every request in `/var/log/nginx/access.log`; requests refused by the rate limit show status 429.

Recommended:

- **Monitoring:** point an uptime checker (UptimeRobot, Uptime Kuma, the team's Prometheus) at
  `https://mcp.impactu.colav.co/healthz`. `/healthz` checks only the MCP server; run `pytest -m live` against the
  public URL after every API release to catch route changes.
- **API changes:** the tools follow the routes documented at help.impactu.colav.co. When a route or parameter changes
  there, update `src/impactu_mcp/server.py` and run the tests.
- **Scaling:** the server is stateless. Raise `WORKERS`, or run several containers behind nginx's `upstream` block.
  Each worker keeps its own 10-minute cache.
- **Load on the API:** each worker sends at most `IMPACTU_MAX_CONCURRENCY` (8) requests at once, pages are capped at
  25 records, and author lists are fetched only on demand. Lower these if the API struggles.

## 9. Security

- The server is **read-only**: every tool only reads public ImpactU data, and none sends data anywhere else.
- **No accounts and no secrets.** It doesn't use ImpactU's session or API key and doesn't expose `/submit`,
  `/admin` or `/users` routes.
- **Personal data:** names, affiliations and public ids (ORCID, Scholar, OpenAlex, Scienti) are passed on, as on
  impactu.colav.co. National ID numbers are dropped even if the API returns them (`PRIVATE_ID_SOURCES` in `compact.py`).
- **Host and Origin checks:** requests for other host names get 421, and browser requests from other web origins
  get 403.
- **Abuse:** nginx limits each IP to 5 requests per second. Anthropic's cloud sends the requests of many users from
  a few addresses, so don't set this much lower; if needed, raise `burst` instead.
- To restrict access later (for example to UdeA accounts), MCP supports OAuth 2.1; that would need an authorization
  server and is outside this first version.

## 10. Listing it in Claude's connector directory (optional)

Custom connectors work with the URL alone. To have ImpactU appear in Claude's directory, like OpenAlex, Colav can
apply to Anthropic once the server is public and stable. Check Anthropic's current requirements and submission form
in the connector documentation at <https://claude.com/docs/connectors>. Expect to provide at least a stable HTTPS
URL, documentation, a privacy policy and a support contact, and to have the tool descriptions reviewed.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `421 Misdirected Request` | The `Host` header isn't in `MCP_PUBLIC_HOSTS`. Set it to `mcp.impactu.colav.co` and check that nginx sends `proxy_set_header Host $host`. |
| `403 Forbidden` from the server | A browser request came from an origin that isn't allowed. Normal for random web pages; Claude isn't affected. |
| `502 Bad Gateway` from nginx | The server isn't running on `127.0.0.1:8000`: check `docker compose ps` or `systemctl status impactu-mcp`. |
| `504 Gateway Timeout` | The ImpactU API took too long (large indicators can take 15–30 s). Raise `proxy_read_timeout` and `IMPACTU_TIMEOUT`. |
| Claude: "couldn't connect" | Check `curl https://mcp.impactu.colav.co/healthz` from outside Colav's network; check the certificate chain (`fullchain.pem`); the URL must end in `/mcp`. |
| A tool answers "Not found in ImpactU" | The id doesn't exist in the API set in `IMPACTU_API_BASE`. Dev and production ids differ. |
| Tools fail after an ImpactU release | A route or field changed. Run `pytest -m live` to see which, and update `server.py`. |
