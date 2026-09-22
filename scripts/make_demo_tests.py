"""Assemble five test folders under data/demo/test/, one client each, with a
file for every reader the platform has.

    python scripts/make_demo_tests.py

Drop a whole folder into the intake form and every file finds its reader:

    chest-xray.png      -> chest X-ray reader
    retina.jpeg         -> retinal photo reader
    ecg-12-lead.csv     -> 12-lead ECG reader
    mammogram-*.dcm     -> mammogram reader (four views)
    discharge-note.txt  -> medication check (a clinical note)
    blood-panel.json    -> lab reader (the values are typed in for you)
    client.json         -> the client, their cover and their health questions

Sources are the public samples already on disk (Shenzhen chest films,
EyePACS retinal photographs, CODE-test ECGs, the mammogram test set and the
discharge-summary sample). Only the names and the blood values are invented.
data/ is gitignored, so run this on each machine that will demo.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo" / "test"
CHEST_NORMAL = ROOT / "data" / "demo" / "01-normal"
CHEST_TB = ROOT / "data" / "demo" / "02-tuberculosis"
RETINA = ROOT / "samples" / "retina"
ECG = ROOT / "data" / "ecg" / "demo"
MAMMO = ROOT / "Mirai" / "Test"
NOTE = ROOT / "docs" / "demo" / "discharge_summary_sample.txt"

MAMMO_VIEWS = {"LEFT_CC.dcm": "mammogram-left-cc.dcm", "LEFT_MLO.dcm": "mammogram-left-mlo.dcm",
               "RIGHT_CC.dcm": "mammogram-right-cc.dcm", "RIGHT_MLO.dcm": "mammogram-right-mlo.dcm"}

# Ordered low risk to elevated, so a demo can climb.
CLIENTS = [
    {
        "folder": "test-01-rahim",
        "story": "Healthy 34-year-old. Clean film, clean retina, normal rhythm, normal bloods. Expect low.",
        "chest": CHEST_NORMAL / "normal-01-shenzhen-0197_0.png",
        "retina": RETINA / "13_left.jpeg",
        "ecg": ECG / "normal_codetest_000.csv",
        "client": {"name": "Rahim Uddin", "phone": "01711 000101", "email": "rahim.uddin@example.com",
                   "dateOfBirth": "1992-03-14", "sex": "Male",
                   "coverage": {"type": "Life", "amount": 1_000_000, "term": "20"},
                   "questions": {"cxr_lung": {"symptoms": [], "history": [], "prior_tb": False}}},
        "blood": {"albumin_g_dl": 4.5, "creatinine_mg_dl": 0.9, "glucose_mg_dl": 88, "crp_mg_l": 0.6,
                  "lymphocyte_pct": 32, "mcv_fl": 88, "rdw_pct": 12.4, "alp_u_l": 62, "wbc_10e3_ul": 5.8,
                  "height_cm": 172, "weight_kg": 68},
    },
    {
        "folder": "test-02-fatema",
        "story": "52-year-old with diabetes. Moderate retinopathy, raised glucose. Expect moderate.",
        "chest": CHEST_NORMAL / "normal-02-shenzhen-0039_0.png",
        "retina": RETINA / "15_right.jpeg",
        "ecg": ECG / "normal_codetest_002.csv",
        "client": {"name": "Fatema Begum", "phone": "01711 000102", "email": "fatema.begum@example.com",
                   "dateOfBirth": "1974-07-02", "sex": "Female",
                   "coverage": {"type": "Health", "amount": 500_000, "term": "10"},
                   "questions": {"cxr_lung": {"symptoms": [], "history": ["diabetes"], "prior_tb": False},
                                 "eyepacs": {"diabetes_duration": "8"}}},
        "blood": {"albumin_g_dl": 4.1, "creatinine_mg_dl": 1.0, "glucose_mg_dl": 168, "crp_mg_l": 3.2,
                  "lymphocyte_pct": 27, "mcv_fl": 90, "rdw_pct": 13.6, "alp_u_l": 84, "wbc_10e3_ul": 7.1,
                  "height_cm": 158, "weight_kg": 71},
    },
    {
        "folder": "test-03-karim",
        "story": "61-year-old smoker with a six-week cough. The film shows tuberculosis. Expect elevated: escalate, doctor decides.",
        "chest": CHEST_TB / "tb-01-shenzhen-0648_1.png",
        "retina": RETINA / "17_left.jpeg",
        "ecg": ECG / "normal_codetest_003.csv",
        "client": {"name": "Karim Hossain", "phone": "01711 000103", "email": "karim.hossain@example.com",
                   "dateOfBirth": "1965-11-23", "sex": "Male",
                   "coverage": {"type": "Life", "amount": 2_500_000, "term": "15"},
                   "questions": {"cxr_lung": {"symptoms": ["cough_over_2_weeks", "night_sweats", "weight_loss"],
                                              "history": ["smoker"], "prior_tb": False}}},
        "blood": {"albumin_g_dl": 3.7, "creatinine_mg_dl": 1.1, "glucose_mg_dl": 102, "crp_mg_l": 14.0,
                  "lymphocyte_pct": 18, "mcv_fl": 93, "rdw_pct": 14.8, "alp_u_l": 96, "wbc_10e3_ul": 9.4,
                  "height_cm": 168, "weight_kg": 61},
    },
    {
        "folder": "test-04-nusrat",
        "story": "45-year-old with palpitations and hypertension. The ECG shows atrial fibrillation. Expect moderate to elevated.",
        "chest": CHEST_NORMAL / "normal-03-shenzhen-0225_0.png",
        "retina": RETINA / "10_left.jpeg",
        "ecg": ECG / "AF_codetest_120.csv",
        "client": {"name": "Nusrat Jahan", "phone": "01711 000104", "email": "nusrat.jahan@example.com",
                   "dateOfBirth": "1981-05-09", "sex": "Female",
                   "coverage": {"type": "Critical illness", "amount": 1_500_000, "term": "20"},
                   "questions": {"cxr_lung": {"symptoms": [], "history": [], "cardio": ["hypertension"], "prior_tb": False},
                                 "ecg": {"palpitations": True}}},
        "blood": {"albumin_g_dl": 4.2, "creatinine_mg_dl": 0.8, "glucose_mg_dl": 94, "crp_mg_l": 2.1,
                  "lymphocyte_pct": 30, "mcv_fl": 87, "rdw_pct": 12.9, "alp_u_l": 70, "wbc_10e3_ul": 6.3,
                  "height_cm": 160, "weight_kg": 64},
    },
    {
        "folder": "test-05-malek",
        "story": "70-year-old with a conduction block on the ECG, kidney values off and a second film with tuberculosis. Expect elevated.",
        "chest": CHEST_TB / "tb-02-shenzhen-0403_1.png",
        "retina": RETINA / "16_left.jpeg",
        "ecg": ECG / "LBBB_codetest_001.csv",
        "client": {"name": "Abdul Malek", "phone": "01711 000105", "email": "abdul.malek@example.com",
                   "dateOfBirth": "1956-01-30", "sex": "Male",
                   "coverage": {"type": "Life", "amount": 3_000_000, "term": "10"},
                   "questions": {"cxr_lung": {"symptoms": [], "history": ["diabetes", "smoker"], "cardio": ["hypertension"], "prior_tb": False},
                                 "ecg": {"known_arrhythmia": True}}},
        "blood": {"albumin_g_dl": 3.4, "creatinine_mg_dl": 1.9, "glucose_mg_dl": 131, "crp_mg_l": 8.5,
                  "lymphocyte_pct": 16, "mcv_fl": 97, "rdw_pct": 15.9, "alp_u_l": 118, "wbc_10e3_ul": 8.8,
                  "height_cm": 165, "weight_kg": 59},
    },
]


def main() -> int:
    sources = [c["chest"] for c in CLIENTS] + [c["retina"] for c in CLIENTS] + [c["ecg"] for c in CLIENTS]
    sources += [MAMMO / v for v in MAMMO_VIEWS] + [NOTE]
    missing = [src for src in sources if not Path(src).is_file()]
    if missing:
        print("Missing source files; see docs/DEMO_SETUP.md for how to fetch the demo data:")
        for m in missing:
            print(f"  {m}")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    for client in CLIENTS:
        folder = OUT / client["folder"]
        folder.mkdir(exist_ok=True)
        shutil.copyfile(client["chest"], folder / "chest-xray.png")
        shutil.copyfile(client["retina"], folder / "retina.jpeg")
        shutil.copyfile(client["ecg"], folder / "ecg-12-lead.csv")
        for src, name in MAMMO_VIEWS.items():
            shutil.copyfile(MAMMO / src, folder / name)
        shutil.copyfile(NOTE, folder / "discharge-note.txt")
        (folder / "client.json").write_text(json.dumps(client["client"], indent=2), encoding="utf-8")
        (folder / "blood-panel.json").write_text(json.dumps(client["blood"], indent=2), encoding="utf-8")
        # .md rather than .txt: the drop zone does not take Markdown, so the
        # note reader is never handed the folder's own readme.
        (folder / "README.md").write_text(
            f"{client['client']['name']}\n\n{client['story']}\n\n"
            "Drop every file in this folder into the intake form (the zone on the first step).\n"
            "client.json fills the client and the cover; blood-panel.json fills the lab reader;\n"
            "every other file is identified and sent to its reader.\n",
            encoding="utf-8",
        )
        print(f"{folder.name}: {sum(1 for _ in folder.iterdir())} files")

    (OUT / "README.md").write_text(
        "# Test folders\n\nFive clients, low risk to elevated, each with a file for every reader.\n"
        "Drop a whole folder into the intake form. Regenerate with `python scripts/make_demo_tests.py`.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
