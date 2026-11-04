#!/usr/bin/env python3
"""Valida sintaxis JS, fixtures y rutas HTTP de interfaces I20 sin datos sensibles."""
from __future__ import annotations
import argparse,json,re,subprocess,tempfile,urllib.request
from pathlib import Path
def scripts(html):return [body for attrs,body in re.findall(r'<script([^>]*)>(.*?)</script>',html,flags=re.S|re.I) if 'application/json' not in attrs]
def main():
 p=argparse.ArgumentParser();p.add_argument('--workflow-root',type=Path,required=True);p.add_argument('--base-url',required=True);a=p.parse_args();root=a.workflow_root;pages={'scene-review':'scene-review/review-scenes.html','annotation':'annotation/annotate.html','review-a':'review-a/review.html','review-b':'review-b/review.html','adjudication':'adjudication/adjudicate.html'};result={}
 for name,relative in pages.items():
  path=root/relative;html=path.read_text(encoding='utf-8');blocks=scripts(html)
  if not blocks:raise ValueError(f'{name}: sin JavaScript ejecutable')
  for index,body in enumerate(blocks):
   with tempfile.NamedTemporaryFile('w',suffix='.js',encoding='utf-8') as stream:
    stream.write(body);stream.flush();check=subprocess.run(['node','--check',stream.name],capture_output=True,text=True)
   if check.returncode:raise ValueError(f'{name}: error JS bloque {index}: {check.stderr.strip()}')
  with urllib.request.urlopen(a.base_url.rstrip('/')+'/'+relative,timeout=5) as response:
   if response.status!=200:raise ValueError(f'{name}: HTTP {response.status}')
  result[name]={'script_blocks':len(blocks),'visible_error_panel':'id="init-error"' in html,'http_status':200}
 fixture=json.loads((root/'scene-review/fixture.json').read_text());image_urls=[]
 for row in fixture['records']:
  image_urls.extend(('scene-review/'+row['left_reference_path'],'scene-review/'+row['right_reference_path']))
 for relative in image_urls:
  with urllib.request.urlopen(a.base_url.rstrip('/')+'/'+relative,timeout=5) as response:
   if response.status!=200 or not response.headers.get_content_type().startswith('image/'):raise ValueError(f'asset no servido: {relative}')
 result['scene_pairs']=len(fixture['records']);result['scene_image_requests']=len(image_urls);print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
