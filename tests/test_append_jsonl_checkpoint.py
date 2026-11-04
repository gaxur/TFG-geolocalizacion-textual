import json
import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path

from src.tfg_phase0.append_jsonl_checkpoint import CheckpointError, PlannedJob, checkpoint_writer_lock, finalize_json_atomic, run_resumable


def job(index,execute=True):
    key=("H",f"c{index}",f"i{index}",f"k{index}")
    return PlannedJob(key,{"index":index,"mode":"model" if execute else "policy"},None,execute)


def record(j,verdict="supported"):
    return {"query_id":j.key[0],"candidate_id":j.key[1],"image_id":j.key[2],"claim_id":j.key[3],"status":"valid","verdict":verdict}


def hold_lock(path, ready, release):
    with checkpoint_writer_lock(Path(path)):
        ready.set();release.wait(timeout=5)


class AppendCheckpointTests(unittest.TestCase):
    def test_resume_calls_only_suffix_and_preserves_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"run.jsonl";jobs=[job(0),job(1,False),job(2)];calls=[]
            first=run_resumable(checkpoint_path=path,provenance={"x":1},jobs=jobs[:2],execute=lambda j:(calls.append(j.key) or record(j)),policy_result=lambda j:record(j,"unverifiable"))
            self.assertEqual(len(first),2)
            with self.assertRaises(CheckpointError):run_resumable(checkpoint_path=path,provenance={"x":1},jobs=jobs,execute=lambda j:record(j),policy_result=lambda j:record(j))

    def test_interruption_resumes_failed_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"run.jsonl";jobs=[job(0),job(1),job(2)];calls=[]
            def fail(j):
                calls.append(j.key)
                if j.key==jobs[1].key:raise RuntimeError("stop")
                return record(j)
            with self.assertRaises(RuntimeError):run_resumable(checkpoint_path=path,provenance={"x":1},jobs=jobs,execute=fail,policy_result=lambda j:record(j))
            calls.clear();rows=run_resumable(checkpoint_path=path,provenance={"x":1},jobs=jobs,execute=lambda j:(calls.append(j.key) or record(j)),policy_result=lambda j:record(j))
            self.assertEqual(calls,[jobs[1].key,jobs[2].key]);self.assertEqual([r["candidate_id"] for r in rows],["c0","c1","c2"])

    def test_duplicate_jobs_and_provenance_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"run.jsonl";j=job(0)
            with self.assertRaises(CheckpointError):run_resumable(checkpoint_path=path,provenance={},jobs=[j,j],execute=lambda x:record(x),policy_result=lambda x:record(x))
            run_resumable(checkpoint_path=path,provenance={"x":1},jobs=[j],execute=lambda x:record(x),policy_result=lambda x:record(x))
            with self.assertRaises(CheckpointError):run_resumable(checkpoint_path=path,provenance={"x":2},jobs=[j],execute=lambda x:record(x),policy_result=lambda x:record(x))

    def test_truncated_tail_is_repaired(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"run.jsonl";jobs=[job(0),job(1)]
            run_resumable(checkpoint_path=path,provenance={},jobs=jobs[:1],execute=lambda j:record(j),policy_result=lambda j:record(j));path.write_bytes(path.read_bytes()+b'{"broken"')
            with self.assertRaises(CheckpointError):run_resumable(checkpoint_path=path,provenance={},jobs=jobs,execute=lambda j:record(j),policy_result=lambda j:record(j))

    def test_atomic_finalize_is_idempotent_and_rejects_difference(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"out.json";finalize_json_atomic(output_path=path,document={"a":1});finalize_json_atomic(output_path=path,document={"a":1})
            self.assertEqual(json.loads(path.read_text()),{"a":1})
            with self.assertRaises(CheckpointError):finalize_json_atomic(output_path=path,document={"a":2})

    def test_progress_reports_deterministic_eta(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"run.jsonl";jobs=[job(0),job(1,False),job(2)];current=[0.0];snapshots=[]
            def execute(j):current[0]+=2;return record(j)
            rows=run_resumable(checkpoint_path=path,provenance={},jobs=jobs,execute=execute,policy_result=lambda j:record(j,"unverifiable"),on_progress=snapshots.append,clock=lambda:current[0])
            self.assertEqual(len(rows),3);self.assertIsNone(snapshots[0].eta_seconds);self.assertEqual(snapshots[-1].remaining,0);self.assertEqual(snapshots[-1].eta_seconds,0.0)

    def test_second_process_cannot_write_same_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"run.jsonl";ready=multiprocessing.Event();release=multiprocessing.Event();process=multiprocessing.Process(target=hold_lock,args=(str(path),ready,release));process.start()
            self.assertTrue(ready.wait(timeout=2))
            with self.assertRaisesRegex(CheckpointError,"escritor activo"):
                run_resumable(checkpoint_path=path,provenance={},jobs=[job(0)],execute=lambda j:record(j),policy_result=lambda j:record(j))
            release.set();process.join(timeout=2);self.assertEqual(process.exitcode,0)

    def test_lock_releases_after_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"run.jsonl"
            with self.assertRaises(RuntimeError):
                run_resumable(checkpoint_path=path,provenance={},jobs=[job(0)],execute=lambda j:(_ for _ in ()).throw(RuntimeError("stop")),policy_result=lambda j:record(j))
            rows=run_resumable(checkpoint_path=path,provenance={},jobs=[job(0)],execute=lambda j:record(j),policy_result=lambda j:record(j))
            self.assertEqual(len(rows),1)


if __name__=="__main__":unittest.main()
