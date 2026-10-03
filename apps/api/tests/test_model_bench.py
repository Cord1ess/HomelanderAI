"""The owner runs one model on one test, outside any application; progress is reported."""

import json
import uuid

from fastapi.testclient import TestClient

from app import pipeline, progress
from app.main import app
from tests.conftest import needs_database
from tests.test_applications import a_chest_xray, sign_in
from tests.test_mortality import HEALTHY as COMPLETE
from tests.test_roles import an_application, skip_scoring  # noqa: F401  (fixture)


@needs_database
def test_the_owner_tries_the_blood_panel_model(carrier):
    _, underwriter, admin, _ = an_application(carrier, "low", "12.00")
    with TestClient(app) as client:
        sign_in(client, underwriter)
        assert client.post("/api/models/xgboost/try", data={"values": "{}"}).status_code == 403
    with TestClient(app) as client:
        sign_in(client, admin)
        r = client.post(
            "/api/models/xgboost/try",
            data={"values": json.dumps(COMPLETE), "date_of_birth": "1970-05-01", "sex": "male"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        [run] = body["runs"]
        assert run["score"] is not None and run["durationMs"] >= 0
        assert body["tier"] in ("low", "moderate", "elevated")
        assert client.post("/api/models/nope/try", data={}).status_code == 404


@needs_database
def test_a_file_model_needs_a_file_and_says_what_it_was_given(carrier):
    _, _, admin, _ = an_application(carrier, "low", "12.00")
    with TestClient(app) as client:
        sign_in(client, admin)
        assert client.post("/api/models/cxr_lung/try", data={}).status_code == 422
        r = client.post(
            "/api/models/cxr_lung/try",
            files={"files": ("film.png", a_chest_xray(), "image/png")},
        )
        assert r.status_code == 200, r.text
        [run] = r.json()["runs"]
        assert run["fileName"] == "film.png"
        assert run["identifiedAs"]


def test_the_pipeline_reports_progress_as_it_goes():
    seen: list[tuple[int, int, str]] = []
    pipeline.evaluate(
        [],
        COMPLETE,
        age=55,
        models_requested=["xgboost"],
        on_progress=lambda done, total, step: seen.append((done, total, step)),
    )
    assert seen, "nothing was reported"
    assert seen[0][0] == 0 and seen[0][1] == 1
    assert seen[-1] == (1, 1, "Combining the readings")


def test_progress_is_kept_while_running_and_dropped_after():
    key = uuid.uuid4()
    progress.start(key)
    progress.update(key, 1, 3, "Reading the chest x-ray")
    assert progress.get(key).done == 1 and progress.get(key).total == 3
    progress.finish(key)
    assert progress.get(key) is None
