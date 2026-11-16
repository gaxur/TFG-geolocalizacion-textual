from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_application_compose_is_loopback_internal_and_fail_closed():
    compose = (ROOT / "compose.app.yaml").read_text(encoding="utf-8")
    entrypoint = (ROOT / "scripts/run_mvp1_api.sh").read_text(encoding="utf-8")
    assert '"127.0.0.1:${APP_HTTP_PORT:-18085}:8080"' in compose
    assert "APP_BIND_HOST" not in compose
    assert compose.count("ports:") == 1
    assert "internal: true" in compose
    assert "app-backend" in compose and "app-edge" in compose
    assert "ATLAS_FREETEXT_APPLICATION_ENABLED: ${APP_MODE_ENABLED:-true}" in compose
    assert "/api/v1/health/live" in compose
    assert "ATLAS_FREETEXT_OPERATIONAL_ENABLED: \"false\"" in compose
    assert "ATLAS_DIALOGUE_ENABLED: \"false\"" in compose
    assert "ATLAS_VISUAL_PROMOTION_ENABLED: \"false\"" in compose
    assert "scripts/run_mvp1_api.sh" in compose
    assert "Dockerfile.app" in compose
    assert "docker/app-api.Dockerfile" in compose
    assert "atlas-app-api:local" in compose
    assert "APP_PROJECT_DIR" not in compose
    assert "--workers 1" in entrypoint


def test_application_compose_has_only_expected_mount_classes():
    compose = (ROOT / "compose.app.yaml").read_text(encoding="utf-8")
    for forbidden in ("cohort", "authorization", "dialogue-images", "visual-bundles", "mapillary"):
        assert forbidden not in compose.casefold()
    for required in ("APP_QWEN_MODEL_DIR", "APP_CHECKPOINT_DIR", "APP_MAP_ASSETS_DIR", "app-state"):
        assert required in compose
    assert ":rw" not in "\n".join(line for line in compose.splitlines() if line.lstrip().startswith("- ${APP_"))


def test_default_application_profile_is_unapproved():
    profile = (ROOT / "config/freetext_application_profile.template.json").read_text(encoding="utf-8")
    assert '"status": "PENDING_APPROVAL"' in profile
    assert '"approved": false' in profile


def test_application_api_build_context_excludes_scientific_data_and_models():
    ignore=(ROOT/'.dockerignore').read_text();assert all(name in ignore.splitlines() for name in ('data','external','checkpoints','results','runtime'));assert '*.pth' in ignore and '*.safetensors' in ignore


def test_application_nginx_is_loopback_allowlist_not_broad_api_proxy():
    nginx=(ROOT/'frontend/nginx.app.conf').read_text();assert 'X-Atlas-App-Loopback 1' in nginx;assert 'freetext-application-[0-9a-f-]{36}' in nginx;assert 'location /api/v1/dialogue-freetext/ { return 404; }' in nginx;assert 'location /api/ { return 404; }' in nginx;assert 'location ^~ /api/' not in nginx;assert 'location ^~ /api/v1/dialogue-freetext/' not in nginx
