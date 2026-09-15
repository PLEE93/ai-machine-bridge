# Installation protocol for an LLM/operator

Your job is to install this bridge stably on the user's machine, verify it, and then give the user the exact endpoints and wiring steps. Do not invent a public URL and do not claim success until probes pass.

1. Detect OS, architecture, Python version, init/service manager, current privilege level, and whether ports/services named `ai-machine-bridge` already exist. Require Python 3.11+. For full host/root control, elevate to root/Administrator before installation.
2. Copy/clone this repository locally. Run `python scripts/install.py` from an elevated shell. Record the printed token without publishing it anywhere.
3. Verify persistence: Linux `systemctl is-enabled ai-machine-bridge && systemctl is-active ai-machine-bridge`; macOS `launchctl print system/org.ai-machine-bridge`; Windows `schtasks /Query /TN "AI Machine Bridge"`.
4. Verify REST locally using `Authorization: Bearer TOKEN`: GET `/health`, GET `/tools`, POST `/tools/call` with `server_admin` executing the OS identity command (`id`/`whoami`), and a harmless file write/read/delete in a temporary location.
5. Verify Playwright: call `playwright.navigate` to `https://example.com`, then `playwright.snapshot`, and confirm page text is returned.
6. Verify MCP by POSTing an MCP `initialize` JSON-RPC request to `/mcp` with headers `Authorization: Bearer TOKEN`, `Content-Type: application/json`, and `Accept: application/json, text/event-stream`; then call `tools/list`. Do not stop at a TCP/HTTP health check.
7. If the user needs ChatGPT/another cloud AI to reach the machine, configure a secure HTTPS tunnel or reverse proxy. Never expose the raw port directly. Prefer an existing user-controlled domain/tunnel. Keep bearer auth enabled. After configuring the tunnel, repeat `/health`, REST tool call, and MCP initialization through the public HTTPS URL.
8. Return a concise handoff containing: service status, local REST base URL, local MCP URL, public HTTPS base URL if actually configured, public MCP URL, where the token is stored on disk, and exact client wiring steps below. Never print the token again unless the user explicitly needs it for setup.

## Custom GPT wiring

In ChatGPT: edit/create the GPT → Configure → Actions → create/import an action from `https://PUBLIC_HOST/openapi.json` → Authentication → API Key → Bearer → paste the bridge token → save. Test the action with GET `/health` or POST `/tools/call`. If the editor refuses a private/local URL, the HTTPS tunnel is mandatory.

## MCP client wiring

Add a remote Streamable HTTP MCP server whose URL is `https://PUBLIC_HOST/mcp`. Configure request header `Authorization: Bearer TOKEN`. Connect, enumerate tools, then run a harmless `files.list` or `server_admin` identity command.

## Failure handling

If installation fails, inspect service logs and fix the root cause before reporting. Linux: `journalctl -u ai-machine-bridge -n 200 --no-pager`. macOS: inspect launchd state and unified logs for `org.ai-machine-bridge`. Windows: inspect Task Scheduler status and run the uvicorn command manually in an elevated PowerShell to expose the traceback. Re-run the full probes after every fix.
