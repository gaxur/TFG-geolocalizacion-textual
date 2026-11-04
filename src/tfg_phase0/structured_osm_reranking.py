"""Evidencia OSM/F3 estructurada para reranking offline sin ground truth."""

from __future__ import annotations

from collections import Counter, defaultdict
import math
import re
import unicodedata
from typing import Any, Mapping, Sequence


NAME_KEYS = ("name:es", "name", "official_name", "brand", "alt_name", "short_name", "loc_name", "old_name")
GENERIC_NAMES = {"farmacia", "pisos", "mini supermarket", "supermercado", "museo", "cafeteria", "restaurante"}
DESCRIPTORS = {"bar", "cafe", "cafeteria", "restaurante", "taberna", "farmacia", "museo", "supermercado"}
ORIENTATION_PATTERN = re.compile(r"\b(?:a mi derecha|a mi izquierda|delante|detras|al fondo|encima|al otro lado)\b", re.I)

# Las categorías son globales y versionadas; no contienen reglas por query_id.
CATEGORY_RULES = (
    ("pharmacy", r"\bfarmacia\b", (("amenity", "pharmacy"), ("healthcare", "pharmacy"), ("shop", "chemist")), "specific"),
    ("cafe", r"\bcafeter[ií]a\b", (("amenity", "cafe"),), "specific"),
    ("restaurant", r"\brestaurante\b", (("amenity", "restaurant"),), "specific"),
    ("supermarket", r"\bsupermercado\b|\bmini supermarket\b", (("shop", "supermarket"), ("shop", "convenience")), "specific"),
    ("hairdresser", r"\bpeluquer[ií]a\b", (("shop", "hairdresser"),), "specific"),
    ("museum", r"\bmuseo\b", (("tourism", "museum"),), "specific"),
    ("square", r"\bplaza\b", (("place", "square"),), "specific"),
    ("pedestrian", r"\bpeatonal\b", (("highway", "pedestrian"), ("area:highway", "pedestrian")), "specific"),
    ("passage", r"\bpasaje\b|\barco\b", (("tunnel", "building_passage"), ("arcade", "yes"), ("covered", "yes")), "specific"),
    ("crossing", r"\bpaso de peatones\b", (("highway", "crossing"), ("footway", "crossing")), "specific"),
    ("bollard", r"\bbolardos?\b", (("barrier", "bollard"),), "specific"),
    ("waste_basket", r"\bpapelera\b", (("amenity", "waste_basket"),), "specific"),
    ("street_lamp", r"\bfarolas?\b", (("highway", "street_lamp"),), "specific"),
    ("tree", r"\b[áa]rbol(?:es)?\b", (("natural", "tree"),), "generic"),
    ("construction", r"\bobra\b", (("building", "construction"), ("landuse", "construction"), ("barrier", "construction")), "specific"),
    ("clock", r"\breloj\b", (("amenity", "clock"), ("tower:type", "clock")), "specific"),
    ("tower", r"\btorre\b", (("man_made", "tower"), ("building", "tower")), "specific"),
    ("bus_stop", r"\bautob[uú]s\b", (("highway", "bus_stop"),), "generic"),
    ("residential", r"\bresidenciales?\b", tuple(("building", value) for value in ("apartments", "residential", "house", "terrace")), "generic"),
    ("commercial", r"\b(?:comercios?|establecimientos?|local(?:es)? comercial(?:es)?)\b", (), "generic"),
    ("building", r"\bedificios?\b", (), "generic"),
)


def normalize_text(value: str) -> str:
    value = "".join(character for character in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def extract_text_evidence(text: str) -> dict[str, Any]:
    names = []
    for match in re.finditer(r"[«\"]([^»\"]{3,80})[»\"]", text):
        value = match.group(1).strip()
        normalized = normalize_text(value)
        names.append({"text": value, "normalized": normalized, "generic": normalized in GENERIC_NAMES, "span": [match.start(1), match.end(1)]})
    categories = []
    for category, pattern, tags, specificity in CATEGORY_RULES:
        matches = list(re.finditer(pattern, text, re.I))
        if matches:
            categories.append({"category": category, "specificity": specificity, "tag_rules": [list(rule) for rule in tags], "evidence": [match.group(0) for match in matches]})
    relations = [{"text": match.group(0), "requires_orientation": True, "used_for_scoring": False} for match in ORIENTATION_PATTERN.finditer(normalize_text(text))]
    return {"names": names, "categories": categories, "spatial_relations": relations}


def object_names(tags: Mapping[str, str]) -> list[dict[str, str]]:
    seen = set()
    output = []
    for key in NAME_KEYS:
        value = tags.get(key)
        if not isinstance(value, str) or not 3 <= len(value) <= 120:
            continue
        normalized = normalize_text(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append({"key": key, "value": value, "normalized": normalized})
    return output


def category_matches(tags: Mapping[str, str], category: Mapping[str, Any]) -> bool:
    if category["category"] == "commercial":
        return any(key in tags for key in ("shop", "amenity", "office", "craft"))
    if category["category"] == "building":
        return "building" in tags
    return any(tags.get(key) == value for key, value in category["tag_rules"])


def association_quality(association: Mapping[str, Any], geometry_role: str) -> float:
    if association.get("touches"):
        topology = 0.75
    elif association.get("within") or association.get("contains"):
        topology = 1.0
    elif association.get("crosses") and geometry_role == "line":
        topology = 0.95
    elif association.get("overlaps"):
        topology = 0.9
    else:
        topology = 0.85
    distance = float(association.get("center_distance_m", 35.355339))
    return round(topology * (0.85 + 0.15 * max(0.0, 1.0 - distance / 35.355339)), 6)


def _name_match(query_name: Mapping[str, Any], osm_name: Mapping[str, str], tags: Mapping[str, str]) -> tuple[str | None, float]:
    if query_name["generic"]:
        return None, 0.0
    query = query_name["normalized"]
    candidate = osm_name["normalized"]
    if query == candidate:
        return "exact_name", 5.0
    if query.replace(" ", "") == candidate.replace(" ", ""):
        return "compact_name", 4.0
    candidate_tokens = candidate.split()
    if candidate_tokens and candidate_tokens[0] in DESCRIPTORS and " ".join(candidate_tokens[1:]) == query:
        if any(key in tags for key in ("amenity", "shop", "tourism")):
            return "descriptor_core_name", 3.0
    return None, 0.0


def build_structured_evidence(
    *,
    text: str,
    candidate_ids: Sequence[str],
    associations_by_candidate: Mapping[str, Sequence[Mapping[str, Any]]],
    objects: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    textual = extract_text_evidence(text)
    candidate_set = set(candidate_ids)
    object_df = Counter()
    name_df = Counter()
    category_df = Counter()
    for candidate_id in candidate_ids:
        seen_objects, seen_names, seen_categories = set(), set(), set()
        for association in associations_by_candidate.get(candidate_id, ()):
            obj = objects.get(association["osm_ref"])
            if not obj:
                continue
            seen_objects.add(obj["osm_ref"])
            for name in object_names(obj.get("tags", {})):
                seen_names.add(name["normalized"])
            for category in textual["categories"]:
                if category_matches(obj.get("tags", {}), category):
                    seen_categories.add(category["category"])
        object_df.update(seen_objects)
        name_df.update(seen_names)
        category_df.update(seen_categories)

    rows = []
    for original_rank, candidate_id in enumerate(candidate_ids, 1):
        matches = []
        matched_categories = set()
        for association in associations_by_candidate.get(candidate_id, ()):
            obj = objects.get(association["osm_ref"])
            if not obj:
                continue
            tags = obj.get("tags", {})
            quality = association_quality(association, obj.get("geometry_role", "point"))
            for query_name in textual["names"]:
                for osm_name in object_names(tags):
                    kind, base = _name_match(query_name, osm_name, tags)
                    if kind:
                        df = name_df[osm_name["normalized"]]
                        rarity = math.log((len(candidate_set) + 1) / (df + 1)) / math.log(len(candidate_set) + 1)
                        matches.append({"kind": kind, "query": query_name["text"], "value": osm_name["value"], "osm_ref": obj["osm_ref"], "candidate_frequency": df, "quality": quality, "score": round(base * (0.75 + 0.25 * rarity) * quality, 6)})
            for category in textual["categories"]:
                if not category_matches(tags, category):
                    continue
                matched_categories.add(category["category"])
                df = category_df[category["category"]]
                rarity = math.log((len(candidate_set) + 1) / (df + 1)) / math.log(len(candidate_set) + 1)
                base = 2.0 if category["specificity"] == "specific" else 0.35
                matches.append({"kind": "category", "category": category["category"], "specificity": category["specificity"], "osm_ref": obj["osm_ref"], "candidate_frequency": df, "quality": quality, "score": round(base * rarity * quality, 6)})
        # Un objeto puede tener varios alias; se conserva solo la mejor evidencia por nombre/categoría y objeto.
        deduplicated = {}
        for match in matches:
            key = (match["kind"], match.get("category") or match.get("query"), match["osm_ref"])
            if key not in deduplicated or match["score"] > deduplicated[key]["score"]:
                deduplicated[key] = match
        matches = sorted(deduplicated.values(), key=lambda row: (-row["score"], row["kind"], row["osm_ref"]))
        name_scores = [row["score"] for row in matches if row["kind"] != "category"]
        category_best = {}
        for row in matches:
            if row["kind"] == "category":
                category_best[row["category"]] = max(category_best.get(row["category"], 0.0), row["score"])
        score = (max(name_scores) if name_scores else 0.0) + sum(category_best.values())
        if len([value for value in category_best.values() if value >= 0.5]) >= 2:
            score += 0.5
        strongest_name = max((row for row in matches if row["kind"] != "category"), key=lambda row: row["score"], default=None)
        specific_categories = [row for row in category_best.values() if row >= 0.5]
        if strongest_name and strongest_name["candidate_frequency"] <= 3 and strongest_name["score"] >= 3.0:
            level = "strong"
        elif len(specific_categories) >= 2 and score >= 1.5 or len(specific_categories) == 1 and score >= 1.2 and min((row["candidate_frequency"] for row in matches if row.get("specificity") == "specific"), default=101) <= 10:
            level = "moderate"
        elif score > 0:
            level = "weak"
        else:
            level = "none"
        rows.append({"candidate_id": candidate_id, "original_rank": original_rank, "score": round(score, 6), "evidence_level": level, "matched_specific_categories": sorted(category_best), "matches": matches})
    rows.sort(key=lambda row: (-row["score"], row["original_rank"], row["candidate_id"]))
    strong = [row for row in rows if row["evidence_level"] == "strong"]
    moderate = [row for row in rows if row["evidence_level"] == "moderate"]
    informative = bool(strong or moderate)
    return {"textual_evidence": textual, "candidate_evidence": rows, "summary": {"informative": informative, "strong_candidates": len(strong), "moderate_candidates": len(moderate), "weak_candidates": sum(row["evidence_level"] == "weak" for row in rows), "abstain": not informative}}


def build_variants(candidate_ids: Sequence[str], evidence: Mapping[str, Any], *, rrf_k: int = 60) -> tuple[dict[str, list[str]], dict[str, Any]]:
    baseline = list(candidate_ids)
    rows = list(evidence["candidate_evidence"])
    informative = evidence["summary"]["informative"]
    osm_order = [row["candidate_id"] for row in rows] if informative else baseline
    variants = {"structured_osm": osm_order}
    if informative:
        osm_rank = {candidate_id: rank for rank, candidate_id in enumerate(osm_order, 1)}
        ct_rank = {candidate_id: rank for rank, candidate_id in enumerate(baseline, 1)}
        rrf = sorted(baseline, key=lambda candidate_id: (-(1 / (rrf_k + ct_rank[candidate_id]) + 1 / (rrf_k + osm_rank[candidate_id])), ct_rank[candidate_id], candidate_id))
    else:
        rrf = baseline
    variants[f"rrf_k{rrf_k}"] = rrf

    eligible = [row for row in rows if row["evidence_level"] in {"strong", "moderate"}]
    promotion = eligible[0] if eligible else None
    conservative = list(baseline)
    if promotion and promotion["original_rank"] > 5:
        conservative.remove(promotion["candidate_id"])
        conservative.insert(4, promotion["candidate_id"])
    variants["conditional_top5"] = conservative
    strong_top1 = list(baseline)
    if promotion and promotion["evidence_level"] == "strong" and promotion["original_rank"] > 1:
        strong_top1.remove(promotion["candidate_id"])
        strong_top1.insert(0, promotion["candidate_id"])
    variants["conditional_strong_top1"] = strong_top1
    audit = {"abstained": not informative, "promoted_candidate_id": promotion["candidate_id"] if promotion else None, "source_rank": promotion["original_rank"] if promotion else None, "evidence_level": promotion["evidence_level"] if promotion else None, "reason": promotion["matches"][:5] if promotion else []}
    return variants, audit


def index_f3(associations: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    output = defaultdict(list)
    for row in associations:
        output[row["candidate_id"]].append(row)
    return dict(output)
