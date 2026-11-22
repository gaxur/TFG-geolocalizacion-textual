from pathlib import Path

import pytest

from backend.atlas_api.dialogue_freetext_executor import FreeTextRuntimeExecutor


def test_identity_uses_cached_hashes_and_fingerprint(monkeypatch):
    executor = object.__new__(FreeTextRuntimeExecutor)
    executor._identity = {'runtime_sha256': 'a' * 64}
    executor._identity_stats = {'file': (1, 2, 3, 4)}
    monkeypatch.setattr(executor, '_artifact_stats', lambda: {'file': (1, 2, 3, 4)})
    monkeypatch.setattr(executor, '_build_identity', lambda: (_ for _ in ()).throw(AssertionError('no rehash')))
    assert executor.identity == {'runtime_sha256': 'a' * 64}


def test_identity_blocks_changed_fingerprint(monkeypatch):
    executor = object.__new__(FreeTextRuntimeExecutor)
    executor._identity = {'runtime_sha256': 'a' * 64}
    executor._identity_stats = {'file': (1, 2, 3, 4)}
    monkeypatch.setattr(executor, '_artifact_stats', lambda: {'file': (2, 2, 3, 5)})
    with pytest.raises(RuntimeError, match='modificados'):
        executor.identity
