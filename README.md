# AI Machine Bridge

A small, self-hosted bridge that lets an AI client operate **your own computer** through authenticated tools. It exposes the same capabilities over two interfaces:

- **MCP (Streamable HTTP):** `/mcp`
- **REST/OpenAPI:** `/tools/call` and `/openapi.json`, suitable for Custom GPT Actions and generic HTTP clients

Included tools: `files` (read/write/edit/delete/list/search), `playwright` (persistent Chromium navigation and interaction), `server_admin` (shell/service/root-level machine administration when the service itself runs as root/Administrator), and `tools` (capability discovery).

## Security warning

This server can intentionally provide full control of the host. Treat its bearer token like a root password. Do **not** expose port 8765 directly to the public internet. Put it behind HTTPS and an authenticated/private tunnel. Rotate the token if it is ever disclosed.

## Install

Python 3.11+ is required. For full machine control, run the installer from an elevated shell:

```bash
sudo python3 scripts/install.py       # Linux/macOS
```

On Windows, open PowerShell **as Administrator** and run `python scripts\install.py`.

The installer creates an isolated virtualenv, installs Chromium, installs a persistent boot service (systemd / launchd / Scheduled Task), generates a random bearer token, starts the bridge, and prints the local REST/MCP endpoints and token.

For an AI agent performing installation, follow **INSTALL_FOR_LLM.md** exactly.

## Local test

```bash
TOKEN='the token printed by the installer'
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/health
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/tools
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  http://127.0.0.1:8765/tools/call \
  -d '{"tool":"server_admin","arguments":{"action":"exec","command":"whoami"}}'
```

## Wire a Custom GPT

Custom GPT Actions need a publicly reachable **HTTPS** URL. Use your preferred secure tunnel/reverse proxy to map `https://YOUR_HOST` to `http://127.0.0.1:8765` without changing paths. In the GPT editor, add an Action, import `https://YOUR_HOST/openapi.json`, choose **API key / Bearer** authentication, and enter the generated token. The action endpoint is `POST /tools/call`.

## Wire an MCP client

Configure a remote/streamable-HTTP MCP server at `https://YOUR_HOST/mcp` and send `Authorization: Bearer YOUR_TOKEN` on every request. Exact UI wording differs by client; the endpoint and header are the portable pieces.

## No bundled prompt

The server intentionally ships with no user instructions, assistant prompt, memory, policies, personalities, or task-specific system text. Tool descriptions only document callable capabilities.
