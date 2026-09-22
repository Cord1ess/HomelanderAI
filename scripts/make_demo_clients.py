"""Assemble five demo clients under data/demo/clients/, one folder each.

    python scripts/make_demo_clients.py

Each folder holds the files an operator drags into the intake form's
"drop everything" zone (a chest X-ray, a retinal photo, an ECG export) and a
`client.txt` with what to type: the client's details, the cover, the blood
values for the lab reader and the health questions to tick.

The files come from the public samples already on disk (Shenzhen chest films
in data/demo, EyePACS retinal photographs in samples/retina, CODE-test ECGs in
data/ecg/demo). Nothing is invented except the names, and the blood values,
which are chosen to be plausible for the story each client tells. Every file
is copied, so the originals are untouched.

data/ is gitignored, so run this on each machine that will demo.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo" / "clients"
CHEST_NORMAL = ROOT / "data" / "demo" / "01-normal"
CHEST_TB = ROOT / "data" / "demo" / "02-tuberculosis"
RETINA = ROOT / "samples" / "retina"
ECG = ROOT / "data" / "ecg" / "demo"

# Each client: the story, the files (source -> name in the folder), and what
# to type. Ordered so a demo can run low to elevated.
CLIENTS = [
    {
        "folder": "client-01-rahim",
        "story": "Healthy 34-year-old. Everything should read clean: low tier, standard rate.",
        "files": {
            CHEST_NORMAL / "normal-01-shenzhen-0197_0.png": "chest-xray.png",
            RETINA / "13_left.jpeg": "retina-left.jpeg",
            ECG / "normal_codetest_000.csv": "ecg-12-lead.csv",
        },
        "details": {
            "Name": "Rahim Uddin",
            "Phone": "01711 000101",
            "Email": "rahim.uddin@example.com",
            "Date of birth": "1992-03-14",
            "Sex": "Male",
            "Cover": "Life, 1,000,000, 20 years",
        },
        "blood": {
            "Serum albumin (g/dL)": 4.5,
            "Serum creatinine (mg/dL)": 0.9,
            "Glucose (mg/dL)": 88,
            "C-reactive protein (mg/L)": 0.6,
            "Lymphocytes (%)": 32,
            "Mean cell volume (fL)": 88,
            "RDW-CV (%)": 12.4,
            "Alkaline phosphatase (U/L)": 62,
            "White blood cells (x10^3/uL)": 5.8,
        },
        "questions": "Tick nothing. No symptoms, no history.",
    },
    {
        "folder": "client-02-fatema",
        "story": "52-year-old with diabetes. The retina shows moderate retinopathy; blood sugar is high. Expect moderate: approved with an adjusted premium.",
        "files": {
            CHEST_NORMAL / "normal-02-shenzhen-0039_0.png": "chest-xray.png",
            RETINA / "15_right.jpeg": "retina-right.jpeg",
            ECG / "normal_codetest_002.csv": "ecg-12-lead.csv",
        },
        "details": {
            "Name": "Fatema Begum",
            "Phone": "01711 000102",
            "Email": "fatema.begum@example.com",
            "Date of birth": "1974-07-02",
            "Sex": "Female",
            "Cover": "Health, 500,000, 10 years",
        },
        "blood": {
            "Serum albumin (g/dL)": 4.1,
            "Serum creatinine (mg/dL)": 1.0,
            "Glucose (mg/dL)": 168,
            "C-reactive protein (mg/L)": 3.2,
            "Lymphocytes (%)": 27,
            "Mean cell volume (fL)": 90,
            "RDW-CV (%)": 13.6,
            "Alkaline phosphatase (U/L)": 84,
            "White blood cells (x10^3/uL)": 7.1,
        },
        "questions": "Tick: Diabetes (history). Retinal reader: diabetes duration 8 years.",
    },
    {
        "folder": "client-03-karim",
        "story": "61-year-old smoker with a six-week cough. The chest film shows tuberculosis. Expect elevated: the underwriter escalates, a medical professional decides.",
        "files": {
            CHEST_TB / "tb-01-shenzhen-0648_1.png": "chest-xray.png",
            RETINA / "17_left.jpeg": "retina-left.jpeg",
            ECG / "normal_codetest_003.csv": "ecg-12-lead.csv",
        },
        "details": {
            "Name": "Karim Hossain",
            "Phone": "01711 000103",
            "Email": "karim.hossain@example.com",
            "Date of birth": "1965-11-23",
            "Sex": "Male",
            "Cover": "Life, 2,500,000, 15 years",
        },
        "blood": {
            "Serum albumin (g/dL)": 3.7,
            "Serum creatinine (mg/dL)": 1.1,
            "Glucose (mg/dL)": 102,
            "C-reactive protein (mg/L)": 14.0,
            "Lymphocytes (%)": 18,
            "Mean cell volume (fL)": 93,
            "RDW-CV (%)": 14.8,
            "Alkaline phosphatase (U/L)": 96,
            "White blood cells (x10^3/uL)": 9.4,
        },
        "questions": "Tick: Cough lasting more than 2 weeks, Night sweats, Unexplained weight loss; Current or former smoker.",
    },
    {
        "folder": "client-04-nusrat",
        "story": "45-year-old with palpitations and hypertension. The ECG shows atrial fibrillation. Expect moderate to elevated depending on the boundaries.",
        "files": {
            CHEST_NORMAL / "normal-03-shenzhen-0225_0.png": "chest-xray.png",
            RETINA / "10_left.jpeg": "retina-left.jpeg",
            ECG / "AF_codetest_120.csv": "ecg-12-lead.csv",
        },
        "details": {
            "Name": "Nusrat Jahan",
            "Phone": "01711 000104",
            "Email": "nusrat.jahan@example.com",
            "Date of birth": "1981-05-09",
            "Sex": "Female",
            "Cover": "Critical illness, 1,500,000, 20 years",
        },
        "blood": {
            "Serum albumin (g/dL)": 4.2,
            "Serum creatinine (mg/dL)": 0.8,
            "Glucose (mg/dL)": 94,
            "C-reactive protein (mg/L)": 2.1,
            "Lymphocytes (%)": 30,
            "Mean cell volume (fL)": 87,
            "RDW-CV (%)": 12.9,
            "Alkaline phosphatase (U/L)": 70,
            "White blood cells (x10^3/uL)": 6.3,
        },
        "questions": "Tick: Hypertension; ECG reader: Palpitations or irregular heartbeat.",
    },
    {
        "folder": "client-05-malek",
        "story": "70-year-old with a conduction block on the ECG and kidney values off. Expect elevated: escalation, then a medical decision.",
        "files": {
            CHEST_TB / "tb-02-shenzhen-0403_1.png": "chest-xray.png",
            RETINA / "16_left.jpeg": "retina-left.jpeg",
            ECG / "LBBB_codetest_001.csv": "ecg-12-lead.csv",
        },
        "details": {
            "Name": "Abdul Malek",
            "Phone": "01711 000105",
            "Email": "abdul.malek@example.com",
            "Date of birth": "1956-01-30",
            "Sex": "Male",
            "Cover": "Life, 3,000,000, 10 years",
        },
        "blood": {
            "Serum albumin (g/dL)": 3.4,
            "Serum creatinine (mg/dL)": 1.9,
            "Glucose (mg/dL)": 131,
            "C-reactive protein (mg/L)": 8.5,
            "Lymphocytes (%)": 16,
            "Mean cell volume (fL)": 97,
            "RDW-CV (%)": 15.9,
            "Alkaline phosphatase (U/L)": 118,
            "White blood cells (x10^3/uL)": 8.8,
        },
        "questions": "Tick: Diabetes, Hypertension, Current or former smoker; ECG reader: Known arrhythmia or pacemaker.",
    },
]


def main() -> int:
    missing = [
        src for client in CLIENTS for src in client["files"] if not Path(src).is_file()
    ]
    if missing:
        print("Missing source files; see docs/DEMO_SETUP.md for how to fetch the demo data:")
        for m in missing:
            print(f"  {m}")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    for client in CLIENTS:
        folder = OUT / client["folder"]
        folder.mkdir(exist_ok=True)
        for src, name in client["files"].items():
            shutil.copyfile(src, folder / name)
        lines = [
            f"{client['details']['Name']}",
            "",
            client["story"],
            "",
            "CLIENT (type into step 1)",
        ]
        lines += [f"  {k}: {v}" for k, v in client["details"].items() if k != "Cover"]
        lines += ["", "COVER (step 2)", f"  {client['details']['Cover']}", ""]
        lines += ["FILES (drop all of them into the zone at the top of step 3)"]
        lines += [f"  {name}" for name in client["files"].values()]
        lines += ["", "BLOOD PANEL (select the lab reader in step 3 and type these)"]
        lines += [f"  {k}: {v}" for k, v in client["blood"].items()]
        lines += ["", "HEALTH QUESTIONS", f"  {client['questions']}", ""]
        (folder / "client.txt").write_text("\n".join(lines), encoding="utf-8")
        print(f"{folder.name}: {len(client['files'])} files + client.txt")

    (OUT / "README.md").write_text(
        "# Demo clients\n\n"
        "Five folders, one client each, ordered low risk to elevated. Open `client.txt`\n"
        "in a folder for what to type, then drag the other files into the intake form.\n"
        "Regenerate with `python scripts/make_demo_clients.py`.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
