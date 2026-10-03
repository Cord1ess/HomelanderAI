/**
 * The readers the intake form knows, and the questions each one asks.
 *
 * Shared by the intake form and the owner's model test bench, so a question is
 * asked the same way, with the same keys, wherever a model is run.
 */

export type Scalar = string | boolean | number | string[] | null

export interface ModelValues {
  [key: string]: Scalar
}

export type SimpleField =
  | { kind: 'checkbox'; key: string; label: string }
  | { kind: 'select'; key: string; label: string; data: string[]; placeholder?: string }
  | { kind: 'number'; key: string; label: string; description?: string }

/**
 * File-type filters, as MIME-type keys with extensions in the value array.
 *
 * The shape matters. react-dropzone validates the **key** as a MIME type and
 * silently drops any entry whose key is not one, warning to the console. Passing
 * an array of bare extensions (`['.dcm', '.png']`) leaves an empty accept object
 * — which disables filtering entirely and accepts every file type.
 *
 * `.dcm` has no registered browser MIME type and most browsers report an empty
 * string for it, so the extension in the value array is what actually matches.
 */
export type AcceptMap = Record<string, string[]>

export const DICOM: AcceptMap = { 'application/dicom': ['.dcm'] }
export const PHOTO: AcceptMap = { 'image/png': ['.png'], 'image/jpeg': ['.jpg', '.jpeg'] }
export const DOCUMENT: AcceptMap = { 'application/pdf': ['.pdf'], 'text/plain': ['.txt'] }
export const ECG_EXPORT: AcceptMap = { 'text/csv': ['.csv'], 'text/plain': ['.txt', '.tsv'] }

export interface ModelDef {
  id: string
  label: string
  modality: string
  upload: { category: string; accept: AcceptMap; instruction: string } | null
  fields: SimpleField[]
}

/**
 * Declared-health options.
 *
 * `key` is what the scoring engine matches on and MUST NOT be edited casually —
 * the authoritative list is SYMPTOM_KEYS and RULES in
 * `apps/api/app/scoring.py`, mirrored in docs/TB.md. A key that does not match
 * fails silently: the rule simply never fires and the applicant is scored on
 * imaging alone. `label` is display text and is safe to reword.
 */
export interface Option {
  key: string
  label: string
}

export const SYMPTOMS: Option[] = [
  { key: 'cough_over_2_weeks', label: 'Cough lasting more than 2 weeks' },
  { key: 'weight_loss', label: 'Unexplained weight loss' },
  { key: 'night_sweats', label: 'Night sweats' },
  { key: 'haemoptysis', label: 'Coughing up blood' },
  { key: 'fever', label: 'Fever' },
]

export const HISTORY_ONCE: Option[] = [
  { key: 'diabetes', label: 'Diabetes' },
  { key: 'hiv', label: 'HIV positive' },
  { key: 'household_tb_contact', label: 'Someone in the household has had TB' },
  { key: 'antibiotics_no_improvement', label: 'Took a course of antibiotics without improvement' },
  { key: 'smoker', label: 'Current or former smoker' },
]

export const CARDIO: Option[] = [
  { key: 'hypertension', label: 'Hypertension' },
  { key: 'high_cholesterol', label: 'High cholesterol' },
  { key: 'family_heart_disease', label: 'Family history of heart disease' },
]

// The model registry drives the whole form. Adding or dropping an arm is one
// entry here (see docs/INTAKE_FORM.md and SPEC.md §6).
export const MODELS: ModelDef[] = [
  {
    id: 'cxr_lung',
    label: 'Chest X-ray',
    modality: 'TorchXRayVision (DenseNet)',
    upload: {
      category: 'Chest X-ray',
      accept: { ...DICOM, ...PHOTO },
      instruction: 'Chest X-ray — .dcm, .png, or .jpg',
    },
    fields: [],
  },
  {
    id: 'mirai',
    label: 'Mirai',
    modality: 'Breast · mammography',
    upload: {
      category: 'Mammogram',
      accept: DICOM,
      instruction: 'Screening mammogram, all four views (right/left MLO and CC) — four .dcm files',
    },
    fields: [
      { kind: 'checkbox', key: 'family_breast_cancer', label: 'Family history of breast cancer' },
      { kind: 'checkbox', key: 'prior_biopsy', label: 'Prior breast biopsy' },
      {
        kind: 'select',
        key: 'brca_status',
        label: 'Known BRCA / genetic test result',
        data: ['Not tested', 'Negative', 'Positive'],
        placeholder: 'Not tested',
      },
    ],
  },
  {
    id: 'eyepacs',
    label: 'EyePACS',
    modality: 'Retinopathy · fundus',
    upload: {
      category: 'Retinal photo',
      accept: { ...PHOTO, ...DICOM },
      instruction: 'Retinal / fundus photo — .png, .jpg, or .dcm',
    },
    fields: [
      {
        kind: 'select',
        key: 'diabetes_duration',
        label: 'Diabetes duration',
        data: ['No diabetes', 'Under 5 years', '5–10 years', 'Over 10 years'],
        placeholder: 'Select',
      },
      { kind: 'checkbox', key: 'hypertension', label: 'Hypertension' },
      { kind: 'checkbox', key: 'smoker', label: 'Current or former smoker' },
    ],
  },
  {
    id: 'ecg',
    label: '12-lead ECG',
    modality: 'Rhythm · conduction · ECG age',
    upload: {
      category: '12-lead ECG',
      // The signal the machine exports, not a picture of it: a scanned strip
      // holds 2.5 s of each lead at poor fidelity, and the models want ten.
      accept: ECG_EXPORT,
      instruction: 'ECG export with all 12 leads and a time column or sampling rate — .csv or .txt',
    },
    fields: [
      { kind: 'checkbox', key: 'palpitations', label: 'Palpitations or irregular heartbeat' },
      { kind: 'checkbox', key: 'known_arrhythmia', label: 'Known arrhythmia or pacemaker' },
    ],
  },
  {
    id: 'biobert',
    label: 'Clinical notes and prescriptions',
    modality: 'BioBERT · medications and diagnoses',
    upload: {
      category: 'Clinical note',
      accept: DOCUMENT,
      // A scanned PDF has no text layer and is refused with that reason; the
      // note has to be the exported or typed text.
      instruction: 'Discharge summary, prescription or physician report — .pdf (with text) or .txt',
    },
    fields: [],
  },
  {
    id: 'xgboost',
    label: 'Blood panel and lifestyle',
    modality: 'Mortality · phenotypic age',
    upload: null,
    // The nine blood values are Levine's Phenotypic Age inputs, in the units a
    // Bangladeshi laboratory prints. The keys and units are read by
    // `apps/api/app/arms/mortality.py`; a value typed in the wrong unit is
    // refused there rather than silently scored decades older.
    fields: [
      { kind: 'number', key: 'albumin_g_dl', label: 'Serum albumin (g/dL)', description: 'Liver function test. Typical 3.5–5.0. The nine blood values are optional together: with all nine the phenotypic age is computed as well.' },
      { kind: 'number', key: 'creatinine_mg_dl', label: 'Serum creatinine (mg/dL)', description: 'Typical 0.6–1.2.' },
      { kind: 'number', key: 'glucose_mg_dl', label: 'Glucose (mg/dL)', description: 'Fasting if available. Typical 70–100.' },
      { kind: 'number', key: 'crp_mg_l', label: 'C-reactive protein (mg/L)', description: 'Typical under 3. Enter 0 for "below detection".' },
      { kind: 'number', key: 'lymphocyte_pct', label: 'Lymphocytes (%)', description: 'From the CBC differential. Typical 20–40.' },
      { kind: 'number', key: 'mcv_fl', label: 'Mean cell volume (fL)', description: 'From the CBC. Typical 80–100.' },
      { kind: 'number', key: 'rdw_pct', label: 'Red cell distribution width, RDW-CV (%)', description: 'From the CBC. Typical 11.5–14.5. Not RDW-SD.' },
      { kind: 'number', key: 'alp_u_l', label: 'Alkaline phosphatase (U/L)', description: 'Liver function test. Typical 40–130.' },
      { kind: 'number', key: 'wbc_10e3_ul', label: 'White blood cells (×10³/µL)', description: 'From the CBC. Typical 4–11.' },
      // Optional. These feed the kidney, liver and weight readings shown beside
      // the phenotypic age; they never move the score.
      { kind: 'number', key: 'ast_u_l', label: 'AST (U/L) — optional', description: 'Liver function test. With ALT and platelets gives the FIB-4 fibrosis index.' },
      { kind: 'number', key: 'alt_u_l', label: 'ALT (U/L) — optional' },
      { kind: 'number', key: 'platelets_10e3_ul', label: 'Platelets (×10³/µL) — optional', description: 'From the CBC.' },
      { kind: 'number', key: 'sbp_mmhg', label: 'Systolic blood pressure (mm Hg) — optional', description: 'Seated, at rest.' },
      { kind: 'number', key: 'height_cm', label: 'Height (cm)' },
      { kind: 'number', key: 'weight_kg', label: 'Weight (kg)' },
      { kind: 'select', key: 'alcohol', label: 'Alcohol use', data: ['None', 'Occasionally', 'Regularly'], placeholder: 'Select' },
      { kind: 'select', key: 'activity', label: 'Physical activity', data: ['Sedentary', 'Light', 'Moderate', 'Active'], placeholder: 'Select' },
      { kind: 'select', key: 'occupation', label: 'Occupation', data: ['Office / professional', 'Manual / physical', 'Retired', 'Student', 'Not employed'], placeholder: 'Select' },
      { kind: 'checkbox', key: 'smoker', label: 'Current or former smoker' },
    ],
  },
]


/**
 * Turn the form's per-model state into the `declared_history` shape the API
 * stores and the scoring engine reads (DATABASE.md §C):
 *
 *   { cxr_lung: { symptoms: { cough_over_2_weeks: true, ... },
 *                 history:  { prior_tb: true, ... } } }
 *
 * The form tracks ticked boxes as arrays of keys; the contract is an explicit
 * true/false per option. Sending the array instead would mean every rule reads
 * a missing key as false and never fires.
 */
export function declaredHistory(
  selectedModels: string[],
  modelFields: Record<string, ModelValues>,
): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {}

  for (const id of selectedModels) {
    const values = modelFields[id] ?? {}
    const block: Record<string, unknown> = {}

    if (id === 'cxr_lung') {
      const flags = (group: Option[], picked: unknown) =>
        Object.fromEntries(
          group.map((o) => [o.key, ((picked as string[]) ?? []).includes(o.key)]),
        )

      block.symptoms = flags(SYMPTOMS, values.symptoms)
      block.history = {
        ...flags(HISTORY_ONCE, values.history),
        prior_tb: values.prior_tb === true,
        // null (unanswered) is gated at submit, so this is only ever a real answer.
        prior_tb_treatment_completed: values.prior_tb_treatment_completed === 'yes',
      }
      block.cardio = flags(CARDIO, values.cardio)
    } else {
      // Every other arm's fields are already scalars keyed by `key`.
      Object.assign(block, values)
    }

    out[id] = block
  }

  return out
}

export function bool(v: Scalar | undefined) {
  return v === true
}
