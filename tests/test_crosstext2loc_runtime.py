import unittest
import threading
import time
from types import SimpleNamespace

import numpy as np

from src.tfg_phase0.crosstext2loc_runtime import (
    CrossText2LocRetriever,
    GalleryNotLoadedError,
    ModelCompatibilityError,
    ResidentGallery,
    RetrievalInputError,
    RuntimeClosedError,
    validate_retrieval_request,
)
from src.tfg_phase0.f4_retrieval import exhaustive_rank
from src.tfg_phase0.validation import validate_document


CHECKPOINT = "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d"


class FakeEncoder:
    model_name = "CLIP-L/14@336"
    checkpoint_sha256 = CHECKPOINT

    def __init__(self, vector=None, fail=False):
        self.vector = np.asarray(vector if vector is not None else [1.0] + [0.0] * 767, dtype=np.float32)
        self.fail = fail
        self.encode_count = 0
        self.closed = False

    def encode_text(self, text):
        self.encode_count += 1
        if self.fail:
            raise RuntimeError("encoder failure")
        return self.vector

    def close(self):
        self.closed = True


class BlockingEncoder(FakeEncoder):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def encode_text(self, text):
        self.started.set()
        self.release.wait(timeout=2)
        return super().encode_text(text)


def gallery(gallery_id, count, checkpoint=CHECKPOINT):
    matrix = np.zeros((count, 768), dtype="<f4")
    matrix[:, 0] = 1.0
    ids = tuple(f"{gallery_id}-candidate-{index:04d}" for index in range(count))
    candidates = tuple(SimpleNamespace(candidate_id=candidate_id, latitude=40.4 + index / 100000, longitude=-3.7) for index, candidate_id in enumerate(ids))
    catalog = SimpleNamespace(candidates=candidates)
    embedding = {
        "embedding_dataset_id": f"f4-madrid-embeddings-sha256-{'1' if count == 3 else '2'}" + "0" * 63,
        "checkpoint": {"sha256": checkpoint},
        "model": {"name": "CLIP-L/14@336", "architecture": "ViT-L/14@336px", "text_context_length": 300},
        "embedding": {"count": count},
    }
    visual = {"visual_dataset_id": f"visual-{gallery_id}"}
    return ResidentGallery(gallery_id, catalog, visual, embedding, matrix, ids)


class CrossText2LocRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.encoder = FakeEncoder()
        self.small = gallery("madrid-50m", 3)
        self.large = gallery("madrid-25m", 5)
        self.runtime = CrossText2LocRetriever(self.encoder, [self.small, self.large])

    def tearDown(self):
        self.runtime.close()

    def test_multigallery_encodes_once_and_matches_exhaustive_rank(self):
        response = self.runtime.retrieve_many(gallery_ids=["madrid-50m", "madrid-25m"], query_id="q1", text="description", language="en", k=3)
        self.assertEqual(self.encoder.encode_count, 1)
        self.assertEqual(len(response["retrievals"]), 2)
        self.assertEqual(response["retrievals"][0]["requested_k"], 3)
        self.assertEqual(response["retrievals"][0]["effective_k"], 3)
        self.assertEqual(response["retrievals"][0]["tie_break"], "candidate_id_ascending")
        expected = exhaustive_rank(self.small.matrix, self.small.candidate_ids, self.encoder.vector, 3)
        actual = [(row["candidate_id"], row["cosine_similarity"]) for row in response["retrievals"][0]["results"]]
        self.assertEqual(actual, expected)
        self.assertEqual([row["candidate_id"] for row in response["retrievals"][0]["results"]], sorted(self.small.candidate_ids))
        self.assertNotIn("ground_truth", response)
        validate_document(response, "crosstext2loc_retrieval_response")

    def test_repeated_queries_do_not_reload_resources(self):
        matrix_id = id(self.small.matrix)
        for index in range(10):
            self.runtime.retrieve(gallery_id="madrid-50m", query_id=f"q{index}", text="same", language="en", k=2)
        self.assertEqual(self.encoder.encode_count, 10)
        self.assertEqual(id(self.small.matrix), matrix_id)

    def test_request_contract(self):
        request = {"schema_version": "1.0", "contract_version": "crosstext2loc-retrieval-request-v1", "query": {"query_id": "q", "text": "text", "language": "es"}, "gallery_ids": ["madrid-50m"], "top_k": 2}
        validate_document(request, "crosstext2loc_retrieval_request")
        validate_retrieval_request(request, self.runtime.gallery_ids)
        request["ground_truth"] = {}
        with self.assertRaises(RetrievalInputError): validate_retrieval_request(request)

    def test_invalid_inputs_and_unknown_gallery(self):
        invalid = [
            {"query_id": "", "text": "x", "language": "en", "k": 1},
            {"query_id": "q", "text": " ", "language": "en", "k": 1},
            {"query_id": "q", "text": "x", "language": "e", "k": 1},
            {"query_id": "q", "text": "x", "language": "en", "k": 0},
            {"query_id": "q", "text": "x", "language": "en", "k": True},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(RetrievalInputError):
                self.runtime.retrieve(gallery_id="madrid-50m", **values)
        with self.assertRaises(GalleryNotLoadedError):
            self.runtime.retrieve(gallery_id="missing", query_id="q", text="x", language="en", k=1)
        with self.assertRaises(RetrievalInputError):
            self.runtime.retrieve(gallery_id="madrid-50m", query_id="q", text="x", language="en", k=4)

    def test_duplicate_gallery_and_checkpoint_mismatch(self):
        with self.assertRaises(Exception):
            CrossText2LocRetriever(self.encoder, [self.small, self.small])
        with self.assertRaises(ModelCompatibilityError):
            CrossText2LocRetriever(self.encoder, [gallery("other", 2, checkpoint="f" * 64)])

    def test_close_waits_for_inflight_retrieval(self):
        encoder = BlockingEncoder()
        runtime = CrossText2LocRetriever(encoder, [self.small])
        errors = []
        thread = threading.Thread(target=lambda: self._thread_retrieve(runtime, errors))
        thread.start()
        self.assertTrue(encoder.started.wait(timeout=1))
        closer = threading.Thread(target=runtime.close)
        closer.start()
        time.sleep(0.02)
        self.assertTrue(closer.is_alive())
        encoder.release.set()
        thread.join(timeout=2)
        closer.join(timeout=2)
        self.assertEqual(errors, [])
        with self.assertRaises(RuntimeClosedError):
            runtime.retrieve(gallery_id="madrid-50m", query_id="q", text="x", language="en", k=1)

    @staticmethod
    def _thread_retrieve(runtime, errors):
        try:
            runtime.retrieve(gallery_id="madrid-50m", query_id="q", text="x", language="en", k=1)
        except Exception as error:
            errors.append(error)

    def test_encoder_error_propagates_and_close_blocks_queries(self):
        failing = CrossText2LocRetriever(FakeEncoder(fail=True), [self.small])
        with self.assertRaises(RuntimeError):
            failing.retrieve(gallery_id="madrid-50m", query_id="q", text="x", language="en", k=1)
        failing.close()
        self.runtime.close()
        self.assertTrue(self.encoder.closed)
        with self.assertRaises(RuntimeClosedError):
            self.runtime.retrieve(gallery_id="madrid-50m", query_id="q", text="x", language="en", k=1)


if __name__ == "__main__":
    unittest.main()
