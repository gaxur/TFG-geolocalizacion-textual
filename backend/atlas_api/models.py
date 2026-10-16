"""Modelos HTTP equivalentes a los contratos F4.6."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StringConstraints, model_validator
from typing_extensions import Annotated


Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]
NonNegativeFloat = Annotated[float, Field(ge=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryModel(StrictModel):
    query_id: NonEmpty
    text: NonEmpty
    language: Annotated[str, StringConstraints(min_length=2)]


class RetrievalRequest(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["crosstext2loc-retrieval-request-v1"]
    query: QueryModel
    gallery_ids: list[NonEmpty] = Field(min_length=1, max_length=2, json_schema_extra={"uniqueItems": True})
    top_k: StrictInt = Field(ge=1, le=1115)

    @model_validator(mode="after")
    def unique_galleries(self):
        if len(set(self.gallery_ids)) != len(self.gallery_ids):
            raise ValueError("gallery_ids must be unique")
        return self


class CandidateResult(StrictModel):
    rank: StrictInt = Field(ge=1)
    candidate_id: NonEmpty
    latitude: StrictFloat = Field(ge=-90, le=90)
    longitude: StrictFloat = Field(ge=-180, le=180)
    cosine_similarity: StrictFloat = Field(ge=-1, le=1)


class GalleryRetrieval(StrictModel):
    gallery_id: NonEmpty
    visual_dataset_id: NonEmpty
    embedding_dataset_id: NonEmpty
    gallery_count: StrictInt = Field(ge=1)
    requested_k: StrictInt = Field(ge=1)
    effective_k: StrictInt = Field(ge=1)
    ranking_method: Literal["exhaustive_cosine"]
    tie_break: Literal["candidate_id_ascending"]
    results: list[CandidateResult] = Field(min_length=1)


class ModelIdentity(StrictModel):
    name: Literal["CLIP-L/14@336"]
    checkpoint_sha256: Sha256


class ResponseTimings(StrictModel):
    text_encoding: NonNegativeFloat
    ranking_by_gallery: dict[NonEmpty, NonNegativeFloat]
    total: NonNegativeFloat


class RetrievalResponse(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["crosstext2loc-retrieval-response-v1"]
    query: QueryModel
    model: ModelIdentity
    retrievals: list[GalleryRetrieval] = Field(min_length=1, max_length=2)
    timings_ms: ResponseTimings


class ErrorDetail(StrictModel):
    code: NonEmpty
    message: NonEmpty
    request_id: NonEmpty


class ErrorResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    contract_version: Literal["atlas-api-error-v1"] = "atlas-api-error-v1"
    error: ErrorDetail
