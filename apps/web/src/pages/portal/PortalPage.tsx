import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { ApiError, getPortalStatus, portalLogout } from '../../api/client'
import type { PortalStatus } from '../../api/client'
import { BrandIcon } from '../../components/BrandIcon'

/**
 * The client portal: one applicant reading their own application.
 *
 * It answers the three things an applicant wants to know, in this order: where
 * is it, when will I hear, and do you need anything from me. Once a person has
 * decided, it shows the outcome.
 *
 * There is no risk score or model finding here, and no way to add one by
 * accident: `PortalStatus` has no such field (see schemas/portal.py for why).
 *
 * It lives outside the staff console on purpose. An applicant is not a console
 * user, so this page has its own sign-in, its own cookie and its own layout.
 */

const STEPS = ['Received', 'Being assessed', 'With an underwriter', 'Decided']

/** How far along the track each stage is. Step 0 is reached by applying. */
const STEP_FOR_STAGE: Record<string, number> = {
  being_assessed: 1,
  with_underwriter: 2,
  waiting_on_you: 2,
  senior_review: 2,
  decided: 3,
}

// The page refreshes itself, which is how an applicant hears about a change
// without being emailed each time. A minute is frequent enough for something
// measured in working days.
const REFRESH_MS = 60_000

/** "Thursday 24 September 2026". Local midnight, so a bare date never shifts a day. */
function formatDay(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

function formatMoment(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

function formatTaka(value: string | number): string {
  return `৳${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

/** `critical_illness` to "Critical illness". */
function readable(value: string): string {
  const words = value.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function PortalPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data, error, isPending } = useQuery({
    queryKey: ['portal', 'me'],
    queryFn: getPortalStatus,
    retry: false,
    refetchInterval: REFRESH_MS,
  })

  const signOut = async () => {
    try {
      await portalLogout()
    } finally {
      queryClient.removeQueries({ queryKey: ['portal'] })
      navigate('/auth?as=client', { replace: true })
    }
  }

  // No session, or it ran out: back to the client sign-in.
  if (error instanceof ApiError && error.status === 401) {
    return <Navigate to="/auth?as=client" replace />
  }

  return (
    <div className="neo-shell">
      <header className="portal-bar">
        <div className="portal-bar__inner">
          <Link to="/" className="portal-bar__brand">
            <BrandIcon width={18} height={18} style={{ display: 'block' }} />
            homelander
          </Link>
          {data && (
            <button type="button" className="portal-bar__signout" onClick={signOut}>
              Sign out
            </button>
          )}
        </div>
      </header>

      <main className="portal-main">
        {isPending && <p className="portal-sub">Loading your application.</p>}

        {error && !data && (
          <div className="portal-card">
            <p className="portal-card__headline">We could not load your application.</p>
            <p className="portal-card__body">{error.message}</p>
          </div>
        )}

        {data && <Status status={data} />}
      </main>
    </div>
  )
}

function Status({ status }: { status: PortalStatus }) {
  const step = STEP_FOR_STAGE[status.stage] ?? 1
  const decided = status.stage === 'decided'
  const waitingOnApplicant = status.stage === 'waiting_on_you'
  // Once a case is decided or escalated for senior review, the date given
  // at intake no longer governs anything. Showing it would be a stale promise,
  // possibly one already in the past.
  const dateIsLive = !decided && status.stage !== 'senior_review'
  // Optional in the generated type because the API gives it a default.
  const documents = status.documents ?? []
  const outstanding = documents.filter((d) => !d.received)

  const cover = [
    status.coverageType ? `${readable(status.coverageType)} cover` : null,
    status.coverageAmount ? formatTaka(status.coverageAmount) : null,
  ]
    .filter(Boolean)
    .join(', ')

  return (
    <>
      <p className="portal-eyebrow">Application {status.reference}</p>
      <h1 className="portal-title">
        {status.applicantName ? `Hello, ${status.applicantName}.` : 'Your application.'}
      </h1>
      <p className="portal-sub">
        {cover ? `${cover}. ` : ''}Applied on {formatMoment(status.submittedAt)}.
      </p>

      {/* 1. Where is it */}
      <section className="portal-card" aria-labelledby="portal-where">
        <p className="portal-card__label" id="portal-where">Where it is</p>
        <ol className="portal-track">
          {STEPS.map((name, index) => (
            <li
              key={name}
              className="portal-track__step"
              data-reached={index <= step}
              data-current={index === step && !decided}
            >
              {name}
            </li>
          ))}
        </ol>
        <p className="portal-card__headline">{status.stageLabel}</p>
        <p className="portal-card__body">{status.stageDetail}</p>
      </section>

      {/* 2. Do you need anything from me. Shown above the date when it is the
          thing holding the application up. */}
      {documents.length > 0 && (
        <section
          className="portal-card"
          data-attention={outstanding.length > 0}
          aria-labelledby="portal-docs"
        >
          <p className="portal-card__label" id="portal-docs">
            {outstanding.length > 0 ? 'What we need from you' : 'Documents you sent'}
          </p>
          <ul className="portal-docs">
            {documents.map((doc) => (
              <li
                key={`${doc.requestedAt}-${doc.description}`}
                className="portal-docs__item"
                data-received={doc.received}
              >
                <span className="portal-docs__text">{doc.description}</span>
                <span className="portal-docs__state" data-received={doc.received}>
                  {doc.received ? 'Received' : 'Still needed'}
                </span>
              </li>
            ))}
          </ul>
          {outstanding.length > 0 && (
            <p className="portal-card__note">
              Bring or send these to the office where you applied. Sending documents
              from this page is not available yet.
            </p>
          )}
        </section>
      )}

      {/* 3. When will I hear. A date, never a countdown. */}
      {dateIsLive && status.expectedBy && (
        <section className="portal-card" aria-labelledby="portal-when">
          <p className="portal-card__label" id="portal-when">When to expect an answer</p>
          <p className="portal-card__headline">By {formatDay(status.expectedBy)}</p>
          {status.overdue && (
            <p className="portal-card__body">
              This is taking longer than we told you. We are sorry for the delay.
            </p>
          )}
          {waitingOnApplicant && (
            <p className="portal-card__body">
              We are waiting for your documents, so this date may change once they arrive.
            </p>
          )}
          {status.expectedByNote && (
            <p className="portal-card__note">
              Your underwriter changed this date: {status.expectedByNote}
            </p>
          )}
        </section>
      )}

      {/* 4. The outcome, once a person has recorded one. */}
      {status.offer && (
        <section className="portal-card" data-attention="true" aria-labelledby="portal-offer">
          <p className="portal-card__label" id="portal-offer">Your offer</p>
          <p className="portal-card__headline">{status.offer.outcome}</p>
          <dl className="portal-offer">
            {status.offer.planName && (
              <div>
                <dt>Plan</dt>
                <dd>{status.offer.planName}</dd>
              </div>
            )}
            {status.offer.monthlyPremiumBdt != null && (
              <div>
                <dt>Premium</dt>
                <dd>{formatTaka(status.offer.monthlyPremiumBdt)} a month</dd>
              </div>
            )}
            <div>
              <dt>Decided on</dt>
              <dd>{formatMoment(status.offer.decidedAt)}</dd>
            </div>
          </dl>
          <p className="portal-card__note">
            Contact the office where you applied to complete your policy.
          </p>
        </section>
      )}

      <p className="portal-foot">
        This page updates on its own. For anything else about your application,
        contact the office where you applied and quote {status.reference}.
      </p>
    </>
  )
}
