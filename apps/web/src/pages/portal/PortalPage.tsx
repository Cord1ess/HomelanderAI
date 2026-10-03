import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  ApiError,
  getPortalStatus,
  portalClaimDocuments,
  portalFileClaim,
  portalLogin,
  portalLogout,
  portalRequestDeletion,
  portalUpload,
  portalWithdrawDeletion,
} from '../../api/client'
import type { Policy, PortalClaim, PortalStatus } from '../../api/client'
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

function formatTaka(value: string | number): string {
  return `৳${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

/** `critical_illness` to "Critical illness". */
function readable(value: string): string {
  const words = value.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
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

      {/* Once decided, the outcome is what matters most. */}
      {policy && <PolicyCard policy={policy} />}
      {status.declined && <DeclineCard declined={status.declined} />}
      {policy && <ClaimsSection status={status} />}

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
            <dd>
              {status.coverageType === 'Health'
                ? 'Hospital cover'
                : status.coverageType
                  ? `${readable(status.coverageType)} cover`
                  : '—'}
            </dd>
          </div>
          <div>
            <dt>Amount</dt>
            <dd>{status.coverageAmount ? formatTaka(status.coverageAmount) : '—'}</dd>
          </div>
          {status.policyTerm && (
            <div>
              <dt>For</dt>
              <dd>
                {status.coverageType === 'Health'
                  ? 'One year, renewed yearly'
                  : /^\d+$/.test(status.policyTerm)
                    ? `${status.policyTerm} year${status.policyTerm === '1' ? '' : 's'}`
                    : status.policyTerm}
              </dd>
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

      <DeletionSection status={status} />

      <p className="portal-foot">
        Questions? Contact the office where you applied and give them your reference, {status.reference}
        {policy ? `, or your policy number, ${policy.policyNumber}` : ''}. We never show test scores on this page: your
        results are checked by people at our company.
      </p>
    </>
  )
}

/** The policy: what it covers, what it costs and when, what it does not cover. */
function PolicyCard({ policy }: { policy: Policy }) {
  const state = policy.effectiveStatus
  const active = state === 'active'
  const health = policy.product === 'health'
  const until = formatDate(policy.endDate)
  const payout = formatTaka(policy.sumAssuredBdt)
  const exclusions = policy.exclusions ?? []

  return (
    <section className="portal-card portal-policy" data-state={active ? 'active' : 'cancelled'} aria-labelledby="portal-policy">
      <p className="portal-card__label" id="portal-policy">
        Your policy · {policy.policyNumber}
      </p>
      <p className="portal-card__headline">
        {active
          ? `You are covered. ${policy.productName}.`
          : state === 'expired'
            ? `This policy ended on ${until}.`
            : `This policy was cancelled${policy.cancelledAt ? ` on ${formatDate(policy.cancelledAt)}` : ''}.`}
      </p>
      {state === 'cancelled' && (
        <p className="portal-card__body">
          {policy.cancelReason ? `Reason: ${policy.cancelReason} ` : ''}No more premiums are due. If you think this is a
          mistake, contact the office where you applied.
        </p>
      )}

      <dl className="portal-offer">
        <div>
          <dt>{health ? 'We pay each year, up to' : 'We pay out'}</dt>
          <dd>{payout}</dd>
        </div>
        <div>
          <dt>You pay</dt>
          <dd>
            {formatTaka(policy.premiumAmountBdt)} {policy.premiumMode === 'yearly' ? 'a year' : 'a month'}
          </dd>
        </div>
        <div>
          <dt>Covered</dt>
          <dd>
            {formatDate(policy.startDate)} to {until}
          </dd>
        </div>
        {active && policy.nextPremiumDue && (
          <div>
            <dt>Next premium due</dt>
            <dd>{formatDate(policy.nextPremiumDue)}</dd>
          </div>
        )}
      </dl>
      <p className="portal-card__body">
        {health
          ? `Until ${until}, your hospital and treatment bills are paid up to ${payout}. ${policy.remainingLimitBdt != null ? `${formatTaka(policy.remainingLimitBdt)} of that is left this year.` : ''}`
          : `If you die before ${until}, your nominee is paid ${payout}.`}{' '}
        Pay your premium to the bank and quote your policy number, {policy.policyNumber}.
      </p>

      {active && policy.inFreeLook && policy.freeLookUntil && (
        <p className="portal-card__note">
          You can change your mind until {formatDate(policy.freeLookUntil)} and get back everything you have paid. Contact
          the office where you applied.
        </p>
      )}
      {health && active && (
        <p className="portal-card__note">
          Illness is covered from {policy.waitingUntil ? formatDate(policy.waitingUntil) : 'the start'}; accidents from the
          first day. Conditions you had before the policy are covered from{' '}
          {policy.preexistingUntil ? formatDate(policy.preexistingUntil) : '—'}.
          {policy.renewalDue && ` Your cover renews on ${until}: we will be in touch.`}
        </p>
      )}
      {exclusions.length > 0 && (
        <div className="portal-card__note">
          <strong>Not covered by this policy:</strong>
          <ul className="portal-list">
            {exclusions.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

/** A decline: why, in plain words, and when they may apply again. */
function DeclineCard({ declined }: { declined: NonNullable<PortalStatus['declined']> }) {
  return (
    <section className="portal-card" data-attention="true" aria-labelledby="portal-declined">
      <p className="portal-card__label" id="portal-declined">
        Our decision
      </p>
      <p className="portal-card__headline">We are not able to offer you cover</p>
      <p className="portal-card__body">{declined.reason}</p>
      {declined.note && <p className="portal-card__body">{declined.note}</p>}
      {declined.reapplyAfter && (
        <p className="portal-card__body">
          You are welcome to apply again from <strong>{formatDate(declined.reapplyAfter)}</strong>.
        </p>
      )}
      <p className="portal-card__note">
        This decision was made by a person at our company, not by a computer. If you have questions, contact the office
        where you applied.
      </p>
    </section>
  )
}

const CLAIM_WORDS: Record<string, string> = {
  submitted: 'We have it',
  documents_requested: 'We need more documents',
  under_review: 'Being reviewed',
  approved: 'Approved: being paid',
  rejected: 'Not paid',
  settled: 'Paid',
}

/** Claims: file one for hospital bills, see each one's progress, add documents. */
function ClaimsSection({ status }: { status: PortalStatus }) {
  const queryClient = useQueryClient()
  const policy = status.policy!
  const claims = status.claims ?? []
  const [open, setOpen] = useState(false)
  const [eventDate, setEventDate] = useState('')
  const [amount, setAmount] = useState('')
  const [hospital, setHospital] = useState('')
  const [description, setDescription] = useState('')
  const [accident, setAccident] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const file = useMutation({
    mutationFn: () =>
      portalFileClaim(
        { eventDate, claimedAmountBdt: Number(amount), description: description.trim(), hospital: hospital.trim() || null, accident },
        files,
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(['portal', 'me'], updated)
      setOpen(false)
      setFiles([])
      setDescription('')
      setAmount('')
    },
  })
  const health = policy.product === 'health'
  const canFile = health && policy.effectiveStatus !== 'cancelled'

  return (
    <section className="portal-card" aria-labelledby="portal-claims">
      <p className="portal-card__label" id="portal-claims">
        Claims
      </p>
      {claims.length === 0 && (
        <p className="portal-card__body" style={{ marginTop: 0 }}>
          {health
            ? 'No claims yet. If you are treated in hospital, send us the bills here.'
            : `A claim on life cover is made by your nominee, ${status.nomineeName ?? 'the person you named'}, at the office where you applied, with the death certificate.`}
        </p>
      )}
      <ul className="portal-docs">
        {claims.map((c) => (
          <ClaimRow key={c.id} claim={c} />
        ))}
      </ul>
      {canFile && !open && (
        <button type="button" className="portal-upload" style={{ marginTop: '0.8rem' }} onClick={() => setOpen(true)}>
          Make a claim
        </button>
      )}
      {canFile && open && (
        <form
          className="portal-claim-form"
          onSubmit={(e) => {
            e.preventDefault()
            file.mutate()
          }}
        >
          {file.error && (
            <p className="portal-error" role="alert">
              {file.error.message}
            </p>
          )}
          <label className="portal-field">
            <span>Date you went into hospital</span>
            <input type="date" value={eventDate} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setEventDate(e.currentTarget.value)} required />
          </label>
          <label className="portal-field">
            <span>Total of the bills (taka)</span>
            <input type="number" min={1} value={amount} onChange={(e) => setAmount(e.currentTarget.value)} required />
          </label>
          <label className="portal-field">
            <span>Hospital</span>
            <input value={hospital} onChange={(e) => setHospital(e.currentTarget.value)} />
          </label>
          <label className="portal-field">
            <span>What happened</span>
            <input value={description} onChange={(e) => setDescription(e.currentTarget.value)} placeholder="For example: three nights for dengue fever" required minLength={5} />
          </label>
          <label className="portal-check">
            <input type="checkbox" checked={accident} onChange={(e) => setAccident(e.currentTarget.checked)} /> It was an accident
          </label>
          <label className="portal-field">
            <span>The bills and the discharge summary (photos or PDF)</span>
            <input type="file" multiple accept="image/*,.pdf" onChange={(e) => setFiles(Array.from(e.currentTarget.files ?? []))} required />
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="submit" className="portal-upload" disabled={file.isPending}>
              {file.isPending ? 'Sending…' : 'Send the claim'}
            </button>
            <button type="button" className="portal-field__toggle" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
          <p className="portal-card__note">
            We decide within 90 days of having all the documents we need, and usually much sooner. Payment comes from the
            bank.
          </p>
        </form>
      )}
    </section>
  )
}

function ClaimRow({ claim }: { claim: PortalClaim }) {
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const add = useMutation({
    mutationFn: (files: File[]) => portalClaimDocuments(claim.id, files),
    onSuccess: (updated) => queryClient.setQueryData(['portal', 'me'], updated),
  })
  const open = ['submitted', 'documents_requested', 'under_review'].includes(claim.status)
  return (
    <li className="portal-docs__item" data-received={claim.status === 'settled'}>
      <span className="portal-docs__text">
        {claim.claimNumber} · {formatTaka(claim.claimedAmountBdt)} · {formatDate(claim.eventDate)}
        <span className="portal-docs__file">
          {claim.hospital ? `${claim.hospital} · ` : ''}
          {claim.documents} document{claim.documents === 1 ? '' : 's'} sent
          {claim.settleBy && open ? ` · decided by ${formatDate(claim.settleBy)}` : ''}
        </span>
        {claim.status === 'documents_requested' && claim.documentsNote && (
          <span className="portal-docs__error">We need: {claim.documentsNote}</span>
        )}
        {claim.status === 'approved' && claim.approvedAmountBdt && (
          <span className="portal-docs__file">Approved for {formatTaka(claim.approvedAmountBdt)}. The bank will pay it.</span>
        )}
        {claim.status === 'settled' && claim.approvedAmountBdt && (
          <span className="portal-docs__file">
            Paid {formatTaka(claim.approvedAmountBdt)}
            {claim.settledAt ? ` on ${formatDate(claim.settledAt)}` : ''}.
          </span>
        )}
        {claim.status === 'rejected' && claim.decisionNote && <span className="portal-docs__error">{claim.decisionNote}</span>}
        {add.error && <span className="portal-docs__error">{add.error.message}</span>}
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
        <span className="portal-chip" data-status={claim.status === 'settled' ? 'paid' : claim.status === 'rejected' ? 'overdue' : 'due'}>
          {CLAIM_WORDS[claim.status] ?? claim.status}
        </span>
        {open && (
          <>
            <input ref={input} type="file" multiple accept="image/*,.pdf" hidden onChange={(e) => { const f = Array.from(e.currentTarget.files ?? []); if (f.length) add.mutate(f); e.currentTarget.value = '' }} />
            <button type="button" className="portal-field__toggle" onClick={() => input.current?.click()} disabled={add.isPending}>
              {add.isPending ? 'Sending…' : 'Add documents'}
            </button>
          </>
        )}
      </span>
    </li>
  )
}

/** Asking for their data to be deleted, and where that stands. */
function DeletionSection({ status }: { status: PortalStatus }) {
  const queryClient = useQueryClient()
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState('')
  const ask = useMutation({
    mutationFn: () => portalRequestDeletion(reason.trim() || null),
    onSuccess: (updated) => {
      queryClient.setQueryData(['portal', 'me'], updated)
      setAsking(false)
    },
  })
  const withdraw = useMutation({
    mutationFn: portalWithdrawDeletion,
    onSuccess: (updated) => queryClient.setQueryData(['portal', 'me'], updated),
  })
  const d = status.deletion
  const live = d && (d.status === 'pending' || d.status === 'approved')
  return (
    <section className="portal-card" aria-labelledby="portal-delete">
      <p className="portal-card__label" id="portal-delete">
        Your data
      </p>
      {live ? (
        <>
          <p className="portal-card__body" style={{ marginTop: 0 }}>
            You asked on {formatDate(d!.requestedAt)} for your data to be deleted.{' '}
            {d!.status === 'approved'
              ? `It has been approved and will be deleted on ${formatDate(d!.deleteOn)}. After that you will not be able to sign in.`
              : `We will deal with it by ${formatDate(d!.deleteOn)}.`}
          </p>
          <button type="button" className="portal-field__toggle" onClick={() => withdraw.mutate()} disabled={withdraw.isPending}>
            I have changed my mind
          </button>
        </>
      ) : (
        <>
          {d?.status === 'declined' && (
            <p className="portal-card__body" style={{ marginTop: 0 }}>
              Your last request to delete your data was not approved: {d.declineReason}
            </p>
          )}
          <p className="portal-card__body" style={{ marginTop: 0 }}>
            You can ask us to delete your personal and health information. It is deleted within 30 days of your request.
            Records the law requires us to keep (that a policy or a claim existed, and its amounts) are kept without your
            name.
          </p>
          {!asking ? (
            <button type="button" className="portal-field__toggle" style={{ marginTop: '0.6rem' }} onClick={() => setAsking(true)}>
              Ask to delete my data
            </button>
          ) : (
            <div style={{ marginTop: '0.6rem' }}>
              {ask.error && <p className="portal-error">{ask.error.message}</p>}
              <label className="portal-field">
                <span>Why (optional)</span>
                <input value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
              </label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button type="button" className="portal-upload" onClick={() => ask.mutate()} disabled={ask.isPending}>
                  Ask to delete my data
                </button>
                <button type="button" className="portal-field__toggle" onClick={() => setAsking(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
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
