import json
import tempfile
import unittest
from pathlib import Path

from src.tfg_phase0.append_jsonl_checkpoint import CheckpointError
from src.tfg_phase0.immutable_attempt_ledger import AttemptLedgerError, ImmutableAttemptLedger, execute_immutable_attempt


class ImmutableAttemptLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger = ImmutableAttemptLedger(self.root, plan_id="plan-v4", maximum_attempts=1)
        self.clock = iter(["start", "finish", "later", "last"])

    def tearDown(self):
        self.temporary.cleanup()

    def execute(self, generate, build=lambda raw, metadata: {"raw": raw, "metadata": metadata}):
        return execute_immutable_attempt(
            ledger=self.ledger,
            kind="scene",
            target_id="pair-1",
            cache_entry_id="cache-1",
            now=lambda: next(self.clock),
            generate_raw=generate,
            parse_and_build=build,
        )

    def paths(self):
        return self.ledger.paths(kind="scene", target_id="pair-1")

    def test_success_persists_attempt_raw_then_result(self):
        record = self.execute(lambda: ('{"ok":true}', {"generated_token_count": 4}))
        paths = self.paths()
        self.assertEqual(record["raw"], '{"ok":true}')
        self.assertTrue(paths.attempt.exists())
        self.assertTrue(paths.raw.exists())
        self.assertTrue(paths.result.exists())
        self.assertFalse(paths.failure.exists())
        self.assertEqual(json.loads(paths.raw.read_text())["raw_output"], '{"ok":true}')

    def test_invalid_json_preserves_raw_and_records_failure(self):
        with self.assertRaises(json.JSONDecodeError):
            self.execute(lambda: ('{"ok":True}', {"generated_token_count": 4}), lambda raw, metadata: json.loads(raw))
        paths = self.paths()
        self.assertTrue(paths.raw.exists())
        self.assertTrue(paths.failure.exists())
        self.assertFalse(paths.result.exists())

    def test_contract_and_semantic_failures_preserve_raw(self):
        for message in ("contrato", "semántica"):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary:
                ledger = ImmutableAttemptLedger(Path(temporary), plan_id="p", maximum_attempts=1)
                with self.assertRaisesRegex(ValueError, message):
                    execute_immutable_attempt(ledger=ledger,kind="scene",target_id="x",cache_entry_id="c",now=lambda:"now",generate_raw=lambda:("{}",{}),parse_and_build=lambda raw,metadata:(_ for _ in ()).throw(ValueError(message)))
                paths=ledger.paths(kind="scene",target_id="x")
                self.assertTrue(paths.raw.exists());self.assertTrue(paths.failure.exists());self.assertFalse(paths.result.exists())

    def test_generation_failure_has_attempt_and_no_raw(self):
        with self.assertRaisesRegex(RuntimeError, "generation"):
            self.execute(lambda: (_ for _ in ()).throw(RuntimeError("generation")))
        paths=self.paths();self.assertTrue(paths.attempt.exists());self.assertFalse(paths.raw.exists());self.assertTrue(paths.failure.exists())

    def test_interruption_between_generation_and_raw_is_charged_and_not_retried(self):
        original=self.ledger.preserve_raw
        self.ledger.preserve_raw=lambda *args,**kwargs:(_ for _ in ()).throw(OSError("raw persistence interrupted"))
        with self.assertRaisesRegex(OSError,"raw persistence"):
            self.execute(lambda:("generated",{"generated_token_count":1}))
        self.ledger.preserve_raw=original
        paths=self.paths();self.assertTrue(paths.attempt.exists());self.assertFalse(paths.raw.exists());self.assertTrue(paths.failure.exists())
        called=[]
        with self.assertRaises(AttemptLedgerError):self.execute(lambda:(called.append(True) or ("again",{})))
        self.assertEqual(called,[])

    def test_interruption_after_attempt_blocks_reexecution(self):
        self.ledger.begin(kind="scene",target_id="pair-1",cache_entry_id="cache-1",started_at_utc="start")
        called=[]
        with self.assertRaisesRegex(AttemptLedgerError,"interrumpido"):
            self.execute(lambda:(called.append(True) or ("{}",{})))
        self.assertEqual(called,[])

    def test_interruption_after_raw_resumes_cpu_without_generation(self):
        paths=self.ledger.begin(kind="scene",target_id="pair-1",cache_entry_id="cache-1",started_at_utc="start")
        self.ledger.preserve_raw(paths,raw_output="{}",metadata={"generated_token_count":1})
        called=[];record=self.execute(lambda:(called.append(True) or ("bad",{})))
        self.assertEqual(called,[]);self.assertEqual(record["raw"],"{}");self.assertTrue(paths.result.exists())

    def test_different_raw_for_same_attempt_is_rejected(self):
        paths=self.ledger.begin(kind="scene",target_id="pair-1",cache_entry_id="cache-1",started_at_utc="start")
        self.ledger.preserve_raw(paths,raw_output="first",metadata={})
        with self.assertRaises(CheckpointError):self.ledger.preserve_raw(paths,raw_output="second",metadata={})
        self.assertEqual(json.loads(paths.raw.read_text())["raw_output"],"first")

    def test_result_recovery_does_not_generate_or_duplicate(self):
        expected=self.execute(lambda:("{}",{}));called=[]
        recovered=self.execute(lambda:(called.append(True) or ("bad",{})))
        self.assertEqual(recovered,expected);self.assertEqual(called,[]);self.assertEqual(len(list(self.root.glob("attempts/*/attempt-*/result.json"))),1)

    def test_failure_never_retries_automatically(self):
        with self.assertRaises(ValueError):self.execute(lambda:("{}",{}),lambda raw,metadata:(_ for _ in ()).throw(ValueError()))
        called=[]
        with self.assertRaisesRegex(AttemptLedgerError,"retry no autorizado"):self.execute(lambda:(called.append(True) or ("{}",{})))
        self.assertEqual(called,[])

    def test_terminal_states_cannot_contradict(self):
        self.execute(lambda:("{}",{}));paths=self.paths()
        with self.assertRaisesRegex(AttemptLedgerError,"resultado terminal"):
            self.ledger.record_failure(paths,stage="late",error=RuntimeError(),finished_at_utc="later")

    def test_immutable_file_rejects_different_content(self):
        paths=self.ledger.begin(kind="scene",target_id="pair-1",cache_entry_id="cache-1",started_at_utc="start")
        with self.assertRaises(CheckpointError):
            self.ledger.begin(kind="scene",target_id="pair-1",cache_entry_id="different",started_at_utc="other")
        self.assertEqual(json.loads(paths.attempt.read_text())["cache_entry_id"],"cache-1")

    def test_budget_counts_attempts_not_results(self):
        self.ledger.begin(kind="scene",target_id="pair-1",cache_entry_id="cache-1",started_at_utc="start")
        with self.assertRaisesRegex(AttemptLedgerError,"presupuesto"):
            self.ledger.begin(kind="scene",target_id="pair-2",cache_entry_id="cache-2",started_at_utc="start")

    def test_checkpoint_failure_cannot_erase_terminal_result(self):
        expected=self.execute(lambda:("{}",{}));paths=self.paths()
        with self.assertRaisesRegex(OSError,"checkpoint"):raise OSError("checkpoint")
        called=[];recovered=self.execute(lambda:(called.append(True) or ("bad",{})))
        self.assertEqual(recovered,expected);self.assertEqual(called,[]);self.assertTrue(paths.result.exists())


if __name__ == "__main__":
    unittest.main()
