from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import platform
import re
import shlex
import shutil
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field
from jsonschema import validate as jsonschema_validate
from playwright.async_api import async_playwright
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

NAME = "AI Machine Bridge"
VERSION = "0.2.0"
TOKEN = os.environ.get("AMB_TOKEN", "")
WORKSPACE = Path(os.environ.get("AMB_WORKSPACE", str(Path.home()))).expanduser().resolve()
BROWSER_DIR = Path(os.environ.get("AMB_BROWSER_DIR", str(Path.home() / ".ai-machine-bridge" / "browser"))).expanduser().resolve()
TOOLS_DIR = Path(os.environ.get("AMB_TOOLS_DIR", str(Path.home() / ".ai-machine-bridge" / "tools"))).expanduser().resolve()
MEMORY_DIR = Path(os.environ.get("AMB_MEMORY_DIR", str(Path.home() / ".ai-machine-bridge" / "memory"))).expanduser().resolve()
PRIVACY_FILE = Path(os.environ.get("AMB_PRIVACY_FILE", str(Path(__file__).with_name("PRIVACY.md")))).resolve()
MAX_OUTPUT = int(os.environ.get("AMB_MAX_OUTPUT", "20000"))

if not TOKEN:
    raise RuntimeError("AMB_TOKEN is required")

bearer = HTTPBearer(auto_error=False, scheme_name="BridgeBearer")


def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer" or credentials.credentials != TOKEN:
        raise HTTPException(status_code=401, detail="invalid bearer token")


def _clip(text: str, n: int = MAX_OUTPUT) -> str:
    return text if len(text) <= n else text[:n] + f"\n...[truncated {len(text) - n} chars]"


def _path(raw: str) -> Path:
    p = Path(raw).expanduser()
    return (WORKSPACE / p).resolve() if not p.is_absolute() else p.resolve()


FileAction = Literal["read", "write", "edit", "delete", "list", "search", "grep"]
AdminAction = Literal["exec", "file_read", "file_write", "service"]
ServiceOperation = Literal["status", "start", "stop", "restart", "enable", "disable"]
BrowserAction = Literal["navigate", "snapshot", "click", "type", "eval", "screenshot"]


class FilesRequest(BaseModel):
    action: FileAction = Field(description="Filesystem operation")
    path: str = Field(default=".", description="Absolute path, or path relative to the configured workspace")
    content: str | None = Field(default=None, description="Content for write")
    query: str | None = Field(default=None, description="Search/grep text or regular expression")
    old_text: str | None = Field(default=None, description="Exact text to replace for edit")
    new_text: str | None = Field(default=None, description="Replacement text for edit")
    limit: int = Field(default=200, ge=1, le=5000, description="Maximum list/search results")


class ServerAdminRequest(BaseModel):
    action: AdminAction = Field(default="exec", description="Administrative operation")
    command: str | None = Field(default=None, description="Shell command for exec")
    path: str | None = Field(default=None, description="Path for file_read/file_write")
    content: str | None = Field(default=None, description="Content for file_write")
    service: str | None = Field(default=None, description="Service name")
    operation: ServiceOperation | None = Field(default=None, description="Service operation; defaults to status")
    timeout: int = Field(default=30, ge=1, le=300, description="Command timeout in seconds")


class PlaywrightRequest(BaseModel):
    action: BrowserAction = Field(description="Browser operation")
    url: str | None = Field(default=None, description="URL for navigate")
    selector: str | None = Field(default=None, description="Selector for click/type")
    text: str | None = Field(default=None, description="Text for type, or output path for screenshot")
    script: str | None = Field(default=None, description="JavaScript expression for eval")


class CustomToolCall(BaseModel):
    name: str = Field(description="Custom tool name returned by GET /custom-tools")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments matching the tool's declared input_schema")


class GenericToolRequest(BaseModel):
    tool: str = Field(description="Built-in tool name or custom tool name")
    arguments: dict[str, Any] = Field(default_factory=dict)


def files_impl(action: FileAction, path: str = ".", content: str | None = None, query: str | None = None,
               old_text: str | None = None, new_text: str | None = None, limit: int = 200) -> dict[str, Any]:
    p = _path(path)
    if action == "read":
        return {"path": str(p), "content": _clip(p.read_text(errors="replace"))}
    if action == "write":
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content or "")
        return {"status": "success", "path": str(p), "bytes": p.stat().st_size}
    if action == "edit":
        s = p.read_text()
        if old_text is None or old_text not in s: raise ValueError("old_text not found")
        p.write_text(s.replace(old_text, new_text or "", 1))
        return {"status": "success", "path": str(p)}
    if action == "delete":
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        return {"status": "success", "path": str(p)}
    if action == "list":
        rows = []
        for x in sorted(p.iterdir(), key=lambda z: (not z.is_dir(), z.name.lower()))[:limit]:
            rows.append({"name": x.name, "path": str(x), "type": "dir" if x.is_dir() else "file", "bytes": None if x.is_dir() else x.stat().st_size})
        return {"path": str(p), "items": rows}
    if action in {"search", "grep"}:
        if not query: raise ValueError("query is required")
        cmd = ["rg", "--line-number", "--hidden", "--glob", "!.git/*", "--max-count", str(limit), query, str(p)] if shutil.which("rg") else ["grep", "-RIn", query, str(p)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return {"status": "success" if r.returncode in (0, 1) else "error", "output": _clip(r.stdout or r.stderr)}
    raise ValueError(f"unknown files action: {action}")


def admin_impl(action: AdminAction = "exec", command: str | None = None, path: str | None = None,
               content: str | None = None, service: str | None = None, operation: ServiceOperation | None = None,
               timeout: int = 30) -> dict[str, Any]:
    if action == "exec":
        if not command: raise ValueError("command is required")
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"status": "success" if r.returncode == 0 else "error", "stdout": _clip(r.stdout), "stderr": _clip(r.stderr), "returncode": r.returncode}
    if action == "file_read": return files_impl("read", path or "")
    if action == "file_write": return files_impl("write", path or "", content=content)
    if action == "service":
        if not service: raise ValueError("service is required")
        op = operation or "status"
        system = platform.system()
        if system == "Windows":
            verbs = {"status": f"Get-Service -Name '{service}' | Format-List *", "start": f"Start-Service -Name '{service}'", "stop": f"Stop-Service -Name '{service}'", "restart": f"Restart-Service -Name '{service}'", "enable": f"Set-Service -Name '{service}' -StartupType Automatic", "disable": f"Set-Service -Name '{service}' -StartupType Disabled"}
            cmd = f'powershell -NoProfile -Command "{verbs[op]}"'
        elif system == "Darwin":
            if op == "status": cmd = f"launchctl print system/{shlex.quote(service)}"
            elif op in {"start", "restart"}: cmd = f"launchctl kickstart -k system/{shlex.quote(service)}"
            elif op == "stop": cmd = f"launchctl kill SIGTERM system/{shlex.quote(service)}"
            else: raise ValueError("enable/disable are managed by plist presence on macOS")
        else:
            cmd = f"systemctl {shlex.quote(op)} {shlex.quote(service)}"
        return admin_impl("exec", command=cmd, timeout=timeout)
    raise ValueError(f"unknown server_admin action: {action}")


class Browser:
    def __init__(self): self.pw = self.ctx = self.page = None; self.lock = asyncio.Lock()
    async def ensure(self):
        if self.page and not self.page.is_closed(): return
        self.pw = await async_playwright().start(); BROWSER_DIR.mkdir(parents=True, exist_ok=True)
        self.ctx = await self.pw.chromium.launch_persistent_context(str(BROWSER_DIR), headless=True)
        self.page = self.ctx.pages[0] if self.ctx.pages else await self.ctx.new_page()
    async def run(self, action: BrowserAction, url: str | None = None, selector: str | None = None, text: str | None = None, script: str | None = None):
        async with self.lock:
            await self.ensure(); p = self.page
            if action == "navigate": await p.goto(url or "about:blank", wait_until="domcontentloaded"); return {"url": p.url, "title": await p.title()}
            if action == "snapshot": return {"url": p.url, "title": await p.title(), "text": _clip(await p.locator("body").inner_text())}
            if action == "click": await p.locator(selector or "").click(); return {"url": p.url}
            if action == "type": await p.locator(selector or "").fill(text or ""); return {"status": "success"}
            if action == "eval": return {"result": await p.evaluate(script or "")}
            if action == "screenshot":
                out = _path(text or "screenshot.png"); out.parent.mkdir(parents=True, exist_ok=True); await p.screenshot(path=str(out), full_page=True); return {"path": str(out)}
            raise ValueError(f"unknown playwright action: {action}")

browser = Browser()


def _tool_files() -> list[Path]:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in TOOLS_DIR.glob("*.py") if not p.name.startswith("_") and p.name != "__init__.py")


def _load_custom_tool(path: Path):
    mod_name = f"amb_custom_{path.stem}_{path.stat().st_mtime_ns}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if not spec or not spec.loader: raise ValueError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    meta = getattr(module, "TOOL", None); run = getattr(module, "run", None)
    if not isinstance(meta, dict) or not callable(run): raise ValueError(f"{path.name}: requires TOOL dict and run(arguments) function")
    name = meta.get("name"); desc = meta.get("description"); schema = meta.get("input_schema")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", name): raise ValueError(f"{path.name}: invalid TOOL.name")
    if not isinstance(desc, str) or not desc.strip(): raise ValueError(f"{path.name}: TOOL.description is required")
    if not isinstance(schema, dict) or schema.get("type") != "object": raise ValueError(f"{path.name}: TOOL.input_schema must be JSON Schema object")
    return module, {"name": name, "description": desc, "input_schema": schema, "file": str(path)}


def custom_tools_impl() -> dict[str, Any]:
    tools, errors = [], []
    for p in _tool_files():
        try: _, meta = _load_custom_tool(p); tools.append(meta)
        except Exception as e: errors.append({"file": str(p), "error": str(e)})
    return {"directory": str(TOOLS_DIR), "tools": tools, "errors": errors}


async def custom_tool_call(name: str, arguments: dict[str, Any]) -> Any:
    for p in _tool_files():
        try:
            module, meta = _load_custom_tool(p)
        except Exception:
            continue
        if meta["name"] == name:
            jsonschema_validate(instance=arguments, schema=meta["input_schema"])
            run = module.run
            if inspect.iscoroutinefunction(run): return await run(arguments)
            return await asyncio.to_thread(run, arguments)
    raise ValueError(f"custom tool not found: {name}")


transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
mcp = FastMCP(NAME, instructions=None, stateless_http=True, json_response=True, streamable_http_path="/", transport_security=transport_security)

@mcp.tool(name="files")
def mcp_files(action: FileAction, path: str = ".", content: str | None = None, query: str | None = None, old_text: str | None = None, new_text: str | None = None, limit: int = 200):
    """Read, write, edit, delete, list, or search files on the host."""
    return files_impl(action, path, content, query, old_text, new_text, limit)

@mcp.tool(name="server_admin")
def mcp_admin(action: AdminAction = "exec", command: str | None = None, path: str | None = None, content: str | None = None, service: str | None = None, operation: ServiceOperation | None = None, timeout: int = 30):
    """Run shell commands and administer the host with the bridge process privileges."""
    return admin_impl(action, command, path, content, service, operation, timeout)

@mcp.tool(name="playwright")
async def mcp_playwright(action: BrowserAction, url: str | None = None, selector: str | None = None, text: str | None = None, script: str | None = None):
    """Control a persistent Chromium browser."""
    return await browser.run(action, url, selector, text, script)

@mcp.tool(name="custom_tools")
def mcp_custom_tools():
    """Discover user-created Python tools and their declared JSON input schemas."""
    return custom_tools_impl()

@mcp.tool(name="custom_tool_call")
async def mcp_custom_tool_call(name: str, arguments: dict[str, Any]):
    """Call a discovered user-created Python tool by name with arguments matching its declared schema."""
    return await custom_tool_call(name, arguments)

mcp_app = mcp.streamable_http_app()

@asynccontextmanager
async def app_lifespan(app):
    TOOLS_DIR.mkdir(parents=True, exist_ok=True); MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    async with mcp.session_manager.run(): yield

app = FastAPI(title=NAME, version=VERSION, docs_url="/docs", redoc_url=None, lifespan=app_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "Accept", "Mcp-Session-Id", "MCP-Protocol-Version", "Last-Event-ID"], expose_headers=["Mcp-Session-Id"])

@app.get("/privacy", response_class=PlainTextResponse, include_in_schema=False)
def privacy():
    return PRIVACY_FILE.read_text(errors="replace") if PRIVACY_FILE.exists() else "Privacy policy file is not installed."

@app.get("/health", operation_id="bridgeHealth", dependencies=[Depends(require_auth)])
def health(): return {"ok": True, "name": NAME, "version": VERSION, "os": platform.system(), "workspace": str(WORKSPACE), "tools_dir": str(TOOLS_DIR), "memory_dir": str(MEMORY_DIR)}

@app.get("/files", operation_id="describeFilesystemTool", dependencies=[Depends(require_auth)])
def describe_files(): return {"request_schema": FilesRequest.model_json_schema()}

@app.post("/files", operation_id="useFilesystem", dependencies=[Depends(require_auth)])
async def files(req: FilesRequest):
    try: return await asyncio.to_thread(files_impl, **req.model_dump())
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/server-admin", operation_id="useServerAdmin", dependencies=[Depends(require_auth)])
async def server_admin(req: ServerAdminRequest):
    try: return await asyncio.to_thread(admin_impl, **req.model_dump())
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/playwright", operation_id="usePlaywright", dependencies=[Depends(require_auth)])
async def playwright(req: PlaywrightRequest):
    try: return await browser.run(**req.model_dump())
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/custom-tools", operation_id="discoverCustomTools", dependencies=[Depends(require_auth)])
def custom_tools(): return custom_tools_impl()

@app.post("/custom-tools/call", operation_id="callCustomTool", dependencies=[Depends(require_auth)])
async def call_custom_tool(req: CustomToolCall):
    try: return await custom_tool_call(req.name, req.arguments)
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/tools", operation_id="discoverAllTools", dependencies=[Depends(require_auth)])
def tools(): return {"builtins": ["files", "playwright", "server_admin", "custom_tools", "custom_tool_call"], **custom_tools_impl()}

@app.post("/tools/call", operation_id="callToolGeneric", dependencies=[Depends(require_auth)], include_in_schema=False)
async def call(req: GenericToolRequest):
    try:
        if req.tool == "files": return await asyncio.to_thread(files_impl, **req.arguments)
        if req.tool == "server_admin": return await asyncio.to_thread(admin_impl, **req.arguments)
        if req.tool == "playwright": return await browser.run(**req.arguments)
        return await custom_tool_call(req.tool, req.arguments)
    except Exception as e: raise HTTPException(400, str(e))

class BearerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.headers.get("authorization") != f"Bearer {TOKEN}": return JSONResponse({"detail": "invalid bearer token"}, status_code=401)
        return await call_next(request)

mcp_app.add_middleware(BearerMiddleware)
app.mount("/mcp", mcp_app)
