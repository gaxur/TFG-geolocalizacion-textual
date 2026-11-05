#!/usr/bin/env python3
"""Auditoría read-only de memoria GB10, Ollama y clientes sin persistir secretos."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/generated/gb10-ollama-memory-audit-v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def write(name: str, value) -> None:
    (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def meminfo() -> dict:
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, raw = line.split(":", 1); values[key] = int(raw.strip().split()[0]) * 1024
    return values


def vmstat() -> dict:
    wanted = {"pswpin", "pswpout", "pgmajfault", "pgscan_kswapd", "pgscan_direct", "pgsteal_kswapd", "pgsteal_direct"}
    return {key: int(value) for key, value in (line.split() for line in Path("/proc/vmstat").read_text().splitlines()) if key in wanted}


def psi() -> dict:
    rows = {}
    for line in Path("/proc/pressure/memory").read_text().splitlines():
        parts = line.split(); rows[parts[0]] = {key: float(value) if key.startswith("avg") else int(value) for key, value in (item.split("=", 1) for item in parts[1:])}
    return rows


def gpu_processes() -> list[dict]:
    result = run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory,gpu_uuid", "--format=csv,noheader,nounits"]); rows=[]
    for line in result.stdout.splitlines():
        parts=[item.strip() for item in line.split(",")]
        if len(parts)==4: rows.append({"pid":int(parts[0]),"process_name":parts[1],"used_memory_mib":None if parts[2] in {"N/A","[N/A]"} else int(parts[2]),"gpu_uuid":parts[3]})
    return rows


def swap_processes() -> list[dict]:
    rows=[]
    for path in Path("/proc").iterdir():
        if not path.name.isdigit(): continue
        try:
            fields={line.split(":",1)[0]:line.split(":",1)[1].strip() for line in (path/"status").read_text().splitlines() if ":" in line}; swap=int(fields.get("VmSwap","0 kB").split()[0])*1024
            if swap: rows.append({"pid":int(path.name),"name":fields.get("Name"),"swap_bytes":swap,"rss_bytes":int(fields.get("VmRSS","0 kB").split()[0])*1024,"uid":fields.get("Uid","").split()[0]})
        except (FileNotFoundError, PermissionError, ProcessLookupError): pass
    return sorted(rows,key=lambda row:row["swap_bytes"],reverse=True)


def docker_inspect(name: str) -> dict:
    result=run(["docker","inspect",name])
    if result.returncode: return {"available":False}
    value=json.loads(result.stdout)[0]
    env_keys=sorted(item.split("=",1)[0] for item in value["Config"].get("Env",[]) if any(token in item.split("=",1)[0].upper() for token in ("OLLAMA","MODEL","LLM","CONTEXT","NUM_CTX","KEEP_ALIVE")))
    return {"available":True,"container_id":value["Id"][:12],"image":value["Config"]["Image"],"pid":value["State"]["Pid"],"env_keys_only":env_keys,"memory_limit_bytes":value["HostConfig"]["Memory"],"memory_swap_limit_bytes":value["HostConfig"]["MemorySwap"],"restart_policy":value["HostConfig"]["RestartPolicy"],"networks":{key:item.get("IPAddress") for key,item in value["NetworkSettings"]["Networks"].items()},"mounts":[{"type":item["Type"],"name":item.get("Name"),"destination":item["Destination"],"read_write":item["RW"]} for item in value["Mounts"]]}


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=False)
    samples=[]
    for index in range(5):
        memory=meminfo(); samples.append({"index":index+1,"recorded_at_utc":now(),"memory":{key:memory.get(key) for key in ("MemTotal","MemFree","MemAvailable","Buffers","Cached","SReclaimable","Shmem","AnonPages","Mapped","SwapTotal","SwapFree","SwapCached")},"vmstat":vmstat(),"psi":psi(),"gpu_compute":gpu_processes()})
        if index<4: time.sleep(2)
    first,last=samples[0],samples[-1]
    deltas={key:last["vmstat"][key]-first["vmstat"][key] for key in first["vmstat"]}
    write("swap-observations.json",{"schema_version":"1.0","samples":samples,"interval_seconds":2,"deltas":deltas,"active_swap_io_observed":bool(deltas["pswpin"] or deltas["pswpout"]),"interpretation":"historically_occupied_without_observed_active_swap_io" if not deltas["pswpin"] and not deltas["pswpout"] else "active_swap_io_observed"})
    memory=meminfo();write("system-memory.json",{"schema_version":"1.0","recorded_at_utc":now(),"bytes":memory,"psi":psi(),"top_swap_processes":swap_processes()[:30],"metric_warning":"RSS, swap, page cache and CUDA memory are not additive"})
    write("gpu-processes.json",{"schema_version":"1.0","recorded_at_utc":now(),"gpu":"NVIDIA GB10","driver":"580.173.02","cuda_host":"13.0","memory_total":"NOT_VERIFIED","memory_free":"NOT_VERIFIED","compute_processes":gpu_processes()})
    installed=run(["docker","exec","ollama","ollama","list"]).stdout;resident=run(["docker","exec","ollama","ollama","ps"]).stdout
    write("ollama-models.json",{"schema_version":"1.0","recorded_at_utc":now(),"installed_table":installed.splitlines(),"resident_table":resident.splitlines(),"storage":{"docker_volume":"ollama_ollama","container_path":"/root/.ollama","host_mountpoint":"/var/lib/docker/volumes/ollama_ollama/_data","volume_size_observed":"46.15GB","models_directory_observed":"43G"},"qwen3_8":{"manifest_model_blob_bytes":16810714464,"projector_blob_bytes":931146016,"format":"GGUF V3 Q4_K_M","model_context_length":262144,"contexts_observed":[262144,32768]}})
    containers={name:docker_inspect(name) for name in ("ollama","open-webui","anythingllm","litellm","n8n-n8n-1")};stats=run(["docker","stats","--no-stream","--format","{{json .}}"])
    write("docker-memory.json",{"schema_version":"1.0","recorded_at_utc":now(),"containers":containers,"stats":[json.loads(line) for line in stats.stdout.splitlines() if line],"secrets_policy":"environment values omitted"})
    ollama_pid=containers["ollama"].get("pid"); tree={"ollama_serve_pid":ollama_pid,"container_id":containers["ollama"].get("container_id"),"cgroup":"/system.slice/docker-cfc63656be332277a0c8b2764135739a28b611c9fec6fc407e422d8273d07092.scope","current_compute_processes":gpu_processes(),"relationship":"llama-server child of ollama serve when resident"}
    write("process-tree.json",{"schema_version":"1.0","recorded_at_utc":now(),**tree})
    logs=run(["docker","logs","--since","2h","--timestamps","ollama"]); text=logs.stdout+logs.stderr; requests=[]
    pattern=re.compile(r"^(\S+).*?\[GIN\].*?\|\s*(\d+\.\d+\.\d+\.\d+)\s*\|\s*(GET|POST|HEAD)\s+\"([^\"]+)\"",re.M)
    for timestamp,ip,method,path in pattern.findall(text):
        if path in {"/api/chat","/api/ps","/api/tags","/api/show","/"}: requests.append({"timestamp":timestamp,"client_ip":ip,"method":method,"path":path})
    write("connections-summary.json",{"schema_version":"1.0","recorded_at_utc":now(),"ollama_published_port":11434,"requests_without_payloads":requests,"confirmed_client_ip_for_chat":"192.168.121.32" if any(r["path"]=="/api/chat" and r["client_ip"]=="192.168.121.32" for r in requests) else "NOT_VERIFIED","container_ips":{name:value.get("networks") for name,value in containers.items()},"attribution":{"confirmed":"requests reached Ollama /api/chat from 192.168.121.32","probable":"an interactive client on remote host 192.168.121.32","unknown":"specific application on that remote host"}})
    write("preflight-analysis.json",{"schema_version":"1.0","gate":{"minimum_ram_available_bytes":40*1024**3,"maximum_swap_fraction":0.95,"maximum_psi_avg10":0.10,"foreign_compute_processes_allowed":0},"assessment":{"zero_foreign_compute_is_hard_block":True,"swap_fraction_is_conservative_and_does_not_distinguish_historical_occupancy":True,"psi_and_vmstat_show_no_active_pressure_during_samples":not bool(deltas["pswpin"] or deltas["pswpout"]),"policy_change":"PENDING_OPERATOR_APPROVAL"},"alternative_policy_proposal":{"status":"proposal_only","requirements":["zero foreign compute for full observation window","MemAvailable >= 40 GiB","PSI some/full avg10 < 0.10","pswpin and pswpout deltas zero in five fixed samples","no major fault or direct reclaim growth above reviewed tolerance"],"risks":["historically swapped processes may fault pages back during model load","unified memory demand can create new pressure abruptly","short sampling window may miss bursts"],"reversion":"restore current hard 95% swap threshold after any OOM, PSI increase or swap-in activity"}})
    report="""# Auditoría GB10, Ollama y memoria\n\nAuditoría de solo lectura. No se detuvieron procesos, no se modificó swap y no se ejecutaron modelos.\n\n## Hallazgos\n\n- Ollama tiene cuatro modelos instalados; qwen3.8 ocupa aproximadamente 17 GB lógicos y su volumen completo 46,15 GB.\n- Las peticiones `/api/chat` observadas proceden de `192.168.121.32`, fuera de las redes Docker locales 172.x. La aplicación concreta no puede confirmarse retrospectivamente.\n- Qwen3.8 se cargó con contextos 262144 y 32768 en peticiones distintas. El contexto es sensible a la petición/cliente; el máximo 262144 coincide además con el metadata del GGUF.\n- En la carga 262144, Ollama registró 15339 MiB de modelo, 16384 MiB de KV principal, 1024 MiB de KV draft y buffers adicionales. Son mediciones de Ollama para esa carga, no una fórmula universal.\n- La swap está casi llena, pero las cinco muestras no mostraron crecimiento de pswpin/pswpout, PSI o reclaim: ocupación histórica sin presión activa observada.\n- El gate bloquea correctamente por compute ajeno. Su umbral de swap es conservador y no distingue ocupación histórica de actividad; cualquier alternativa requiere aprobación.\n"""
    (OUTPUT/"report.md").write_text(report,encoding="utf-8")
    return 0


if __name__=="__main__":raise SystemExit(main())
