import os, requests, sys
base=os.getenv('AMB_BASE','http://127.0.0.1:8765'); token=os.environ['AMB_TOKEN']; h={'Authorization':f'Bearer {token}'}
assert requests.get(base+'/health',headers=h,timeout=5).json()['ok']
r=requests.post(base+'/tools/call',headers={**h,'Content-Type':'application/json'},json={'tool':'server_admin','arguments':{'action':'exec','command':'whoami'}},timeout=10); r.raise_for_status(); assert r.json()['returncode']==0
print('REST smoke OK')
