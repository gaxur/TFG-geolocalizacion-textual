from pathlib import Path

import pytest

from backend.atlas_api.settings import Settings


def base(monkeypatch):
    monkeypatch.setenv('ATLAS_CVG_UTILS_SHA256','a'*64);monkeypatch.setenv('CLIP_WEIGHTS_PATH','clip.pt');monkeypatch.setenv('ATLAS_FREETEXT_OPERATIONAL_ENABLED','true');monkeypatch.setenv('ATLAS_QWEN_MODEL_PATH','qwen');monkeypatch.setenv('ATLAS_FREETEXT_OPERATIONAL_SESSION_ROOT','sessions')


def test_operational_activation_requires_authorization_root_and_execution_id(monkeypatch):
    base(monkeypatch)
    with pytest.raises(ValueError,match='authorization root'):Settings.from_env()
    monkeypatch.setenv('ATLAS_FREETEXT_OPERATIONAL_AUTHORIZATION_ROOT','authorizations')
    with pytest.raises(ValueError,match='execution id'):Settings.from_env()


def test_operational_activation_keeps_exact_authorization_paths(monkeypatch):
    base(monkeypatch);monkeypatch.setenv('ATLAS_FREETEXT_OPERATIONAL_AUTHORIZATION_ROOT','authorizations');monkeypatch.setenv('ATLAS_FREETEXT_OPERATIONAL_EXECUTION_ID','execution-01');settings=Settings.from_env();assert settings.freetext_operational_authorization_root==Path('authorizations');assert settings.freetext_operational_execution_id=='execution-01'
