from copy import deepcopy

import pytest
from pydantic import ValidationError

from healthvideo.domain.explainer import Explainer, SkippedLayer, validate_claim_refs


def explainer_data() -> dict:
    return {
        "topic_question": "How does the illustrative test system change?",
        "organ_system": "test_system",
        "layers": [
            {
                "id": f"L{index}",
                "layer": layer,
                "concept": "Illustrative concept, not a medical claim",
                "plain_explanation": "An illustrative test explanation",
                "analogy": {"text": "Test model", "limits": "Illustration only"},
                "terms_introduced": [f"test term {index}"],
                "visual": {
                    "kind": kind,
                    "subject": "test_shape",
                    "motion": "Illustrative motion",
                    "reuse_of": "L1" if index > 1 else None,
                },
                "claim_ids": ["R-TEST-01"],
            }
            for index, (layer, kind) in enumerate(
                [
                    ("anatomy", "anatomy_animation"),
                    ("physiology", "process_animation"),
                    ("pathophysiology", "comparison"),
                    ("pathology", "timelapse"),
                ],
                start=1,
            )
        ],
    }


def test_complete_explainer_and_claim_binding() -> None:
    explainer = Explainer.model_validate(explainer_data())
    assert explainer.schema_version == "1.0"
    assert len(explainer.layers) == 4
    assert explainer.layers[2].visual.reuse_of == "L1"
    validate_claim_refs(explainer, {"R-TEST-01"})
    with pytest.raises(ValueError, match="R-TEST-01"):
        validate_claim_refs(explainer, set())


def test_duplicate_layer_ids_rejected() -> None:
    data = explainer_data()
    data["layers"][1]["id"] = "L1"
    with pytest.raises(ValidationError, match="duplicate layer ID"):
        Explainer.model_validate(data)


def test_layers_cannot_go_backwards() -> None:
    data = explainer_data()
    data["layers"][1], data["layers"][2] = data["layers"][2], data["layers"][1]
    with pytest.raises(ValidationError, match="order"):
        Explainer.model_validate(data)


@pytest.mark.parametrize("selected", [[], [0, 1], [2, 3]])
def test_requires_normal_and_disease_layers(selected: list[int]) -> None:
    data = explainer_data()
    data["layers"] = [data["layers"][index] for index in selected]
    for layer in data["layers"]:
        layer["visual"]["reuse_of"] = None
    with pytest.raises(ValidationError):
        Explainer.model_validate(data)


def test_missing_layers_require_explicit_reasons_and_optional_details_default() -> None:
    data = explainer_data()
    data["layers"] = [data["layers"][0], data["layers"][2]]
    with pytest.raises(ValidationError, match="skipped_layers"):
        Explainer.model_validate(data)
    data["skipped_layers"] = [
        {"layer": "physiology", "reason": "Test scope"},
        {"layer": "pathology", "reason": "Test scope"},
    ]
    for layer in data["layers"]:
        for key in ("analogy", "terms_introduced", "claim_ids"):
            layer.pop(key)
        layer["visual"].pop("reuse_of")
    explainer = Explainer.model_validate(data)
    assert explainer.layers[0].plain_explanation == "An illustrative test explanation"
    assert explainer.layers[0].analogy is None
    assert explainer.layers[0].terms_introduced == ()
    assert explainer.layers[0].claim_ids == ()
    assert explainer.layers[0].visual.reuse_of is None
    validate_claim_refs(explainer, set())
    for reason in ("", " \t"):
        data["skipped_layers"][0]["reason"] = reason
        with pytest.raises(ValidationError):
            Explainer.model_validate(data)


def test_plain_explanation_is_required() -> None:
    data = explainer_data()
    del data["layers"][0]["plain_explanation"]
    with pytest.raises(ValidationError, match="plain_explanation"):
        Explainer.model_validate(data)


@pytest.mark.parametrize("explanation", [None, "", " \t\n"])
def test_plain_explanation_must_be_nonblank(explanation: str | None) -> None:
    data = explainer_data()
    data["layers"][0]["plain_explanation"] = explanation
    with pytest.raises(ValidationError, match="plain_explanation"):
        Explainer.model_validate(data)


@pytest.mark.parametrize("reference", ["missing", "L2", "L3"])
def test_reuse_must_reference_an_earlier_layer(reference: str) -> None:
    data = explainer_data()
    data["layers"][1]["visual"]["reuse_of"] = reference
    with pytest.raises(ValidationError, match="reuse_of"):
        Explainer.model_validate(data)


@pytest.mark.parametrize("limits", [None, "", " \t"])
def test_analogy_requires_nonblank_limits(limits: str | None) -> None:
    data = explainer_data()
    data["layers"][0]["analogy"] = {"text": "Test analogy", "limits": limits}
    with pytest.raises(ValidationError):
        Explainer.model_validate(data)
    del data["layers"][0]["analogy"]["limits"]
    with pytest.raises(ValidationError):
        Explainer.model_validate(data)


@pytest.mark.parametrize("terms", [[""], [" \t"], ["test term 1"], ["x", "x"]])
def test_terms_are_nonblank_and_globally_unique(terms: list[str]) -> None:
    data = explainer_data()
    data["layers"][1]["terms_introduced"] = terms
    with pytest.raises(ValidationError):
        Explainer.model_validate(data)


def test_repeated_layer_type_is_allowed_in_forward_order() -> None:
    data = explainer_data()
    extra = deepcopy(data["layers"][0])
    extra.update(id="L1b", terms_introduced=[])
    data["layers"].insert(1, extra)
    assert len(Explainer.model_validate(data).layers) == 5


@pytest.mark.parametrize("field", ["layer", "kind"])
def test_unknown_layer_and_visual_kind_rejected(field: str) -> None:
    data = explainer_data()
    target = data["layers"][0] if field == "layer" else data["layers"][0]["visual"]
    target[field] = "unknown"
    with pytest.raises(ValidationError):
        Explainer.model_validate(data)


def test_models_are_frozen_and_forbid_extra_fields() -> None:
    data = explainer_data()
    explainer = Explainer.model_validate(data)
    models = [
        explainer,
        explainer.layers[0],
        explainer.layers[0].visual,
        explainer.layers[0].analogy,
        SkippedLayer(layer="pathology", reason="Test scope"),
    ]
    for model in models:
        with pytest.raises(ValidationError, match="frozen"):
            model.schema_version = "changed"
        with pytest.raises(ValidationError, match="Extra inputs"):
            type(model).model_validate({**model.model_dump(), "unexpected": True})
    with pytest.raises(ValidationError):
        Explainer.model_validate({**data, "schema_version": "2.0"})
