#!/usr/bin/env python3
"""Freeze and mark one application session incompatible with a superseding runtime."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import uuid


SESSION = re.compile(r"^freetext-application-[0-9a-f-]{36}$")


def canonical(document) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, document) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = canonical(document) + b"\n"
    with temporary.open("xb") as stream:
        stream.write(payload);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY);os.fsync(descriptor);os.close(descriptor)

def verify_archive(archive:Path,expected_session_sha:str,expected_runtime:str):
    manifest=json.loads((archive/"archive-manifest.json").read_text())
    manifest_payload={key:value for key,value in manifest.items() if key!="manifest_sha256"}
    if hashlib.sha256(canonical(manifest_payload)).hexdigest()!=manifest.get("manifest_sha256") or manifest.get("source_session_sha256")!=expected_session_sha or manifest.get("superseding_runtime")!=expected_runtime:raise RuntimeError("manifest de archivo divergente")
    expected_files={row["path"] for row in manifest.get("files",[])}
    actual_files={path.relative_to(archive).as_posix() for path in archive.rglob("*") if path.is_file()}-{"archive-manifest.json"}
    if actual_files!=expected_files:raise RuntimeError("inventario archivado divergente")
    for row in manifest.get("files",[]):
        path=archive/row["path"]
        if not path.is_file() or path.stat().st_size!=row["size_bytes"] or digest_file(path)!=row["sha256"]:raise RuntimeError("archivo archivado divergente")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--expected-session-sha256", required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--superseding-runtime", required=True)
    args = parser.parse_args()
    if not SESSION.fullmatch(args.session_id): parser.error("session_id inválido")
    args.archive_root.mkdir(parents=True, exist_ok=True)
    lock_path = args.state_root / "freetext-application-supersession.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        profile_lock=(args.state_root/"freetext-application-profile.lock").open("a+b")
        fcntl.flock(profile_lock,fcntl.LOCK_EX)
        source = args.state_root / "sessions" / args.session_id
        transition_path = source / ".transition.lock"
        transition = transition_path.open("a+b")
        fcntl.flock(transition, fcntl.LOCK_EX)
        session_path = source / "session.json"
        document = json.loads(session_path.read_text(encoding="utf-8"))
        archive = args.archive_root / args.session_id
        if document.get("status") == "unknown" and archive.exists():
            manifest=verify_archive(archive,args.expected_session_sha256,args.superseding_runtime)
            current_payload={key:value for key,value in document.items() if key!="session_sha256"}
            with sqlite3.connect(args.state_root/"freetext-application.sqlite3") as connection:current_ledger=connection.execute("SELECT status FROM sessions WHERE session_id=?",(args.session_id,)).fetchone()
            if hashlib.sha256(canonical(current_payload)).hexdigest()==document.get("session_sha256") and current_ledger and current_ledger[0]=="unknown" and document.get("runtime_supersession",{}).get("archived_manifest_sha256")==manifest.get("manifest_sha256") and manifest.get("source_session_sha256")==args.expected_session_sha256 and manifest.get("superseding_runtime")==args.superseding_runtime:
                print(json.dumps({"session_id":args.session_id,"status":"unknown","archive":str(archive),"manifest_sha256":manifest["manifest_sha256"],"new_session_sha256":document["session_sha256"],"idempotent":True},sort_keys=True));return 0
            raise RuntimeError("supersession existente divergente")
        payload = {key: value for key, value in document.items() if key != "session_sha256"}
        computed = hashlib.sha256(canonical(payload)).hexdigest()
        if document.get("session_id") != args.session_id or document.get("session_sha256") != args.expected_session_sha256 or computed != args.expected_session_sha256 or document.get("status") != "waiting_user":
            raise RuntimeError("sesión divergente; no se archiva ni modifica")
        ledger = args.state_root / "freetext-application.sqlite3"
        with sqlite3.connect(ledger) as connection:
            row = connection.execute("SELECT profile_id,status FROM sessions WHERE session_id=?", (args.session_id,)).fetchone()
        if row is None or row[1] not in {"waiting_user","unknown"} or row[0] != document["profile_binding"]["profile_id"]:
            raise RuntimeError("ledger divergente")
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if archive.exists():
            manifest=verify_archive(archive,args.expected_session_sha256,args.superseding_runtime)
        else:
            temporary = args.archive_root / f".{args.session_id}.{uuid.uuid4().hex}.tmp"
            try:
                shutil.copytree(source, temporary)
                files = [{"path": path.relative_to(temporary).as_posix(), "sha256": digest_file(path), "size_bytes": path.stat().st_size} for path in sorted(candidate for candidate in temporary.rglob("*") if candidate.is_file())]
                manifest = {"schema_version":"1.0","contract_version":"atlas-freetext-application-session-supersession-archive-v1","session_id":args.session_id,"archived_at_utc":now,"source_session_sha256":args.expected_session_sha256,"source_status":"waiting_user","source_executor_identity_sha256":document["profile_binding"]["executor_identity_sha256"],"superseding_runtime":args.superseding_runtime,"files":files}
                manifest["manifest_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
                atomic(temporary / "archive-manifest.json", manifest)
                if digest_file(temporary / "session.json") != digest_file(session_path):
                    raise RuntimeError("copia de sesión divergente")
                os.replace(temporary, archive)
                descriptor = os.open(args.archive_root, os.O_RDONLY);os.fsync(descriptor);os.close(descriptor)
            finally:
                if temporary.exists():shutil.rmtree(temporary)
        with sqlite3.connect(ledger) as connection:
            connection.execute("PRAGMA synchronous=FULL");connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute("UPDATE sessions SET status='unknown' WHERE session_id=? AND status IN ('waiting_user','unknown')", (args.session_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("ledger cambió durante supersession")
            connection.commit()
        document["status"] = "unknown"
        document["stop_reason"] = "runtime_identity_superseded_no_retry"
        document["runtime_supersession"] = {"archived_manifest_sha256":manifest["manifest_sha256"],"previous_executor_identity_sha256":manifest["source_executor_identity_sha256"],"superseding_runtime":args.superseding_runtime,"timestamp":now}
        document["events"].append({"session_id":args.session_id,"event_id":str(len(document["events"])+1),"stage":"runtime_supersession","status":"unknown","timestamp":now,"message":"Sesión archivada e incompatible con el nuevo runtime; no completada, no reintentada.","error":None})
        document["updated_at"] = now
        payload = {key:value for key,value in document.items() if key != "session_sha256"}
        document["session_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
        atomic(session_path, document)
        transition.close()
    print(json.dumps({"session_id":args.session_id,"status":"unknown","archive":str(archive),"manifest_sha256":manifest["manifest_sha256"],"new_session_sha256":document["session_sha256"]},sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
