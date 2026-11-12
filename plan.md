# AcadLedger — APAAR-Linked Student Records & Verification Platform

> One verified, deduplicated student record per APAAR ID, from institute upload to third-party verification.

| | |
|---|---|
| **Domain** | Software |
| **Level** | Intermediate |
| **SIH problem statement** | SIH26263 — Development of an APAAR ID-Based Student Data Management and Verification Platform for AICTE-Approved Institutions |
| **Organisation** | AICTE |
| **Theme / category** | Smart Automation / Software |
| **Suggested duration** | 8 weeks |
| **Status** | All six milestones done. Remaining gaps are listed under "Not done yet" in README.md |

Source: [SIH 2026 problem statements](https://www.sih.gov.in/sih2026PS) (search for SIH26263). Read the full statement there before starting; this plan paraphrases it.

## 1. Problem

AICTE receives student-level data only from PGDM institutes; everyone else reports totals. Records cannot be verified, the same student can appear in two institutes, and enrolment beyond approved intake goes unnoticed.

## 2. Users

Institute data-entry admins, AICTE Regulation Bureau officers, authorised verifiers (employers, universities).

## 3. Goals and success criteria

The project is done when all of these are true:

- Bulk upload of 10,000 student rows validated in under 60 s with a row-level error report
- 100% of duplicate APAAR IDs across institutes rejected or flagged
- Dashboard flags every programme where enrolment exceeds approved intake
- Verification API answers in under 500 ms and every lookup is audit-logged

## 4. Scope

**In scope**

- Institute onboarding with role-based access
- CSV/Excel upload with a staged validation pipeline (schema, APAAR format, duplicates, intake)
- APAAR validation through an adapter backed by a mock service
- Central repository with a hash-chained audit trail
- Analytics dashboard and a consent-based verification endpoint with QR

**Out of scope**

- Live APAAR/ABC/DigiLocker production integration (needs government API access)
- Fees, admissions or exam workflows
- Native mobile app

## 5. Approach and architecture

- Next.js web app talks to a REST API backed by PostgreSQL
- Uploads land in object storage; a queue worker runs the validation stages and writes per-row results
- `ApaarClient` interface with a mock implementation now and a real one later, so nothing else changes
- Append-only audit table where each row stores the hash of the previous row
- Materialised views feed the intake-vs-enrolment dashboard

## 6. Tech stack

Next.js + TypeScript, FastAPI (or NestJS), PostgreSQL, Redis + Celery/BullMQ, MinIO/S3, Docker Compose, pytest + Playwright

## 7. Data and resources

- Synthetic students generated with Faker (never real PII)
- Public AICTE list of approved institutes and intake
- APAAR ID format rules (12-digit identifier)

## 8. Milestones

| # | When | Deliverable | Done |
|---|---|---|---|
| 1 | Week 1 | Read the PS, map the data flow, design schema and API contract | ☑ |
| 2 | Week 2-3 | Auth, institute onboarding, upload + validation pipeline | ☑ |
| 3 | Week 4-5 | Mock APAAR adapter, dedupe, central repository, audit chain | ☑ |
| 4 | Week 6 | Dashboards and excess-enrolment alerts | ☑ |
| 5 | Week 7 | Verification API + QR, load test with 100k rows | ☑ |
| 6 | Week 8 | Hardening, docs, demo rehearsal | ☑ |

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| No access to the real APAAR API | Adapter pattern + mock that mirrors the documented request/response shape |
| PII handling | Synthetic data only, field-level encryption, access logging. *As built: synthetic data only, verification lookups audit-logged, staging copies deleted on commit. Field-level encryption was not built: uploaded files and name search would still hold plain text, so it would add complexity without closing the gap. Use encryption at rest for a real deployment.* |
| Messy institute spreadsheets | Downloadable template and precise row-level error messages |

## 10. Demo script

1. Upload a file with deliberate errors and show the error report
2. Fix and re-upload; a duplicate APAAR in another institute is caught
3. Open the AICTE dashboard and show the excess-enrolment flag
4. Scan a QR to verify one student

## 11. Stretch goals

- DigiLocker-style consent flow
- Year-on-year enrolment trend analytics

## 12. Learn first

REST API design, SQL modelling and indexing, background job queues, basic auth/RBAC.

## Progress log

| Date | What changed | Next step |
|---|---|---|
| 2026-11-12 | Chose FastAPI + Celery (the plan's test tool is pytest). Built milestones 1-3: schema and migrations, auth and roles, institute onboarding, CSV/Excel upload, five-stage validation pipeline, all-or-nothing commit, mock APAAR adapter, hash-chained audit log, and the Next.js app for them. 10,000 rows validate in about 7 s. | Dashboard and verification |
| 2026-11-12 | Built milestones 4-5: enrolment dashboard on a materialised view with over-intake flags, consent-based verification links with QR, verifier accounts, students page, public home page. 100,000-row load test: about 100 s. 61 pytest tests and a Playwright run of the full demo pass. README written. | Milestone 6: field-level encryption, login rate limiting, CSRF tokens, production compose, demo rehearsal. See "Not done yet" in README.md |
| 2026-11-12 | Milestone 6, sized for a small deployment: login lockout, CSRF header check, change-password page, start-up check on the signing secret, security headers, staging rows deleted on commit, demo reset script, security section in the README. Field-level encryption was deliberately left out (see the note in section 9). 67 pytest tests and the Playwright demo pass. | Rehearse the demo with `./scripts/reset-demo.sh`; decide whether a real deployment is planned |
