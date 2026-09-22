import type { ApplicationStatus } from './api/client'

/**
 * What each application status means, in the words every screen uses.
 *
 * `label` is what is shown; `meaning` is the sentence behind it, shown on
 * hover, so nobody has to guess what "Waiting on client" is waiting for.
 * `live` marks the one status where something is happening right now.
 */
export const STATUS_META: Record<
  ApplicationStatus,
  { label: string; meaning: string; color: string; live?: boolean }
> = {
  submitted: {
    label: 'Queued',
    meaning: 'Received. The models have not started reading the evidence yet.',
    color: 'gray',
  },
  processing: {
    label: 'Reading evidence',
    meaning: 'The models are reading the evidence now. This takes under a minute.',
    color: 'blue',
    live: true,
  },
  scored: {
    label: 'Ready to decide',
    meaning: 'Scored. Waiting for a person to record a decision.',
    color: 'teal',
  },
  insufficient_evidence: {
    label: 'Could not be scored',
    meaning: 'Nothing the models could read arrived. Open it to see why and what to ask for.',
    color: 'yellow',
  },
  // Distinct from the line above: this one waits on the applicant, that one
  // on the operator. Orange, not yellow, so the two do not read as the same.
  awaiting_evidence: {
    label: 'Waiting on client',
    meaning: 'Documents were requested from the client. The answer date is paused until they arrive.',
    color: 'orange',
  },
  decided: {
    label: 'Decided',
    meaning: 'A person has recorded a decision. It cannot be changed.',
    color: 'gray',
  },
}

export const STATUS_ORDER: ApplicationStatus[] = [
  'submitted',
  'processing',
  'scored',
  'insufficient_evidence',
  'awaiting_evidence',
  'decided',
]
