#!/usr/bin/env python3
"""Descarga atómica de los ocho ficheros Commons autorizados."""
from __future__ import annotations
import argparse,hashlib,json,os,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ALLOWED_LICENSE_PREFIXES=("CC BY ","CC BY-SA ","CC0","Public domain","FAL","Copyrighted free use")
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,required=True);p.add_argument("--authorization",type=Path,required=True);p.add_argument("--output-dir",type=Path,required=True);p.add_argument("--manifest",type=Path,required=True);a=p.parse_args();plan=json.load(open(a.plan));auth=json.load(open(a.authorization))
 if plan["plan_id"]!=auth.get("plan_id") or digest(a.plan)!=auth.get("plan_sha256") or not auth.get("approved") or not all(auth.get("operator_confirmations",{}).values()):raise PermissionError("autorización Commons piloto incompatible")
 if len(plan["assets"])!=8:raise ValueError("plan Commons debe contener ocho assets")
 a.output_dir.mkdir(parents=True,exist_ok=True);records=[];total=0
 for row in plan["assets"]:
  if not row.get("author") or not row.get("attribution") or not row.get("license_identifier","").startswith(ALLOWED_LICENSE_PREFIXES):raise ValueError(f"licencia/autor incompleto: {row['page_id']}")
  url=row["canonical_url"];host=(urlsplit(url).hostname or "").casefold()
  if not host.endswith("upload.wikimedia.org"):raise ValueError("host Commons no autorizado")
  suffix=Path(urlsplit(url).path).suffix.lower() or ".bin";destination=a.output_dir/f"{row['page_id']}{suffix}"
  if destination.exists():raw=destination.read_bytes();status="reused"
  else:
   request=Request(url,headers={"User-Agent":"TFG-geolocalizacion-textual/commons-pilot-v1"})
   raw=None
   for attempt,delay in enumerate((20,40,80,120),1):
    try:
     with urlopen(request,timeout=60) as response:
      length=response.headers.get("Content-Length")
      if length and int(length)>8_000_000:raise ValueError("fichero Commons supera 8 MB")
      raw=response.read(8_000_001)
     break
    except HTTPError as error:
     if error.code not in {429,503} or attempt==4:raise
     retry=error.headers.get("Retry-After") if error.headers else None;time.sleep(min(180,max(delay,int(retry) if retry and retry.isdigit() else delay)))
   if len(raw)>8_000_000:raise ValueError("fichero Commons supera 8 MB")
   fd,name=tempfile.mkstemp(prefix=destination.name+".",suffix=".tmp",dir=a.output_dir)
   try:
    with os.fdopen(fd,"wb") as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.replace(name,destination)
   finally:
    if os.path.exists(name):os.unlink(name)
   status="downloaded";time.sleep(2.0)
  total+=len(raw)
  if total>64_000_000:raise ValueError("presupuesto Commons total excedido")
  records.append({**row,"status":status,"logical_path":os.path.relpath(destination.resolve(),a.manifest.parent.resolve()),"sha256":hashlib.sha256(raw).hexdigest(),"size_bytes":len(raw),"retention_deadline_utc":auth["retention_deadline_utc"]})
 document={"schema_version":"1.0","contract_version":"h26-h37-commons-semantic-assets-v1","plan_id":plan["plan_id"],"plan_sha256":digest(a.plan),"authorization_sha256":digest(a.authorization),"assets":records,"summary":{"assets":len(records),"downloaded":sum(r["status"]=="downloaded" for r in records),"reused":sum(r["status"]=="reused" for r in records),"total_bytes":total},"protocol":{"location_kind":"object","camera_position_claimed":False,"no_substitution":True,"private_academic_use":True,"redistribution":False}};a.manifest.write_text(json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+"\n");print(json.dumps(document["summary"],sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
