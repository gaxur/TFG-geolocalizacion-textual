from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
import inspect

from backend.atlas_api.ephemeral_retrieval import (
    EphemeralCrossText2LocRetriever,
    EphemeralProviderError,
    EphemeralQwenTransformer,
    StableSwapV2Gate,
)
from backend.atlas_api.settings import Settings
from src.tfg_phase0.f5_text_transform import GenerationConfig


class PassingGate:
    def __init__(self):
        self.active = 0
        self.maximum = 0
        self.calls = []
        self.lock = threading.Lock()

    @contextmanager
    def acquire(self, workspace, label):
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            self.calls.append(label)
            try:
                yield
            finally:
                self.active -= 1


def make_settings(root: Path, qwen: Path | None = None) -> Settings:
    config = root / "runtime.json"
    selection_25 = root / "selection-25.json"
    selection_50 = root / "selection-50.json"
    selection_25.write_text(json.dumps({"candidate_count": 1115}))
    selection_50.write_text(json.dumps({"candidate_count": 253}))
    config.write_text(json.dumps({"galleries": {
        "madrid-25m": {"selection": str(selection_25)},
        "madrid-50m": {"selection": str(selection_50)},
    }}))
    return Settings(config, root / "region.json", "a" * 64, str(root / "clip.pt"), (), qwen_model_path=qwen)


class FakeRunner:
    def __init__(self, *, fail=False, delay=0.0):
        self.fail = fail
        self.delay = delay
        self.commands = []

    def __call__(self, command, timeout):
        self.commands.append((list(command), timeout))
        time.sleep(self.delay)
        output = Path(command[command.index("--output") + 1])
        request = json.loads(Path(command[command.index("--request") + 1]).read_text())
        if self.fail:
            return subprocess.CompletedProcess(command, 7, "secret stdout", "/private/model/path secret")
        if command[2] == "retrieve":
            ids = request["gallery_ids"]
            rows = [{"rank": 1, "candidate_id": "c1", "latitude": 40.4, "longitude": -3.7, "cosine_similarity": 0.8}]
            document = {
                "schema_version": "1.0", "contract_version": "crosstext2loc-retrieval-response-v1",
                "query": {"query_id": request["query_id"], "text": request["text"], "language": request["language"]},
                "model": {"name": "CLIP-L/14@336", "checkpoint_sha256": "d" * 64},
                "retrievals": [{"gallery_id": gallery, "visual_dataset_id": "v", "embedding_dataset_id": "e", "gallery_count": 1115 if gallery.endswith("25m") else 253, "requested_k": 1, "effective_k": 1, "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "results": rows} for gallery in ids],
                "timings_ms": {"text_encoding": 1.0, "ranking_by_gallery": {gallery: 2.0 for gallery in ids}, "total": 3.0},
            }
        else:
            document = {
                "result": {"text": "A square.", "raw_output": "A square.", "duration_ms": 4.0},
                "metadata": {"adapter": "transformers-qwen3-v1", "model_id": "Qwen/Qwen3-8B", "revision": "r", "tokenizer_id": "Qwen/Qwen3-8B", "tokenizer_revision": "r", "artifact_manifest_sha256": "b" * 64, "real_model_inference": True},
                "resource_usage": {"model_load_ms": 1.0},
            }
        output.write_text(json.dumps(document))
        return subprocess.CompletedProcess(command, 0, "", "")


class EphemeralProviderTests(unittest.TestCase):
    def test_retriever_is_lightweight_and_preserves_multigallery_contract_and_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = FakeRunner()
            provider = EphemeralCrossText2LocRetriever(make_settings(root), gate=PassingGate(), runner=runner)
            events = []
            self.assertEqual(provider.gallery_ids, ("madrid-25m", "madrid-50m"))
            self.assertEqual(provider.gallery_count("madrid-25m"), 1115)
            response = provider.retrieve_many(gallery_ids=("madrid-25m", "madrid-50m"), query_id="q", text="plaza", language="es", k=1, progress_callback=lambda *row: events.append(row))
            self.assertEqual([row["gallery_id"] for row in response["retrievals"]], ["madrid-25m", "madrid-50m"])
            self.assertEqual(events[0][:2], ("text_encoding", "running"))
            self.assertFalse(any("torch" in part or "transformers" in part for part in runner.commands[0][0]))

    def test_qwen_implements_transformer_interface_without_loading_at_construction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "qwen"
            model.mkdir()
            runner = FakeRunner()
            provider = EphemeralQwenTransformer(model, gate=PassingGate(), revision="r", runner=runner)
            self.assertEqual(provider.resource_usage, {"ephemeral": True, "model_resident": False})
            result = provider.transform("Una plaza", "translate_en_cartographic", (), GenerationConfig())
            self.assertEqual(result.text, "A square.")
            self.assertEqual(provider.metadata.artifact_manifest_sha256, "b" * 64)
            self.assertFalse(provider.resource_usage["model_resident"])

    def test_shared_gate_serializes_qwen_and_ct2l_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "qwen"
            model.mkdir()
            gate = PassingGate()
            runner = FakeRunner(delay=0.03)
            retriever = EphemeralCrossText2LocRetriever(make_settings(root, model), gate=gate, runner=runner)
            transformer = EphemeralQwenTransformer(model, gate=gate, revision="r", runner=runner)
            threads = [
                threading.Thread(target=lambda: retriever.retrieve_many(gallery_ids=("madrid-50m",), query_id="q", text="x", language="es", k=1)),
                threading.Thread(target=lambda: transformer.transform("x", "translate_en_cartographic", (), GenerationConfig())),
            ]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(gate.maximum, 1)
            self.assertCountEqual(gate.calls, ["retrieve", "transform"])

    def test_child_failure_is_sanitized_and_has_no_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = FakeRunner(fail=True)
            provider = EphemeralCrossText2LocRetriever(make_settings(root), gate=PassingGate(), runner=runner)
            with self.assertRaisesRegex(EphemeralProviderError, "ephemeral retrieve failed") as raised:
                provider.retrieve_many(gallery_ids=("madrid-50m",), query_id="q", text="x", language="es", k=1)
            self.assertNotIn("private", str(raised.exception))
            self.assertEqual(len(runner.commands), 1)

    def test_real_gate_can_be_exercised_with_a_static_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            gate = StableSwapV2Gate(probe=lambda: {"available": 41 * 1024**3, "gpu": [], "ollama": []}, lock_path=workspace / "lock")
            with gate.acquire(workspace, "fixture"):
                pass
            self.assertTrue(json.loads((workspace / "resource-gate.json").read_text())["passed"])

    def test_worker_sets_parent_death_signal_before_loading_models(self):
        source=(Path(__file__).resolve().parents[1]/'scripts/run_mvp_ephemeral_retrieval_worker.py').read_text();self.assertIn('prctl(1, 9',source);self.assertLess(source.index('_die_with_parent()\n    parser'),source.index('request = json.loads'))

    def test_real_runner_sets_parent_death_signal_before_exec(self):
        from backend.atlas_api import ephemeral_retrieval
        source=inspect.getsource(ephemeral_retrieval._run_child);self.assertIn('preexec_fn=parent_death_signal',source);worker=(Path(__file__).resolve().parents[1]/'scripts/run_mvp_ephemeral_retrieval_worker.py').read_text();self.assertIn('_die_with_parent()',worker);self.assertIn('prctl(1, 9',worker)


if __name__ == "__main__":
    unittest.main()
