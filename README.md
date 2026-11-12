# AcadLedger

One verified, deduplicated student record per APAAR ID, from institute upload to
third-party verification. Built for Smart India Hackathon 2026, problem statement
SIH26263 (AICTE). See [plan.md](plan.md) for the brief and milestones.

Institutes upload their admission lists; every row is validated; a fully valid
file is committed to a central repository that allows one record per APAAR ID;
AICTE sees enrolment against approved intake; employers verify a student from a
QR code the student shares. Every significant action lands in a hash-chained
audit log.

## Run it

Needs Docker, Node 22+ and pnpm.

```sh
cp .env.example .env            # then set JWT_SECRET (openssl rand -hex 32)
docker compose up -d            # Postgres, Redis, MinIO, API (:8000), Celery worker
docker compose exec api python -m app.seed

cd web && pnpm install && pnpm dev    # http://localhost:3000
```

The seed creates these accounts. All of them use the password in `SEED_PASSWORD`
(see `.env`); it is for local development only.

| Email | Role |
|---|---|
| `officer@aicte.example` | AICTE officer |
| `admin@sahyadri.example` | Institute admin, Sahyadri Institute of Technology (CSE, ECE, ME) |
| `admin@kaveri.example` | Institute admin, Kaveri College of Engineering (CSE, MBA) |
| `verifier@employer.example` | Verifier |

Generate synthetic student files (never use real student data):

```sh
docker compose exec api python scripts/generate_students.py \
    --rows 200 --programmes CSE,ECE,ME --errors 8 --out /app/data/with-errors.csv
docker compose exec api python scripts/generate_students.py \
    --rows 200 --programmes CSE,ECE,ME --out /app/data/clean.csv
```

They are written to `api/data/` on your machine.

## Demo

To rehearse from a clean slate, run `./scripts/reset-demo.sh`. It asks first,
then **deletes all local data**, restarts the stack, seeds the accounts above and
writes `api/data/demo-with-errors.csv` and `api/data/demo-clean.csv`.

For the demo itself, `pnpm build && pnpm start` in `web/` gives much faster
pages than `pnpm dev`.

1. Sign in as `admin@sahyadri.example`, upload `demo-with-errors.csv`, and read the row-level error report.
2. Upload `demo-clean.csv` and commit it. Then sign in as `admin@kaveri.example` and upload the same file: every row is refused, because those APAAR IDs are enrolled elsewhere.
3. Sign in as `officer@aicte.example`. The dashboard flags ECE and ME at Sahyadri as over their approved intake.
4. As the Sahyadri admin, open **Students**, create a verification link for one student, and copy it. Open it in a private window, sign in as `verifier@employer.example`, and see the verified record. The lookup appears in the officer's **Audit log**.

The QR code encodes a `localhost` link, so scanning it with a phone only works if
you serve the app on an address the phone can reach.

## How it works

```
browser ──> Next.js (web/) ──/api proxy──> FastAPI (api/) ──> PostgreSQL
                                             │      └──────> MinIO (uploaded files)
                                             └─ Redis ─> Celery worker ─> validation pipeline
```

**Upload and validation.** `POST /uploads` stores the file in object storage and
queues a job. The worker parses it (CSV or Excel) and runs five stages over every
row: `schema`, `apaar_format`, `apaar_registry`, `duplicates`, `intake`
(`api/app/pipeline/stages.py`). A row keeps going after it fails a stage, so one
pass reports everything wrong with it. Results go to the `upload_rows` staging
table; nothing reaches the repository yet.

**Commit.** All or nothing, and only when every row is valid. The duplicate
checks run again inside the commit transaction, and `students.apaar_id` has a
unique constraint, so two institutes committing the same student at the same
moment cannot both succeed.

**Intake.** Enrolment above a programme's approved intake is accepted and
flagged, not rejected: showing it to AICTE is the point. The dashboard reads the
`programme_enrolment` materialised view, which is refreshed in the same
transaction as every commit and intake change, so it is never stale.

**APAAR registry.** The pipeline depends only on the `ApaarClient` protocol
(`api/app/apaar.py`). The one implementation today is a mock that treats an ID as
registered when its last digit is a Verhoeff check digit. That rule belongs to
the mock, not to real APAAR IDs. A real client can be added and selected with
`APAAR_CLIENT` without touching the pipeline.

**Verification.** An institute issues a link for one student at the student's
request. The link carries a random token in its `#fragment` (so it never reaches
a server log) and only the token's SHA-256 hash is stored. A signed-in verifier
who presents the token gets a minimal record: name, institute, programme, year,
enrolment number, last four digits of the APAAR ID. Links expire and can be
revoked. Successful and refused lookups are both audit-logged.

**Audit trail.** `audit_log` is append-only (triggers reject UPDATE, DELETE and
TRUNCATE) and hash-chained: each entry's hash covers its own fields plus the
previous entry's hash. `GET /audit/verify` recomputes the chain and reports the
first entry that does not fit.

### Data model

| Table | Holds |
|---|---|
| `institutes` | AICTE ID, name, state, status (`pending`, `active`, `suspended`, `rejected`) |
| `users` | Email, password hash (Argon2), role, institute (institute admins only) |
| `programmes`, `programme_intakes` | Programmes per institute; approved intake per academic year |
| `uploads`, `upload_rows` | Each submitted file and its per-row validation result |
| `students` | The central repository; `apaar_id` is unique across all institutes |
| `verification_grants` | Hashed verification tokens with expiry, revocation and lookup count |
| `audit_log` | The hash-chained trail |
| `programme_enrolment` (materialised view) | Enrolled vs. approved intake per programme and year |

### API

Interactive docs: <http://localhost:8000/docs>. Everything is under `/api/v1`.

| Area | Endpoints | Who |
|---|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | anyone |
| Onboarding | `POST /institutes/register` | public |
| | `GET /institutes`, `POST /institutes/{id}/status` | officer |
| Programmes | `GET /institutes/{id}/programmes` | officer, own institute |
| | `POST /institutes/{id}/programmes`, `PUT /programmes/{id}/intakes/{year}` | officer |
| Uploads | `POST /uploads`, `POST /uploads/{id}/commit` | institute admin |
| | `GET /uploads`, `GET /uploads/{id}`, `/rows`, `/errors.csv`, `GET /uploads/template.csv` | officer, own institute |
| Students | `GET /students?q=` | officer, own institute |
| Dashboard | `GET /dashboard/summary`, `GET /dashboard/intake` | officer |
| Verification | `POST`/`GET /students/{id}/verification-links`, `DELETE /verification-links/{id}` | institute admin |
| | `POST /verify` | verifier, officer |
| | `GET`/`POST /verifiers` | officer |
| Audit | `GET /audit`, `GET /audit/verify` | officer |

The browser authenticates with an HTTP-only cookie; scripts can send the token
from `/auth/login` as a `Bearer` header instead.

## Security

Sized for a small deployment (tens of users), not for the open internet at scale.

- **Passwords** are hashed with Argon2. Five wrong passwords in a row lock an
  account for 15 minutes. Anyone can change their own password under **Account**
  (click your email in the header), which matters for verifiers, whose first
  password is set by an officer.
- **Sessions** are a signed token in an HTTP-only, `SameSite=Lax` cookie. Set
  `COOKIE_SECURE=true` when serving over HTTPS. The API refuses to start if
  `JWT_SECRET` is shorter than 32 characters.
- **Cross-site request forgery.** Requests that change anything must carry an
  `X-Requested-With` header, which another site cannot add. The web app sends it
  on every call; requests with a `Bearer` token are exempt.
- **Access control** is checked on every endpoint: an institute sees only its own
  uploads and students, and gets a 404 rather than a 403 for anyone else's.
- **Personal data.** Only synthetic data is used. Staging rows are deleted as
  soon as an upload is committed, so the repository holds the only copy. The
  verification endpoint returns the minimum needed to confirm enrolment, and the
  token is stored only as a hash.
- **Uploads** are capped at 25 MB and 200,000 rows, and the error report
  neutralises cells a spreadsheet would run as formulas.
- **Browser headers**: framing is denied, MIME sniffing is off, and no referrer
  is sent.

## Tests

```sh
docker compose run --rm --no-deps api pytest        # 67 tests, uses a separate *_test database
docker compose run --rm --no-deps api ruff check .

cd web
pnpm lint
pnpm exec playwright test       # needs the stack running and seeded; drives your installed Chrome
```

The Playwright test walks the whole demo through the real UI. It creates a new
"E2E Institute" on every run, so those accumulate in a development database.

Measured on a slow laptop: 10,000 rows validate in about 7 s (target: under
60 s); a 100,000-row file took about 100 s. The verification endpoint is asserted
to answer in under 500 ms.

## Not done yet

- Field-level encryption of personal data. For a real deployment, turn on
  encryption at rest in the database and object store instead; names and dates
  of birth are stored as plain columns, and the original uploaded files are kept.
- A real APAAR client, and a consent flow where the student grants access
  directly instead of through the institute.
- Forgotten-password reset (an officer or a database edit is the only way back
  in), and signing out other sessions when a password changes.
- Rate limiting beyond the login lockout. The public registration form can be
  spammed, and the lockout lets someone who knows an email lock that account.
- A production setup: `docker-compose.yml` is for development (default database
  and MinIO credentials, `--reload`), and the web app is not containerised.
- Transfers. A student who moves between institutes is currently just a duplicate.

## Layout

```
api/app/            FastAPI app: routers/, pipeline/ (parser, stages, runner, commit),
                    audit.py, apaar.py, enrolment.py, storage.py, worker.py, seed.py
api/migrations/     Alembic migrations
api/tests/          pytest suite
api/scripts/        synthetic data generator
web/src/app/        Next.js pages: home, login, register, and the signed-in app in (app)/
web/e2e/            Playwright end-to-end test
```
