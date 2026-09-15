#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, platform, tempfile, time
from pathlib import Path
import requests


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8765')
    ap.add_argument('--token-file')
    ap.add_argument('--public-base', default=os.environ.get('AMB_PUBLIC_BASE'))
    args=ap.parse_args()
    token=os.environ.get('AMB_TOKEN')
    if not token and args.token_file: token=Path(args.token_file).read_text().strip()
    if not token: raise SystemExit('Provide AMB_TOKEN or --token-file')
    h={'Authorization':f'Bearer {token}'}
    base=args.base.rstrip('/')

    def get(path, b=base):
        r=requests.get(b+path,headers=h,timeout=20); r.raise_for_status(); return r.json()
    def post(path, body, b=base, extra=None):
        hh={**h,'Content-Type':'application/json',**(extra or {})}; r=requests.post(b+path,headers=hh,json=body,timeout=60); r.raise_for_status(); return r

    health=get('/health'); assert health['ok']
    tools_dir=Path(health['tools_dir']); tools_dir.mkdir(parents=True,exist_ok=True)

    ident='whoami' if platform.system()=='Windows' else 'id -u'
    admin=post('/server-admin',{'action':'exec','command':ident}).json(); assert admin['returncode']==0
    if platform.system()!='Windows': assert admin['stdout'].strip()=='0', 'bridge service is not running as root'

    probe=Path(health['workspace'])/'.amb-self-test.txt'
    post('/files',{'action':'write','path':str(probe),'content':'bridge-ok'})
    assert post('/files',{'action':'read','path':str(probe)}).json()['content']=='bridge-ok'
    post('/files',{'action':'delete','path':str(probe)})

    nav=post('/playwright',{'action':'navigate','url':'data:text/html,<title>AMB Self Test</title><h1>AMB Browser OK</h1>'}).json(); assert 'AMB Self Test' in nav.get('title','')
    snap=post('/playwright',{'action':'snapshot'}).json(); assert 'AMB Browser OK' in snap.get('text','')

    temp_tool=tools_dir/'amb_self_test_echo.py'
    temp_tool.write_text('''TOOL={"name":"amb_self_test_echo","description":"Echo text for bridge self-test.","input_schema":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"],"additionalProperties":False}}\ndef run(arguments): return {"echo":arguments["text"]}\n''')
    try:
        discovered=get('/custom-tools'); assert any(t['name']=='amb_self_test_echo' for t in discovered['tools'])
        good=post('/custom-tools/call',{'name':'amb_self_test_echo','arguments':{'text':'hello'}}).json(); assert good=={'echo':'hello'}
        bad=requests.post(base+'/custom-tools/call',headers={**h,'Content-Type':'application/json'},json={'name':'amb_self_test_echo','arguments':{'wrong':1}},timeout=20); assert bad.status_code==400
    finally:
        temp_tool.unlink(missing_ok=True)

    mcp_headers={**h,'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
    init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'amb-self-test','version':'1'}}}
    r=requests.post(base+'/mcp/',headers=mcp_headers,json=init,timeout=30); r.raise_for_status(); assert r.json().get('result')
    listed=requests.post(base+'/mcp/',headers=mcp_headers,json={'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}},timeout=30); listed.raise_for_status(); names={t['name'] for t in listed.json()['result']['tools']}; assert {'files','server_admin','playwright','custom_tools','custom_tool_call'} <= names

    if args.public_base:
        pub=args.public_base.rstrip('/')
        pr=requests.get(pub+'/health',headers=h,timeout=30); pr.raise_for_status(); assert pr.json()['ok']
        pm=requests.post(pub+'/mcp/',headers=mcp_headers,json=init,timeout=30); pm.raise_for_status(); assert pm.json().get('result')

    print(json.dumps({'ok':True,'base':base,'public_base':args.public_base,'checks':['health','root_admin','filesystem','playwright','custom_tool_discovery','custom_tool_schema_validation','custom_tool_execution','mcp_initialize','mcp_tools_list']},indent=2))

if __name__=='__main__': main()
