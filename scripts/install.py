#!/usr/bin/env python3
from __future__ import annotations
import json, os, platform, secrets, shutil, subprocess, sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]; system=platform.system(); token=secrets.token_urlsafe(40)
if os.geteuid()!=0 if hasattr(os,'geteuid') else False:
    print('ERROR: run installer as Administrator/root for full machine control.'); sys.exit(2)
base=Path('/opt/ai-machine-bridge') if system in ('Linux','Darwin') else Path(os.environ.get('ProgramData','C:/ProgramData'))/'ai-machine-bridge'
base.mkdir(parents=True,exist_ok=True)
for name in ('bridge.py','requirements.txt','LICENSE','README.md','INSTALL_FOR_LLM.md'):
    shutil.copy2(root/name,base/name)
venv=base/'.venv'; subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
py=venv/('Scripts/python.exe' if system=='Windows' else 'bin/python')
subprocess.run([str(py),'-m','pip','install','-U','pip'],check=True)
subprocess.run([str(py),'-m','pip','install','-r',str(base/'requirements.txt')],check=True)
subprocess.run([str(py),'-m','playwright','install','chromium'],check=True)
env=base/'.env'; env.write_text(f'AMB_TOKEN={token}\nAMB_WORKSPACE={Path.home()}\nAMB_BROWSER_DIR={base/"browser"}\nPORT=8765\n')
if system=='Linux':
    unit=Path('/etc/systemd/system/ai-machine-bridge.service'); unit.write_text(f'''[Unit]\nDescription=AI Machine Bridge\nAfter=network-online.target\n[Service]\nType=simple\nWorkingDirectory={base}\nEnvironmentFile={env}\nExecStart={py} -m uvicorn bridge:app --host 0.0.0.0 --port 8765\nRestart=always\nRestartSec=3\n[Install]\nWantedBy=multi-user.target\n''')
    subprocess.run(['systemctl','daemon-reload'],check=True); subprocess.run(['systemctl','enable','--now','ai-machine-bridge'],check=True)
elif system=='Darwin':
    plist=Path('/Library/LaunchDaemons/org.ai-machine-bridge.plist'); plist.write_text(f'''<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>Label</key><string>org.ai-machine-bridge</string><key>ProgramArguments</key><array><string>{py}</string><string>-m</string><string>uvicorn</string><string>bridge:app</string><string>--host</string><string>0.0.0.0</string><string>--port</string><string>8765</string></array><key>WorkingDirectory</key><string>{base}</string><key>EnvironmentVariables</key><dict><key>AMB_TOKEN</key><string>{token}</string><key>AMB_WORKSPACE</key><string>{Path.home()}</string><key>AMB_BROWSER_DIR</key><string>{base/'browser'}</string></dict><key>RunAtLoad</key><true/><key>KeepAlive</key><true/></dict></plist>''')
    subprocess.run(['launchctl','bootstrap','system',str(plist)],check=True)
else:
    wrapper=base/'run.cmd'
    wrapper.write_text(f'@echo off\nset AMB_TOKEN={token}\nset AMB_WORKSPACE={Path.home()}\nset AMB_BROWSER_DIR={base/"browser"}\n"{py}" -m uvicorn bridge:app --host 0.0.0.0 --port 8765\n')
    cmd=str(wrapper)
    subprocess.run(['schtasks','/Create','/TN','AI Machine Bridge','/SC','ONSTART','/RU','SYSTEM','/TR',cmd,'/F'],check=True)
    subprocess.run(['schtasks','/Run','/TN','AI Machine Bridge'],check=True)
print(json.dumps({'installed':str(base),'local_rest':'http://127.0.0.1:8765','local_mcp':'http://127.0.0.1:8765/mcp','token':token},indent=2))
