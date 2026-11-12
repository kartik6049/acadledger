"use client";

import { type FormEvent, useState, useSyncExternalStore } from "react";
import useSWR from "swr";
import { Alert, Button, Card, PageHeader, Spinner, inputClass } from "@/components/ui";
import { type ApiError, formatDateTime, postJson, type VerifiedRecord } from "@/lib/api";

const TOKEN_PATTERN = /^[A-Za-z0-9_-]{20,100}$/;

function subscribeToHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

/** The token from the URL's #fragment: that is where a scanned QR code puts it. */
function useTokenFromUrl(): string {
  return useSyncExternalStore(
    subscribeToHash,
    () => window.location.hash.slice(1),
    () => "",
  );
}

function TokenForm() {
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const pasted = String(new FormData(event.currentTarget).get("link") ?? "").trim();
    // accept either the whole link or just the code at the end of it
    const token = pasted.includes("#") ? pasted.slice(pasted.lastIndexOf("#") + 1) : pasted;
    if (!TOKEN_PATTERN.test(token)) {
      setError("That does not look like a verification link. Paste the whole link and try again.");
      return;
    }
    window.location.hash = token;
  }

  return (
    <Card className="max-w-2xl p-5">
      <h2 className="font-medium">Check a student&apos;s record</h2>
      <p className="mt-1 text-sm text-muted">
        Scan the QR code the student gave you with your phone&apos;s camera, or paste their
        verification link here. You can only look up students who have shared a link with you.
      </p>
      <form onSubmit={submit} className="mt-4 flex flex-wrap gap-3">
        <input
          name="link"
          required
          autoComplete="off"
          aria-label="Verification link"
          placeholder="Paste the verification link"
          className={`${inputClass} min-w-0 flex-1 basis-72 font-mono text-xs`}
        />
        <Button type="submit">Verify</Button>
      </form>
      {error && (
        <div className="mt-4">
          <Alert tone="danger">{error}</Alert>
        </div>
      )}
    </Card>
  );
}

function Result({ token }: { token: string }) {
  // One lookup per visit: each call is logged against the verifier, so no background refetching.
  const { data: record, error } = useSWR<VerifiedRecord, ApiError>(
    ["verify", token],
    () => postJson<VerifiedRecord>("/verify", { token }),
    { revalidateOnFocus: false, revalidateOnReconnect: false, shouldRetryOnError: false },
  );
  const another = (
    <Button variant="secondary" onClick={() => (window.location.hash = "")}>
      Check another link
    </Button>
  );

  if (error) {
    return (
      <div className="max-w-2xl space-y-4">
        <Alert tone="danger">
          <strong>Not verified.</strong> {error.message}. Ask the student for a new link.
        </Alert>
        {another}
      </div>
    );
  }
  if (!record) return <Spinner label="Checking the central repository…" />;

  const facts: [string, string][] = [
    ["Student", record.full_name],
    ["APAAR ID", `ending ${record.apaar_last4}`],
    ["Institute", `${record.institute_name} (AICTE ID ${record.institute_aicte_id})`],
    ["State", record.institute_state],
    ["Programme", `${record.programme_name} (${record.programme_code})`],
    ["Admitted in", record.academic_year],
    ["Enrolment no.", record.enrolment_no],
  ];

  return (
    <div className="max-w-2xl space-y-4">
      <Card className="overflow-hidden">
        <div className="flex items-center gap-3 border-b border-line bg-success-soft px-5 py-4">
          <span
            aria-hidden
            className="flex size-8 items-center justify-center rounded-full bg-success text-surface"
          >
            ✓
          </span>
          <div>
            <h2 className="font-semibold text-success">Record verified</h2>
            <p className="text-sm text-muted">
              This student is enrolled, according to the AICTE central repository.
            </p>
          </div>
        </div>
        <dl className="divide-y divide-line text-sm">
          {facts.map(([label, value]) => (
            <div key={label} className="flex flex-wrap gap-x-4 gap-y-1 px-5 py-2.5">
              <dt className="w-32 shrink-0 text-muted">{label}</dt>
              <dd className="min-w-0 flex-1 font-medium break-words">{value}</dd>
            </div>
          ))}
        </dl>
      </Card>
      {record.institute_status !== "active" && (
        <Alert tone="warning">
          Note: this institute&apos;s status with AICTE is currently{" "}
          <strong>{record.institute_status}</strong>.
        </Alert>
      )}
      <p className="text-xs text-muted">
        Checked on {formatDateTime(record.verified_at)}. This lookup has been recorded in the audit
        log. The student&apos;s link stays valid until {formatDateTime(record.link_expires_at)}{" "}
        unless it is revoked.
      </p>
      {another}
    </div>
  );
}

export default function VerifyPage() {
  const token = useTokenFromUrl();
  return (
    <>
      <PageHeader
        title="Verify a student"
        description="Confirm an enrolment record with the student's consent."
      />
      {token ? <Result key={token} token={token} /> : <TokenForm />}
    </>
  );
}
