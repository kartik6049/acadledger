import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "AcadLedger · One verified student record per APAAR ID",
};

const PROBLEMS = [
  {
    title: "AICTE sees totals, not students",
    body: "AICTE receives student-level data only from PGDM institutes. Every other institute reports headcounts, so there is no record to check a claim against.",
  },
  {
    title: "The same student can be counted twice",
    body: "With no shared identifier across institutes, one person can appear on two institutes' rolls and nobody can tell. Individual records cannot be verified either.",
  },
  {
    title: "Over-enrolment goes unnoticed",
    body: "Each programme has an intake that AICTE approved. Without per-student data, an institute admitting more than that is invisible to the regulator.",
  },
];

const STEPS = [
  {
    title: "AICTE approves the institute and its intake",
    body: "An institute registers and waits. An AICTE officer approves it and records each programme with its approved intake for the year. Until then it cannot upload anything.",
  },
  {
    title: "The institute uploads its admission list",
    body: "A CSV or Excel file with one row per student, each carrying the student's 12-digit APAAR ID. The file is stored and queued, so a large file never blocks the page.",
  },
  {
    title: "Every row passes five checks",
    body: "Required fields and formats, the APAAR ID format, the APAAR registry, duplicates, and the programme's approved intake. Each failure is reported against its spreadsheet row and column, with a downloadable error report.",
  },
  {
    title: "Only a fully valid file is committed",
    body: "Committing is all or nothing. The database itself allows one record per APAAR ID across all institutes, so a student already enrolled elsewhere is rejected even if two institutes upload at the same moment.",
  },
  {
    title: "AICTE sees enrolment against intake",
    body: "The dashboard compares every programme's enrolment with its approved intake and flags each one that is over. Excess enrolment is accepted and flagged rather than rejected, because surfacing it is the point.",
  },
  {
    title: "Employers verify with the student's consent",
    body: "A student asks their institute for a verification link, shown as a QR code. An authorised verifier who scans it sees that one enrolment record and nothing else.",
  },
];

const TARGETS = [
  {
    goal: "10,000 rows validated in under 60 seconds, with a row-level error report",
    result:
      "About 7 seconds on a laptop in the test suite. A 100,000-row file took about 100 seconds.",
  },
  {
    goal: "Every duplicate APAAR ID across institutes is rejected or flagged",
    result:
      "Checked at validation, checked again at commit, and enforced by a unique constraint in the database.",
  },
  {
    goal: "The dashboard flags every programme whose enrolment exceeds its approved intake",
    result:
      "Read from a database view that is refreshed in the same transaction as every commit and intake change.",
  },
  {
    goal: "The verification API answers in under 500 ms and every lookup is audit-logged",
    result: "Asserted in the test suite. Refused lookups are logged too.",
  },
];

const ROLES = [
  {
    name: "Institute data-entry admins",
    body: "Upload admission lists, fix the rows that fail, commit, and issue verification links when a student asks.",
  },
  {
    name: "AICTE Regulation Bureau officers",
    body: "Approve institutes, set approved intake, watch the enrolment dashboard, and inspect the audit log.",
  },
  {
    name: "Authorised verifiers",
    body: "Employers and universities who confirm a student's enrolment from a link the student shared.",
  },
];

const STACK = [
  "Next.js + TypeScript",
  "FastAPI",
  "PostgreSQL",
  "Celery + Redis",
  "MinIO object storage",
  "Docker Compose",
  "pytest + Playwright",
];

function Section({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: string;
  title: string;
  intro?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-line py-14">
      <div className="mx-auto w-full max-w-5xl px-4">
        <p className="text-sm font-medium text-accent">{eyebrow}</p>
        <h2 className="mt-2 max-w-2xl text-2xl font-semibold tracking-tight text-balance">
          {title}
        </h2>
        {intro && <p className="mt-3 max-w-2xl text-muted">{intro}</p>}
        <div className="mt-8">{children}</div>
      </div>
    </section>
  );
}

const primaryLink =
  "inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-medium text-surface hover:opacity-90";
const secondaryLink =
  "inline-flex h-10 items-center rounded-lg border border-line bg-surface px-4 text-sm font-medium hover:bg-background";

export default function HomePage() {
  return (
    <>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <span className="font-semibold tracking-tight">AcadLedger</span>
          <nav className="flex items-center gap-2 text-sm">
            <Link href="/register" className="rounded-md px-2.5 py-1.5 text-muted hover:text-foreground">
              Register an institute
            </Link>
            <Link href="/login" className={`${primaryLink} h-9`}>
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1 bg-surface">
        <section className="mx-auto w-full max-w-5xl px-4 py-16 sm:py-20">
          <p className="text-sm font-medium text-accent">
            Smart India Hackathon 2026 · Problem statement SIH26263 · AICTE
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            One verified student record per APAAR ID
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-muted">
            AcadLedger takes an institute&apos;s admission list, checks every row, and keeps a
            single deduplicated record for each student, from the institute&apos;s upload all the
            way to an employer verifying it.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/login" className={primaryLink}>
              Sign in
            </Link>
            <Link href="/register" className={secondaryLink}>
              Register an institute
            </Link>
          </div>
        </section>

        <Section
          eyebrow="The problem statement"
          title="Development of an APAAR ID-based student data management and verification platform for AICTE-approved institutions"
          intro={
            <>
              Set by AICTE under the Smart Automation theme. In our words, it comes down to three
              gaps. The original wording is on the{" "}
              <a
                href="https://www.sih.gov.in/sih2026PS"
                className="font-medium text-accent hover:underline"
              >
                SIH 2026 problem statements page
              </a>{" "}
              (search for SIH26263).
            </>
          }
        >
          <div className="grid gap-4 sm:grid-cols-3">
            {PROBLEMS.map((problem) => (
              <div key={problem.title} className="rounded-xl border border-line p-5">
                <h3 className="font-medium">{problem.title}</h3>
                <p className="mt-2 text-sm text-muted">{problem.body}</p>
              </div>
            ))}
          </div>
        </Section>

        <Section
          eyebrow="How we approached it"
          title="Check every row on the way in, then keep exactly one record per student"
          intro="The APAAR ID is the key that makes this possible: it identifies the same student at every institute. The platform is built around what happens to a row between the spreadsheet and the central repository."
        >
          <ol className="grid gap-x-10 gap-y-8 sm:grid-cols-2">
            {STEPS.map((step, index) => (
              <li key={step.title} className="flex gap-4">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent">
                  {index + 1}
                </span>
                <div>
                  <h3 className="font-medium">{step.title}</h3>
                  <p className="mt-1.5 text-sm text-muted">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="mt-10 rounded-xl border border-line p-5">
            <h3 className="font-medium">An audit trail that shows tampering</h3>
            <p className="mt-2 max-w-3xl text-sm text-muted">
              Registrations, approvals, uploads, commits and verification lookups are written to an
              append-only log. Each entry stores the hash of the entry before it, so altering or
              deleting any past entry breaks every hash after it, and an officer can re-check the
              whole chain with one click.
            </p>
          </div>
        </Section>

        <Section
          eyebrow="Did it work"
          title="The four targets we set, and where each stands"
        >
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line text-xs text-muted">
                <tr>
                  <th className="px-5 py-3 font-medium">Target</th>
                  <th className="px-5 py-3 font-medium">How it is met</th>
                </tr>
              </thead>
              <tbody>
                {TARGETS.map((target) => (
                  <tr key={target.goal} className="border-t border-line align-top first:border-t-0">
                    <td className="w-1/2 px-5 py-3 font-medium">{target.goal}</td>
                    <td className="px-5 py-3 text-muted">{target.result}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section eyebrow="Who it is for" title="Three kinds of user, each with their own view">
          <div className="grid gap-4 sm:grid-cols-3">
            {ROLES.map((role) => (
              <div key={role.name} className="rounded-xl border border-line p-5">
                <h3 className="font-medium">{role.name}</h3>
                <p className="mt-2 text-sm text-muted">{role.body}</p>
              </div>
            ))}
          </div>
        </Section>

        <Section
          eyebrow="What is real and what is simulated"
          title="A working prototype, with its limits stated"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-line p-5">
              <h3 className="font-medium">Simulated</h3>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-muted">
                <li>
                  The APAAR registry. Real access needs government API credentials, so the registry
                  sits behind an adapter with a mock implementation that can be swapped for the real
                  one without touching the rest of the system.
                </li>
                <li>All student data. It is generated; no real personal data is used anywhere.</li>
                <li>
                  Consent. The institute issues the verification link on the student&apos;s behalf.
                  A DigiLocker-style flow where the student grants it directly is a stretch goal.
                </li>
              </ul>
            </div>
            <div className="rounded-xl border border-line p-5">
              <h3 className="font-medium">Not attempted</h3>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-muted">
                <li>Live APAAR, ABC or DigiLocker integration.</li>
                <li>Fees, admissions or examination workflows.</li>
                <li>A native mobile app.</li>
                <li>
                  Field-level encryption of personal data. Encryption at rest is left to the
                  database and disk it runs on.
                </li>
              </ul>
            </div>
          </div>
          <div className="mt-8">
            <h3 className="text-sm font-medium">Built with</h3>
            <ul className="mt-3 flex flex-wrap gap-2">
              {STACK.map((item) => (
                <li
                  key={item}
                  className="rounded-full border border-line px-3 py-1 text-sm text-muted"
                >
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </Section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto w-full max-w-5xl px-4 py-6 text-sm text-muted">
          AcadLedger is a student project for Smart India Hackathon 2026. It is not an AICTE
          service.
        </div>
      </footer>
    </>
  );
}
