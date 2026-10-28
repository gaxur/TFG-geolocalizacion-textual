#!/usr/bin/env python3
"""Monitor externo para ejecutar una evaluación sin alterar CVG-Text."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

MIN_AVAILABLE_BYTES = 8 * 1024**3
MAX_SWAP_GROWTH_BYTES = 2 * 1024**3
MAX_GPU_UTILIZATION_PERCENT = 95
MAX_GPU_UTILIZATION_SAMPLES = 30
SERVICE_SPECS = {
    3157568: "serve_embeddings.py",
    3158341: "VLLM::EngineCore",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--dry-run-seconds", type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def read_meminfo() -> dict[str, int]:
    values = {}
    with Path("/proc/meminfo").open(encoding="ascii") as file:
        for line in file:
            key, raw = line.split(":", 1)
            fields = raw.split()
            if fields and fields[0].isdigit():
                multiplier = 1024 if len(fields) > 1 and fields[1] == "kB" else 1
                values[key] = int(fields[0]) * multiplier
    required = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    missing = required - values.keys()
    if missing:
        raise RuntimeError(f"Faltan campos en /proc/meminfo: {sorted(missing)}")
    return {
        "ram_total_bytes": values["MemTotal"],
        "ram_used_bytes": values["MemTotal"] - values["MemAvailable"],
        "ram_available_bytes": values["MemAvailable"],
        "swap_total_bytes": values["SwapTotal"],
        "swap_used_bytes": values["SwapTotal"] - values["SwapFree"],
        "swap_available_bytes": values["SwapFree"],
    }


def process_state(pid: int, expected_command: str) -> dict[str, object]:
    proc = Path("/proc") / str(pid)
    if not proc.exists():
        return {"pid": pid, "active": False, "expected_command": expected_command}
    command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
    return {
        "pid": pid,
        "active": expected_command in command,
        "expected_command": expected_command,
        "command": command,
    }


def gpu_state() -> dict[str, object]:
    query = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,utilization.memory,power.draw,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().splitlines()
    if len(query) != 1:
        raise RuntimeError(f"Se esperaba una GPU y se obtuvieron {len(query)} filas")
    fields = [field.strip() for field in query[0].split(",")]
    if len(fields) != 4:
        raise RuntimeError(f"Salida inesperada de nvidia-smi: {query[0]!r}")
    gpu, memory, power, temperature = fields
    return {
        "gpu_utilization_percent": int(gpu),
        "gpu_memory_utilization_percent": int(memory),
        "power_watts": float(power),
        "temperature_celsius": int(temperature),
    }


def process_usage(pid: int | None) -> dict[str, object] | None:
    if pid is None or not (Path("/proc") / str(pid)).exists():
        return None
    output = subprocess.run(
        ["ps", "-p", str(pid), "-o", "pid=,%cpu=,rss=,stat=,etime="],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split(maxsplit=4)
    if len(output) != 5:
        raise RuntimeError(f"Salida inesperada de ps para PID {pid}: {output!r}")
    return {
        "pid": int(output[0]),
        "cpu_percent": float(output[1]),
        "rss_bytes": int(output[2]) * 1024,
        "state": output[3],
        "elapsed": output[4],
    }


def sample(evaluation_pid: int | None) -> dict[str, object]:
    result: dict[str, object] = {
        "timestamp": datetime.now().astimezone().isoformat(),
        **read_meminfo(),
        **gpu_state(),
        "load_average": list(os.getloadavg()),
        "services": [process_state(pid, name) for pid, name in SERVICE_SPECS.items()],
    }
    result["evaluation_process"] = process_usage(evaluation_pid)
    return result


def abort_reason(current: dict[str, object], baseline_swap: int, high_gpu_samples: int):
    for service in current["services"]:
        if not service["active"]:
            return {
                "category": "SERVICE_FAILURE",
                "metric": "service_active",
                "value": service,
                "threshold": True,
                "reason": "Un servicio root esperado no esta activo o no coincide su comando.",
            }
    if current["ram_available_bytes"] < MIN_AVAILABLE_BYTES:
        return {
            "category": "RESOURCE_PRESSURE",
            "metric": "ram_available_bytes",
            "value": current["ram_available_bytes"],
            "threshold": MIN_AVAILABLE_BYTES,
            "reason": "La RAM disponible esta por debajo del umbral de seguridad.",
        }
    swap_growth = current["swap_used_bytes"] - baseline_swap
    if swap_growth > MAX_SWAP_GROWTH_BYTES:
        return {
            "category": "RESOURCE_PRESSURE",
            "metric": "swap_growth_bytes",
            "value": swap_growth,
            "threshold": MAX_SWAP_GROWTH_BYTES,
            "reason": "El crecimiento de swap supera el umbral de seguridad.",
        }
    if high_gpu_samples >= MAX_GPU_UTILIZATION_SAMPLES:
        return {
            "category": "RESOURCE_PRESSURE",
            "metric": "consecutive_gpu_utilization_samples",
            "value": high_gpu_samples,
            "threshold": MAX_GPU_UTILIZATION_SAMPLES,
            "reason": (
                f"La GPU lleva muestras consecutivas con utilizacion >= "
                f"{MAX_GPU_UTILIZATION_PERCENT} %."
            ),
        }
    return None


def main() -> int:
    args = parse_args()
    if args.interval <= 0:
        raise ValueError("--interval debe ser positivo")
    if args.dry_run_seconds is None and not args.command:
        raise ValueError("Falta el comando que se debe monitorizar")
    if args.dry_run_seconds is not None and args.command:
        raise ValueError("El dry-run no acepta un comando")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / "resources.jsonl"
    events_path = output_dir / "monitor-events.jsonl"
    stdout_path = output_dir / "zeroshot.stdout.log"
    stderr_path = output_dir / "zeroshot.stderr.log"
    metadata_path = output_dir / "run.json"

    try:
        initial = sample(None)
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as error:
        event = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "category": "MONITORING_ERROR",
            "reason": str(error),
        }
        events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
        print(json.dumps(event, indent=2), file=sys.stderr)
        return 2

    baseline_swap = initial["swap_used_bytes"]
    started = time.time()
    process = None
    abort = abort_reason(initial, baseline_swap, high_gpu_samples=0)
    high_gpu_samples = 0
    exit_code = 0

    if abort:
        abort["timestamp"] = initial["timestamp"]
        with events_path.open("a", encoding="utf-8") as events_file:
            events_file.write(json.dumps(abort) + "\n")
        metadata = {
            "exit_code": 3,
            "monitor_abort": abort,
            "duration_seconds": time.time() - started,
            "evaluation_pid": None,
            "command": None,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(metadata, indent=2), file=sys.stderr)
        return 3

    with samples_path.open("a", encoding="utf-8") as samples_file:
        samples_file.write(json.dumps(initial) + "\n")
        samples_file.flush()
        if args.dry_run_seconds is None:
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(
                    command,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                )
                while process.poll() is None:
                    time.sleep(args.interval)
                    try:
                        current = sample(process.pid)
                    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as error:
                        abort = {
                            "timestamp": datetime.now().astimezone().isoformat(),
                            "category": "MONITORING_ERROR",
                            "reason": str(error),
                        }
                        os.killpg(process.pid, signal.SIGTERM)
                        break
                    high_gpu_samples = (
                        high_gpu_samples + 1
                        if current["gpu_utilization_percent"]
                        >= MAX_GPU_UTILIZATION_PERCENT
                        else 0
                    )
                    samples_file.write(json.dumps(current) + "\n")
                    samples_file.flush()
                    abort = abort_reason(current, baseline_swap, high_gpu_samples)
                    if abort:
                        abort["timestamp"] = current["timestamp"]
                        os.killpg(process.pid, signal.SIGTERM)
                        break
                exit_code = process.wait()
        else:
            deadline = started + args.dry_run_seconds
            while time.time() < deadline:
                time.sleep(args.interval)
                try:
                    current = sample(None)
                except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as error:
                    abort = {
                        "timestamp": datetime.now().astimezone().isoformat(),
                        "category": "MONITORING_ERROR",
                        "reason": str(error),
                    }
                    exit_code = 2
                    break
                high_gpu_samples = (
                    high_gpu_samples + 1
                    if current["gpu_utilization_percent"] >= MAX_GPU_UTILIZATION_PERCENT
                    else 0
                )
                samples_file.write(json.dumps(current) + "\n")
                samples_file.flush()
                abort = abort_reason(current, baseline_swap, high_gpu_samples)
                if abort:
                    abort["timestamp"] = current["timestamp"]
                    exit_code = 3
                    break

    if abort:
        with events_path.open("a", encoding="utf-8") as events_file:
            events_file.write(json.dumps(abort) + "\n")
    metadata = {
        "exit_code": exit_code,
        "monitor_abort": abort,
        "duration_seconds": time.time() - started,
        "evaluation_pid": process.pid if process else None,
        "command": args.command if process else None,
        "thresholds": {
            "minimum_ram_available_bytes": MIN_AVAILABLE_BYTES,
            "maximum_swap_growth_bytes": MAX_SWAP_GROWTH_BYTES,
            "maximum_gpu_utilization_percent": MAX_GPU_UTILIZATION_PERCENT,
            "maximum_consecutive_gpu_samples": MAX_GPU_UTILIZATION_SAMPLES,
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"MONITORING_ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(2)
