"""Unit and integration tests for the BioBERT Clinical NLP service."""

import pytest

from app.schemas.model import AssertionStatus, ModelResult
from app.services.biobert import AssertionDetector, BioBERTClinicalNLPService


@pytest.fixture(scope="module")
def nlp_service() -> BioBERTClinicalNLPService:
    """Instantiate the NLP service once for all tests in the module."""
    return BioBERTClinicalNLPService()


def test_output_schema_contract(nlp_service: BioBERTClinicalNLPService):
    """Output strictly conforms to the requested ModelResult contract."""
    note = "Patient presents with acute hypertension."
    result = nlp_service.predict(note)

    assert isinstance(result, ModelResult)
    data = result.model_dump()

    # Required contract keys
    assert data["model_id"] == "biobert"
    assert data["status"] == "success"
    assert "raw_output" in data
    assert "entities" in data["raw_output"]

    entities = data["raw_output"]["entities"]
    assert len(entities) > 0

    first = entities[0]
    assert "text" in first
    assert "label" in first
    assert "assertion" in first
    assert "start_char" in first
    assert "end_char" in first
    assert isinstance(first["text"], str)
    assert isinstance(first["label"], str)
    assert first["assertion"] in {"PRESENT", "NEGATED", "FAMILY_HISTORY", "HYPOTHETICAL"}
    assert isinstance(first["start_char"], int)
    assert isinstance(first["end_char"], int)


def test_negation_detection(nlp_service: BioBERTClinicalNLPService):
    """Verify negation handling (e.g. 'Patient has no history of diabetes')."""
    note = (
        "Patient has no history of diabetes. "
        "Denies chest pain. "
        "Patient is without shortness of breath."
    )
    result = nlp_service.predict(note)

    entities = {e["text"].lower(): e for e in result.raw_output["entities"]}

    assert "diabetes" in entities
    assert entities["diabetes"]["assertion"] == AssertionStatus.NEGATED

    assert "chest pain" in entities
    assert entities["chest pain"]["assertion"] == AssertionStatus.NEGATED

    assert "shortness of breath" in entities
    assert entities["shortness of breath"]["assertion"] == AssertionStatus.NEGATED


def test_present_assertion(nlp_service: BioBERTClinicalNLPService):
    """Verify positive / confirmed clinical findings."""
    note = "Patient presents with acute hypertension. Confirmed acute myocardial infarction."
    result = nlp_service.predict(note)

    entities = {e["text"].lower(): e for e in result.raw_output["entities"]}

    assert "acute hypertension" in entities or "hypertension" in entities
    ent_htn = entities.get("acute hypertension") or entities.get("hypertension")
    assert ent_htn["assertion"] == AssertionStatus.PRESENT

    assert (
        "acute myocardial infarction" in entities or "myocardial infarction" in entities
    )
    ent_mi = entities.get("acute myocardial infarction") or entities.get("myocardial infarction")
    assert ent_mi["assertion"] == AssertionStatus.PRESENT


def test_family_history_assertion(nlp_service: BioBERTClinicalNLPService):
    """Verify family history mentions are tagged FAMILY_HISTORY."""
    note = (
        "Mother was diagnosed with breast cancer. "
        "Strong family history of coronary artery disease. "
        "Father had colon cancer."
    )
    result = nlp_service.predict(note)

    entities = {e["text"].lower(): e for e in result.raw_output["entities"]}

    assert "breast cancer" in entities
    assert entities["breast cancer"]["assertion"] == AssertionStatus.FAMILY_HISTORY

    assert "coronary artery disease" in entities
    assert entities["coronary artery disease"]["assertion"] == AssertionStatus.FAMILY_HISTORY

    assert "colon cancer" in entities
    assert entities["colon cancer"]["assertion"] == AssertionStatus.FAMILY_HISTORY


def test_hypothetical_assertion(nlp_service: BioBERTClinicalNLPService):
    """Verify rule-out, conditional, and suspected findings are tagged HYPOTHETICAL."""
    note = "Rule out pneumonia. Return to ED if chest pain develops. Suspected pulmonary embolism."
    result = nlp_service.predict(note)

    entities = {e["text"].lower(): e for e in result.raw_output["entities"]}

    assert "pneumonia" in entities
    assert entities["pneumonia"]["assertion"] == AssertionStatus.HYPOTHETICAL

    assert "chest pain" in entities
    assert entities["chest pain"]["assertion"] == AssertionStatus.HYPOTHETICAL

    assert "pulmonary embolism" in entities
    assert entities["pulmonary embolism"]["assertion"] == AssertionStatus.HYPOTHETICAL


def test_clause_boundary_isolation(nlp_service: BioBERTClinicalNLPService):
    """Negation in an initial clause must not spill over contrastive conjunctions."""
    note = "Patient has no history of diabetes, but presents with acute hypertension."
    result = nlp_service.predict(note)

    entities = {e["text"].lower(): e for e in result.raw_output["entities"]}

    assert "diabetes" in entities
    assert entities["diabetes"]["assertion"] == AssertionStatus.NEGATED

    assert "acute hypertension" in entities or "hypertension" in entities
    ent_htn = entities.get("acute hypertension") or entities.get("hypertension")
    assert ent_htn["assertion"] == AssertionStatus.PRESENT


def test_negated_family_history(nlp_service: BioBERTClinicalNLPService):
    """Negative mentions of family history are tagged NEGATED."""
    note = "No family history of heart disease or colon cancer."
    result = nlp_service.predict(note)

    entities = {e["text"].lower(): e for e in result.raw_output["entities"]}
    assert "colon cancer" in entities
    assert entities["colon cancer"]["assertion"] == AssertionStatus.NEGATED


def test_exact_character_spans(nlp_service: BioBERTClinicalNLPService):
    """All reported character spans must map directly to substrings in the original text."""
    note = (
        "54 yo female presents with acute hypertension and asthma. "
        "Denies chest pain. Mother had breast cancer. Rule out pneumonia."
    )
    result = nlp_service.predict(note)

    for ent in result.raw_output["entities"]:
        start = ent["start_char"]
        end = ent["end_char"]
        extracted_text = ent["text"]
        assert note[start:end] == extracted_text, (
            f"Offset mismatch: note[{start}:{end}]='{note[start:end]}' != '{extracted_text}'"
        )


def test_empty_and_whitespace_input(nlp_service: BioBERTClinicalNLPService):
    """Gracefully handles empty strings or whitespace-only inputs."""
    for empty_input in ["", "   ", "\n\t  \n"]:
        res = nlp_service.predict(empty_input)
        assert res.status == "success"
        assert res.model_id == "biobert"
        assert res.raw_output == {"entities": []}


def test_dict_input_payload(nlp_service: BioBERTClinicalNLPService):
    """Accepts dict input payload with 'text' key."""
    payload = {"text": "Patient has asthma."}
    res = nlp_service.predict(payload)

    assert res.status == "success"
    entities = res.raw_output["entities"]
    assert any(e["text"].lower() == "asthma" for e in entities)


def test_assertion_detector_standalone():
    """Unit test individual assertion patterns in isolation."""
    # Negation
    assert (
        AssertionDetector.determine_assertion(
            ent_text="diabetes",
            sent_text="Patient has no history of diabetes.",
            ent_start_in_sent=26,
            ent_end_in_sent=34,
            negex_flag=True,
        )
        == AssertionStatus.NEGATED
    )

    # Family history
    assert (
        AssertionDetector.determine_assertion(
            ent_text="breast cancer",
            sent_text="Mother had breast cancer.",
            ent_start_in_sent=11,
            ent_end_in_sent=24,
            negex_flag=False,
        )
        == AssertionStatus.FAMILY_HISTORY
    )

    # Hypothetical
    assert (
        AssertionDetector.determine_assertion(
            ent_text="pneumonia",
            sent_text="Rule out pneumonia.",
            ent_start_in_sent=9,
            ent_end_in_sent=18,
            negex_flag=False,
        )
        == AssertionStatus.HYPOTHETICAL
    )

    # Present
    assert (
        AssertionDetector.determine_assertion(
            ent_text="asthma",
            sent_text="Patient currently manages chronic asthma.",
            ent_start_in_sent=34,
            ent_end_in_sent=40,
            negex_flag=False,
        )
        == AssertionStatus.PRESENT
    )
