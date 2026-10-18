"""Pure validation for an explain-first visual mechanism map."""

from collections.abc import Collection
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Layer = Literal["anatomy", "physiology", "pathophysiology", "pathology"]
Nonblank = Annotated[str, Field(min_length=1, pattern=r"\S")]
_LAYER_ORDER = ("anatomy", "physiology", "pathophysiology", "pathology")


class Analogy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Nonblank
    limits: Nonblank


class LayerVisual(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["anatomy_animation", "process_animation", "comparison", "timelapse"]
    subject: Nonblank
    motion: Nonblank
    reuse_of: Nonblank | None = None


class ExplainerLayer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Nonblank
    layer: Layer
    concept: Nonblank
    plain_explanation: Nonblank
    analogy: Analogy | None = None
    terms_introduced: tuple[Nonblank, ...] = ()
    visual: LayerVisual
    claim_ids: tuple[Nonblank, ...] = ()


class SkippedLayer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    layer: Layer
    reason: Nonblank


class Explainer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    topic_question: Nonblank
    organ_system: Nonblank
    layers: tuple[ExplainerLayer, ...] = Field(min_length=2)
    skipped_layers: tuple[SkippedLayer, ...] = ()

    @model_validator(mode="after")
    def _validate_mechanism_map(self) -> "Explainer":
        ids = [layer.id for layer in self.layers]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate layer ID")
        ranks = [_LAYER_ORDER.index(layer.layer) for layer in self.layers]
        if ranks != sorted(ranks):
            raise ValueError("layer order must not go backwards")
        present = {layer.layer for layer in self.layers}
        if not present.intersection({"anatomy", "physiology"}):
            raise ValueError("explainer requires a normal layer (anatomy or physiology)")
        if not present.intersection({"pathophysiology", "pathology"}):
            raise ValueError("explainer requires a disease layer")
        skipped = [entry.layer for entry in self.skipped_layers]
        if len(skipped) != len(set(skipped)):
            raise ValueError("duplicate skipped layer")
        if present.intersection(skipped):
            raise ValueError("present layer cannot appear in skipped_layers")
        missing = set(_LAYER_ORDER) - present - set(skipped)
        if missing:
            raise ValueError(f"missing layers must appear in skipped_layers: {sorted(missing)}")

        seen_ids: set[str] = set()
        seen_terms: set[str] = set()
        for layer in self.layers:
            if layer.visual.reuse_of is not None and layer.visual.reuse_of not in seen_ids:
                raise ValueError(f"layer {layer.id}: reuse_of must reference an earlier layer")
            seen_ids.add(layer.id)
            for term in layer.terms_introduced:
                if term in seen_terms:
                    raise ValueError(f"duplicate term introduced: {term}")
                seen_terms.add(term)
        return self


def validate_claim_refs(explainer: Explainer, claim_ids: Collection[str]) -> None:
    """Raise for unknown ledger IDs without reading the ledger or any files."""
    known = set(claim_ids)
    unknown = {claim for layer in explainer.layers for claim in layer.claim_ids} - known
    if unknown:
        raise ValueError(f"unknown claim IDs: {', '.join(sorted(unknown))}")
