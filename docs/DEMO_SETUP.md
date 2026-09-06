# Demo setup — database on one machine, app on another

For the first showcase. One laptop runs PostgreSQL; the other runs the API and
the dashboard and connects to it over the network.

There is also a built-in `admin` / `admin123` sign-in that works with no
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
| `admin@dev.local` | `devpassword123` | Administrator |
| `senior@dev.local` | `devpassword123` | Senior underwriter |
| `underwriter@dev.local` | `devpassword123` | Underwriter |
| `admin` | `admin123` | Administrator, "Demo Insurance Co." |

The last row is the built-in admin. It is seeded as a real account too, so with
the database up it behaves like any other user — it can submit applications and
its actions are named in the audit trail.

---

## The built-in admin

If the database machine cannot be reached, one account still works. It touches
no database at all.

| | |
|---|---|
| Username | `admin` |
| Password | `admin123` |

**No setup needed** — it is on by default in development. You get an
administrator session for "Demo Insurance Co." and the dashboard opens normally.

Two things keep it contained:

1. **Development only.** `ENVIRONMENT` must be `development`; anywhere else it
   is ignored, whatever the password says.
2. **Clearing `ADMIN_PASSWORD` switches it off**, and empty never means "any
   password".

Every use writes a warning to the API log.

**What it cannot do while the database is unreachable:** anything that reads or
writes data. The queue, the intake form and the review screen all need the
database. Signing in this way when the database is *down* shows the application
running and nothing more.

With the database up, this account is seeded (`db/seed.sql`) and works fully.

---

## Quick reference

| | Command |
|---|---|
| Start the database | `npm run infra:up` |
| Apply the schema | `cd apps/api && uv run alembic upgrade head` |
| Load sample accounts | `docker exec -i homelander-postgres psql -U homelander -d homelander < db/seed.sql` |
| Start API + dashboard | `npm run dev` |
| Is the database reachable? | `http://127.0.0.1:8000/api/health/database` |
| Sign in with no database | `admin` / `admin123` |
| Is the API alive? | `http://127.0.0.1:8000/api/health` |
| Dashboard | `http://localhost:5173` |

Both machines must be on the same network. A phone hotspot works if the office
network blocks machine-to-machine traffic, which many do.
