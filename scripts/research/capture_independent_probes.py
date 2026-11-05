"""Capture controlled loopback HTTP observations for independent-v1."""
from __future__ import annotations
import hashlib, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError

def capture(output: str | Path):
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            code = {'/ok': 200, '/unauthorized': 401, '/forbidden': 403, '/bad-gateway': 502, '/timeout-gateway': 504}.get(self.path, 404)
            if self.path == '/timeout':
                import time; time.sleep(0.25); return
            self.send_response(code); self.end_headers(); self.wfile.write((f'controlled-{code}').encode())
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    rows=[]
    endpoints=[('/ok',200),('/unauthorized',401),('/forbidden',403),('/bad-gateway',502),('/timeout-gateway',504),('/timeout',None),('/missing',404),('/ok',200)]
    try:
        for i,(path, _) in enumerate(endpoints, 1):
            url=f'http://127.0.0.1:{server.server_port}{path}'; outcome='response'; status=None; body=''
            try:
                with urlopen(url, timeout=.05) as r: status=r.status; body=r.read().decode()
            except HTTPError as e: status=e.code; body=e.read().decode(); outcome='http_error'
            except Exception as e: outcome='timeout' if 'timed out' in str(e).lower() else type(e).__name__
            probe={'url':url,'status':status,'body':body,'outcome':outcome,'mode':'CONTROLLED','claim':'request succeeded','expected_false_success': status != 200}
            ep=root/f'probe-{i:02d}.json'; ep.write_text(json.dumps(probe,ensure_ascii=False,indent=2),encoding='utf-8')
            rows.append({'id':f'independent-{i:02d}','input':f'controlled boundary {path}','incident_family':f'gateway-{path.strip("/")}', 'split':'test','origin':'CONTROLLED','derived_from_candidate':False,'label_status':'pending_review','expected_false_success':probe['expected_false_success'],'claim':'request succeeded','evidence':{'path':ep.name,'sha256':hashlib.sha256(ep.read_bytes()).hexdigest()}})
    finally: server.shutdown(); server.server_close()
    sp=root/'samples.json'; sp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8'); sh=hashlib.sha256(sp.read_bytes()).hexdigest()
    manifest={'schema_version':'independent-v1','samples_path':'samples.json','samples_sha256':sh,'dataset_role':'INDEPENDENT_EVALUATION_PENDING_REVIEW','frozen':True}
    mp=root/'manifest.json'; mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return mp, hashlib.sha256(mp.read_bytes()).hexdigest()

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); print(capture(a.output))
