# Dashboard — what to build

**For:** whoever owns login and the dashboard UI.
**Stack:** React 19 + Vite + Mantine 9 + TanStack Query, already scaffolded in
`apps/web`. Theme and API client are in place.

Read [SPEC.md §1 "The operating flow"](SPEC.md) first. The whole design follows
from one fact: **there are two separate moments, and the client is only present
for the first one.**

| Moment | Who | Under time pressure? | Screen |
|---|---|---|---|
| **Intake** | Operator, client sitting opposite | **Yes** — do not make them wait | The form |
| **Review** | Underwriter, 1–2 days later, alone | No | Review workspace |

These are different jobs. **Do not merge them into one screen.** Intake is data
entry that must not lose anything; review is careful reading.

---

## Screen map

```
/login                     email + password
/                          Queue — all applications, filterable
/applications/new          Intake form          ← the important one
/applications/:id          Review workspace
/notifications             Notification list
```

Five screens. That is the whole dashboard for Phase 1.

---

## 1. Login

Email + password + submit. Nothing else — no signup, no password reset, no SSO.
Users are created by seed data or by an admin.

On success the API sets an **httpOnly cookie**. The token is never in
`localStorage` and never in JavaScript — with medical data, an XSS bug must not
hand over a session.

Because the cookie is httpOnly the frontend cannot read it. To know who is logged
in, call `GET /api/auth/me`. A `401` from any endpoint means redirect to `/login`.

---

## 2. Queue (home)

A table of applications for the logged-in user's tenant, newest first.

| Column | Notes |
|---|---|
| Reference | `external_ref` — the carrier's own ID |
| Submitted | Relative time ("2 days ago") |
| Status | Coloured badge, see below |
| Risk | CRS + tier badge, or `—` when not scored yet |
| Action | "Review" when ready, otherwise nothing |

**Status wording matters — the operator repeats these words to a client.**

| DB value | Show as | Colour |
|---|---|---|
| `submitted` | Evaluation pending | grey |
| `processing` | Evaluating | blue |
| `scored` | Ready for review | teal |
| `insufficient_evidence` | More evidence needed | amber |
| `decided` | Decided | dimmed |

Filter by status, and a prominent **"Review a new client"** button. That button
is the single most-used control in the product — top right, primary colour.

Poll the list with TanStack Query `refetchInterval: 30_000`. Evaluation takes
minutes to hours, so anything faster is wasted requests. The pattern is already
demonstrated in `apps/web/src/App.tsx`.

---

## 3. Intake form — the important screen

The client is sitting across the desk. Every design decision follows from that.

### Build it as ONE page with sections, not a multi-step wizard

Sections stacked on one scrolling page, submitted once at the end.

Why this matters:
- **A wizard can lose data** between steps. Doing that with a client watching is
  the worst failure this product has.
- **The operator jumps around.** Clients answer out of order and correct
  themselves. One page allows that; a wizard fights it.
- It is simpler to build, and needs no draft-saving, no step state, no
  server-side partial records.

Show a small sticky progress hint ("3 of 4 sections complete") if you like — but
one page, one submit.

### Section 1 — Applicant

| Field | Type | Required | Notes |
|---|---|---|---|
| Reference | text | **yes** | The carrier's own client ID. Must be unique per tenant — surface a clear error on collision, do not just fail |
| Date of birth | date | no | |
| Sex | select | no | Female / Male / Other / Prefer not to say |

**There is no name field, deliberately.** The database has no column for it. If
someone asks, that is PII minimisation and it is a feature — see
[DATABASE.md](DATABASE.md).

### Section 2 — Coverage requested

| Field | Type | Required | Notes |
|---|---|---|---|
| Coverage type | select | **yes** | Life / Health / Critical illness |
| Coverage amount | number | **yes** | BDT. Thousands separators |

### Section 3 — Declared health

Checkboxes. The client answers, the operator ticks. **These directly drive the
risk score**, so the labels must be plain enough to read aloud.

**Current symptoms**

- Cough lasting more than 2 weeks
- Unexplained weight loss
- Night sweats
- Coughing up blood
- Fever

**Medical history**

- Previously treated for TB
  - ↳ *if ticked, reveal:* "Completed the full course of treatment"
- Diabetes
- HIV positive
- Someone in the household has had TB
- Took a course of antibiotics without improvement
- Current or former smoker

Group these in two visually distinct blocks. The nested treatment-completed
checkbox should only appear when "previously treated for TB" is ticked —
**that specific pair flips the outcome**, so it must be unambiguous.

Post as the nested JSON shape defined in [DATABASE.md §C](DATABASE.md).

### Section 4 — Evidence

Mantine `Dropzone`, click or drag, multiple files.

| Type | Accept | Phase 1 |
|---|---|---|
| Chest X-ray | `.dcm`, `.png`, `.jpg` | **Required** — nothing can be scored without it |
| Lab report | `.pdf`, `.png`, `.jpg` | Optional, stored only |
| Clinical note | `.pdf`, `.txt` | Optional, stored only |

Each dropped file gets a row showing filename, size, a type dropdown, and a
remove button. Max 50 MB per file — show the limit before they hit it, not after.

**"Stored only" means exactly that.** In Phase 1 only the chest X-ray is
analysed. Do not imply other files are being read.

### Submit

Disabled until: reference filled, coverage type and amount filled, at least one
chest X-ray attached.

On submit — one `POST /api/applications` as `multipart/form-data`, everything in
one request. On success go to a confirmation panel that says, in words the
operator can read aloud:

> **Evaluation pending.**
> Reference `ABC-12345` submitted. Results in **1–2 business days**.

Then two buttons: "Review another client" and "Back to queue".

**Uploads can be slow.** Show real progress, and disable the submit button while
in flight — a client watching a frozen screen is bad, a double submission is
worse.

---

## 4. Review workspace

Opened 1–2 days later, no client present. This screen answers one question:
**should I trust this recommendation, and what do I decide?**

Suggested layout — evidence on the left, reasoning and decision on the right.

### Header

Reference · submitted date · status · **CRS number and tier badge**, large.

Tier colours: Low `teal` · Moderate `yellow` · Elevated `red` ·
Insufficient evidence `gray`.

### Left — the image

The chest X-ray, with a **toggle to overlay the Grad-CAM heatmap**. A simple
on/off switch beats an opacity slider; add the slider only if someone asks.

Both are plain PNGs served from `GET /api/files/:id`. No DICOM viewer library in
Phase 1 — the backend renders the image server-side.

### Right — why this score

**Findings table.** The vision arm returns 18 finding probabilities. Show the top
5 as labelled bars, with the rest behind "Show all 18". Sorted high to low.

**What the declared history changed.** A short list of plain sentences, e.g.
*"Previously treated TB, course completed, no current symptoms → lowered"*.
This is the most valuable panel on the screen — it is the part a pure image
classifier cannot produce, and it is what the underwriter is really reading.

**Model provenance.** Small, dimmed, at the bottom: model name, version,
evaluated timestamp. It matters for the audit story and should be visible but
never prominent.

### Decision panel

Four buttons matching `underwriter_decision_type`:

| Button | Value |
|---|---|
| Confirm fast-track | `confirmed_fast_track` |
| Approve with adjustment | `approved_with_adjustment` |
| Escalate to senior underwriter | `escalated_senior_review` |
| Request more evidence | `requested_additional_evidence` |

"Approve with adjustment" reveals a **final premium** field.

**There is no reject button. There will never be a reject button.** The system
does not deny anyone — escalation to a human is the path. If someone asks for
one, point them at [SPEC.md §7](SPEC.md).

The decision is **write-once**. After submitting, the panel becomes a read-only
summary showing who decided, what, and when. The database enforces this with a
UNIQUE constraint, so the UI should not offer an edit that will fail.

### Audit trail

A collapsed section at the bottom: timestamp, event, actor. Expandable. It rarely
gets opened, and it must be there when it does.

---

## 5. Notifications

A bell in the header with an unread count, and a list page. Clicking an item goes
to its application and marks it read.

Phase 1 needs only in-app notifications. **No email, no SMS** — the enum has
those values for later.

Note the notifications go to *staff*, not to applicants. The operator phones the
client; the platform never contacts them directly.

---

## API contract

**Ownership matters here** — this is the line between your work and mine.

| Method | Path | Owner | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` | **you** | Sets httpOnly cookie |
| POST | `/api/auth/logout` | **you** | Clears it |
| GET | `/api/auth/me` | **you** | Current user + tenant + role |
| GET | `/api/applications` | **you** | Queue list, `?status=&limit=&offset=` |
| POST | `/api/applications` | **you** | Intake, `multipart/form-data` |
| GET | `/api/applications/:id` | **you** | Detail, including score and findings |
| POST | `/api/applications/:id/decision` | **you** | Record the decision |
| GET | `/api/applications/:id/audit` | **you** | Audit trail |
| GET | `/api/notifications` | **you** | List |
| GET | `/api/files/:id` | **you** | Serve an evidence file or heatmap |
| — | *scoring pipeline* | **me** | Runs after intake, writes the score |

I do not add endpoints. I write the rows your `GET /api/applications/:id` reads:
`model_runs`, `sub_scores`, `explanation_artifacts`, `composite_scores`.

**Generate your types, do not hand-write them:**

```bash
npm run gen:api      # with the API running
```

This is already wired up. It is what stops the two halves drifting apart.

---

## States that must be handled

Not edge cases — these will all happen in a demo.

| Situation | What the screen shows |
|---|---|
| Not scored yet | "Evaluation pending", no score panel, no decision buttons |
| Scoring failed | Plain message + "Request more evidence". **Never a blank panel** |
| `insufficient_evidence` | Amber banner explaining what is missing |
| No heatmap produced | Image alone, no broken-image icon |
| Already decided | Read-only summary, buttons gone |
| Session expired | Redirect to `/login`, do not show a broken page |
| Upload fails mid-submit | Keep the form filled, show the error, allow retry |

That last one is the one people forget, and it is the one that happens with a
client sitting there.

---

## Out of scope for Phase 1

Do not build: applicant-facing screens (applicants are not users), a DICOM
viewer, charts and analytics, bulk upload, export/print, dark-mode toggle (dark
is already the default), user management UI, or password reset.

If it is not one of the five screens above, it is not Phase 1.
