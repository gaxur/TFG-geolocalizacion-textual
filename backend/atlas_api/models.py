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
    contract_version: Literal["atlas-experimental-retrieval-request-v2"]
    query: QueryModel
    gallery_id: Literal["madrid-25m", "madrid-50m"]
    processing_mode: Literal["no_llm", "with_llm"]
    top_k: Literal[10]

    @model_validator(mode="after")
    def spanish_original_only(self):
        if self.query.language != "es":
            raise ValueError("query.language must be es")
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
    transformation: NonNegativeFloat
    text_encoding: NonNegativeFloat
    ranking_by_gallery: dict[NonEmpty, NonNegativeFloat]
    total: NonNegativeFloat


class RetrievalResponse(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["atlas-experimental-retrieval-response-v3"]
    query: QueryModel
    processing: "ProcessingMetadata"
    model: ModelIdentity
    retrievals: list[GalleryRetrieval] = Field(min_length=1, max_length=1)
    visual_postprocessing: "VisualPostprocessing"
    timings_ms: ResponseTimings


class TransformerIdentity(StrictModel):
    model_id: Literal["Qwen/Qwen3-8B"]
    revision: Literal["b968826d9c46dd6066d109eabc6255188de91218"]
    prompt_version: Literal["f53b-text-transform-v2"]


class ProcessingMetadata(StrictModel):
    mode: Literal["no_llm", "with_llm"]
    variant: Literal["es_original", "en_cartographic"]
    effective_query: QueryModel
    transformer: TransformerIdentity | None


class VisualEvidence(StrictModel):
    candidate_id: NonEmpty
    reason: NonEmpty


class VisualPostprocessing(StrictModel):
    status: Literal["applied", "fallback_baseline", "disabled"]
    source: Literal["precomputed", "none"]
    request_id: NonEmpty | None
    reason: NonEmpty | None
    model: dict | None
    policy_id: NonEmpty | None
    baseline_results: list[CandidateResult]
    final_results: list[CandidateResult]
    evidence: list[VisualEvidence]


class ErrorDetail(StrictModel):
    code: NonEmpty
    message: NonEmpty
    request_id: NonEmpty


class ErrorResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    contract_version: Literal["atlas-api-error-v1"] = "atlas-api-error-v1"
    error: ErrorDetail


class DialogueStartRequest(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["atlas-dialogue-start-request-v1"]
    mode: Literal["official", "exploratory"]
    query_id: NonEmpty
    description_es: Annotated[str, StringConstraints(min_length=3, max_length=2400)]
    policy_id: Literal["legacy-official-v1", "post-final-answer-retrieval-v1", "post-final-answer-retrieval-v3", "dialogue-vpr-freetext-v1"] = "legacy-official-v1"


class DialogueAnswerRequest(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["atlas-dialogue-answer-request-v1"]
    answer_literal: Annotated[str, StringConstraints(min_length=1, max_length=1200)]
    answer_kind: Literal["affirmation", "negation", "unknown", "unobservable", "ambiguous", "stop", "free_text", "spatial_description", "orientation_clarification"]
    human_attested: Literal[True]
    external_context_used: Literal[False]

class FreeTextStartRequest(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["atlas-dialogue-freetext-start-request-v1"]
    experimental_query_id: NonEmpty
    description_es: Annotated[str, StringConstraints(min_length=3,max_length=2400)]

class FreeTextPolicyStartRequest(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["atlas-dialogue-freetext-start-request-v2"]
    policy_id: Literal["dialogue-vpr-freetext-v1-medium-provisional"]
    variant_id: NonEmpty


class OperationalFreeTextStartRequest(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["atlas-dialogue-freetext-start-request-v2"]
    policy_id: Literal["dialogue-vpr-freetext-v1-operational"]
    description_es: Annotated[str, StringConstraints(min_length=3, max_length=2400)]
    client_operation_id: NonEmpty

class FreeTextAnswerRequest(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["atlas-dialogue-freetext-answer-request-v1"]
    answer_literal: Annotated[str, StringConstraints(min_length=1,max_length=1200)]
    human_attested: Literal[True]
    external_context_used: Literal[False]


class OperationalFreeTextAnswerRequest(StrictModel):
    schema_version: Literal["1.0"]
    contract_version: Literal["atlas-dialogue-freetext-answer-request-v2"]
    turn_index: StrictInt = Field(ge=1, le=3)
    question_id: NonEmpty | None = None
    question_sha256: Sha256 | None = None
    answer_literal: Annotated[str, StringConstraints(min_length=1, max_length=1200)]
    human_attested: Literal[True]
    external_context_used: Literal[False]
    client_operation_id: NonEmpty

    @model_validator(mode="after")
    def question_binding(self):
        if self.question_id is None and self.question_sha256 is None:
            raise ValueError("question_id or question_sha256 is required")
        return self
