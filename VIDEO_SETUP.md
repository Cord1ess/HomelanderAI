# Video setup

How to get the app running and record the demonstration. Written for whoever is
holding the camera — you do not need to know the codebase.

Everything you need is in this repository. There is no separate download.

---

## 1. Before you start

You need **Node 22+**, **Python 3.12**, **uv**, and **PostgreSQL 17**.

```bash
node --version      # v22 or higher
uv --version
```

If `uv` is missing: `winget install astral-sh.uv` (Windows) or
`curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux).

### Install and set up

From the repository root:

```bash
npm run setup
cp .env.example .env
```

### Start PostgreSQL and create the database

If you have Docker, this is one command:

```bash
npm run infra:up
```

Without Docker, install PostgreSQL 17 and create the role and database:

```bash
psql -U postgres -c "CREATE ROLE homelander LOGIN SUPERUSER PASSWORD 'devpassword';"
psql -U postgres -c "CREATE DATABASE homelander OWNER homelander;"
```

Then apply the schema:

```bash
uv run --directory apps/api python -m alembic upgrade head
```

---

## 2. Start the app

**The mammogram model runs on a server that is currently down.** Start with the
stand-in switched on, or the mammogram panel shows an error on camera:

```bash
MIRAI_SIMULATE=true npm run dev
```

On Windows PowerShell:

```powershell
$env:MIRAI_SIMULATE = "true"; npm run dev
```

Wait for both lines to appear, then open **http://localhost:5173**.

> The first start downloads the model backbones (about 600 MB) and takes a few
> minutes. Later starts are quick. Do not record the first one.

### Check it works before you record

```bash
uv run --directory apps/api python ../../scripts/check_demo.py
```

This submits two applicants end to end and checks every reader ran. It must
print **ALL CHECKS PASSED**. If it does not, stop and send the output to Jonay —
do not try to record around a failure.

### Sign in

| Who | Username | Password |
|---|---|---|
| Underwriter | `underwriter` | `admin123` |
| Medical professional | `medical` | `admin123` |
| Administrator | `admin` | `admin123` |

---

## 3. The five applicants

They live in `demo/test/`. **Drag a whole folder** into the drop zone — the
platform identifies each file and fills in the form. Nothing is typed.

| Folder | Who | Comes out | What it shows |
|---|---|---|---|
| `test-01-rahim` | Rahim Uddin, 34 | **low** | Everything clean. The happy path. |
| `test-02-fatema` | Fatema Begum, 52 | **moderate** | Diabetic retinopathy, high glucose, and the mammogram. |
| `test-03-karim` | Karim Hossain, 61 | **elevated** | Tuberculosis on the chest film. |
| `test-04-nusrat` | Nusrat Jahan, 45 | **elevated** | Atrial fibrillation on the ECG. |
| `test-05-malek` | Abdul Malek, 70 | **elevated** | Conduction block, kidney values, severe retinopathy. |

Only Fatema and Nusrat carry a mammogram — that is correct, not a missing file.
Screening mammography is offered to women from about forty, so the three men's
folders run five readers instead of six.

`demo/clients/` is the same five people with images only, for a shorter take.

---

## 4. What to record

Six parts. Each is a separate clip; record them in this order.

### Part 1 — The landing page (about 30 seconds)

Open **http://localhost:5173** signed out.

Scroll slowly from the top through the timeline to the bottom. Pause a beat on
the two buttons: **Sign in** (for staff) and **Check status** (for applicants).

### Part 2 — A clean application, start to finish (about 3 minutes)

The main clip. Sign in as **underwriter**.

1. **Applications** in the sidebar — show the queue with existing cases.
2. **New application**, top right.
3. Open `demo/test/test-01-rahim` in your file manager, select **all seven
   files**, and drag them onto the drop zone in one go.
4. **Pause here.** The form fills itself in: name, date of birth, cover, the
   blood values, the health questions. Let it land on camera — this is the part
   people remember.
5. Scroll down through the identified files. Each one names what it is and which
   reader takes it.
6. **Submit.** A reference appears (`HL-…`) along with the applicant's portal
   sign-in. **Write both down** — you need them for Part 5.
7. The queue shows it scoring. It takes about a minute.
8. Open it when it turns green.

### Part 3 — The review screen (about 2 minutes)

Stay on Rahim's application.

- The score at the top: **low**, with the tier boundaries beside it.
- Each reader's panel, scrolling down: chest X-ray, retina, ECG, the clinical
  note, the blood panel. Each shows its score and what it found.
- Toggle **Heatmap overlay** on the chest X-ray and pause on it.
- The findings list, ranked by how much each moved the score.

### Part 4 — A harder case and the hand-over (about 3 minutes)

Submit `demo/test/test-03-karim` the same way as Part 2.

- He comes out **elevated** — the chest film shows tuberculosis.
- On the review screen, show the chest panel and its heatmap.
- Choose **Escalate to a medical professional**, type a short note, confirm.
- Sign out. Sign in as **medical** (`admin123`).
- **Escalations** in the sidebar — Karim's case is waiting.
- Open it, and record the decision.

### Part 5 — The applicant's side (about 1 minute)

Sign out completely.

- **Check status** on the landing page.
- Enter the portal ID and password from Part 2.
- Show the stage the application has reached, and the offer when there is one.

> The applicant sees the **decision only** — no risk score, no model findings.
> Worth saying out loud if you are narrating.

### Part 6 — The mammogram and the administrator (about 2 minutes)

Sign in as **underwriter** and submit `demo/test/test-02-fatema`.

- She comes out **moderate**.
- Scroll to the mammogram panel. It carries an orange banner saying the reading
  is **simulated**. **Show this banner** — do not crop it out. It is there
  because the real mammogram server is down, and the honesty is the point.

Then sign out and sign in as **admin**:

- **Company settings** — the risk-score boundaries.
- **Plans and pricing** — what each tier costs.
- **Staff** — the three accounts.

Finish on **Analytics** for a closing shot.

---

## 5. If something goes wrong

**`npm run dev` fails with "socket ... forbidden by its access permissions"
(WinError 10013), or "address already in use".**
Something is already on port 8000 — almost always an API server from an earlier
run that did not shut down. Close the other terminal, or:

```powershell
netstat -ano | findstr :8000          # last column is the process id
taskkill /PID <that number> /F
```

Then `npm run dev` again. Same for port 5173 and the dashboard.

**`npm run dev` fails some other way, or the dashboard has no data.**
Check the database is running: open http://127.0.0.1:8000/api/health/database —
it should say `"connected": true`. If not, start PostgreSQL and try again.

**The mammogram panel shows an error instead of a reading.**
You started without the stand-in. Stop the app and start it again with
`MIRAI_SIMULATE=true`.

**A file is not recognised on the drop zone.**
Make sure you dragged the whole folder's contents, including `client.json` and
`blood-panel.json`. Those two fill the form and are not sent to any reader.

**Scoring takes more than two minutes.**
The first application after a fresh start loads the models. Submit one throwaway
application before you start recording, and delete the take.

**Anything else.**
Run `scripts/check_demo.py` (Section 2) and send Jonay the output.

---

## 6. Notes for whoever edits

- Record at 1080p or better. The review screen has small text.
- Light mode reads better on a projector; the toggle is in the top bar.
- The reference numbers (`HL-001234`) differ every run — do not cut between
  takes in a way that makes them jump.
- The simulated-mammogram banner is deliberate. Leave it in.
