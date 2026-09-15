from __future__ import annotations

import asyncio, json, os, platform, secrets, shlex, shutil, subprocess
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright

NAME = "AI Machine Bridge"
VERSION = "0.1.0"
TOKEN = os.environ.get("AMB_TOKEN", "")
WORKSPACE = Path(os.environ.get("AMB_WORKSPACE", str(Path.home()))).expanduser().resolve()
BROWSER_DIR = Path(os.environ.get("AMB_BROWSER_DIR", str(Path.home()/".ai-machine-bridge"/"browser"))).expanduser()
MAX_OUTPUT = int(os.environ.get("AMB_MAX_OUTPUT", "20000"))

if not TOKEN:
    raise RuntimeError("AMB_TOKEN is required. Generate a strong random token before starting the server.")


def auth(authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="invalid bearer token")


def _clip(s: str, n: int = MAX_OUTPUT) -> str:
    return s if len(s) <= n else s[:n] + f"\n...[truncated {len(s)-n} chars]"


def _path(raw: str) -> Path:
    p = Path(raw).expanduser()
    return (WORKSPACE / p).resolve() if not p.is_absolute() else p.resolve()


def files_impl(action: str, path: str = ".", content: str | None = None, query: str | None = None,
               old_text: str | None = None, new_text: str | None = None, limit: int = 200) -> dict[str, Any]:
    p = _path(path)
    if action == "read":
        return {"path": str(p), "content": _clip(p.read_text(errors="replace"))}
    if action == "write":
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content or "")
        return {"status":"success","path":str(p),"bytes":p.stat().st_size}
    if action == "edit":
        s=p.read_text();
        if old_text is None or old_text not in s: raise ValueError("old_text not found")
        p.write_text(s.replace(old_text, new_text or "", 1)); return {"status":"success","path":str(p)}
    if action == "delete":
        if p.is_dir(): shutil.rmtree(p)
        else: p.unlink()
        return {"status":"success","path":str(p)}
    if action == "list":
        rows=[]
        for x in sorted(p.iterdir(), key=lambda z:(not z.is_dir(), z.name.lower()))[:limit]:
            rows.append({"name":x.name,"path":str(x),"type":"dir" if x.is_dir() else "file","bytes":None if x.is_dir() else x.stat().st_size})
        return {"path":str(p),"items":rows}
    if action in {"search","grep"}:
        if not query: raise ValueError("query is required")
        cmd=["rg","--line-number","--hidden","--glob","!.git/*","--max-count",str(limit),query,str(p)] if shutil.which("rg") else ["grep","-RIn",query,str(p)]
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        return {"status":"success" if r.returncode in (0,1) else "error","output":_clip(r.stdout or r.stderr)}
    raise ValueError(f"unknown files action: {action}")


def admin_impl(action: str = "exec", command: str | None = None, path: str | None = None,
               content: str | None = None, service: str | None = None, operation: str | None = None,
               timeout: int = 30) -> dict[str, Any]:
    if action == "exec":
        if not command: raise ValueError("command is required")
        r=subprocess.run(command,shell=True,capture_output=True,text=True,timeout=timeout)
        return {"status":"success" if r.returncode==0 else "error","stdout":_clip(r.stdout),"stderr":_clip(r.stderr),"returncode":r.returncode}
    if action == "file_read": return files_impl("read", path or "")
    if action == "file_write": return files_impl("write", path or "", content=content)
    if action == "service":
        if not service: raise ValueError("service is required")
        op=operation or "status"
        if platform.system()=="Windows": cmd=f'powershell -NoProfile -Command "{op.title()}-Service -Name \'{service}\'"'
        elif platform.system()=="Darwin": cmd=f"launchctl {shlex.quote(op)} {shlex.quote(service)}"
        else: cmd=f"systemctl {shlex.quote(op)} {shlex.quote(service)}"
        return admin_impl("exec",command=cmd,timeout=timeout)
    raise ValueError(f"unknown server_admin action: {action}")


class Browser:
    def __init__(self): self.pw=self.ctx=self.page=None; self.lock=asyncio.Lock()
    async def ensure(self):
        if self.page and not self.page.is_closed(): return
        self.pw=await async_playwright().start(); BROWSER_DIR.mkdir(parents=True,exist_ok=True)
        self.ctx=await self.pw.chromium.launch_persistent_context(str(BROWSER_DIR),headless=True)
        self.page=self.ctx.pages[0] if self.ctx.pages else await self.ctx.new_page()
    async def run(self, action:str, url:str|None=None, selector:str|None=None, text:str|None=None, script:str|None=None):
        async with self.lock:
            await self.ensure(); p=self.page
            if action=="navigate": await p.goto(url or "about:blank",wait_until="domcontentloaded"); return {"url":p.url,"title":await p.title()}
            if action=="snapshot": return {"url":p.url,"title":await p.title(),"text":_clip(await p.locator("body").inner_text())}
            if action=="click": await p.locator(selector or "").click(); return {"url":p.url}
            if action=="type": await p.locator(selector or "").fill(text or ""); return {"status":"success"}
            if action=="eval": return {"result":await p.evaluate(script or "")}
            if action=="screenshot":
                out=_path(text or "screenshot.png"); out.parent.mkdir(parents=True,exist_ok=True); await p.screenshot(path=str(out),full_page=True); return {"path":str(out)}
            raise ValueError(f"unknown playwright action: {action}")

browser=Browser()

mcp = FastMCP(NAME, instructions=None, stateless_http=True, json_response=True, streamable_http_path="/")

@mcp.tool(name="files")
def mcp_files(action:str,path:str=".",content:str|None=None,query:str|None=None,old_text:str|None=None,new_text:str|None=None,limit:int=200):
    """Read, write, edit, delete, list, or search files on the host."""
    return files_impl(action,path,content,query,old_text,new_text,limit)

@mcp.tool(name="server_admin")
def mcp_admin(action:str="exec",command:str|None=None,path:str|None=None,content:str|None=None,service:str|None=None,operation:str|None=None,timeout:int=30):
    """Run shell commands and perform host administration with the server process privileges."""
    return admin_impl(action,command,path,content,service,operation,timeout)

@mcp.tool(name="playwright")
async def mcp_playwright(action:str,url:str|None=None,selector:str|None=None,text:str|None=None,script:str|None=None):
    """Control a persistent Chromium browser: navigate, snapshot, click, type, eval, screenshot."""
    return await browser.run(action,url,selector,text,script)

@mcp.tool(name="tools")
def mcp_tools():
    """List the bridge tools."""
    return {"tools":["files","playwright","server_admin","tools"]}


class ToolRequest(BaseModel):
    tool: Literal["files","playwright","server_admin","tools"]
    arguments: dict[str,Any]=Field(default_factory=dict)

mcp_app=mcp.streamable_http_app()

@asynccontextmanager
async def app_lifespan(app):
    async with mcp.session_manager.run():
        yield

app=FastAPI(title=NAME,version=VERSION,dependencies=[Depends(auth)],docs_url="/docs",redoc_url=None,lifespan=app_lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["GET","POST"],allow_headers=["Authorization","Content-Type"])

@app.get("/health")
def health(): return {"ok":True,"name":NAME,"version":VERSION,"os":platform.system(),"workspace":str(WORKSPACE)}

@app.get("/tools")
def tools(): return {"tools":["files","playwright","server_admin","tools"]}

@app.post("/tools/call")
async def call(req:ToolRequest):
    try:
        if req.tool=="files": return await asyncio.to_thread(files_impl,**req.arguments)
        if req.tool=="server_admin": return await asyncio.to_thread(admin_impl,**req.arguments)
        if req.tool=="playwright": return await browser.run(**req.arguments)
        return tools()
    except Exception as e: raise HTTPException(400,str(e))

# MCP authentication is enforced by middleware wrapper because mounted sub-apps do not inherit FastAPI dependencies.
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
class BearerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.headers.get("authorization") != f"Bearer {TOKEN}": return JSONResponse({"detail":"invalid bearer token"},status_code=401)
        return await call_next(request)

mcp_app.add_middleware(BearerMiddleware)
app.mount("/mcp",mcp_app)
