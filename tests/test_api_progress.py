from __future__ import annotations

import asyncio
import json
from pathlib import Path
import threading
import time
import unittest

from fastapi.testclient import TestClient

from backend.atlas_api.main import create_app
from backend.atlas_api.progress import ProgressHub
from backend.atlas_api.settings import Settings
from src.tfg_phase0.f5_text_transform import TextTransformationError, TransformResult, TransformerMetadata


SETTINGS = Settings(Path("runtime.json"), Path("config/madrid.yaml"), "a" * 64, Path("clip.pt"), (), True)


def request(query_id: str, mode: str = "no_llm"):
    return {
        "schema_version": "1.0",
        "contract_version": "atlas-experimental-retrieval-request-v2",
        "query": {"query_id": query_id, "text": "Una plaza", "language": "es"},
        "gallery_id": "madrid-50m",
        "processing_mode": mode,
        "top_k": 10,
    }


class ProgressFakeRetriever:
    gallery_ids = ("madrid-50m",)

    def close(self):
        return None

    def gallery_count(self, gallery_id: str) -> int:
        return 253

    def retrieve_many(self, *, gallery_ids, query_id, text, language, k, progress_callback=None):
        if progress_callback is not None:
            progress_callback("text_encoding", "running", None, None)
            progress_callback("text_encoding", "completed", 1.25, None)
            progress_callback("ranking", "running", None, gallery_ids[0])
            progress_callback("ranking", "completed", 2.5, gallery_ids[0])
        rows = [
            {"rank": rank, "candidate_id": f"madrid-50m-{rank}", "latitude": 40.41, "longitude": -3.70, "cosine_similarity": 0.8-rank/100}
            for rank in range(1, k + 1)
        ]
        return {
            "model": {"name": "CLIP-L/14@336", "checkpoint_sha256": "d"*64},
            "timings_ms": {"text_encoding": 1.25, "ranking_by_gallery": {gallery_ids[0]: 2.5}, "total": 3.75},
            "retrievals": [{"gallery_id": gallery_ids[0], "visual_dataset_id": "visual", "embedding_dataset_id": "embedding", "gallery_count": 253, "requested_k": k, "effective_k": k, "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "results": rows}],
        }


class ProgressFakeTransformer:
    metadata = TransformerMetadata("fake", "Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218", "Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218", "a"*64, False)

    def transform(self, text, task, protected, config):
        return TransformResult("A mapped square.", "A mapped square.", 4.0)

    def close(self):
        return None


class ProgressFakeVisual:
    reserve_k = 10

    def apply(self, *, query_text, processing_variant, retrieval):
        baseline = retrieval["results"][:10]
        return {"status": "fallback_baseline", "source": "precomputed", "request_id": "visual-fake", "reason": "no_compatible_precomputed_result", "model": None, "policy_id": None, "baseline_results": baseline, "final_results": baseline, "evidence": []}

    def close(self):
        return None


def run_streamed_request(client: TestClient, app, body: dict):
    events: list[dict] = []
    errors: list[Exception] = []

    def consume() -> None:
        try:
            with client.stream("GET", f"/api/v1/progress/{body['query']['query_id']}") as response:
                if response.status_code != 200:
                    raise AssertionError(f"SSE HTTP {response.status_code}")
                for line in response.iter_lines():
                    if isinstance(line, bytes):
                        line = line.decode("utf-8")
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))
                        if events[-1].get("event_type") == "pipeline" and events[-1].get("state") in {"completed", "failed"}:
                            break
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3
    while app.state.progress_hub.subscriber_count(body["query"]["query_id"]) == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    if app.state.progress_hub.subscriber_count(body["query"]["query_id"]) == 0:
        raise AssertionError("SSE subscriber was not registered before POST")
    response = client.post("/api/v1/retrievals", json=body)
    thread.join(timeout=4)
    if thread.is_alive():
        raise AssertionError("SSE stream did not close after the terminal event")
    if errors:
        raise errors[0]
    if app.state.progress_hub.subscriber_count(body["query"]["query_id"]):
        raise AssertionError("SSE subscriber was not released after the terminal event")
    return response, events


class ProgressHubTests(unittest.TestCase):
    def test_hub_fans_out_and_releases_subscriptions(self):
        async def run():
            hub = ProgressHub()
            queue = await hub.subscribe("request-a")
            self.assertTrue(await hub.has_subscribers("request-a"))
            await hub.publish({"query_id": "request-a", "sequence": 1})
            self.assertEqual((await queue.get())["sequence"], 1)
            await hub.unsubscribe("request-a", queue)
            self.assertFalse(await hub.has_subscribers("request-a"))
        asyncio.run(run())

    def test_sse_events_report_llm_ct2l_precomputed_vlm_and_unavailable_dialogue(self):
        app = create_app(
            settings=SETTINGS,
            retriever_factory=lambda _settings: ProgressFakeRetriever(),
            transformer_factory=lambda _settings: ProgressFakeTransformer(),
            visual_factory=lambda _settings: ProgressFakeVisual(),
        )
        body = request("progress-with-llm", "with_llm")
        with TestClient(app) as client:
            response, events = run_streamed_request(client, app, body)

        self.assertEqual(response.status_code, 200)
        document = response.json()
        self.assertEqual(document["contract_version"], "atlas-experimental-retrieval-response-v3")
        self.assertEqual(document["retrievals"][0]["results"][0]["candidate_id"], "madrid-50m-1")
        self.assertNotIn("ground_truth", document)
        self.assertEqual([event["sequence"] for event in events], list(range(len(events))))
        stages = [event for event in events if event.get("event_type") == "stage"]
        llm = [event for event in stages if event["stage_id"] == "llm"]
        self.assertEqual([event["state"] for event in llm], ["running", "completed"])
        ct2l_subphases = [event["subphase"]["id"] for event in stages if event.get("subphase")]
        self.assertEqual(ct2l_subphases, ["text_encoding", "text_encoding", "ranking", "ranking"])
        self.assertTrue(any(event["stage_id"] == "vlm" and event.get("outcome") == "fallback_baseline" for event in stages))
        self.assertTrue(any(event["stage_id"] == "dialoguevpr" and event["state"] == "unavailable" for event in stages))
        self.assertEqual(events[-1]["event_type"], "pipeline")
        self.assertEqual(events[-1]["state"], "completed")
        self.assertFalse(any("ground_truth" in event or "query_text" in event for event in events))

    def test_no_llm_is_skipped_and_ct2l_failure_is_reported_without_changing_api_contract(self):
        class BrokenRetriever(ProgressFakeRetriever):
            def retrieve_many(self, *, gallery_ids, query_id, text, language, k, progress_callback=None):
                if progress_callback:
                    progress_callback("text_encoding", "running", None, None)
                raise RuntimeError("simulated test-only retrieval failure")

        app = create_app(
            settings=SETTINGS,
            retriever_factory=lambda _settings: BrokenRetriever(),
            transformer_factory=lambda _settings: None,
            visual_factory=lambda _settings: None,
        )
        body = request("progress-no-llm", "no_llm")
        with TestClient(app, raise_server_exceptions=False) as client:
            response, events = run_streamed_request(client, app, body)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["contract_version"], "atlas-api-error-v1")
        stages = [event for event in events if event.get("event_type") == "stage"]
        self.assertTrue(any(event["stage_id"] == "llm" and event["state"] == "skipped" for event in stages))
        self.assertTrue(any(event["stage_id"] == "crosstext2loc" and event["state"] == "failed" for event in stages))
        self.assertTrue(any(event["stage_id"] == "vlm" and event["state"] == "skipped" for event in stages))
        self.assertEqual(events[-1]["state"], "failed")

    def test_llm_rejection_reports_ct2l_as_skipped_and_not_unknown(self):
        class BrokenTransformer(ProgressFakeTransformer):
            def transform(self, text, task, protected, config):
                raise TextTransformationError("test-only transformer rejection")

        app = create_app(
            settings=SETTINGS,
            retriever_factory=lambda _settings: ProgressFakeRetriever(),
            transformer_factory=lambda _settings: BrokenTransformer(),
            visual_factory=lambda _settings: None,
        )
        body = request("progress-llm-rejected", "with_llm")
        with TestClient(app, raise_server_exceptions=False) as client:
            response, events = run_streamed_request(client, app, body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "TRANSFORMATION_FAILED")
        stages = [event for event in events if event.get("event_type") == "stage"]
        self.assertTrue(any(event["stage_id"] == "llm" and event["state"] == "failed" for event in stages))
        self.assertTrue(any(event["stage_id"] == "crosstext2loc" and event["state"] == "skipped" for event in stages))
        self.assertTrue(any(event["stage_id"] == "vlm" and event["state"] == "skipped" for event in stages))
        self.assertEqual(events[-1]["state"], "failed")

    def test_sync_endpoint_remains_usable_without_sse_subscribers(self):
        app = create_app(
            settings=SETTINGS,
            retriever_factory=lambda _settings: ProgressFakeRetriever(),
            transformer_factory=lambda _settings: None,
            visual_factory=lambda _settings: None,
        )
        body = request("progress-sync-only")
        with TestClient(app) as client:
            response = client.post("/api/v1/retrievals", json=body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["retrievals"][0]["effective_k"], 10)
        self.assertEqual(app.state.progress_hub.subscriber_count("progress-sync-only"), 0)

    def test_unavailable_llm_is_reported_without_starting_downstream_stages(self):
        app = create_app(
            settings=SETTINGS,
            retriever_factory=lambda _settings: ProgressFakeRetriever(),
            transformer_factory=lambda _settings: None,
            visual_factory=lambda _settings: None,
        )
        body = request("progress-llm-unavailable", "with_llm")
        with TestClient(app, raise_server_exceptions=False) as client:
            response, events = run_streamed_request(client, app, body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "LLM_NOT_READY")
        stages = [event for event in events if event.get("event_type") == "stage"]
        states = {event["stage_id"]: event["state"] for event in stages}
        self.assertEqual(states["llm"], "unavailable")
        self.assertEqual(states["crosstext2loc"], "skipped")
        self.assertEqual(states["vlm"], "skipped")
        self.assertEqual(states["dialoguevpr"], "unavailable")


if __name__ == "__main__":
    unittest.main()
