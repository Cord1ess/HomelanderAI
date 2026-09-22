# Medication check — how it works

A clinical note, discharge summary or prescription goes in as text. The arm
finds the medications named in it, looks up what each one is prescribed for,
and compares that with what the applicant declared on the intake form. Every
condition a medication implies that was declared nowhere comes out as a
question for the underwriter to ask, and the most serious of them sets the
arm's score.

This is the oldest check in underwriting — read the prescriptions — done
consistently. It is deliberately a table and a set of rules, not a model:
every flag traces to one row in one file, and a drug the table does not know
produces nothing rather than a guess.

---

## Why prescriptions, not diagnoses

A note paraphrases, abbreviates and omits diagnoses ("DM", "sugar", "on
treatment for pressure"). It spells drug names the same way everywhere, and a
drug has a short list of reasons to be prescribed. Metformin on a discharge
summary is diabetes with near certainty; "known case of DM" may or may not be
written. The medication list is the one part of a note that reads reliably.

## What goes in

**File:** `apps/api/app/intake.py`

- A `.txt` (or `.md`, `.csv`, `.tsv`) file that is not a 12-lead ECG export,
  or a PDF **with a text layer**. Both are stored as plain UTF-8 text.
- A scanned PDF has no text layer and is refused with that reason. Optical
  character recognition would produce a note the arm could not vouch for;
  saying "export or type the text" is more useful than a silent miss.
- The note is **not de-identified**. It names its patient throughout and
  cannot be stripped without reading it, so the evidence row records that
  honestly (`deidentified_at` is null) and the text is shown only to the
  underwriter who holds the case. The arm stores the sentences it matched,
  not the note.

## The table

**File:** `apps/api/app/arms/medications.json`

Two lists:

**Conditions** — each with a label, a weight out of 100, and how the intake
form declares it (`declared_by`). Diabetes, for example, is declared by the
chest panel's history box or by any answer but "No diabetes" on the retina
panel. Conditions the form never asks about have an empty `declared_by`; a
flag on one of those says so ("the form does not ask about this").

| Condition | Weight | Condition | Weight |
|---|---|---|---|
| Tuberculosis under treatment | 85 | Epilepsy | 55 |
| HIV | 85 | Autoimmune disease | 50 |
| Cancer | 85 | Diabetes | 45 |
| Transplant | 85 | Long-term steroids | 45 |
| Heart failure | 80 | Asthma / COPD | 40 |
| Chronic kidney disease | 80 | Hypertension | 35 |
| Stroke / TIA | 75 | Depression / anxiety | 35 |
| Opioid dependence | 75 | High cholesterol | 30 |
| Coronary heart disease | 70 | Smoking (cessation drugs) | 30 |
| Hepatitis B | 70 | Thyroid disease | 20 |
| Dementia | 70 | Gout | 15 |
| Arrhythmia / anticoagulation | 65 | Osteoporosis | 15 |
| Parkinson's | 65 | Bipolar / psychosis | 60 |
| Hepatitis C | 65 | Alcohol dependence | 60 |
| DVT / pulmonary embolism | 45 | | |

The weights are an underwriting judgement about how much an undeclared case
of each would matter, and they live in JSON so they can be argued about
without touching code. They are not published figures.

**Medications** — about 150 generics, each with the brand names an applicant
in Bangladesh is likely to write (DGDA-registered products such as Comet,
Amdocal, Seclo, Napa, alongside the global originators), an ATC code, and
the conditions it is prescribed for, following the BNF and the MED-RT
`may_treat` relation. A row with several conditions lists them in order of
likelihood and is marked **ambiguous**. Rows with no condition (omeprazole,
paracetamol, antibiotics) are there so those drugs are seen and reported as
immaterial rather than silently ignored.

## Reading the note

**File:** `apps/api/app/arms/medication_check.py`

1. **Sentences.** Split on sentence punctuation and on line breaks — notes
   are terse, and a line is usually one statement.
2. **Names.** One regular expression of every name, longest first, at word
   boundaries, case-insensitive — except short capitalised abbreviations
   (INH, PTU, GTN, HCTZ), which are matched only as written because in lower
   case they are ordinary letters. "Insulin glargine" wins over "insulin";
   "insulin resistance" and "lithium level" are measurements and not
   prescriptions, and are skipped.
3. **Assertion.** The same clause rules the clinical-note service uses decide
   whether each mention is the applicant's, present-tense prescription:
   - *negated*: "allergic to amoxicillin", "no metformin"
   - *family*: "mother takes levothyroxine"
   - *hypothetical*: "consider insulin if HbA1c stays above 9"
   - *past*: "stopped warfarin in 2024" — this one **does** count. A
     condition that once needed treatment is still a condition the form
     should have heard about.
   - "as needed" is how an inhaler is prescribed and is not hypothetical.
4. **Comparison.** For each medication that counts, its conditions are
   compared with the set the form declared. Any one declared condition
   explains the medication. If none is, each of its conditions becomes a flag
   worth the condition's weight — halved when the medication is ambiguous.
   Four TB drugs for one condition are one flag, not four.

## The score

- The highest flag governs, as the highest reading governs everywhere else.
- Every medication explained or immaterial: **10**.
- Medications found but none implying anything material: **5**.
- No medication in the table named at all: **no score**, with the reason. A
  low number there would read as reassurance about a note that was never
  actually checked.

An undeclared tuberculosis course therefore sends the application to senior
review on its own; an undeclared amlodipine puts it in the moderate band with
a question attached; a fully declared history leaves the note in the low
band. The panel on the review screen lists every flag with the sentence it
came from, every medication with its status, what was not counted and why,
and the note itself.

## What it does not do

- **It does not know drugs outside the table.** Add a row. There is no
  fuzzy matching, so a misspelling is a miss, not a wrong hit.
- **It does not read scans.** Text layer or nothing.
- **It does not infer a diagnosis from anything but a prescription.** "Known
  case of DM" in the note is left to the underwriter; the arm reads only the
  drug list. That is its whole claim to reliability.
- **It does not decide.** A flag is a question to ask the applicant, and the
  screen says so on every one.

## Showing it

`docs/demo/discharge_summary_sample.txt` is a fictional discharge summary
written for the demo. Upload it on the "Clinical notes and prescriptions"
panel with only diabetes declared and the arm flags the blood-pressure tablet,
the statin, the aspirin, the inhaler and the old warfarin course; declare
hypertension and cholesterol too and those flags become "declared". The
relative's levothyroxine, the penicillin allergy and the insulin that was only
being considered are listed as not counted.

## Files

    apps/api/app/arms/medication_check.py    the arm
    apps/api/app/arms/medications.json       conditions, weights, medications, brands
    apps/api/app/intake.py                   documents: text and PDF text layers
    apps/api/tests/test_medication_check.py
