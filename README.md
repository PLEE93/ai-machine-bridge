# AI Machine Bridge

A compact self-hosted bridge that lets an AI client operate **your own computer** through authenticated tools. It is vendor-neutral and exposes the same machine capabilities through:

- **MCP (Streamable HTTP):** `/mcp/`
- **Typed REST/OpenAPI:** `/files`, `/server-admin`, `/playwright`, `/custom-tools/call`
- **OpenAPI schema:** `/openapi.json`

Built-in capabilities are filesystem access, persistent Playwright/Chromium browser control, host administration, and a hot-loadable custom Python tool system. The server carries **no assistant persona, memory prompt, user instructions, or hidden task instructions**. Tool descriptions document callable capabilities only.

## Security model

This software is intentionally capable of root/SYSTEM-level machine control. The installer runs the persistent service elevated, binds it to **127.0.0.1 only**, generates a strong bearer token, stores that token in a protected local file, and expects remote/cloud access to arrive through a user-controlled authenticated HTTPS tunnel or reverse proxy.

Treat the bearer token like a root password. Never expose port 8765 directly to the public Internet. Only install custom Python tools you trust: custom tools execute with the same OS privileges as the bridge.

## Install

Python 3.11+ is required. Download/clone this repository, then run from an elevated shell:

```bash
sudo python3 scripts/install.py
```

On Windows, open PowerShell or Command Prompt **as Administrator** and run:

```text
python scripts\install.py
```

The installer is idempotent: updates preserve the existing bearer token, memory, and user-created custom tools, replace application files, update dependencies/browser binaries, recreate/reload the persistent service, and restart it. Use `--rotate-token` only when you intentionally want a new credential.

The installer uses the invoking human user's home directory as the default relative-path workspace even when installation is performed with sudo. Absolute filesystem paths remain available.

For installation by Codex, Claude Code, or another coding agent, give it this repository and say: **"Install this according to INSTALL_FOR_LLM.md, run the full self-test, and only then give me the endpoints and wiring instructions."**

## Custom tools that an AI can build for itself

`TOOLS.md` contains the complete custom-tool contract. It is a normal file, **not injected into the model**. A non-technical user can tell an AI with bridge access:

> Read the installed TOOLS.md and build yourself a tool that does X. Test it and make sure you can call it before telling me it is ready.

The AI writes one `.py` file into the persistent `data/tools/` directory. The bridge rescans that directory on discovery and every call, validates arguments against the tool's declared JSON Schema, and exposes the new tool immediately through REST and MCP without restarting the service.

## Plain-files memory

The installer creates a persistent `data/memory/` hierarchy with `README.md`, `INDEX.md`, subject folders, nested subfolders, and files. It is intentionally just user-controlled files: nothing is automatically injected into AI context. See `memory/README.md` for the organization/read-write convention.

## Local verification

The repository includes a real end-to-end test. On an installed machine:

```bash
sudo /opt/ai-machine-bridge/.venv/bin/python /opt/ai-machine-bridge/scripts/self_test.py \
  --token-file /opt/ai-machine-bridge/data/token
```

The test verifies authenticated health, root execution, filesystem round-trip, real Chromium navigation, dynamically created custom-tool discovery/schema validation/execution, MCP initialization, and MCP tool enumeration. An installer or coding agent should not report success until this passes.

## Remote access

Keep the bridge itself on `127.0.0.1:8765`. Configure your preferred HTTPS tunnel/reverse proxy to forward a public HTTPS hostname to that loopback address without removing the Authorization header. Then repeat the self-test with `--public-base https://YOUR_HOST`.

The MCP server disables its own DNS-rebinding host check specifically for this **loopback + authenticated reverse proxy + bearer token** architecture. The raw bridge remains inaccessible off-machine unless the user deliberately provides a proxy/tunnel.

## Custom GPT Actions

ChatGPT product eligibility and GPT/Actions availability can change by plan and mode. Where Custom GPT Actions are available for your existing/eligible GPT, add an Action from:

```text
https://YOUR_HOST/openapi.json
```

Choose API-key/Bearer authentication and enter the bridge token. The schema exposes typed operations and explicit action enums/fields so the GPT can understand filesystem, browser, and administration calls without a behavioral prompt. `/privacy` serves a generic privacy-policy document for the unmodified self-hosted bridge; if you publish your own GPT/service you remain responsible for any deployment-specific disclosures.

MCP is the preferred vendor-neutral integration for clients that support remote Streamable HTTP MCP. Configure:

```text
URL: https://YOUR_HOST/mcp/
Authorization: Bearer YOUR_TOKEN
```

## Public unauthenticated endpoints

Only the documentation needed for client setup is intentionally public: `/openapi.json`, `/docs`, and `/privacy`. Machine-control endpoints, health metadata, tool discovery, and MCP all require the bearer token.

## Updating

Pull/download the newer repository and run the installer again as root/Administrator. It preserves the token, memory and custom-tool data by default, refreshes application/dependencies/browser installation, and restarts the persistent service. Run `scripts/self_test.py` after every update.
