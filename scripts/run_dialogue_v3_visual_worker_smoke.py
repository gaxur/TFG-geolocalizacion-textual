#!/usr/bin/env python3
"""Supervisor con timeout efectivo para un único worker visual aislado."""

from __future__ import annotations
import argparse,hashlib,json,os,sys
from pathlib import Path
import subprocess,time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from scripts.run_qwen3_vl_8b_memory_smoke import atomic_write_json,compute_processes,digest,system_memory,utc_now

MINIMUM_RAM_BYTES=40*1024**3
MAXIMUM_SWAP_FRACTION=0.95
MAXIMUM_PSI_AVG10=0.10
STABLE_SWAP_SAMPLES=5
STABLE_SWAP_INTERVAL_SECONDS=2
MAXIMUM_RAM_DROP_BYTES=1024**3

def memory_pressure():
    path=Path('/proc/pressure/memory')
    if not path.is_file():return {"status":"NOT_VERIFIED"}
    rows={}
    for line in path.read_text().splitlines():
        parts=line.split();rows[parts[0]]={key:float(value) if key.startswith('avg') else int(value) for key,value in (item.split('=',1) for item in parts[1:])}
    return {"status":"VERIFIED",**rows}

def vmstat_counters():
    wanted={"pswpin","pswpout","pgmajfault","pgscan_direct","pgsteal_direct","oom_kill"};values={}
    for line in Path('/proc/vmstat').read_text().splitlines():
        key,value=line.split()
        if key in wanted:values[key]=int(value)
    return values

def collect_stable_swap_samples(*,count=STABLE_SWAP_SAMPLES,interval_seconds=STABLE_SWAP_INTERVAL_SECONDS,sleep=time.sleep):
    rows=[]
    for index in range(count):
        rows.append({"index":index+1,"recorded_at_utc":utc_now(),"system":system_memory(),"memory_pressure":memory_pressure(),"vmstat":vmstat_counters(),"compute_processes":compute_processes()})
        if index<count-1:sleep(interval_seconds)
    return rows

def evaluate_memory_gate(*,policy,host_compute_process_count,host_ollama_status,samples):
    reasons=[]
    if not samples:return {"passed":False,"blocking_reasons":["memory_samples_missing"],"deltas":"NOT_VERIFIED"}
    first,last=samples[0],samples[-1];all_keys=set(first["vmstat"])|set(last["vmstat"]);deltas={key:last["vmstat"].get(key,0)-first["vmstat"].get(key,0) for key in all_keys};ram_values=[row["system"]["ram_available_bytes"] for row in samples];psi_verified=all(row["memory_pressure"].get("status")=="VERIFIED" for row in samples);psi_ok=psi_verified and all(row["memory_pressure"][kind]["avg10"]<MAXIMUM_PSI_AVG10 for row in samples for kind in ("some","full"));compute_ok=host_compute_process_count==0 and all(not row["compute_processes"] for row in samples);ram_ok=min(ram_values)>=MINIMUM_RAM_BYTES and max(ram_values)-min(ram_values)<=MAXIMUM_RAM_DROP_BYTES
    if not compute_ok:reasons.append("foreign_compute_process_present")
    if host_ollama_status!="no_model_resident":reasons.append("ollama_status_not_safe_or_unverified")
    if not ram_ok:reasons.append("ram_stability_failed")
    if not psi_ok:reasons.append("memory_pressure_not_safe_or_unverified")
    if policy=="hard-swap":
        fraction=last["system"]["swap_used_bytes"]/last["system"]["swap_total_bytes"] if last["system"]["swap_total_bytes"] else 0.0
        if fraction>MAXIMUM_SWAP_FRACTION:reasons.append("swap_fraction_above_limit")
    elif policy=="stable-swap":
        required=("pswpin","pswpout","pgmajfault","pgscan_direct","pgsteal_direct","oom_kill")
        if len(samples)!=STABLE_SWAP_SAMPLES:reasons.append("memory_sample_count_invalid")
        if any(key not in row["vmstat"] for row in samples for key in required):reasons.append("memory_metrics_missing")
        elif any(deltas[key]!=0 for key in required):reasons.append("active_swap_fault_reclaim_or_oom")
    else:reasons.append("unknown_memory_policy")
    return {"passed":not reasons,"blocking_reasons":reasons,"policy":policy,"sample_count":len(samples),"interval_seconds":STABLE_SWAP_INTERVAL_SECONDS,"deltas":deltas,"ram_available_min_bytes":min(ram_values),"ram_available_max_bytes":max(ram_values),"ram_drop_span_bytes":max(ram_values)-min(ram_values),"residual_risk":"accepted residual risk: swap nearly full leaves little backing capacity; unified-memory pressure may change abruptly"}

def request_id(document):return "visual-worker-request-sha256-"+hashlib.sha256(json.dumps({key:value for key,value in document.items() if key!="request_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def run_supervised(command:list[str],timeout_seconds:int,output_root:Path)->dict:
    started=time.perf_counter();process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:stdout,stderr=process.communicate(timeout=timeout_seconds);timed_out=False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,15)
        try:stdout,stderr=process.communicate(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(process.pid,9);stdout,stderr=process.communicate()
        timed_out=True
    result={"recorded_at_utc":utc_now(),"returncode":process.returncode,"timed_out":timed_out,"duration_ms":(time.perf_counter()-started)*1000,"stdout":stdout,"stderr":stderr,"command_role":"single_authorized_worker"};atomic_write_json(output_root/"supervisor.json",result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument("--output-root",type=Path,required=True);p.add_argument("--fixture",type=Path,required=True);p.add_argument("--model-dir",type=Path,required=True);p.add_argument("--image-mount-dir",type=Path,required=True);p.add_argument("--docker-image",default="crosstext2loc-gb10:f511");p.add_argument("--total-timeout",type=int,default=240);p.add_argument("--host-compute-process-count",type=int,default=-1);p.add_argument("--host-ollama-status",default="NOT_VERIFIED");p.add_argument("--memory-policy",choices=("hard-swap","stable-swap"),default="hard-swap");p.add_argument("--validate-only",action="store_true");a=p.parse_args()
    if a.output_root.exists():raise ValueError("output-root ya existe")
    a.output_root.mkdir(parents=True);fixture=a.fixture.resolve();mount=a.image_mount_dir.resolve()
    if fixture.parent!=mount:raise ValueError("fixture debe estar directamente en allowlist")
    image_sha=digest(fixture);base={"schema_version":"1.0","contract_version":"dialogue-visual-worker-request-v2","model":{"model_id":"Qwen/Qwen3-VL-8B-Instruct","revision":"0c351dd01ed87e9c1b53cbc748cba10e6187ff3b","model_path":"/models/Qwen3-VL-8B"},"image":{"image_id":"synthetic-transport-v1","path":"/authorized-images/"+fixture.name,"sha256":image_sha,"provenance":{"source":"synthetic-local-fixture","purpose":"transport-only-no-geographic-evidence"},"authorized":True,"authorization_id":"synthetic-worker-smoke-v1","observer_relation":"synthetic_transport_only"},"claim":{"claim_id":"worker-claim-synthetic-shapes","kind":"object_presence","value":{"object":"geometric_shapes"},"source_text":"La imagen contiene figuras geométricas."},"generation":{"dtype":"bfloat16","attention":"sdpa","do_sample":False,"max_new_tokens":192},"timeouts":{"load_seconds":150,"inference_seconds":30,"total_seconds":a.total_timeout},"protocol":{"ground_truth_used":False,"reserved_sets_used":False,"network_used":False,"single_inference":True}};base["request_id"]=request_id(base);atomic_write_json(a.output_root/"request.json",base)
    sample_count=STABLE_SWAP_SAMPLES if a.memory_policy=="stable-swap" else 1;samples=collect_stable_swap_samples(count=sample_count,interval_seconds=0 if a.validate_only else STABLE_SWAP_INTERVAL_SECONDS);gate=evaluate_memory_gate(policy=a.memory_policy,host_compute_process_count=a.host_compute_process_count,host_ollama_status=a.host_ollama_status,samples=samples);atomic_write_json(a.output_root/"memory-samples.json",{"schema_version":"1.0","contract_version":"dialogue-visual-memory-samples-v1","memory_policy":a.memory_policy,"samples":samples})
    preflight={"recorded_at_utc":utc_now(),"host_compute_process_count":a.host_compute_process_count,"ollama":a.host_ollama_status,"memory_policy":{"name":a.memory_policy,"version":"stable-swap-v1" if a.memory_policy=="stable-swap" else "hard-swap-v1","minimum_ram_available_bytes":MINIMUM_RAM_BYTES,"maximum_swap_fraction":MAXIMUM_SWAP_FRACTION,"maximum_psi_avg10":MAXIMUM_PSI_AVG10,"maximum_ram_drop_bytes":MAXIMUM_RAM_DROP_BYTES},"disk_free_bytes":__import__('shutil').disk_usage(a.output_root).free,"gate":gate};atomic_write_json(a.output_root/"preflight.json",preflight)
    if not a.validate_only and not preflight["gate"]["passed"]:
        reasons=preflight["gate"]["blocking_reasons"];status="BLOCKED_BY_GPU" if "foreign_compute_process_present" in reasons else "BLOCKED_BY_MEMORY_POLICY"
        atomic_write_json(a.output_root/"report.json",{"status":status,"worker_started":False,"visual_inferences":0,"automatic_retries":0,"dialogue_session_executed":False,"image_eligible_for_dialogue_v3":False,"image_role":"synthetic_transport_only","memory_policy":a.memory_policy,"blocking_reasons":reasons,"foreign_processes_modified":False});print(json.dumps({"status":status,"blocking_reasons":reasons}));return 2
    worker_out=a.output_root/"worker";worker_out.mkdir()
    if a.validate_only:
        command=[sys.executable,str(ROOT/"scripts/qwen3_vl_dialogue_worker.py"),"--request",str(a.output_root/"request.json"),"--output-root",str(worker_out),"--authorized-root",str(mount),"--validate-only"]
    else:
        project=ROOT.resolve();model=a.model_dir.resolve();request_inside="/workspace/project/"+str((a.output_root/"request.json").resolve().relative_to(project));output_inside="/workspace/project/"+str(worker_out.resolve().relative_to(project))
        command=["docker","run","--rm","--gpus","all","--network","none","--ipc=host","--ulimit","memlock=-1","--ulimit","stack=67108864","-e","CUDA_VISIBLE_DEVICES=0","-e","HOME=/root","-e","HF_HOME=/tmp/huggingface","-v",f"{project}:/workspace/project","-v",f"{model}:/models/Qwen3-VL-8B:ro","-v",f"{mount}:/authorized-images:ro","-w","/workspace/project",a.docker_image,"python","scripts/qwen3_vl_dialogue_worker.py","--request",request_inside,"--output-root",output_inside]
    result=run_supervised(command,a.total_timeout,a.output_root);response_path=worker_out/"response.json";success=result["returncode"]==0 and not result["timed_out"] and (a.validate_only or response_path.is_file());status="VALIDATION_PASS" if success and a.validate_only else "VLM_WORKER_REAL_SMOKE_PASS" if success else "VLM_WORKER_RUNTIME_FAIL";atomic_write_json(a.output_root/"report.json",{"status":status,"worker_started":True,"visual_inferences":1 if response_path.is_file() else 0,"automatic_retries":0,"worker_only":True,"dialogue_session_executed":False,"image_eligible_for_dialogue_v3":False,"reason":"synthetic_transport_only_not_observer_view","memory_policy":a.memory_policy,"residual_risk":gate["residual_risk"],"request_contract_validated":(worker_out/"request.validated.json").is_file(),"model_loaded":(worker_out/"loaded.json").is_file(),"response_validated":response_path.is_file(),"supervisor_duration_ms":result["duration_ms"],"timed_out":result["timed_out"],"system_after":system_memory()});print(json.dumps({"status":status,"timed_out":result["timed_out"]}));return 0 if success else 1

if __name__=="__main__":raise SystemExit(main())
