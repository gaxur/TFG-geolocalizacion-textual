#!/usr/bin/env python3
"""Wait for a stable GB10 memory window, then run official CrossText2Loc."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

GIB = 1024**3
EXPECTED_CVG_TEXT_COMMIT = "6910d2747a94fbe985309bde60cd4732bcbbf50f"
EXPECTED_CLIP_COMMIT = "dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1"
CHECKPOINT_NAME = "long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth"
CHECKPOINT_SIZE = 1_712_649_548
CHECKPOINT_SHA256 = "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d"
EXPECTED_CONFIG = {
    "osm_root_dir": "./local_data/{version}-OSM",
    "testset_path": "./local_data/annotation/{version}/test.json",
    "checkpoint_dir": "./checkpoints",
    "result_dir": "./results",
}
SERVICE_NAMES = ("serve_embeddings.py", "VLLM::EngineCore")
STATES = (
    "READY",
    "WAITING",
    "TIMEOUT_NO_WINDOW",
    "PRECHECK_FAILED",
    "REPO_VALIDATION_FAILED",
    "CHECKPOINT_VALIDATION_FAILED",
    "DATASET_VALIDATION_FAILED",
    "EVALUATION_STARTED",
    "EVALUATION_SUCCESS",
    "EVALUATION_FAILED",
    "SAFETY_ABORT",
    "MONITORING_ERROR",
)


def gib_to_bytes(value: float) -> int:
    if value < 0:
        raise ValueError("Los umbrales GiB no pueden ser negativos")
    return round(value * GIB)


def parse_meminfo(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        fields = raw.split()
        if not fields or not fields[0].isdigit():
            continue
        multiplier = 1024 if len(fields) > 1 and fields[1] == "kB" else 1
        values[key] = int(fields[0]) * multiplier
    required = {
        "MemTotal",
        "MemFree",
        "MemAvailable",
        "Cached",
        "SReclaimable",
        "SwapTotal",
        "SwapFree",
    }
    missing = required - values.keys()
    if missing:
        raise ValueError(f"Faltan campos de /proc/meminfo: {sorted(missing)}")
    return {key: values[key] for key in sorted(required)}


def read_meminfo() -> dict[str, int]:
    return parse_meminfo(Path("/proc/meminfo").read_text(encoding="ascii"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_simple_yaml_paths(path: Path) -> dict[str, str]:
    values = {}
    in_paths = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "paths:":
            in_paths = True
            continue
        if in_paths and line and not line.startswith(" "):
            break
        if in_paths and line.startswith("  ") and ":" in line:
            key, value = line.strip().split(":", 1)
            value = value.strip().strip('"').strip("'")
            if value:
                values[key] = value
    return values


def find_services() -> dict[str, list[int]]:
    matches = {name: [] for name in SERVICE_NAMES}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            tokens = (entry / "cmdline").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        basenames = {Path(token.decode(errors="replace")).name for token in tokens if token}
        for name in SERVICE_NAMES:
            if name in basenames:
                matches[name].append(int(entry.name))
    return matches


def nvidia_smi_state() -> dict[str, object]:
    gpu_line = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,compute_cap,addressing_mode,"
            "utilization.gpu,utilization.memory,power.draw,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().splitlines()
    if len(gpu_line) != 1:
        raise ValueError(f"Se esperaba una GPU, se obtuvieron {len(gpu_line)}")
    fields = [field.strip() for field in gpu_line[0].split(",")]
    if len(fields) != 8:
        raise ValueError(f"Salida GPU inesperada: {gpu_line[0]!r}")
    processes = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "gpu_name": fields[0],
        "driver_version": fields[1],
        "compute_capability": fields[2],
        "addressing_mode": fields[3],
        "gpu_utilization_percent": int(fields[4]),
        "gpu_memory_utilization_percent": int(fields[5]),
        "power_watts": float(fields[6]),
        "temperature_celsius": int(fields[7]),
        "gpu_processes": processes.replace("\n", "; "),
    }


def cuda_probe(python: Path) -> dict[str, object]:
    code = """
import json, torch
free, total = torch.cuda.mem_get_info(0)
print(json.dumps({
    'cuda_available': torch.cuda.is_available(),
    'device_count': torch.cuda.device_count(),
    'device_name': torch.cuda.get_device_name(0),
    'cuda_free_bytes': free,
    'cuda_total_bytes': total,
    'torch_memory_allocated_bytes': torch.cuda.memory_allocated(0),
    'torch_memory_reserved_bytes': torch.cuda.memory_reserved(0),
}))
"""
    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = "0"
    result = subprocess.run(
        [str(python), "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    return json.loads(result.stdout)


def build_evaluation_command(cvg_text_root: Path, python: Path) -> list[str]:
    relative_python = os.path.relpath(python, cvg_text_root)
    return [
        "env",
        "CUDA_VISIBLE_DEVICES=0",
        relative_python,
        "zeroshot.py",
        "--version",
        "NewYork-mixed",
        "--img_type",
        "osm",
        "--model",
        "CLIP-L/14@336",
        "--expand",
        "--checkpoint",
        CHECKPOINT_NAME,
    ]


def validate_repository(cvg_text_root: Path) -> dict[str, object]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cvg_text_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != EXPECTED_CVG_TEXT_COMMIT:
        raise RuntimeError(f"Commit CVG-Text inesperado: {head}")
    changed = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=cvg_text_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if changed != ["config.yaml"]:
        raise RuntimeError(f"Cambios versionados inesperados en CVG-Text: {changed}")
    paths = parse_simple_yaml_paths(cvg_text_root / "config.yaml")
    actual = {key: paths.get(key) for key in EXPECTED_CONFIG}
    if actual != EXPECTED_CONFIG:
        raise RuntimeError(f"Configuracion local inesperada: {actual}")
    return {"commit": head, "modified_tracked_files": changed, "paths": actual}


def validate_checkpoint(checkpoint: Path) -> dict[str, object]:
    if not checkpoint.is_file():
        raise FileNotFoundError(f"Checkpoint ausente: {checkpoint}")
    if checkpoint.name != CHECKPOINT_NAME:
        raise RuntimeError(f"Nombre de checkpoint inesperado: {checkpoint.name}")
    size = checkpoint.stat().st_size
    if size != CHECKPOINT_SIZE:
        raise RuntimeError(f"Tamano de checkpoint inesperado: {size}")
    digest = sha256(checkpoint)
    if digest != CHECKPOINT_SHA256:
        raise RuntimeError(f"SHA-256 inesperado: {digest}")
    return {"path": str(checkpoint), "size_bytes": size, "sha256": digest}


def validate_dataset(cvg_text_root: Path) -> dict[str, object]:
    paths = parse_simple_yaml_paths(cvg_text_root / "config.yaml")
    root_template = paths["osm_root_dir"].format(version="NewYork-mixed")
    annotation_template = paths["testset_path"].format(version="NewYork-mixed")
    roots = [
        cvg_text_root / root_template.replace("-mixed", ""),
        cvg_text_root / root_template.replace("-mixed", "-photos"),
    ]
    annotations = [
        cvg_text_root / annotation_template.replace("-mixed", ""),
        cvg_text_root / annotation_template.replace("-mixed", "-photos"),
    ]
    expected_counts = [1000, 200]
    split_results = []
    for root, annotation, expected in zip(roots, annotations, expected_counts):
        if not root.is_dir() or not annotation.is_file():
            raise FileNotFoundError(f"Split ausente: {root} / {annotation}")
        data = json.loads(annotation.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or len(data) != expected:
            raise RuntimeError(f"Numero de anotaciones inesperado en {annotation}")
        image_files = [path for path in root.iterdir() if path.is_file()]
        if len(image_files) != expected:
            raise RuntimeError(f"Numero de imagenes inesperado en {root}: {len(image_files)}")
        missing = [name for name in data if not (root / name).is_file()]
        if missing:
            raise RuntimeError(f"Faltan {len(missing)} imagenes en {root}")
        split_results.append(
            {
                "annotation": str(annotation.resolve()),
                "image_root": str(root.resolve()),
                "samples": len(data),
                "images": len(image_files),
                "missing_images": 0,
            }
        )
    return {"samples": sum(expected_counts), "splits": split_results, "query_zip_used": False}


def installed_versions(python: Path) -> dict[str, str]:
    code = """
import importlib.metadata, json, platform, torch, torchvision
d = importlib.metadata.distribution('clip')
direct = json.loads(d.read_text('direct_url.json'))
print(json.dumps({
    'python': platform.python_version(),
    'architecture': platform.machine(),
    'torch': torch.__version__,
    'torchvision': torchvision.__version__,
    'torch_cuda': torch.version.cuda,
    'clip_commit': direct.get('vcs_info', {}).get('commit_id'),
}))
"""
    result = subprocess.run(
        [str(python), "-c", code], check=True, capture_output=True, text=True
    )
    versions = json.loads(result.stdout)
    if versions["clip_commit"] != EXPECTED_CLIP_COMMIT:
        raise RuntimeError(f"Commit CLIP inesperado: {versions['clip_commit']}")
    return versions


def evaluate_conditions(
    sample: dict[str, object],
    min_cuda_free: int,
    min_linux_available: int,
    min_swap_free: int,
    max_gpu_utilization: int,
) -> tuple[bool, list[str]]:
    reasons = []
    checks = (
        (sample["cuda_free_bytes"] >= min_cuda_free, "cuda_free_below_threshold"),
        (
            sample["MemAvailable"] >= min_linux_available,
            "linux_available_below_threshold",
        ),
        (sample["SwapFree"] >= min_swap_free, "swap_free_below_threshold"),
        (
            sample["gpu_utilization_percent"] <= max_gpu_utilization,
            "gpu_utilization_above_threshold",
        ),
        (sample["services_ok"], "required_service_missing"),
    )
    for passed, reason in checks:
        if not passed:
            reasons.append(reason)
    return not reasons, reasons


def update_stable_count(previous: int, ready: bool) -> int:
    return previous + 1 if ready else 0


def wait_timed_out(now: float, deadline: float) -> bool:
    return now >= deadline


def collect_wait_sample(python: Path) -> dict[str, object]:
    memory = read_meminfo()
    cuda = cuda_probe(python)
    gpu = nvidia_smi_state()
    services = find_services()
    return {
        "timestamp": datetime.now().astimezone().isoformat(),
        **memory,
        **cuda,
        **gpu,
        "load_1m": os.getloadavg()[0],
        "services": services,
        "services_ok": all(services[name] for name in SERVICE_NAMES),
    }


def write_csv_row(path: Path, sample: dict[str, object], first: bool) -> None:
    row = {
        key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
        for key, value in sample.items()
    }
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(row))
        if first:
            writer.writeheader()
        writer.writerow(row)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def monitor_evaluation(
    process: subprocess.Popen,
    output_dir: Path,
    interval: float,
    baseline_swap_used: int,
) -> tuple[str, dict[str, object] | None]:
    monitor_path = output_dir / "monitor.csv"
    first = True
    while process.poll() is None:
        try:
            memory = read_meminfo()
            gpu = nvidia_smi_state()
            services = find_services()
            ps = subprocess.run(
                ["ps", "-p", str(process.pid), "-o", "pid=,%cpu=,rss=,stat=,etime="],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            current = {
                "timestamp": datetime.now().astimezone().isoformat(),
                **memory,
                **gpu,
                "services": services,
                "services_ok": all(services[name] for name in SERVICE_NAMES),
                "evaluation_process": ps,
            }
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            event = {
                "state": "MONITORING_ERROR",
                "timestamp": datetime.now().astimezone().isoformat(),
                "reason": str(error),
            }
            os.killpg(process.pid, signal.SIGTERM)
            return "MONITORING_ERROR", event
        write_csv_row(monitor_path, current, first)
        first = False
        abort = None
        if not current["services_ok"]:
            abort = ("service", current["services"], "all required services active")
        elif current["MemAvailable"] < 8 * GIB:
            abort = ("MemAvailable", current["MemAvailable"], 8 * GIB)
        elif current["SwapTotal"] - current["SwapFree"] - baseline_swap_used > 2 * GIB:
            abort = (
                "swap_growth",
                current["SwapTotal"] - current["SwapFree"] - baseline_swap_used,
                2 * GIB,
            )
        if abort:
            event = {
                "state": "SAFETY_ABORT",
                "timestamp": current["timestamp"],
                "metric": abort[0],
                "value": abort[1],
                "threshold": abort[2],
            }
            os.killpg(process.pid, signal.SIGTERM)
            return "SAFETY_ABORT", event
        time.sleep(interval)
    return ("EVALUATION_SUCCESS" if process.returncode == 0 else "EVALUATION_FAILED"), None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-cuda-free-gib", type=float, default=16.0)
    parser.add_argument("--min-linux-available-gib", type=float, default=16.0)
    parser.add_argument("--min-swap-free-gib", type=float, default=8.0)
    parser.add_argument("--max-gpu-utilization-percent", type=int, default=10)
    parser.add_argument("--consecutive-samples", type=int, default=5)
    parser.add_argument("--sample-interval", type=float, default=5.0)
    parser.add_argument("--max-wait-minutes", type=float, default=60.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-root", type=Path, default=Path("results/cross_text2loc_wait_run"))
    args = parser.parse_args()
    if args.consecutive_samples < 1 or args.sample_interval <= 0 or args.max_wait_minutes <= 0:
        parser.error("muestras, intervalo y espera deben ser positivos")
    if not 0 <= args.max_gpu_utilization_percent <= 100:
        parser.error("la utilizacion GPU maxima debe estar entre 0 y 100")

    project_root = Path(__file__).resolve().parent.parent
    cvg_text_root = project_root / "external/CVG-Text"
    python = project_root / ".venv-cvgtext/bin/python"
    checkpoint = cvg_text_root / "checkpoints/CLIP-L_14@336" / CHECKPOINT_NAME
    run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    output_dir = (project_root / args.output_root / run_id).resolve()
    output_dir.mkdir(parents=True)
    command = build_evaluation_command(cvg_text_root, python)
    (output_dir / "command.txt").write_text(" ".join(command) + "\n", encoding="utf-8")

    thresholds = {
        "min_cuda_free_bytes": gib_to_bytes(args.min_cuda_free_gib),
        "min_linux_available_bytes": gib_to_bytes(args.min_linux_available_gib),
        "min_swap_free_bytes": gib_to_bytes(args.min_swap_free_gib),
        "max_gpu_utilization_percent": args.max_gpu_utilization_percent,
    }
    config = {
        "dry_run": args.dry_run,
        "thresholds": thresholds,
        "threshold_status": "UMBRAL OPERACIONAL EXPERIMENTAL",
        "consecutive_samples": args.consecutive_samples,
        "sample_interval_seconds": args.sample_interval,
        "max_wait_minutes": args.max_wait_minutes,
        "platform": "Lenovo ThinkStation PGX / NVIDIA GB10 / ARM64 / ATS UMA",
        "software": None,
        "checkpoint_expected": CHECKPOINT_NAME,
        "checkpoint_sha256_expected": CHECKPOINT_SHA256,
        "command": command,
    }
    write_json(output_dir / "config.json", config)

    try:
        if not python.is_file():
            raise RuntimeError(f"Python aislado ausente: {python}")
        versions = installed_versions(python)
        precheck = {
            "repository": validate_repository(cvg_text_root),
            "checkpoint": validate_checkpoint(checkpoint),
            "dataset": validate_dataset(cvg_text_root),
            "software": versions,
        }
    except Exception as error:
        message = str(error)
        if "Commit CVG-Text" in message or "CVG-Text" in message and "Cambios" in message:
            state = "REPO_VALIDATION_FAILED"
        elif "checkpoint" in message.lower() or "SHA-256" in message:
            state = "CHECKPOINT_VALIDATION_FAILED"
        elif "Split" in message or "anotaciones" in message or "imagenes" in message:
            state = "DATASET_VALIDATION_FAILED"
        else:
            state = "PRECHECK_FAILED"
        result = {"state": state, "error": f"{type(error).__name__}: {error}"}
        write_json(output_dir / "precheck.json", result)
        write_json(output_dir / "result.json", result)
        print(json.dumps(result, indent=2))
        return 2
    config["software"] = versions
    write_json(output_dir / "config.json", config)
    write_json(output_dir / "precheck.json", {"state": "READY", **precheck})

    deadline = time.monotonic() + args.max_wait_minutes * 60
    stable = 0
    sample_number = 0
    wait_path = output_dir / "wait_samples.csv"
    final_sample = None
    state = "WAITING"
    while not wait_timed_out(time.monotonic(), deadline):
        try:
            current = collect_wait_sample(python)
        except Exception as error:
            result = {
                "state": "MONITORING_ERROR",
                "error": f"{type(error).__name__}: {error}",
                "evaluation_started": False,
            }
            write_json(output_dir / "result.json", result)
            print(json.dumps(result, indent=2))
            return 3
        ready, reasons = evaluate_conditions(
            current,
            thresholds["min_cuda_free_bytes"],
            thresholds["min_linux_available_bytes"],
            thresholds["min_swap_free_bytes"],
            thresholds["max_gpu_utilization_percent"],
        )
        stable = update_stable_count(stable, ready)
        current.update(
            {"sample_number": sample_number, "ready": ready, "reasons": reasons, "stable_count": stable}
        )
        write_csv_row(wait_path, current, sample_number == 0)
        sample_number += 1
        print(
            f"{current['timestamp']} state={'READY' if ready else 'WAITING'} "
            f"cuda_free={current['cuda_free_bytes'] / GIB:.2f}GiB "
            f"linux_available={current['MemAvailable'] / GIB:.2f}GiB "
            f"swap_free={current['SwapFree'] / GIB:.2f}GiB stable={stable}/{args.consecutive_samples}",
            flush=True,
        )
        if stable >= args.consecutive_samples:
            try:
                final_sample = collect_wait_sample(python)
            except Exception as error:
                result = {
                    "state": "MONITORING_ERROR",
                    "error": f"{type(error).__name__}: {error}",
                    "evaluation_started": False,
                }
                write_json(output_dir / "result.json", result)
                print(json.dumps(result, indent=2))
                return 3
            final_ready, final_reasons = evaluate_conditions(
                final_sample,
                thresholds["min_cuda_free_bytes"],
                thresholds["min_linux_available_bytes"],
                thresholds["min_swap_free_bytes"],
                thresholds["max_gpu_utilization_percent"],
            )
            write_json(
                output_dir / "final-memory-precheck.json",
                {"ready": final_ready, "reasons": final_reasons, "sample": final_sample},
            )
            if final_ready:
                state = "READY"
                break
            stable = 0
        time.sleep(args.sample_interval)

    if state != "READY":
        result = {
            "state": "TIMEOUT_NO_WINDOW",
            "evaluation_started": False,
            "samples": sample_number,
            "output_dir": str(output_dir),
        }
        write_json(output_dir / "result.json", result)
        print(json.dumps(result, indent=2))
        return 0

    if args.dry_run:
        result = {
            "state": "READY",
            "evaluation_started": False,
            "would_launch": True,
            "samples": sample_number,
            "final_precheck": final_sample,
            "command": command,
            "output_dir": str(output_dir),
        }
        write_json(output_dir / "result.json", result)
        print(json.dumps(result, indent=2))
        return 0

    baseline = read_meminfo()
    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = "0"
    stdout_path = output_dir / "stdout.log"
    stderr_path = output_dir / "stderr.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command[2:],
            cwd=cvg_text_root,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        started = time.time()
        state, event = monitor_evaluation(
            process, output_dir, args.sample_interval, baseline["SwapTotal"] - baseline["SwapFree"]
        )
    result = {
        "state": state,
        "evaluation_started": True,
        "evaluation_pid": process.pid,
        "exit_code": process.wait(),
        "duration_seconds": time.time() - started,
        "event": event,
        "command": command,
        "output_dir": str(output_dir),
    }
    write_json(output_dir / "result.json", result)
    print(json.dumps(result, indent=2))
    return 0 if state == "EVALUATION_SUCCESS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"MONITORING_ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(3)
