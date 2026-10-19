import importlib
from pathlib import Path
import sys
import threading
import time
import unittest

from fastapi.testclient import TestClient

from backend.atlas_api.main import create_app
from backend.atlas_api.settings import Settings
from src.tfg_phase0.crosstext2loc_runtime import GalleryNotLoadedError, InferenceError, RetrievalInputError
from src.tfg_phase0.validation import validate_document


class FakeRetriever:
    gallery_ids = ("madrid-50m", "madrid-25m")

    def __init__(self, *, block=False, error=None):
        self.calls = 0
        self.close_calls = 0
        self.block = block
        self.error = error
        self.started = threading.Event()
        self.release = threading.Event()

    def gallery_count(self, gallery_id):
        if gallery_id not in self.gallery_ids:
            raise GalleryNotLoadedError(gallery_id)
        return 253 if gallery_id == "madrid-50m" else 1115

    def retrieve_many(self, *, gallery_ids, query_id, text, language, k):
        self.calls += 1
        self.started.set()
        if self.block:
            self.release.wait(timeout=2)
        if self.error:
            raise self.error
        retrievals = []
        for gallery_id in gallery_ids:
            count = self.gallery_count(gallery_id)
            if k > count:
                raise RetrievalInputError("K demasiado grande")
            retrievals.append({"gallery_id": gallery_id, "visual_dataset_id": f"visual-{gallery_id}", "embedding_dataset_id": f"embedding-{gallery_id}", "gallery_count": count, "requested_k": k, "effective_k": k, "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "results": [{"rank": rank, "candidate_id": f"{gallery_id}-{rank}", "latitude": 40.41 + rank / 10000, "longitude": -3.70, "cosine_similarity": 0.5 - rank / 100} for rank in range(1, k + 1)]})
        return {"schema_version": "1.0", "contract_version": "crosstext2loc-retrieval-response-v1", "query": {"query_id": query_id, "text": text, "language": language}, "model": {"name": "CLIP-L/14@336", "checkpoint_sha256": "d" * 64}, "retrievals": retrievals, "timings_ms": {"text_encoding": 1.0, "ranking_by_gallery": {gallery_id: 0.1 for gallery_id in gallery_ids}, "total": 1.2}}

    def close(self):
        self.close_calls += 1


SETTINGS = Settings(Path("runtime.json"), Path("config/madrid.yaml"), "a" * 64, Path("clip.pt"), (), True)


def request(galleries=None, k=2):
    return {"schema_version": "1.0", "contract_version": "crosstext2loc-retrieval-request-v1", "query": {"query_id": "q1", "text": "Una plaza", "language": "es"}, "gallery_ids": galleries or ["madrid-50m"], "top_k": k}


class MvpApiTests(unittest.TestCase):
    def test_import_does_not_load_torch_or_clip(self):
        for name in ("torch", "clip"):
            sys.modules.pop(name, None)
        importlib.reload(importlib.import_module("backend.atlas_api.main"))
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("clip", sys.modules)

    def test_lifespan_loads_and_closes_once(self):
        fake = FakeRetriever()
        factory_calls = []
        app = create_app(settings=SETTINGS, retriever_factory=lambda settings: factory_calls.append(settings) or fake)
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/v1/health/live").status_code, 200)
            self.assertEqual(client.get("/api/v1/health/ready").json()["status"], "ready")
            client.post("/api/v1/retrievals", json=request())
            client.post("/api/v1/retrievals", json=request())
            self.assertEqual(fake.calls, 2)
            self.assertEqual(len(factory_calls), 1)
        self.assertEqual(fake.close_calls, 1)

    def test_capabilities_and_valid_multigallery_response(self):
        fake = FakeRetriever()
        app = create_app(settings=SETTINGS, retriever_factory=lambda settings: fake)
        with TestClient(app) as client:
            capabilities = client.get("/api/v1/capabilities").json()
            self.assertEqual(capabilities["galleries"], [{"gallery_id": "madrid-50m", "candidate_count": 253}, {"gallery_id": "madrid-25m", "candidate_count": 1115}])
            self.assertEqual(capabilities["search_area"], {"region_id": "madrid_pilot", "crs": "EPSG:4326", "bbox": {"north": 40.42, "south": 40.412, "east": -3.699, "west": -3.709}})
            response = client.post("/api/v1/retrievals", json=request(["madrid-25m", "madrid-50m"], 3))
            self.assertEqual(response.status_code, 200)
            document = response.json()
            validate_document(document, "crosstext2loc_retrieval_response")
            self.assertEqual([row["gallery_id"] for row in document["retrievals"]], ["madrid-25m", "madrid-50m"])
            self.assertNotIn("ground_truth", document)
            self.assertIn("X-Request-ID", response.headers)

    def test_invalid_body_unknown_gallery_and_oversized_k(self):
        fake = FakeRetriever()
        app = create_app(settings=SETTINGS, retriever_factory=lambda settings: fake)
        with TestClient(app, raise_server_exceptions=False) as client:
            invalid = request(); invalid["ground_truth"] = {}
            response = client.post("/api/v1/retrievals", json=invalid)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")
            unknown = client.post("/api/v1/retrievals", json=request(["missing"]))
            self.assertEqual(unknown.status_code, 404)
            too_large = client.post("/api/v1/retrievals", json=request(["madrid-50m"], 300))
            self.assertEqual(too_large.status_code, 422)

    def test_runtime_unavailable_inference_and_unexpected_errors_are_sanitized(self):
        app = create_app(settings=SETTINGS, retriever_factory=lambda settings: (_ for _ in ()).throw(RuntimeError("secret /path")))
        with self.assertRaises(RuntimeError):
            with TestClient(app, raise_server_exceptions=False):
                pass
        app = create_app(settings=SETTINGS, retriever_factory=lambda settings: FakeRetriever())
        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.retriever = None
            readiness = client.get("/api/v1/health/ready")
            self.assertEqual(readiness.status_code, 503)
            self.assertEqual(readiness.json()["error"]["code"], "RUNTIME_NOT_READY")
        for error, status, code in ((InferenceError("cuda details"), 503, "INFERENCE_FAILED"), (RuntimeError("secret traceback"), 500, "INTERNAL_ERROR")):
            app = create_app(settings=SETTINGS, retriever_factory=lambda settings, error=error: FakeRetriever(error=error))
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post("/api/v1/retrievals", json=request())
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["error"]["code"], code)
                self.assertNotIn("secret", response.text)

    def test_openapi_error_contract_and_cors_request_id_on_500(self):
        settings = Settings(SETTINGS.runtime_config, SETTINGS.region_config, SETTINGS.cvg_utils_sha256, SETTINGS.clip_weights_path, ("http://frontend.test",), True)
        app = create_app(settings=settings, retriever_factory=lambda value: FakeRetriever(error=RuntimeError("hidden")))
        with TestClient(app, raise_server_exceptions=False) as client:
            openapi = client.get("/openapi.json").json()
            responses = openapi["paths"]["/api/v1/retrievals"]["post"]["responses"]
            self.assertIn("503", responses)
            response = client.post("/api/v1/retrievals", json=request(), headers={"Origin": "http://frontend.test", "X-Request-ID": "cors-error"})
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.headers["X-Request-ID"], "cors-error")
            self.assertEqual(response.headers["access-control-allow-origin"], "http://frontend.test")
            self.assertIn("x-request-id", response.headers["access-control-expose-headers"].lower())

    def test_busy_request_is_rejected_and_liveness_remains_available(self):
        fake = FakeRetriever(block=True)
        app = create_app(settings=SETTINGS, retriever_factory=lambda settings: fake)
        with TestClient(app, raise_server_exceptions=False) as client:
            responses = []
            thread = threading.Thread(target=lambda: responses.append(client.post("/api/v1/retrievals", json=request())))
            thread.start()
            self.assertTrue(fake.started.wait(timeout=1))
            self.assertEqual(client.get("/api/v1/health/live").status_code, 200)
            busy = client.post("/api/v1/retrievals", json=request())
            self.assertEqual(busy.status_code, 503)
            self.assertEqual(busy.json()["error"]["code"], "RUNTIME_BUSY")
            fake.release.set()
            thread.join(timeout=2)
            self.assertEqual(responses[0].status_code, 200)


if __name__ == "__main__":
    unittest.main()
