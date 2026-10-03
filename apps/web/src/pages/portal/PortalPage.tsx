import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, getPortalStatus, portalLogin, portalLogout, portalUpload } from '../../api/client'
import type { Installment, Policy, PortalStatus } from '../../api/client'
import { BrandIcon } from '../../components/BrandIcon'
import { ThemeToggle } from '../../components/ThemeToggle'

type PortalDocument = NonNullable<PortalStatus['documents']>[number]

/**
 * The client portal: one person reading their own application, start to end.
 *
 * It is the client's only address. Signed out, it is a plain sign-in card and
 * nothing else: a client never sees the team's sign-in. Signed in, it answers
 * what they want to know, in plain words and in this order: has a doctor
 * written to me, my policy once approved (what I pay, what has been paid,
 * what is due next, what it pays out), where my application is, and do you
 * need anything from me (with a way to upload it).
 *
 * There is no risk score or model finding here, and no way to add one by
 * accident: `PortalStatus` has no such field (see schemas/portal.py for why).
 */

const STEPS = ['Received', 'Checking your tests', 'Making a decision', 'Decision made']

/** How far along the track each stage is. Step 0 is reached by applying. */
const STEP_FOR_STAGE: Record<string, number> = {
  being_assessed: 1,
  with_underwriter: 2,
  waiting_on_you: 2,
  senior_review: 2,
  decided: 3,
}

// The page refreshes itself, which is how a client hears about a change
// without being emailed each time.
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

function formatDate(iso: string): string {
  return new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

function formatMonth(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

function formatTaka(value: string | number): string {
  return `৳${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

/** `critical_illness` to "Critical illness". */
function readable(value: string): string {
  const words = value.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

const METHOD: Record<string, string> = {
  bkash: 'bKash',
  nagad: 'Nagad',
  rocket: 'Rocket',
  bank: 'Bank transfer',
  card: 'Card',
  cash: 'Cash',
}

export function PortalPage() {
  const queryClient = useQueryClient()
  const { data, error, isPending } = useQuery({
    queryKey: ['portal', 'me'],
    queryFn: getPortalStatus,
    retry: false,
    refetchInterval: (q) => (q.state.error ? false : REFRESH_MS),
  })
  const signedOut = error instanceof ApiError && error.status === 401

  const signOut = async () => {
    try {
      await portalLogout()
    } finally {
      await queryClient.resetQueries({ queryKey: ['portal', 'me'] })
    }
  }

  return (
    <div className="neo-shell">
      <header className="portal-bar">
        <div className="portal-bar__inner">
          <Link to="/" className="portal-bar__brand">
            <BrandIcon width={18} height={18} style={{ display: 'block' }} />
            Homelander AI
          </Link>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <ThemeToggle />
            {data && !signedOut && (
              <button type="button" className="portal-bar__signout" onClick={() => void signOut()}>
                Sign out
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="portal-main">
        {isPending && <p className="portal-sub">Loading…</p>}
        {signedOut && <SignIn />}
        {error && !signedOut && !data && (
          <div className="portal-card">
            <p className="portal-card__headline">We could not load your application.</p>
            <p className="portal-card__body">{error.message}</p>
          </div>
        )}
        {data && !signedOut && <Status status={data} />}
      </main>
    </div>
  )
}

/** The client's sign-in: a portal ID and a password, nothing else on the page. */
function SignIn() {
  const queryClient = useQueryClient()
  const [portalId, setPortalId] = useState('')
  const [password, setPassword] = useState('')
  const [shown, setShown] = useState(false)
  const login = useMutation({
    mutationFn: () => portalLogin({ portalId: portalId.trim(), password }),
    onSuccess: (status) => queryClient.setQueryData(['portal', 'me'], status),
  })

  return (
    <div className="portal-signin">
      <h1 className="portal-title">Check your application</h1>
      <p className="portal-sub">Sign in with the portal ID and password you were given when you applied.</p>
      <form
        className="portal-card"
        onSubmit={(e) => {
          e.preventDefault()
          if (portalId.trim() && password) login.mutate()
        }}
      >
        {login.error && (
          <p className="portal-error" role="alert">
            {login.error.message}
          </p>
        )}
        <label className="portal-field">
          <span>Portal ID</span>
          <input
            value={portalId}
            onChange={(e) => setPortalId(e.currentTarget.value)}
            placeholder="HC-XXXXXXXX"
            autoComplete="username"
            autoCapitalize="characters"
            spellCheck={false}
            required
          />
        </label>
        <label className="portal-field">
          <span>Password</span>
          <span className="portal-field__row">
            <input
              type={shown ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
              autoComplete="current-password"
              required
            />
            <button type="button" className="portal-field__toggle" onClick={() => setShown((s) => !s)}>
              {shown ? 'Hide' : 'Show'}
            </button>
          </span>
        </label>
        <button type="submit" className="portal-upload portal-submit" disabled={login.isPending}>
          {login.isPending ? 'Signing in…' : 'See my application'}
        </button>
        <p className="portal-card__note">Lost your password? Contact the office where you applied. They can send you a new one.</p>
      </form>
    </div>
  )
}

function Status({ status }: { status: PortalStatus }) {
  const step = STEP_FOR_STAGE[status.stage] ?? 1
  const decided = status.stage === 'decided'
  const waitingOnApplicant = status.stage === 'waiting_on_you'
  const dateIsLive = !decided && status.stage !== 'senior_review'
  const documents = status.documents ?? []
  const outstanding = documents.filter((d) => !d.received)
  const messages = status.messages ?? []
  const urgent = messages.some((m) => m.urgency === 'urgent')
  const files = status.files ?? []
  const policy = status.policy ?? null

  return (
    <>
      <p className="portal-eyebrow">Your reference: {status.reference}</p>
      <h1 className="portal-title">{status.applicantName ? `Hello, ${status.applicantName}.` : 'Your application.'}</h1>
      <p className="portal-sub">Everything about your application is on this page. It updates by itself.</p>

      {/* A doctor writing to them comes first: it is about their health. */}
      {messages.length > 0 && (
        <section className="portal-card portal-message" data-urgent={urgent} aria-labelledby="portal-messages">
          <p className="portal-card__label" id="portal-messages">
            {urgent ? 'Important: please read this first' : 'A message from our doctor'}
          </p>
          <p className="portal-card__headline">
            {messages.length === 1 ? 'Our doctor has written to you' : `Our doctor has written to you ${messages.length} times`}
          </p>
          {messages.map((m) => (
            <div key={m.sentAt} className="portal-message__item" data-urgent={m.urgency === 'urgent'}>
              <p className="portal-card__body">{m.message}</p>
              <p className="portal-message__when">
                {m.urgency === 'urgent' ? 'Urgent · ' : ''}Sent on {formatDate(m.sentAt)}
              </p>
            </div>
          ))}
          {urgent && (
            <p className="portal-card__note">
              This is about your health, not your insurance. Please act on it even while your application is still open.
            </p>
          )}
        </section>
      )}

      {/* Once approved, the policy is what matters most. */}
      {policy && <PolicyCard policy={policy} />}

      <section className="portal-card" aria-labelledby="portal-where">
        <p className="portal-card__label" id="portal-where">
          Where your application is
        </p>
        <ol className="portal-track">
          {STEPS.map((name, index) => (
            <li key={name} className="portal-track__step" data-reached={index <= step} data-current={index === step && !decided}>
              {name}
            </li>
          ))}
        </ol>
        <p className="portal-card__headline">{status.stageLabel}</p>
        <p className="portal-card__body">{status.stageDetail}</p>
      </section>

      {documents.length > 0 && (
        <section className="portal-card" data-attention={outstanding.length > 0} aria-labelledby="portal-docs">
          <p className="portal-card__label" id="portal-docs">
            {outstanding.length > 0 ? 'What we need from you' : 'Documents you sent'}
          </p>
          {outstanding.length > 0 && (
            <p className="portal-card__body" style={{ marginTop: 0, marginBottom: '0.8rem' }}>
              {outstanding.length === 1 ? 'Please upload this document.' : `Please upload these ${outstanding.length} documents.`} A
              clear photo from your phone is fine.
            </p>
          )}
          <ul className="portal-docs">
            {documents.map((doc) => (
              <DocumentRow key={doc.id} doc={doc} />
            ))}
          </ul>
          {outstanding.length > 0 && (
            <p className="portal-card__note">
              You can send a photo, a scan or a PDF. If you cannot upload it, bring it to the office where you applied.
            </p>
          )}
        </section>
      )}

      {dateIsLive && status.expectedBy && (
        <section className="portal-card" aria-labelledby="portal-when">
          <p className="portal-card__label" id="portal-when">
            When you will hear from us
          </p>
          <p className="portal-card__headline">By {formatDay(status.expectedBy)}</p>
          {status.overdue && <p className="portal-card__body">This is taking longer than we said. We are sorry for the wait.</p>}
          {waitingOnApplicant && (
            <p className="portal-card__body">We are waiting for your documents, so this date may move once they arrive.</p>
          )}
          {status.expectedByNote && <p className="portal-card__note">We changed this date because: {status.expectedByNote}</p>}
        </section>
      )}

      {/* A decision with no policy behind it (an approval from before policies existed). */}
      {status.offer && !policy && (
        <section className="portal-card" data-attention="true" aria-labelledby="portal-offer">
          <p className="portal-card__label" id="portal-offer">
            Our decision
          </p>
          <p className="portal-card__headline">{status.offer.outcome}</p>
          <dl className="portal-offer">
            {status.offer.planName && (
              <div>
                <dt>Your plan</dt>
                <dd>{status.offer.planName}</dd>
              </div>
            )}
            {status.offer.monthlyPremiumBdt != null && (
              <div>
                <dt>You pay</dt>
                <dd>{formatTaka(status.offer.monthlyPremiumBdt)} a month</dd>
              </div>
            )}
            <div>
              <dt>Decided on</dt>
              <dd>{formatDate(status.offer.decidedAt)}</dd>
            </div>
          </dl>
        </section>
      )}

      <section className="portal-card" aria-labelledby="portal-cover">
        <p className="portal-card__label" id="portal-cover">
          What you asked for
        </p>
        <dl className="portal-offer" style={{ marginTop: 0 }}>
          <div>
            <dt>Type of cover</dt>
            <dd>{status.coverageType ? `${readable(status.coverageType)} cover` : '—'}</dd>
          </div>
          <div>
            <dt>Amount</dt>
            <dd>{status.coverageAmount ? formatTaka(status.coverageAmount) : '—'}</dd>
          </div>
          {status.policyTerm && (
            <div>
              <dt>For</dt>
              <dd>{/^\d+$/.test(status.policyTerm) ? `${status.policyTerm} years` : status.policyTerm}</dd>
            </div>
          )}
          <div>
            <dt>Applied on</dt>
            <dd>{formatDate(status.submittedAt)}</dd>
          </div>
        </dl>
      </section>

      {files.length > 0 && (
        <section className="portal-card" aria-labelledby="portal-files">
          <p className="portal-card__label" id="portal-files">
            What you have sent us
          </p>
          <ul className="portal-docs">
            {files.map((f, i) => (
              <li key={`${f.uploadedAt}-${i}`} className="portal-docs__item">
                <span className="portal-docs__text">
                  {f.kind}
                  {f.fileName && <span className="portal-docs__file">{f.fileName}</span>}
                </span>
                <span className="portal-docs__state">{formatDate(f.uploadedAt)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {messages.length === 0 && (
        <section className="portal-card" aria-labelledby="portal-no-messages">
          <p className="portal-card__label" id="portal-no-messages">
            Messages from our doctor
          </p>
          <p className="portal-card__body" style={{ marginTop: 0 }}>
            None. If our doctor needs to tell you something about your health, it will appear at the top of this page.
          </p>
        </section>
      )}

      <p className="portal-foot">
        Questions? Contact the office where you applied and give them your reference, {status.reference}
        {policy ? `, or your policy number, ${policy.policyNumber}` : ''}. We never show test scores on this page: your
        results are checked by people at our company.
      </p>
    </>
  )
}

/** The policy: what it pays out, what they pay, what has been paid and what is next. */
function PolicyCard({ policy }: { policy: Policy }) {
  const active = policy.status === 'active'
  const installments = policy.installments ?? []
  const overdue = (policy.overdueCount ?? 0) > 0
  const paidCount = policy.paidCount ?? 0
  const monthsTotal = policy.monthsTotal ?? policy.termYears * 12
  const progress = Math.min(100, Math.round((paidCount / Math.max(1, monthsTotal)) * 100))
  const until = formatDate(policy.endDate)
  const payout = formatTaka(policy.sumAssuredBdt)

  return (
    <section
      className="portal-card portal-policy"
      data-state={active ? (overdue ? 'overdue' : 'active') : 'cancelled'}
      aria-labelledby="portal-policy"
    >
      <p className="portal-card__label" id="portal-policy">
        Your policy · {policy.policyNumber}
      </p>
      <p className="portal-card__headline">
        {active
          ? `You are covered. ${policy.planName} plan.`
          : `This policy was cancelled${policy.cancelledAt ? ` on ${formatDate(policy.cancelledAt)}` : ''}.`}
      </p>
      {!active && (
        <p className="portal-card__body">
          {policy.cancelReason ? `Reason: ${policy.cancelReason} ` : ''}No more payments are due. If you think this is a
          mistake, contact the office where you applied.
        </p>
      )}

      <dl className="portal-offer">
        <div>
          <dt>We pay out</dt>
          <dd>{payout}</dd>
        </div>
        <div>
          <dt>You pay</dt>
          <dd>{formatTaka(policy.monthlyPremiumBdt)} a month</dd>
        </div>
        <div>
          <dt>That is</dt>
          <dd>{formatTaka(policy.yearlyPremiumBdt)} a year</dd>
        </div>
        <div>
          <dt>Covered</dt>
          <dd>
            {formatDate(policy.startDate)} to {until}
          </dd>
        </div>
      </dl>
      <p className="portal-card__body">
        {policy.coverageType === 'Life'
          ? `If you die before ${until}, your family is paid ${payout}.`
          : policy.coverageType === 'Health'
            ? `Each year until ${until}, your hospital and treatment bills are paid up to ${payout}.`
            : `If you are diagnosed with a covered serious illness before ${until}, you are paid ${payout}.`}{' '}
        Over {policy.termYears} years you pay {formatTaka(policy.totalPremiumBdt)} in all, if every month is paid.
      </p>

      {active && (
        <div className="portal-pay">
          <div className="portal-pay__next" data-overdue={overdue}>
            {overdue ? (
              <>
                <strong>
                  {policy.overdueCount === 1 ? 'One payment is' : `${policy.overdueCount} payments are`} overdue:{' '}
                  {formatTaka(policy.overdueTotalBdt ?? 0)}.
                </strong>{' '}
                Please pay as soon as you can. A policy left unpaid may be cancelled.
              </>
            ) : policy.nextDue ? (
              <>
                Next payment: <strong>{formatTaka(policy.nextAmountBdt ?? policy.monthlyPremiumBdt)}</strong>, due on{' '}
                <strong>{formatDate(policy.nextDue)}</strong>.
              </>
            ) : (
              'Nothing is due right now.'
            )}
          </div>
          <div className="portal-pay__bar" aria-label={`${paidCount} of ${monthsTotal} months paid`}>
            <span style={{ width: `${progress}%` }} />
          </div>
          <p className="portal-message__when">
            {paidCount} of {monthsTotal} monthly payments made · {formatTaka(policy.paidTotalBdt ?? 0)} paid so far
          </p>
        </div>
      )}

      {installments.length > 0 && (
        <div className="portal-payments-wrap">
          <table className="portal-payments">
            <thead>
              <tr>
                <th>Month</th>
                <th>Due</th>
                <th>Amount</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {[...installments].reverse().map((i: Installment) => (
                <tr key={i.dueDate}>
                  <td>{formatMonth(i.dueDate)}</td>
                  <td>{formatDate(i.dueDate)}</td>
                  <td>{formatTaka(i.amountBdt)}</td>
                  <td>
                    <span className="portal-chip" data-status={i.status}>
                      {i.status === 'paid'
                        ? `Paid${i.paidOn ? ` ${formatDate(i.paidOn)}` : ''}${i.method ? ` · ${METHOD[i.method] ?? i.method}` : ''}`
                        : i.status === 'overdue'
                          ? 'Overdue'
                          : i.status === 'due'
                            ? 'Due now'
                            : 'Coming up'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {active && (
        <p className="portal-card__note">
          Pay by bKash, Nagad, bank transfer or at the office where you applied, and quote your policy number,{' '}
          {policy.policyNumber}. A payment shows here once it has been recorded. You have {policy.graceDays} days after each
          due date to pay.
        </p>
      )}
    </section>
  )
}

/** One requested document: upload it, or see that we have it. */
function DocumentRow({ doc }: { doc: PortalDocument }) {
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: (file: File) => portalUpload(doc.id, file),
    onSuccess: (updated) => queryClient.setQueryData(['portal', 'me'], updated),
  })

  return (
    <li className="portal-docs__item" data-received={doc.received}>
      <span className="portal-docs__text">
        {doc.description}
        <span className="portal-docs__file">
          {doc.received
            ? `Received${doc.receivedAt ? ` on ${formatDate(doc.receivedAt)}` : ''}${doc.fileName ? ` · ${doc.fileName}` : ''}`
            : `Asked for on ${formatDate(doc.requestedAt)}`}
        </span>
        {upload.error && (
          <span className="portal-docs__error" role="alert">
            {upload.error.message}
          </span>
        )}
      </span>
      {doc.received ? (
        <span className="portal-docs__state" data-received="true">
          ✓ Received
        </span>
      ) : (
        <>
          <input
            ref={input}
            type="file"
            accept="image/*,.pdf,.jpg,.jpeg,.png"
            hidden
            onChange={(e) => {
              const file = e.currentTarget.files?.[0]
              if (file) upload.mutate(file)
              e.currentTarget.value = ''
            }}
          />
          <button type="button" className="portal-upload" disabled={upload.isPending} onClick={() => input.current?.click()}>
            {upload.isPending ? 'Uploading…' : 'Upload'}
          </button>
        </>
      )}
    </li>
  )
}
