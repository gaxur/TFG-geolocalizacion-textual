#!/usr/bin/env python3
"""Visor estático Top-50: solo muestra bytes locales con SHA-256 válido."""

from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def browser_url(path: Path) -> str:
    return "/" + path.resolve().relative_to(ROOT.resolve()).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/cache/mapillary")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    planned = {row["image_id"]: row for row in plan["assets"]}
    available = {}
    invalid = []
    for image_id, row in planned.items():
        candidates = []
        if row.get("existing_logical_path"):
            candidates.append((Path(row["existing_logical_path"]), row.get("existing_sha256"), "historical"))
        metadata_path = args.cache_dir / "metadata" / f"{image_id}.json"
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            candidates.append((args.cache_dir / metadata["logical_path"], metadata.get("sha256"), "cache"))
        for path, expected_sha, source in candidates:
            if path.is_file() and expected_sha and digest(path) == expected_sha:
                available[image_id] = {"path": path.resolve(), "sha256": expected_sha, "source": source}
                break
            invalid.append({"image_id": image_id, "path": str(path), "source": source})
    associations = {}
    for row in fixture["associations"]:
        associations.setdefault((row["query_id"], row["candidate_id"]), []).append(row)
    shared = {image_id for image_id, row in planned.items() if row["shared_association_count"] > 1}
    nav = []
    sections = []
    summary = {"candidate_slots": 0, "covered_candidates": 0, "available_candidate_image_associations": 0, "pending_candidate_image_associations": 0, "available_unique_images": len(available), "pending_unique_images": len(planned) - len(available)}
    for query in fixture["queries"]:
        query_id = query["query_id"]
        cards = []
        for candidate in query["baseline_results"]:
            summary["candidate_slots"] += 1
            key = (query_id, candidate["candidate_id"])
            rows = sorted(associations.get(key, []), key=lambda row: (row["orientation_band"], row["distance_to_candidate_m"], row["image_id"]))
            if rows:
                summary["covered_candidates"] += 1
            images = []
            for row in rows:
                local = available.get(row["image_id"])
                state = "available" if local else "pending"
                summary[f"{state}_candidate_image_associations"] += 1
                badge = "Disponible" if local else "Pendiente"
                shared_label = '<span class="shared">Compartida</span>' if row["image_id"] in shared else ""
                image = f'<img loading="lazy" src="{escape(browser_url(local["path"]))}" alt="Mapillary {escape(row["image_id"])}">' if local else '<div class="placeholder">Imagen no descargada</div>'
                images.append(f'''<figure class="{state}">{image}<figcaption><b>{badge}</b> {shared_label}<br>image_id <code>{escape(row['image_id'])}</code><br>distancia {row['distance_to_candidate_m']:.2f} m · secuencia <code>{escape(str(row.get('sequence_id') or 'desconocida'))}</code> · banda {row['orientation_band']}</figcaption></figure>''')
            coverage = f"{sum(row['image_id'] in available for row in rows)}/{len(rows)} disponibles" if rows else "Sin cobertura a 100 m"
            cards.append(f'''<article id="{query_id}-r{candidate['rank']}"><header><h3>Rango {candidate['rank']}</h3><span>{coverage}</span></header><p><code>{escape(candidate['candidate_id'])}</code></p><div class="images">{''.join(images) if images else '<div class="no-coverage">Candidato neutral sin fotografías planificadas</div>'}</div></article>''')
        nav.append(f'<a href="#{query_id}">{query_id}</a>')
        sections.append(f'<section id="{query_id}"><h2>{query_id}: Top-50 en_cartographic</h2>{"".join(cards)}</section>')
    html = f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Mapillary H16/H23 Top-50</title><style>:root{{--ink:#17211c;--paper:#eee8da;--green:#174f3b;--gold:#bc8b32;--pending:#8b3d2f}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px system-ui}}nav{{position:sticky;top:0;z-index:4;background:var(--green);padding:1rem;color:white;display:flex;gap:1rem;align-items:center;flex-wrap:wrap}}nav a{{color:white;font-weight:bold}}main{{max-width:1500px;margin:auto;padding:1rem}}article{{background:#fffdf7;margin:1rem 0;padding:1rem;border-left:6px solid var(--gold)}}article header{{display:flex;justify-content:space-between;gap:1rem}}.images{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.8rem}}figure{{margin:0;padding:.7rem;border:1px solid #aaa;background:white}}figure.pending{{border-color:var(--pending)}}img,.placeholder{{width:100%;height:220px;object-fit:contain;background:#151515;color:white}}.placeholder,.no-coverage{{display:grid;place-items:center;padding:2rem}}.shared{{background:#6e4c96;color:white;padding:.15rem .4rem}}code{{overflow-wrap:anywhere}}.summary{{background:#dce5d9;padding:1rem}}</style><nav><b>Visor Mapillary Top-50</b>{''.join(nav)}<span>Solo bytes locales verificados</span></nav><main><h1>H16/H23 · en_cartographic · madrid-50m</h1><div class="summary">Slots: {summary['candidate_slots']} · cubiertos: {summary['covered_candidates']} · imágenes únicas disponibles: {summary['available_unique_images']} · pendientes: {summary['pending_unique_images']} · asociaciones disponibles: {summary['available_candidate_image_associations']} · pendientes: {summary['pending_candidate_image_associations']}</div>{''.join(sections)}<details><summary>Rutas locales inválidas ignoradas ({len(invalid)})</summary><pre>{escape(json.dumps(invalid, ensure_ascii=False, indent=2))}</pre></details></main></html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    report = {"schema_version": "1.0", "contract_version": "h16-h23-photo-viewer-report-v1", "fixture_id": fixture["fixture_id"], "plan_id": plan["plan_id"], "summary": summary, "available_image_ids": sorted(available), "pending_image_ids": sorted(set(planned) - set(available)), "invalid_local_paths": invalid}
    args.output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
