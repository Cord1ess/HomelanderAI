"""The medication check: a note's prescriptions against the declared history.

What matters here is the direction of every mistake. A drug the applicant is
allergic to, a relative's prescription or a drug merely proposed must not
become a flag; a drug the applicant takes for something the form never heard
of must. And the table has to be internally consistent, because a condition
named in a medication row that has no weight would flag as nothing.
"""

import io

import pytest

from app import intake, triage
from app.arms import medication_check as mc
from app.evidence import EvidenceKind
from tests.conftest import needs_database

DECLARED_DIABETES = {"history": {"diabetes": True, "smoker": False}, "hypertension": False}


# ── the table ────────────────────────────────────────────────────────────────


def test_every_medication_condition_has_a_weight_and_a_label():
    for row in mc.MEDICATIONS:
        for condition in row["conditions"]:
            assert condition in mc.CONDITIONS, f"{row['generic']} names unknown {condition}"
        assert row["generic"] == row["generic"].lower()
    for key, spec in mc.CONDITIONS.items():
        assert 0 < spec["weight"] <= 100, key
        assert spec["label"]


def test_ambiguity_is_declared_exactly_when_there_are_several_conditions():
    # A single-indication drug marked ambiguous would be halved for no reason;
    # a multi-indication one not marked would be over-counted.
    for row in mc.MEDICATIONS:
        if len(row["conditions"]) > 1:
            assert row.get("ambiguous"), f"{row['generic']} has several uses but is not ambiguous"


def test_no_name_is_shared_between_two_generics():
    seen: dict[str, str] = {}
    for row in mc.MEDICATIONS:
        for name in [row["generic"], *row.get("brands", [])]:
            key = name.lower()
            assert key not in seen or seen[key] == row["generic"], f"{name} in two rows"
            seen[key] = row["generic"]


# ── reading the note ─────────────────────────────────────────────────────────


def test_brands_are_read_as_their_generic():
    mentions = mc.find_mentions("Rx: Comet 500 mg bd, Amdocal 5 mg, Seclo 20 mg.")[0]
    assert [(m.term, m.generic) for m in mentions] == [
        ("Comet", "metformin"),
        ("Amdocal", "amlodipine"),
        ("Seclo", "omeprazole"),
    ]
    assert all(m.assertion == "PRESENT" for m in mentions)


def test_the_longer_name_wins_and_case_does_not_matter():
    mentions = mc.find_mentions("insulin glargine 10 units nocte; METFORMIN 1 g bd")[0]
    assert [m.term for m in mentions] == ["insulin glargine", "METFORMIN"]
    assert [m.generic for m in mentions] == ["insulin", "metformin"]


def test_short_capital_abbreviations_match_only_as_written():
    assert [m.generic for m in mc.find_mentions("on INH and PTU")[0]] == [
        "isoniazid",
        "propylthiouracil",
    ]
    # In lower case they are ordinary letters, not drugs.
    assert mc.find_mentions("the inh sound; ptu...")[0] == []


def test_a_measurement_is_not_a_prescription():
    assert mc.find_mentions("Insulin resistance noted. Lithium level normal.")[0] == []


@pytest.mark.parametrize(
    ("sentence", "assertion"),
    [
        ("Allergic to amoxicillin.", "NEGATED"),
        ("Mother takes levothyroxine.", "FAMILY_HISTORY"),
        ("Consider adding insulin if HbA1c stays above 9.", "HYPOTHETICAL"),
        ("Stopped warfarin in 2024.", "PAST"),
        ("Salbutamol inhaler as needed for wheeze.", "PRESENT"),
        ("Continues metformin 500 mg bd.", "PRESENT"),
    ],
)
def test_how_a_medication_is_asserted(sentence, assertion):
    (mention,) = mc.find_mentions(sentence)[0]
    assert str(mention.assertion) == assertion


# ── the comparison ───────────────────────────────────────────────────────────


def test_a_declared_condition_explains_its_medication():
    report = mc.check("On Comet 500 mg bd.", DECLARED_DIABETES)
    assert report["explained"] == ["metformin"]
    assert report["undisclosed"] == []
    assert report["score"] == 10.0


def test_diabetes_can_be_declared_on_the_retina_panel_too():
    assert "diabetes" in mc.declared_conditions({"diabetes_duration": "Over 10 years"})
    assert "diabetes" not in mc.declared_conditions({"diabetes_duration": "No diabetes"})
    assert "hypertension" in mc.declared_conditions({"hypertension": True})


def test_an_undeclared_condition_is_flagged_with_its_weight():
    report = mc.check("Amdocal 5 mg od.", DECLARED_DIABETES)
    (flag,) = report["undisclosed"]
    assert flag["condition"] == "hypertension"
    assert flag["medications"] == ["amlodipine"]
    assert flag["points"] == mc.CONDITIONS["hypertension"]["weight"]
    assert flag["asked_on_form"] is True
    assert report["score"] == flag["points"]


def test_an_ambiguous_medication_counts_half_and_any_declared_use_explains_it():
    half = mc.check("Atova 10 mg nocte.", {})
    points = {f["condition"]: f["points"] for f in half["undisclosed"]}
    assert points["coronary_heart_disease"] == mc.CONDITIONS["coronary_heart_disease"]["weight"] / 2
    assert points["high_cholesterol"] == mc.CONDITIONS["high_cholesterol"]["weight"] / 2

    explained = mc.check("Atova 10 mg nocte.", {"high_cholesterol": True})
    assert explained["undisclosed"] == [] and explained["explained"] == ["atorvastatin"]


def test_the_most_serious_undisclosed_condition_sets_the_score():
    report = mc.check(
        "Amdocal 5 mg. Continue 4FDC (isoniazid, rifampicin, pyrazinamide, ethambutol).",
        DECLARED_DIABETES,
    )
    assert report["undisclosed"][0]["condition"] == "tuberculosis"
    assert report["undisclosed"][0]["asked_on_form"] is False
    assert report["score"] == mc.CONDITIONS["tuberculosis"]["weight"]
    # Four drugs for one condition are one flag, not four.
    assert len([f for f in report["undisclosed"] if f["condition"] == "tuberculosis"]) == 1


def test_what_does_not_count_is_shown_but_not_scored():
    report = mc.check(
        "Allergic to amoxicillin. Mother takes levothyroxine. Napa 500 mg prn.", DECLARED_DIABETES
    )
    assert report["undisclosed"] == []
    assert report["immaterial"] == ["paracetamol"]
    assert {e["generic"] for e in report["excluded"]} == {"amoxicillin", "levothyroxine"}
    assert report["score"] == 5.0


def test_a_stopped_medication_still_implies_the_condition():
    report = mc.check("Stopped warfarin in 2024.", {})
    assert report["medications"][0]["assertion"] == "PAST"
    assert {f["condition"] for f in report["undisclosed"]} == {
        "arrhythmia",
        "venous_thromboembolism",
        "stroke",
    }


def test_a_note_naming_no_medication_is_not_checked():
    result = mc.run_with_form(b"Patient reviewed. BP 120/80. No complaints.", {})
    assert result.score is None and "nothing to check" in result.error


def test_run_records_what_it_compared():
    result = mc.run_with_form(b"On Comet 500 mg bd.", DECLARED_DIABETES)
    assert result.score == 10.0
    assert result.details["input_hash"]
    assert result.details["declared_conditions"] == ["diabetes"]
    assert "not a diagnosis" in result.details["validation"]


def test_the_arm_reads_documents_against_the_form():
    from app.arms import ARMS, arms_for

    arm = ARMS["medication_check"]
    assert arms_for(EvidenceKind.DOCUMENT) == [arm]
    assert arm.run is None and arm.run_with_form is not None
    assert arm.read(b"Amdocal 5 mg.", {"hypertension": True}).score == 10.0


# ── BioBERT ──────────────────────────────────────────────────────────────────
#
# The first group feeds `check` what BioBERT would return, so the rules around
# it are pinned without loading a model. The second runs the real models.

from app.services import biobert  # noqa: E402
from app.services.biobert import Span  # noqa: E402


def span(text: str, word: str) -> Span:
    start = text.index(word)
    return Span(text=word, start=start, end=start + len(word), confidence=1.0)


def test_a_misspelt_drug_biobert_found_is_matched_to_the_table():
    note = "Takes metfromin 500 mg bd."
    report = mc.check(note, {}, drug_spans=[span(note, "metfromin")])
    (med,) = report["medications"]
    assert med["generic"] == "metformin" and med["spelling"] is True
    assert med["found_by"] == ["biobert"]
    assert report["undisclosed"][0]["condition"] == "diabetes"


def test_a_misspelling_needs_biobert_to_have_called_it_a_drug():
    """The table alone never stretches a word into a drug."""
    report = mc.check("Takes metfromin 500 mg bd.", {}, drug_spans=[])
    assert report["medications"] == []


def test_a_near_name_that_is_another_drug_is_not_matched():
    assert mc.table_name_for("metoprolol")[0] == "metoprolol"
    assert mc.table_name_for("metfromin") == ("metformin", True)
    assert mc.table_name_for("paracetamolx")[1] is True  # a slip, still paracetamol
    assert mc.table_name_for("ibuprofenazole") == (None, False)


def test_a_drug_the_table_does_not_list_is_shown_and_not_scored():
    note = "Started finasteride 5 mg daily."
    report = mc.check(note, {}, drug_spans=[span(note, "finasteride")])
    assert report["medications"] == []
    assert report["unlisted"][0]["as_written"] == "finasteride"
    assert report["score"] == mc._NOTHING_MATERIAL


def test_both_readers_finding_a_drug_is_recorded_once_with_both():
    note = "On metformin 1 g bd."
    report = mc.check(note, DECLARED_DIABETES, drug_spans=[span(note, "metformin")])
    (med,) = report["medications"]
    assert med["found_by"] == ["biobert", "table"]


def test_a_brand_biobert_misses_is_still_found_by_the_table():
    """BioBERT learned from PubMed, which writes generic names."""
    report = mc.check("On Glucophage 500 mg.", {}, drug_spans=[])
    assert report["medications"][0]["generic"] == "metformin"
    assert report["medications"][0]["found_by"] == ["table"]


def test_a_condition_written_in_the_note_and_not_declared_is_flagged_at_full_weight():
    note = "Known case of chronic kidney disease stage 3."
    report = mc.check(note, {}, disease_spans=[span(note, "chronic kidney disease")])
    (flag,) = report["undisclosed"]
    assert flag["condition"] == "kidney_disease"
    assert flag["stated"] == ["chronic kidney disease"]
    assert flag["points"] == mc.CONDITIONS["kidney_disease"]["weight"]


@pytest.mark.parametrize(
    "note, term",
    [
        ("No history of diabetes.", "diabetes"),
        ("Mother had breast cancer.", "breast cancer"),
        ("Rule out tuberculosis.", "tuberculosis"),
    ],
)
def test_a_condition_negated_or_a_relatives_or_proposed_does_not_count(note, term):
    report = mc.check(note, {}, disease_spans=[span(note, term)])
    assert report["undisclosed"] == []
    assert report["conditions_in_note"][0]["assertion"] != "PRESENT"


def test_a_declared_condition_written_in_the_note_raises_nothing():
    note = "Type 2 diabetes mellitus, on diet."
    spans = [span(note, "Type 2 diabetes mellitus")]
    report = mc.check(note, DECLARED_DIABETES, disease_spans=spans)
    assert report["undisclosed"] == []
    assert report["conditions_in_note"][0]["declared"] is True


def test_abbreviations_match_only_as_written():
    assert mc.conditions_named("HTN") == ["hypertension"]
    assert mc.conditions_named("IHD") == ["coronary_heart_disease"]
    assert mc.conditions_named("htn") == []
    assert mc.conditions_named("diabetic nephropathy") == ["diabetes", "kidney_disease"]
    assert mc.conditions_named("cough") == []


def test_a_symptom_is_shown_but_never_scored():
    note = "Presented with cough and fever."
    report = mc.check(note, {}, disease_spans=[span(note, "cough"), span(note, "fever")])
    assert report["undisclosed"] == []
    assert [o["as_written"] for o in report["other_findings"]] == ["cough", "fever"]


needs_biobert = pytest.mark.skipif(
    not (biobert.is_downloaded("drugs") and biobert.is_downloaded("diseases")),
    reason="BioBERT weights not downloaded — python scripts/fetch_biobert_models.py",
)


@needs_biobert
def test_the_real_models_read_a_note_end_to_end():
    note = (
        b"Known case of hypertension, on amlodipine 5 mg. Takes metfromin 500 mg bd. "
        b"No history of stroke. Mother had breast cancer. Started finasteride."
    )
    result = mc.run_with_form(note, {})
    d = result.details
    flagged = {f["condition"] for f in d["undisclosed"]}
    assert {"hypertension", "diabetes"} <= flagged
    assert "stroke" not in flagged and "cancer" not in flagged
    meds = {m["generic"]: m for m in d["medications"]}
    assert meds["metformin"]["spelling"] is True and "biobert" in meds["metformin"]["found_by"]
    assert any(u["as_written"] == "finasteride" for u in d["unlisted"])
    assert d["biobert"]["drugs_found"] >= 3 and d["biobert"]["diseases_found"] >= 3


@needs_biobert
def test_the_weights_on_disk_are_the_pinned_ones():
    for name, spec in biobert.PINS.items():
        assert biobert._sha256(biobert.weights_path(name)) == spec["safetensors_sha256"]


@needs_biobert
def test_a_long_note_is_read_past_the_512_piece_limit():
    """BERT sees 512 pieces at once; a drug after that must still be found."""
    filler = "The patient was reviewed on the ward and remained comfortable overnight. " * 60
    note = filler + "Discharged on warfarin 5 mg."
    assert len(biobert.load_reader("drugs").tokenizer(note)["input_ids"]) > 512
    assert any(s.text == "warfarin" for s in biobert.find("drugs", note))


def test_no_silent_fallback_when_biobert_cannot_load(monkeypatch):
    """A reading that says BioBERT must have had BioBERT in it."""

    def broken(name, text):
        raise biobert.ModelUnavailable("weights missing")

    monkeypatch.setattr(biobert, "find", broken)
    result = mc.run_with_form(b"On metformin 500 mg bd.", {})
    assert result.score is None and "BioBERT could not be loaded" in result.error


# ── documents through intake ─────────────────────────────────────────────────


def test_a_text_note_is_stored_as_text_and_not_called_deidentified():
    processed = intake.process_upload(b"Mr Rahim: Comet 500 mg bd.\r\n", "note.txt")
    assert processed.source_format == "document"
    assert processed.mime_type == "text/plain"
    assert processed.deidentified is False
    assert processed.data == b"Mr Rahim: Comet 500 mg bd."
    # A second pass over the stored text changes nothing.
    assert intake.process_upload(processed.data, "note.txt").content_hash == processed.content_hash


def test_a_pdf_with_a_text_layer_is_read_and_a_scanned_one_is_refused():
    from pypdf import PdfWriter

    scanned = PdfWriter()
    scanned.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    scanned.write(buffer)
    with pytest.raises(intake.IntakeError, match="no text layer"):
        intake.process_upload(buffer.getvalue(), "scan.pdf")


def test_a_csv_that_was_meant_as_an_ecg_is_refused_as_one_not_stored_as_a_note():
    with pytest.raises(intake.IntakeError, match="12-lead ECG"):
        intake.process_upload(b"time,I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6\n0,1\n", "ecg.csv")
    # A table with no lead columns is a document.
    assert intake.process_upload(b"test,value\nHbA1c,6.1\n", "labs.csv").source_format == "document"


def test_triage_still_calls_a_note_a_document():
    assert triage.classify(b"On Comet 500 mg bd.", "note.txt").kind is EvidenceKind.DOCUMENT


# ── through the API ──────────────────────────────────────────────────────────


@needs_database
def test_a_note_is_scored_against_the_form_and_served_as_text(carrier):
    import asyncio
    import json

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.test_applications import intake_payload, sign_in

    payload = intake_payload(
        modelsRequested=["biobert", "eyepacs"],
        declaredHistory={"eyepacs": {"diabetes_duration": "5–10 years", "hypertension": False}},
    )
    note = b"Discharge medications: Comet 500 mg bd, Amdocal 5 mg od, Napa prn."
    account = asyncio.run(carrier())
    with TestClient(app) as client:
        sign_in(client, account)
        response = client.post(
            "/api/applications",
            data={"payload": payload, "file_arms": ["biobert"]},
            files={"files": ("discharge.txt", note, "text/plain")},
        )
        assert response.status_code == 201, response.text
        detail = client.get(f"/api/applications/{response.json()['id']}").json()
        assert detail["status"] == "scored", json.dumps(detail, indent=1)

        arms = {a["arm"]: a for a in detail["arms"]}
        run = arms["medication_check"]
        assert run["error"] is None
        assert [f["condition"] for f in run["details"]["undisclosed"]] == ["hypertension"]
        assert run["details"]["explained"] == ["metformin"]

        (stored,) = [f for f in detail["files"] if f["kind"] == "evidence"]
        assert stored["mimeType"] == "text/plain"
        served = client.get(f"/api/files/{stored['id']}")
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("text/plain")
        assert served.content == note
