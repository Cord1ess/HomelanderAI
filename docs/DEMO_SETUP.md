# Demo setup — database on one machine, app on another

For the first showcase. One laptop runs PostgreSQL; the other runs the API and
the dashboard and connects to it over the network.

There are also three built-in accounts, one per staff role (`underwriter`,
`medical`, `admin`, all with the password `admin123`), that sign in with no
database at all, so a network problem on the day does not cost you the demo.

---

## Part 1 — The database machine

### 1. Start PostgreSQL

Either way works — pick one.

**With Docker**, from the repository:

```bash
npm run infra:up
```

**Without Docker** (Windows, no admin prompt beyond the installer):

```powershell
winget install --id PostgreSQL.PostgreSQL.17 --source winget --silent `
  --custom "--superpassword devpassword"
```

Then create the role and database the app expects. `psql` lives in
`C:\Program Files\PostgreSQL\17\bin`:

```powershell
$env:PGPASSWORD = "devpassword"
& "$env:ProgramFiles\PostgreSQL\17\bin\psql.exe" -U postgres -h 127.0.0.1 `
  -c "CREATE ROLE homelander LOGIN SUPERUSER PASSWORD 'devpassword';"
& "$env:ProgramFiles\PostgreSQL\17\bin\psql.exe" -U postgres -h 127.0.0.1 `
  -c "CREATE DATABASE homelander OWNER homelander;"
```

**Then, either way**, create the tables and load the sample accounts:

```bash
cd apps/api && uv run alembic upgrade head
```

```powershell
& "$env:ProgramFiles\PostgreSQL\17\bin\psql.exe" -U homelander -h 127.0.0.1 `
  -d homelander -f db/seed.sql
```

With Docker, the seed line is instead:

```bash
docker exec -i homelander-postgres psql -U homelander -d homelander < db/seed.sql
```

### 2. Let the other machine in

By default PostgreSQL only accepts connections from its own machine. Two things
have to change.

**Listen on the network.** In `postgresql.conf`:

```
listen_addresses = '*'
```

**Allow your network.** In `pg_hba.conf`, add a line for your local subnet:

```
host    all    all    192.168.0.0/24    scram-sha-256
```

Use your actual subnet. `192.168.0.0/24` covers `192.168.0.1` to
`192.168.0.254`.

> Running Postgres through the Compose file already publishes port 5432 to the
> host, so if you started it with `npm run infra:up` this part is done for you.

### 3. Open the firewall

Windows, in an **administrator** PowerShell:

```powershell
New-NetFirewallRule -DisplayName "PostgreSQL 5432" -Direction Inbound `
  -Protocol TCP -LocalPort 5432 -Action Allow
```

### 4. Find this machine's IP

```powershell
ipconfig | Select-String "IPv4"
```

Write down the address — something like `192.168.0.42`. The other machine needs
it.

---

## Part 2 — The application machine

### 1. Point at the database machine

In `.env` at the repository root, change **one line**:

```
DB_HOST=192.168.0.42
```

Use the IP you wrote down. Nothing else needs to change.

### 2. Check the connection before anything else

Start the API:

```bash
npm run dev
```

Then open:

```
http://127.0.0.1:8000/api/health/database
```

Working:

```json
{ "connected": true, "target": "192.168.0.42:5432/homelander" }
```

Not working — and the `detail` field tells you which problem it is:

```json
{
  "connected": false,
  "target": "192.168.0.42:5432/homelander",
  "detail": "ConnectionRefusedError: ...",
  "admin_login_enabled": true
}
```

| What `detail` says | What it usually means |
|---|---|
| `ConnectionRefusedError` | Postgres is not running, or `listen_addresses` is still `localhost` |
| `TimeoutError` | Firewall is blocking port 5432 |
| `InvalidPasswordError` | `DB_PASSWORD` does not match the database |
| `InvalidCatalogNameError` | Database name is wrong |
| no route to host | The two machines are not on the same network |

Quick check from the application machine:

```powershell
Test-NetConnection 192.168.0.42 -Port 5432
```

`TcpTestSucceeded : True` means the network is fine and the problem is
PostgreSQL's own configuration.

### 3. Sign in

Accounts from `db/seed.sql`:

| Email | Password | Role |
|---|---|---|
| `underwriter@dev.local` | `devpassword123` | Underwriter |
| `medical@dev.local` | `devpassword123` | Medical Professional |
| `dev@dev.local` | `devpassword123` | Dev |

Those three belong to "Tenant A". For a demo, use the built-in accounts below
instead: they need no seed step.

---

## The built-in accounts and the three roles

There are exactly three staff roles, and one built-in account for each. They
work even when the database machine cannot be reached.

| Username | Password | Role | What it is for |
|---|---|---|---|
| `underwriter` | `admin123` | Underwriter | Takes applications in. Decides low and moderate cases. On an elevated case it can only escalate. |
| `medical` | `admin123` | Medical Professional | Reads the clinical evidence on escalated cases and decides them. Has Escalations. |
| `admin` | `admin123` | Administrator | Runs the carrier's workspace: creates staff accounts and sets the turnaround promise. Has Staff and Company settings. |

Type the username where the sign-in form asks for a work email.

**Applicants are not in this table, and have no role.** They never get a staff
account. When an application is taken, the system generates a portal ID and a
password for them, and they use those on the **Check status** side of the
sign-in page. See "The client portal" below.

**No setup needed.** These are on by default in development. You get a session
for "Demo Insurance Co." and the console opens as that role. All three share one
password, `ADMIN_PASSWORD` in `.env`.

Two things keep them contained:

1. **Development only.** `ENVIRONMENT` must be `development`; anywhere else they
   are ignored, whatever the password says.
2. **Clearing `ADMIN_PASSWORD` switches all three off**, and empty never means
   "any password". Their database rows hold an unusable password hash, so they
   cannot sneak back in through the ordinary sign-in either.

Every use writes a warning to the API log.

**With the database up they are full accounts.** The first built-in sign-in
creates a real row for each of the three, so their decisions and audit entries
name a person, and a staff account created by `admin` is a real account that can
sign in. There is no seed step for this.

**While the database is unreachable** they can sign in and nothing more: the
queue, the intake form and the review screen all need data. Signing in this way
when the database is *down* shows the application running.

The old `senior` username no longer exists (changed 2026-09-22); `medical`
replaces it.

---

## Which X-rays to demo with

**Use `data/demo/`.** Twenty films picked from the Shenzhen set and verified
against the shipped model — ten in `01-normal/` that all score `low`, ten in
`02-tuberculosis/` that all score `elevated`. `data/demo/README.md` lists every
file with the score it produces.

**Do not grab a file from `Reference/Nirnoy/assets/samples/`.** That is the
Kaggle set, and this model is *inverted* on it — normals average 74 and TB films
average 38, because Kaggle's normal images come from a different hospital than
its TB images. A demo run from that folder will show a healthy chest scored as
high risk.

Nor should you pick at random from `data/shenzhen/`: across all 662 films only
67% of normals and 70% of TB cases land in the tier their label implies. The
twenty in `data/demo/` are the ones that do.

### The one file to show

`02-tuberculosis/tb-10-shenzhen-0619_1.png`. Its imaging score is 75.1, close
enough to the cut-points that the declared history moves it across them. Submit
the same file three times, changing only the health questions:

| Declared history | Score | Tier | Recommendation |
|---|---|---|---|
| Nothing | 75.1 | elevated | Senior review |
| Prior TB, treated, no symptoms | **50.1** | **moderate** | Standard with adjustment |
| Prior TB **and** a current cough | **100.0** | elevated | Senior review |

One image, three recommendations — because the same shadow on a lung means
healed scarring or an active relapse depending on something no image model can
see. That is the argument for the whole product, and it is the thing to show.

---

## The showcase flow, with the five demo clients

`python scripts/make_demo_clients.py` builds `data/demo/clients/`, five folders
ordered low risk to elevated. Each holds a chest X-ray, a retinal photo, an ECG
export and a `client.txt` saying what to type.

1. **Take the data.** Sign in as `underwriter`. New application. Type the
   client and the cover from `client.txt`. On the Evidence step, drag the three
   files into the zone at the top: each is identified and its reader switched
   on. Select the lab reader and type the blood values. Tick the health
   questions. Continue to Check, confirm what each file is, submit.
2. **AI reads it.** The application appears in Applications as "Reading
   evidence" and becomes "Ready to decide" on its own. Open it: the composite
   score, and under it every reader's own score and reasons.
3. **Hand it to the doctor.** For an elevated case (clients 3 and 5), pick
   "Escalate to a medical professional", add a note, press Hand over. The
   status becomes "With a medical professional".
4. **The doctor decides.** Sign in as `medical`. The bell shows the
   escalation with the note; Escalations lists the case. Open it and record
   the decision.
5. **Everything updates.** Applications, Clients and Analytics reflect the
   decision; the client's portal (Check status, with the portal ID from the
   confirmation screen) shows the offer.

## Company settings

Signed in as `admin`, **Company settings** in the sidebar holds three things:

- **Risk-score boundaries.** Drag the two handles (or type) to move where low
  becomes moderate and moderate becomes elevated. The preview shows how the
  company's existing scores would fall under the proposed boundaries. Saving
  affects new scores only: every score keeps the boundaries it was tiered
  with, and the review screen shows them.
- **Pricing policy.** The monthly premium for the two quotable plans at a
  reference cover; the table shows what that quotes at common covers. Saving
  changes every premium shown from then on, including the client's offer.
- **Turnaround promise.** Working days until an answer, for new applications.

Every change is recorded with who made it; each card shows the last one.

## The client portal

An applicant can sign in to see where their application stands, when to expect
an answer, which documents are still needed, and the offer once one is recorded.
They never see a risk score or a model finding (SPEC §3 explains why).

### Showing it in a demo

1. Take an application as usual. The **Email** field on the intake form is
   optional.
2. On the confirmation screen you get the client's **portal ID** and
   **password**. With no mail server configured, which is the default, they are
   always shown here. Copy both before leaving the page: only a hash of the
   password is stored, so it cannot be shown again.
3. Open a private window (so the staff session does not get in the way), press
   **Check status** on the landing page (or choose the **Client** tab on the
   sign-in page), and sign in.
4. Back in the console, request a document or record a decision. The portal
   picks the change up on its own within a minute, or on refresh.

The staff and client sign-ins are separate sessions with separate cookies. Both
can be open in one browser, but a private window makes the demo easier to follow.

### Sending real email

Leave `SMTP_HOST` empty and nothing is sent; the message is written to the API
log with the password removed. To send for real, set these in `.env` and restart
the API:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=<a Gmail app password, not your account password>
SMTP_FROM=HomelanderAI <you@gmail.com>
PORTAL_URL=http://localhost:5173/portal
```

When the email goes out, the password is **not** shown to the operator. If
sending fails for any reason, the application is still submitted and the
operator is shown the sign-in instead.

Two messages exist: the sign-in at intake, and a notice when a decision is
recorded. The notice says only that there is an update and links to the portal,
because email is not a confidential channel.

### Carrier registration

The public sign-in page no longer offers "Create account". Staff accounts are
made by an administrator under **Staff** in the console. The form that onboards a
whole new carrier still exists at `/auth/register-carrier`, but nothing links to
it.

---

## Quick reference

| | Command |
|---|---|
| Start the database | `npm run infra:up` |
| Apply the schema | `cd apps/api && uv run alembic upgrade head` |
| Load sample accounts | `docker exec -i homelander-postgres psql -U homelander -d homelander < db/seed.sql` |
| Start API + dashboard | `npm run dev` |
| Is the database reachable? | `http://127.0.0.1:8000/api/health/database` |
| Sign in with no database | `underwriter`, `medical` or `admin`, password `admin123` |
| Is the API alive? | `http://127.0.0.1:8000/api/health` |
| Dashboard | `http://localhost:5173` |
| Images to demo with | `data/demo/` — **not** `Reference/Nirnoy/assets/samples/` |
| Pricing per tier | Pricing tab in the dashboard |

Both machines must be on the same network. A phone hotspot works if the office
network blocks machine-to-machine traffic, which many do.
