#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = platform.system()


def run(cmd, **kwargs):
    print('+', ' '.join(map(str, cmd)))
    return subprocess.run(list(map(str, cmd)), check=True, **kwargs)


def require_elevated():
    if SYSTEM == 'Windows':
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise SystemExit('Run this installer from PowerShell or Command Prompt as Administrator.')
    elif os.geteuid() != 0:
        raise SystemExit('Run this installer with sudo/root privileges for persistent full-machine access.')


def human_home() -> Path:
    if SYSTEM == 'Windows':
        return Path(os.environ.get('USERPROFILE', str(Path.home()))).resolve()
    sudo_user = os.environ.get('SUDO_USER')
    if sudo_user and sudo_user != 'root':
        try:
            import pwd
            return Path(pwd.getpwnam(sudo_user).pw_dir).resolve()
        except Exception: pass
    return Path.home().resolve()


def secure_file(path: Path):
    if SYSTEM == 'Windows':
        run(['icacls', path, '/inheritance:r'])
        run(['icacls', path, '/grant:r', 'SYSTEM:F', 'Administrators:F'])
    else:
        path.chmod(0o600)


def copy_seed(src: Path, dst: Path):
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir(): copy_seed(child, dst / child.name)
    elif not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rotate-token', action='store_true', help='Generate a new bearer token instead of preserving the existing one.')
    ap.add_argument('--workspace', help='Default relative-path workspace. Absolute paths remain available.')
    args = ap.parse_args()
    require_elevated()

    base = Path(os.environ.get('ProgramData', 'C:/ProgramData')) / 'ai-machine-bridge' if SYSTEM == 'Windows' else Path('/opt/ai-machine-bridge')
    data = base / 'data'; tools = data / 'tools'; memory = data / 'memory'; browser = data / 'browser'; pw_browsers = base / 'pw-browsers'
    secret_file = data / 'token'
    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else human_home()

    base.mkdir(parents=True, exist_ok=True); data.mkdir(parents=True, exist_ok=True)
    for name in ('bridge.py', 'requirements.txt', 'LICENSE', 'README.md', 'INSTALL_FOR_LLM.md', 'TOOLS.md', 'PRIVACY.md'):
        shutil.copy2(ROOT / name, base / name)
    (base / 'scripts').mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'scripts' / 'self_test.py', base / 'scripts' / 'self_test.py')
    copy_seed(ROOT / 'tools', tools)
    copy_seed(ROOT / 'memory', memory)

    existing = secret_file.read_text().strip() if secret_file.exists() else ''
    token = secrets.token_urlsafe(48) if args.rotate_token or not existing else existing
    secret_file.write_text(token + '\n'); secure_file(secret_file)

    venv = base / '.venv'
    if not venv.exists(): run([sys.executable, '-m', 'venv', venv])
    py = venv / ('Scripts/python.exe' if SYSTEM == 'Windows' else 'bin/python')
    run([py, '-m', 'pip', 'install', '--upgrade', 'pip'])
    run([py, '-m', 'pip', 'install', '-r', base / 'requirements.txt'])
    env = os.environ.copy(); env['PLAYWRIGHT_BROWSERS_PATH'] = str(pw_browsers)
    if SYSTEM == 'Linux':
        run([py, '-m', 'playwright', 'install', '--with-deps', 'chromium'], env=env)
    else:
        run([py, '-m', 'playwright', 'install', 'chromium'], env=env)

    if SYSTEM == 'Linux':
        runner = base / 'run.sh'
        runner.write_text(f'''#!/bin/sh\nset -eu\nexport AMB_TOKEN="$(cat {secret_file})"\nexport AMB_WORKSPACE={shlex_quote(str(workspace))}\nexport AMB_BROWSER_DIR={shlex_quote(str(browser))}\nexport AMB_TOOLS_DIR={shlex_quote(str(tools))}\nexport AMB_MEMORY_DIR={shlex_quote(str(memory))}\nexport AMB_PRIVACY_FILE={shlex_quote(str(base / 'PRIVACY.md'))}\nexport PLAYWRIGHT_BROWSERS_PATH={shlex_quote(str(pw_browsers))}\ncd {shlex_quote(str(base))}\nexec {shlex_quote(str(py))} -m uvicorn bridge:app --host 127.0.0.1 --port 8765\n''')
        runner.chmod(0o700)
        unit = Path('/etc/systemd/system/ai-machine-bridge.service')
        unit.write_text(f'''[Unit]\nDescription=AI Machine Bridge\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nExecStart={runner}\nRestart=always\nRestartSec=3\nUser=root\n\n[Install]\nWantedBy=multi-user.target\n''')
        run(['systemctl', 'daemon-reload']); run(['systemctl', 'enable', 'ai-machine-bridge']); run(['systemctl', 'restart', 'ai-machine-bridge'])
    elif SYSTEM == 'Darwin':
        runner = base / 'run.sh'
        runner.write_text(f'''#!/bin/sh\nset -eu\nexport AMB_TOKEN="$(cat {secret_file})"\nexport AMB_WORKSPACE={shlex_quote(str(workspace))}\nexport AMB_BROWSER_DIR={shlex_quote(str(browser))}\nexport AMB_TOOLS_DIR={shlex_quote(str(tools))}\nexport AMB_MEMORY_DIR={shlex_quote(str(memory))}\nexport AMB_PRIVACY_FILE={shlex_quote(str(base / 'PRIVACY.md'))}\nexport PLAYWRIGHT_BROWSERS_PATH={shlex_quote(str(pw_browsers))}\ncd {shlex_quote(str(base))}\nexec {shlex_quote(str(py))} -m uvicorn bridge:app --host 127.0.0.1 --port 8765\n''')
        runner.chmod(0o700)
        plist = Path('/Library/LaunchDaemons/org.ai-machine-bridge.plist')
        plist.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>\n<key>Label</key><string>org.ai-machine-bridge</string>\n<key>ProgramArguments</key><array><string>{runner}</string></array>\n<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>\n<key>StandardOutPath</key><string>{base}/service.log</string>\n<key>StandardErrorPath</key><string>{base}/service.err.log</string>\n</dict></plist>''')
        subprocess.run(['launchctl', 'bootout', 'system/org.ai-machine-bridge'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run(['launchctl', 'bootstrap', 'system', plist]); run(['launchctl', 'kickstart', '-k', 'system/org.ai-machine-bridge'])
    elif SYSTEM == 'Windows':
        runner = base / 'run.cmd'
        runner.write_text(f'''@echo off\r\nset /p AMB_TOKEN=<{secret_file}\r\nset "AMB_WORKSPACE={workspace}"\r\nset "AMB_BROWSER_DIR={browser}"\r\nset "AMB_TOOLS_DIR={tools}"\r\nset "AMB_MEMORY_DIR={memory}"\r\nset "AMB_PRIVACY_FILE={base / 'PRIVACY.md'}"\r\nset "PLAYWRIGHT_BROWSERS_PATH={pw_browsers}"\r\ncd /d "{base}"\r\n"{py}" -m uvicorn bridge:app --host 127.0.0.1 --port 8765\r\n''')
        secure_file(runner)
        subprocess.run(['schtasks', '/End', '/TN', 'AI Machine Bridge'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run(['schtasks', '/Create', '/TN', 'AI Machine Bridge', '/SC', 'ONSTART', '/RU', 'SYSTEM', '/RL', 'HIGHEST', '/TR', str(runner), '/F'])
        run(['schtasks', '/Run', '/TN', 'AI Machine Bridge'])
    else:
        raise SystemExit(f'Unsupported OS: {SYSTEM}')

    import time
    time.sleep(2)
    test_env = os.environ.copy(); test_env['AMB_TOKEN'] = token
    run([py, base / 'scripts' / 'self_test.py', '--base', 'http://127.0.0.1:8765'], env=test_env)

    print(json.dumps({
        'installed': str(base), 'workspace': str(workspace), 'tools_dir': str(tools), 'memory_dir': str(memory),
        'token_file': str(secret_file), 'token_preserved': bool(existing and not args.rotate_token),
        'token': token if not existing or args.rotate_token else '(preserved; read protected token file if needed)',
        'local_rest': 'http://127.0.0.1:8765', 'local_mcp': 'http://127.0.0.1:8765/mcp/'
    }, indent=2))


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


if __name__ == '__main__': main()
