"""Contratos provider-neutral para inventarios visuales metadata-only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ImageMetadata:
    provider: str
    provider_record_id: str
    latitude: float
    longitude: float
    collection_or_sequence_id: str | None
    captured_at_utc: str | None
    heading_degrees: float | None
    camera_type: str | None
    width_px: int | None
    height_px: int | None
    horizontal_accuracy_m: float | None
    license_identifier: str | None
    attribution: str | None
    source_page_url: str | None
    location_kind: str = "camera"

    @property
    def global_record_id(self) -> str:
        return f"{self.provider}:{self.provider_record_id}"


class ImageProvider(Protocol):
    provider_id: str
    def normalize_inventory(self, document: Mapping[str, Any]) -> Sequence[ImageMetadata]: ...


class MapillaryMetadataProvider:
    provider_id = "mapillary"
    def normalize_inventory(self, document):
        return [ImageMetadata(self.provider_id, row["image_id"], row["latitude"], row["longitude"], row.get("sequence_id"), str(row.get("captured_at_epoch_ms")) if row.get("captured_at_epoch_ms") is not None else None, row.get("orientation_degrees"), row.get("camera_type"), row.get("width_px"), row.get("height_px"), None, "CC-BY-SA-4.0", None, f"https://www.mapillary.com/app/?pKey={row['image_id']}") for row in document.get("images", [])]


class PanoramaxMetadataProvider:
    provider_id = "panoramax"
    def normalize_inventory(self, document):
        rows=[]
        for row in document.get("items", []):
            position=row["camera_position"]
            rows.append(ImageMetadata(self.provider_id,row["item_id"],position["latitude"],position["longitude"],row.get("collection_id"),row.get("captured_at_utc"),row.get("orientation",{}).get("degrees") if isinstance(row.get("orientation"),dict) else row.get("azimuth_degrees"),None,None,None,position.get("horizontal_accuracy_m"),row.get("license"),row.get("producer"),row.get("item_url")))
        return rows
