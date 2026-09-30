"""Check the demo works, end to end, before anyone records it.

Not the pipeline in-process: the actual HTTP calls the dashboard makes, against
a running server with the real database behind it. That is the only thing that
proves the setup someone else is about to record actually works.

Case A — test-01-rahim, a healthy 34-year-old man. Five readers, no mammogram,
         must come out low.
Case B — test-02-fatema, a 52-year-old diabetic woman. Six readers including
         the mammogram stand-in, must come out moderate, and that reading must
         be marked simulated everywhere it is stored.

Run it with the API already up (`npm run dev`), from the repo root:

    uv run --directory apps/api python ../../scripts/check_demo.py

Exits non-zero if anything a demonstration depends on is broken, and prints
which check failed. Add a base URL to point it at another machine.
"""

from __future__ import annotations

import json
import mimetypes
import sys
import time
from pathlib import Path

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
DEMO = Path(__file__).resolve().parents[1] / "demo" / "test"

CASES = [
    {
        "folder": "test-01-rahim",
        "expect_tier": "low",
        "expect_arms": {"tb_xray", "dr_fundus", "ecg_12lead", "medication_check", "mortality"},
        "expect_mammogram": False,
    },
    {
        "folder": "test-02-fatema",
        "expect_tier": "moderate",
        "expect_arms": {
            "tb_xray", "dr_fundus", "ecg_12lead", "medication_check", "mortality", "mirai",
        },
        "expect_mammogram": True,
    },
]

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"    {'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(f"{label}{': ' + detail if detail else ''}")
    return ok


def evidence_files(folder: Path) -> list[Path]:
    """Everything the operator drags in: not the JSON the form reads itself."""
    skip = {"client.json", "blood-panel.json", "README.md"}
    return [f for f in sorted(folder.iterdir()) if f.is_file() and f.name not in skip]


def run_case(session: requests.Session, case: dict) -> None:
    folder = DEMO / case["folder"]
    client = json.loads((folder / "client.json").read_text())
    blood = json.loads((folder / "blood-panel.json").read_text())
    files = evidence_files(folder)

    print(f"\n=== {case['folder']} — {client['name']} ===")
    print(f"    {len(files)} files: {', '.join(f.name for f in files)}")

    # ── 1. classify, as the drop zone does ──────────────────────────────────
    payload = [
        ("files", (f.name, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream"))
        for f in files
    ]
    t0 = time.time()
    r = session.post(f"{BASE}/api/evidence/classify", files=payload, timeout=300)
    if not check(r.status_code == 200, "classify responds 200", f"got {r.status_code} {r.text[:200]}"):
        return
    classified = r.json()["files"]
    print(f"    classified in {time.time() - t0:.1f}s")

    by_name = {c["filename"]: c for c in classified}
    for f in files:
        c = by_name.get(f.name)
        kind = c["kindLabel"] if c else "MISSING"
        expected = {
            "chest-xray.png": "Chest X-ray",
            "retina.jpeg": "Retinal photo",
            "ecg-12-lead.csv": "12-lead ECG",
            "discharge-note.txt": "Document",
        }.get(f.name, "Mammogram" if f.name.startswith("mammogram") else None)
        check(kind == expected, f"{f.name} identified as {expected}", f"got {kind}")

    # ── 2. submit, as the form does ─────────────────────────────────────────
    cxr = (client.get("questions") or {}).get("cxr_lung") or {}
    declared: dict = {"cxr_lung": {}}
    for group in ("symptoms", "history", "cardio"):
        picked = cxr.get(group) or []
        declared["cxr_lung"][group] = {k: True for k in picked}
    declared["cxr_lung"]["history"]["prior_tb"] = bool(cxr.get("prior_tb"))
    declared["xgboost"] = blood
    for arm, values in (client.get("questions") or {}).items():
        if arm != "cxr_lung":
            declared[arm] = values

    models = ["cxr_lung", "eyepacs", "ecg", "xgboost", "medication_check"]
    if case["expect_mammogram"]:
        models.append("mirai")

    # One `payload` JSON field plus `file_kinds` parallel to `files`, exactly as
    # the dashboard sends it (routers/applications.py submit_application).
    intake = {
        "applicant": {
            "name": client["name"],
            "phone": client["phone"],
            "dateOfBirth": client["dateOfBirth"],
            "sex": client["sex"],
            "email": client["email"],
        },
        "coverage": {
            "coverageType": client["coverage"]["type"],
            "coverageAmount": client["coverage"]["amount"],
            "policyTerm": client["coverage"]["term"],
        },
        "modelsRequested": models,
        "declaredHistory": declared,
    }
    payload = [
        ("files", (f.name, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream"))
        for f in files
    ]
    # file_kinds is positional against files, so it is built from the same list
    # in the same order, taking each file's kind from what classify returned.
    form = [("payload", json.dumps(intake))]
    form += [("file_kinds", by_name[f.name]["kind"]) for f in files]

    t0 = time.time()
    r = session.post(f"{BASE}/api/applications", data=form, files=payload, timeout=900)
    if not check(r.status_code in (200, 201), "submit accepted", f"got {r.status_code} {r.text[:300]}"):
        return
    submitted = r.json()
    ref = submitted.get("reference") or submitted.get("id")
    print(f"    submitted in {time.time() - t0:.1f}s as {ref}")

    # ── 3. poll until scored ────────────────────────────────────────────────
    app_id = submitted.get("id")
    detail = None
    # Scoring runs in a background task, so the application comes back
    # `submitted` first and becomes `scored` when the readers finish. Waiting
    # on the terminal status rather than on a list of in-progress ones means a
    # status we did not think of cannot end the loop early.
    for _ in range(180):
        r = session.get(f"{BASE}/api/applications/{app_id}", timeout=60)
        if r.status_code != 200:
            break
        detail = r.json()
        if detail.get("status") in ("scored", "insufficient_evidence", "escalated", "decided"):
            break
        time.sleep(5)
    if not check(detail is not None, "application readable"):
        return

    # crs and tier live under `score`, where the review screen reads them.
    score = detail.get("score") or {}
    status, crs, tier = detail.get("status"), score.get("crs"), score.get("tier")
    print(f"    status={status}  crs={crs}  tier={tier}")
    check(status == "scored", "scored", f"status={status}")
    check(tier == case["expect_tier"], f"tier is {case['expect_tier']}", f"got {tier}")

    # ── 4. every reader ran, and is on the record ───────────────────────────
    arms = detail.get("arms") or []
    ran = {a["arm"] for a in arms}
    for name in sorted(case["expect_arms"]):
        a = next((x for x in arms if x["arm"] == name), None)
        state = "missing" if a is None else (f"error: {a.get('error')}" if a.get("score") is None else f"score {a['score']}")
        check(a is not None and (a.get("score") is not None or name == "mirai"), f"{name} ran", state)
    check(
        not (ran - case["expect_arms"]),
        "no unexpected reader ran",
        f"extra: {sorted(ran - case['expect_arms'])}",
    )

    # ── 5. the mammogram stand-in, where it matters ─────────────────────────
    mirai = next((a for a in arms if a["arm"] == "mirai"), None)
    if case["expect_mammogram"]:
        if check(mirai is not None, "mammogram reader present"):
            d = mirai.get("details") or {}
            check(mirai.get("score") is not None, "mammogram produced a reading", str(mirai.get("error")))
            check(d.get("simulated") is True, "reading marked simulated in the stored record")
            check("stand-in" in (d.get("scorer") or ""), "scorer names the stand-in", d.get("scorer", ""))
            check(
                (d.get("validation") or "").startswith("SIMULATED"),
                "validation line warns it is simulated",
            )
            check("AUC" not in (d.get("validation") or ""), "Mirai's published figures not attached")
    else:
        check(mirai is None, "no mammogram reader for a male applicant")

    # ── 6. every file stored and labelled ───────────────────────────────────
    stored = detail.get("files") or []
    evidence = [f for f in stored if f.get("kind") == "evidence"]
    check(
        len(evidence) == len(files),
        f"all {len(files)} files stored",
        f"stored {len(evidence)}",
    )
    unlabelled = [f["filename"] for f in evidence if not f.get("evidenceLabel")]
    check(not unlabelled, "every stored file carries its label", str(unlabelled))

    # ── 7. findings reached the screen ──────────────────────────────────────
    findings = detail.get("findings") or []
    check(len(findings) > 0, "findings on the review screen", f"{len(findings)} findings")
    check(crs is not None, "a score was computed", f"crs={crs}")


def main() -> int:
    session = requests.Session()
    r = session.post(
        f"{BASE}/api/auth/login",
        json={"email": "underwriter", "password": "admin123"},
        timeout=60,
    )
    print(f"sign in: {r.status_code}")
    if r.status_code != 200:
        print(r.text[:400])
        return 1

    for case in CASES:
        run_case(session, case)

    print("\n" + "=" * 62)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
