# Installation protocol for a coding LLM / machine operator

Goal: install AI Machine Bridge persistently on the user's machine, verify every important capability, optionally configure secure remote HTTPS reachability, and hand the user exact endpoints. Do not invent success, a hostname, or a public URL. Do not expose the raw bridge port publicly.

## 1. Inspect first

Detect the OS/version/architecture, Python version, service manager, current privileges, invoking human user/home, and whether an existing bridge installation/service is present. Python 3.11+ is required. Elevate to root/Administrator because full host control is an explicit feature.

Read `README.md`, `TOOLS.md`, and this file before changing the machine.

## 2. Install or update

Run the repository's `scripts/install.py` elevated. Do not hand-create a parallel service unless the installer cannot support the OS and you clearly explain why.

The installer must be treated as idempotent: an existing token is preserved unless the user explicitly requests credential rotation; existing runtime `data/tools/` and `data/memory/` content must be preserved; application files/dependencies are refreshed; the service is replaced/reloaded and restarted.

The bridge must remain bound to `127.0.0.1:8765`. Browser binaries must use the install-owned `pw-browsers` path so the service account can launch Chromium independently of the installing user's cache.

## 3. Verify persistence

After installation/update, verify the persistent service is enabled/present and running:

- Linux: `systemctl is-enabled ai-machine-bridge` and `systemctl is-active ai-machine-bridge`.
- macOS: `launchctl print system/org.ai-machine-bridge`.
- Windows: `schtasks /Query /TN "AI Machine Bridge" /V /FO LIST` and verify the task can run as SYSTEM.

Also verify the service is listening only on loopback, not `0.0.0.0` or a LAN/public interface.

## 4. Run the authoritative end-to-end test

Use the installed virtual environment to run `scripts/self_test.py` with the protected token file. Do not substitute a simple health check.

The self-test must pass all of these: authenticated health; root/admin identity; filesystem write/read/delete; actual Chromium navigation/snapshot; temporary custom `.py` tool discovery; JSON Schema rejection of bad custom-tool arguments; successful custom-tool execution; MCP `initialize`; MCP `tools/list`.

If any check fails, inspect logs, fix the cause, restart when necessary, and rerun the complete test. Do not report a partial install as finished.

## 5. Remote HTTPS, only when needed

Cloud-hosted AI clients cannot reach loopback directly. If the user needs remote access, configure a secure HTTPS tunnel/reverse proxy chosen or already controlled by the user. Forward to `http://127.0.0.1:8765`; preserve `Authorization`; do not remove bearer authentication; do not open TCP/8765 to the Internet.

After a real public HTTPS URL exists, rerun `self_test.py --public-base https://REAL_HOST` so both `/health` and MCP initialization are exercised through the proxy. Do not fabricate a hostname merely to finish setup.

## 6. Handoff to the user

Return, in plain language:

- whether the service is persistent/running;
- installed application path;
- custom tools path;
- memory path;
- protected token-file path (do not reprint the token unless the user needs it);
- local REST base `http://127.0.0.1:8765`;
- local MCP endpoint `http://127.0.0.1:8765/mcp/`;
- public HTTPS base/MCP endpoint only if actually configured and tested;
- exact client wiring steps below.

### MCP client

Use `https://REAL_HOST/mcp/` as a remote Streamable HTTP MCP server and send `Authorization: Bearer TOKEN`. Connect, enumerate tools, and perform one harmless call.

### Custom GPT Actions

Only where the user's ChatGPT account/GPT supports Actions: edit the GPT → Actions/Configure area → import `https://REAL_HOST/openapi.json` → configure API key authentication as Bearer → enter the bridge token → save → test an authenticated operation. Product UI wording/eligibility may change, so do not promise that every account can create a new GPT or use Actions.

The generic policy is at `https://REAL_HOST/privacy`. Explain that a publisher may need deployment-specific privacy disclosures.

## 7. When the user asks the AI to build itself a new tool

Read the installed `TOOLS.md` and follow it exactly. Create one top-level `.py` file in the reported `tools_dir`; never modify `bridge.py` just to add a user tool. Verify `GET /custom-tools`, verify a real `/custom-tools/call`, and if MCP is in use verify `custom_tools` + `custom_tool_call`. Do not say the tool is ready before execution succeeds.

## Troubleshooting

- Linux: `journalctl -u ai-machine-bridge -n 200 --no-pager`.
- macOS: `launchctl print system/org.ai-machine-bridge` and inspect `/opt/ai-machine-bridge/service*.log`.
- Windows: inspect Task Scheduler result/history, then execute `C:\ProgramData\ai-machine-bridge\run.cmd` manually from an elevated shell to expose the error.
- Browser launch failures: confirm `PLAYWRIGHT_BROWSERS_PATH` points at the installation-owned `pw-browsers` directory and browser/dependency installation completed.
- MCP 401: bearer header missing/wrong. MCP is intentionally authenticated.
- MCP behind a custom hostname: test through `/mcp/`; the bridge is configured for reverse-proxy hostnames while relying on loopback binding + bearer auth.
