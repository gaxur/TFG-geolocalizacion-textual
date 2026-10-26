#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.visual_reranking import canonical_bytes  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Construye paquete portable y ciego para anotación AI local")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--photo-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    photos = json.loads(args.photo_manifest.read_text(encoding="utf-8"))
    image_ids = {row["image_id"] for row in fixture["associations"]}
    selected = {row["image_id"]: row for row in photos["photos"] if row["status"] == "downloaded" and row["image_id"] in image_ids}
    if set(selected) != image_ids or len(image_ids) != 12:
        raise ValueError("fixture y fotos no coinciden")
    if args.output_root.exists():
        shutil.rmtree(args.output_root)
    images = args.output_root / "images"
    schemas = args.output_root / "schemas"
    scripts = args.output_root / "scripts"
    images.mkdir(parents=True)
    schemas.mkdir()
    scripts.mkdir()

    safe_fields = (
        "image_id", "query_id", "candidate_id", "captured_at", "camera_type",
        "source_resolution", "downloaded_resolution", "orientation_degrees",
        "bearing_to_candidate_degrees", "angular_difference_degrees", "creator",
        "creator_profile_url", "attribution", "license", "license_url",
        "provider_attribution", "source_page_url", "modifications", "media_type",
        "sha256", "size_bytes", "limitations",
    )
    manifest = []
    for image_id in sorted(image_ids):
        source = selected[image_id]
        source_path = (args.photo_manifest.parent / source["logical_path"]).resolve()
        if sha(source_path) != source["sha256"]:
            raise ValueError(f"hash inválido: {image_id}")
        target = images / source_path.name
        shutil.copy2(source_path, target)
        row = {key: source.get(key) for key in safe_fields}
        row["logical_path"] = f"images/{target.name}"
        manifest.append(row)

    claim_sets = [{"query_id": row["query_id"], "source_text_sha256": row["source_text_sha256"], "claims": row["claims"]} for row in fixture["claim_sets"]]
    records = [{key: row[key] for key in ("query_id", "candidate_id", "image_id", "claim_id")} for row in fixture["annotation_template"]["records"]]
    portable = {
        "schema_version": "1.0",
        "contract_version": "visual-codex-annotation-package-v1",
        "package_role": "AI_proposal_then_human_review",
        "source_fixture_id": fixture["fixture_id"],
        "query_ids": fixture["query_ids"],
        "claim_sets": claim_sets,
        "associations": fixture["associations"],
        "expected_records": records,
        "instructions": {
            "blind_to_geographic_reference": True,
            "blind_to_retrieval_order_and_scores": True,
            "blind_to_model_outputs": True,
            "absence_is_unverifiable": True,
            "orientation_must_be_explicitly_supported": True,
        },
    }
    (args.output_root / "fixture.json").write_bytes(canonical_bytes(portable) + b"\n")
    (args.output_root / "photo-manifest.json").write_bytes(canonical_bytes({"schema_version": "1.0", "contract_version": "visual-codex-photo-manifest-v1", "photos": manifest}) + b"\n")
    shutil.copy2(ROOT / "schemas/visual_atomic_ai_proposals.schema.json", schemas / "visual_atomic_ai_proposals.schema.json")
    shutil.copy2(ROOT / "schemas/visual_atomic_human_annotations.schema.json", schemas / "visual_atomic_human_annotations.schema.json")
    shutil.copy2(ROOT / "scripts/validate_codex_ai_proposals.py", scripts / "validate_codex_ai_proposals.py")
    shutil.copy2(ROOT / "scripts/render_codex_proposal_review.py", scripts / "render_codex_proposal_review.py")
    (args.output_root / "CODEX_PROMPT.md").write_text((ROOT / "docs/CODEX_LOCAL_VISUAL_ANNOTATION_PROMPT.md").read_text(encoding="utf-8"), encoding="utf-8")

    attribution = ["# Atribución Mapillary", "", "Las fotografías se usan para anotación académica local. No redistribuir públicamente sin revisar de nuevo licencia, privacidad y alcance autorizado.", ""]
    for row in manifest:
        attribution.extend([f"## {row['image_id']}", f"- {row['attribution']}", f"- Imagen: {row['source_page_url']}", f"- Perfil: {row['creator_profile_url']}", f"- Licencia: {row['license_url']}", f"- Modificaciones: {row['modifications']}", ""])
    (args.output_root / "ATTRIBUTION.md").write_text("\n".join(attribution), encoding="utf-8")
    readme = """# Paquete de anotación visual para Codex local

1. Verifica `CHECKSUMS.sha256`.
2. Abre `CODEX_PROMPT.md` desde la raíz de este paquete.
3. Codex debe inspeccionar `images/` y escribir `ai-proposals.json`.
4. Valida: `python scripts/validate_codex_ai_proposals.py --package-root . --proposals ai-proposals.json`.
5. Genera revisión: `python scripts/render_codex_proposal_review.py --package-root . --proposals ai-proposals.json --output human-review.html`.
6. Las propuestas son `AI-proposed`, nunca etiquetas humanas.

Este paquete no contiene referencias geográficas de evaluación, scores/rangos CrossText2Loc ni predicciones de modelos visuales.
Las imágenes Mapillary conservan atribución en `ATTRIBUTION.md` y no deben publicarse automáticamente.
"""
    (args.output_root / "README.md").write_text(readme, encoding="utf-8")
    files = sorted(path for path in args.output_root.rglob("*") if path.is_file())
    checksums = "".join(f"{sha(path)}  {path.relative_to(args.output_root).as_posix()}\n" for path in files)
    (args.output_root / "CHECKSUMS.sha256").write_text(checksums, encoding="ascii")
    print(json.dumps({"output": str(args.output_root), "images": len(image_ids), "records": len(records), "bytes": sum(path.stat().st_size for path in args.output_root.rglob("*") if path.is_file())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
