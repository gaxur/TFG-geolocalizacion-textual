#!/usr/bin/env python3
from __future__ import annotations
import argparse
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
 def do_GET(self):
  if urlparse(self.path).path=='/__form_autotest__':
   self.send_response(204);self.end_headers();return
  return super().do_GET()
 def end_headers(self):
  self.send_header('Cache-Control','no-store');super().end_headers()
def main():
 p=argparse.ArgumentParser(description='Sirve formularios locales de anotación');p.add_argument('--bind',default='127.0.0.1');p.add_argument('--port',type=int,default=8765);a=p.parse_args();handler=lambda *args,**kwargs:Handler(*args,directory=str(ROOT),**kwargs);server=ThreadingHTTPServer((a.bind,a.port),handler);print(f'http://{a.bind}:{a.port}/',flush=True);server.serve_forever()
if __name__=='__main__':main()
