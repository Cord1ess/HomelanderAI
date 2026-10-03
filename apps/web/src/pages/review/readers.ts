/**
 * What every reader is called, what it reads, and how its result is summed up.
 *
 * Shared by the result page and the client profile, so a reader is described
 * the same way wherever it appears.
 */
import {
  IconActivityHeartbeat,
  IconDroplet,
  IconEye,
  IconLungs,
  IconMicroscope,
  IconPill,
  IconRibbonHealth,
} from '@tabler/icons-react'

import type { ApplicationDetail, ArmRun } from '../../api/client'

export interface ReaderInfo {
  title: string
  /** What the reader looks at and what it answers, in one line. */
  reads: string
  /** The kind of evidence file it reads, to put that file in its section. */
  evidenceKind?: string
  /** Wide evidence (an ECG tracing) goes above the result, not beside it. */
  stacked?: boolean
  icon: typeof IconLungs
}

/** Every reader, in the order an underwriter would read them. */
export const READERS: Record<string, ReaderInfo> = {
  tb_xray: {
    title: 'Chest X-ray',
    reads: 'Tuberculosis screen from the chest film',
    evidenceKind: 'chest_xray',
    icon: IconLungs,
  },
  dr_fundus: {
    title: 'Retina',
    reads: 'Diabetic retinopathy grade from the retinal photo',
    evidenceKind: 'fundus',
    icon: IconEye,
  },
  ecg_12lead: {
    title: '12-lead ECG',
    reads: 'Six rhythm and conduction abnormalities, and an ECG age',
    evidenceKind: 'ecg',
    stacked: true,
    icon: IconActivityHeartbeat,
  },
  mirai: {
    title: 'Mammogram',
    reads: 'Five-year breast-cancer risk from the four views (Mirai)',
    evidenceKind: 'mammogram',
    icon: IconRibbonHealth,
  },
  medication_check: {
    title: 'Clinical note',
    reads: 'Medications and diagnoses written in the note, read by BioBERT',
    icon: IconPill,
  },
  mortality: {
    title: 'Blood panel',
    reads: 'Mortality against a same-age peer, from nine blood values and lifestyle',
    icon: IconDroplet,
  },
}

export const infoFor = (arm: string): ReaderInfo =>
  READERS[arm] ?? { title: arm, reads: 'A reader with no section of its own', icon: IconMicroscope }

export interface Limits {
  low: number
  moderate: number
}

/** The company's tier boundaries, which every reader's score is read against. */
export function limitsOf(data: ApplicationDetail): Limits {
  const t = (data.score?.thresholds ?? {}) as Record<string, unknown>
  return { low: Number(t.low_max ?? 30), moderate: Number(t.moderate_max ?? 65) }
}

export function bandFor(score: number | null | undefined, limits: Limits) {
  if (score == null) return null
  if (score <= limits.low) return { label: 'low', color: 'teal' }
  if (score <= limits.moderate) return { label: 'moderate', color: 'yellow' }
  return { label: 'elevated', color: 'red' }
}

/** One tab per reader, in reading order; a reader that ran twice keeps both runs. */
export function groupRuns(runs: ArmRun[]): { arm: string; runs: ArmRun[] }[] {
  const order = [...Object.keys(READERS), ...runs.map((r) => r.arm)]
  return [...new Set(order)]
    .map((arm) => ({ arm, runs: runs.filter((r) => r.arm === arm) }))
    .filter((g) => g.runs.length > 0)
}

/** What a reader concluded, in the few words that fit on its card. */
export function headlineOf(run: ArmRun, limits: Limits): string {
  if (run.error) return 'Could not be read'
  const details = run.details ?? {}
  switch (run.arm) {
    case 'tb_xray': {
      const c = (details as { contributions?: Record<string, number> }).contributions ?? {}
      const top = Object.entries(c).sort((x, y) => y[1] - x[1])[0]
      const low = run.score != null && run.score <= limits.low
      return !low && top && top[1] > 0 ? `Pushed up by ${top[0]}` : 'Nothing points towards TB'
    }
    case 'dr_fundus': {
      const r = details as { grade_name?: string; referable_probability?: number }
      const referral =
        r.referable_probability != null ? `Referral ${(r.referable_probability * 100).toFixed(0)}%` : null
      return [referral, r.grade_name ? `${r.grade_name} most likely` : null].filter(Boolean).join(' · ')
    }
    case 'ecg_12lead': {
      const reported = (details as { reported_labels?: string[] }).reported_labels ?? []
      return reported.length ? reported.join(', ') : 'No abnormality reported'
    }
    case 'mirai': {
      const five = (details as { five_year_risk?: number }).five_year_risk
      return five != null ? `5-year risk ${(five * 100).toFixed(1)}%` : 'No result'
    }
    case 'medication_check': {
      const n = ((details as { undisclosed?: unknown[] }).undisclosed ?? []).length
      return n ? `${n} undeclared condition${n === 1 ? '' : 's'}` : 'Agrees with the form'
    }
    case 'mortality': {
      const ratio = (details as { mortality_ratio?: number }).mortality_ratio
      return ratio != null ? `Mortality ${ratio.toFixed(2)}× a peer` : 'No result'
    }
    default:
      return ''
  }
}
