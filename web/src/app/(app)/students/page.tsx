"use client";

import { QRCodeSVG } from "qrcode.react";
import { type FormEvent, useState } from "react";
import useSWR from "swr";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Spinner,
  TableCard,
  inputClass,
} from "@/components/ui";
import {
  api,
  errorMessage,
  fetcher,
  formatDateTime,
  type Page,
  postJson,
  type Student,
  type VerificationLink,
} from "@/lib/api";
import { useSession } from "@/lib/session";

const PAGE_SIZE = 50;
const EXPIRY_OPTIONS = [7, 30, 90];

function linkState(link: VerificationLink, now: number): "active" | "revoked" | "expired" {
  if (link.revoked_at) return "revoked";
  return new Date(link.expires_at).getTime() < now ? "expired" : "active";
}

function VerificationPanel({ student, onClose }: { student: Student; onClose: () => void }) {
  const path = `/students/${student.id}/verification-links`;
  const { data: links, error, mutate } = useSWR<VerificationLink[]>(path, fetcher);
  const [now] = useState(() => Date.now());
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // the full link exists only here, in this browser tab, until the panel is closed
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
      await mutate();
    }
  }

  const create = () =>
    run(async () => {
      const link = await postJson<{ token: string }>(path, { expires_in_days: days });
      // The token rides in the #fragment, which browsers never send to a server,
      // so it stays out of access logs.
      setCreated(`${window.location.origin}/verify#${link.token}`);
      setCopied(false);
    });

  const revoke = (link: VerificationLink) =>
    run(() => api(`/verification-links/${link.id}`, { method: "DELETE" }));

  return (
    <Card className="mb-6 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-medium">Verification links for {student.full_name}</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Create a link only when the student asks for one. Whoever they give it to, an employer
            or a university, can confirm this enrolment record until the link expires or you revoke
            it. Every lookup is recorded in the audit log.
          </p>
        </div>
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      </div>

      {actionError && (
        <div className="mt-4">
          <Alert tone="danger">{actionError}</Alert>
        </div>
      )}

      {created ? (
        <div className="mt-4 flex flex-wrap items-center gap-5 rounded-lg border border-line p-4">
          {/* always dark-on-white: QR scanners need the contrast whatever the theme */}
          <div className="rounded-lg bg-white p-3">
            <QRCodeSVG value={created} size={148} title="Verification QR code" />
          </div>
          <div className="min-w-0 flex-1 basis-64 space-y-3 text-sm">
            <p>
              <strong>Give this QR code or link to the student now.</strong> It cannot be shown
              again: only a fingerprint of it is stored.
            </p>
            <input
              readOnly
              value={created}
              aria-label="Verification link"
              onFocus={(event) => event.target.select()}
              className={`${inputClass} font-mono text-xs`}
            />
            <div className="flex gap-2">
              <Button
                variant="secondary"
                onClick={async () => {
                  await navigator.clipboard.writeText(created);
                  setCopied(true);
                }}
              >
                {copied ? "Copied" : "Copy link"}
              </Button>
              <Button variant="secondary" onClick={() => setCreated(null)}>
                Done
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium">Valid for</span>
            <select
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
              className={`${inputClass} w-auto`}
            >
              {EXPIRY_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option} days
                </option>
              ))}
            </select>
          </label>
          <Button disabled={busy} onClick={create}>
            Create link and QR code
          </Button>
        </div>
      )}

      <div className="mt-5">
        {error ? (
          <Alert tone="danger">{errorMessage(error)}</Alert>
        ) : !links ? (
          <Spinner label="Loading links…" />
        ) : links.length === 0 ? (
          <p className="text-sm text-muted">No link has been created for this student yet.</p>
        ) : (
          <TableCard>
            <thead>
              <tr>
                <th>Created</th>
                <th>Expires</th>
                <th>Status</th>
                <th className="text-right">Lookups</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {links.map((link) => {
                const state = linkState(link, now);
                return (
                  <tr key={link.id}>
                    <td className="whitespace-nowrap">{formatDateTime(link.created_at)}</td>
                    <td className="whitespace-nowrap">{formatDateTime(link.expires_at)}</td>
                    <td>
                      <Badge tone={state === "active" ? "success" : "neutral"}>{state}</Badge>
                    </td>
                    <td className="text-right tabular-nums">{link.lookup_count}</td>
                    <td className="text-right">
                      {state === "active" && (
                        <Button variant="danger" disabled={busy} onClick={() => revoke(link)}>
                          Revoke
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </TableCard>
        )}
      </div>
    </Card>
  );
}

export default function StudentsPage() {
  const user = useSession();
  const isAdmin = user.role === "institute_admin";
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Student | null>(null);
  const { data, error } = useSWR<Page<Student>>(
    `/students?limit=${PAGE_SIZE}&offset=${offset}&q=${encodeURIComponent(query)}`,
    fetcher,
    { keepPreviousData: true },
  );

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(String(new FormData(event.currentTarget).get("q") ?? "").trim());
    setOffset(0);
  }

  return (
    <>
      <PageHeader
        title="Students"
        description="Committed records in the central repository: one per APAAR ID."
        action={
          <form onSubmit={search} role="search" className="flex w-96 max-w-full gap-2">
            <input
              name="q"
              type="search"
              placeholder="Name, enrolment no. or APAAR ID"
              aria-label="Search students"
              className={`${inputClass} min-w-0 flex-1`}
            />
            <Button type="submit" variant="secondary">
              Search
            </Button>
          </form>
        }
      />

      {selected && (
        <VerificationPanel
          key={selected.id}
          student={selected}
          onClose={() => setSelected(null)}
        />
      )}

      {error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : !data ? (
        <Spinner label="Loading students…" />
      ) : data.items.length === 0 ? (
        <EmptyState>
          {query
            ? `No student matches “${query}”.`
            : "No students yet. They appear here once an upload has been committed."}
        </EmptyState>
      ) : (
        <>
          <TableCard>
            <thead>
              <tr>
                <th>Enrolment no.</th>
                <th>Name</th>
                <th>APAAR ID</th>
                <th>Programme</th>
                <th>Admitted</th>
                {isAdmin && <th />}
              </tr>
            </thead>
            <tbody>
              {data.items.map((student) => (
                <tr key={student.id}>
                  <td className="font-mono text-xs whitespace-nowrap">{student.enrolment_no}</td>
                  <td className="max-w-64 truncate font-medium">{student.full_name}</td>
                  <td className="font-mono text-xs">{student.apaar_id}</td>
                  <td>{student.programme_code}</td>
                  <td className="whitespace-nowrap">{student.academic_year}</td>
                  {isAdmin && (
                    <td className="text-right">
                      <Button
                        variant="secondary"
                        aria-label={`Verification link for ${student.full_name}`}
                        onClick={() => {
                          setSelected(student);
                          window.scrollTo({ top: 0, behavior: "smooth" });
                        }}
                      >
                        Verification link
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </TableCard>
          <div className="mt-3 flex items-center justify-between text-sm text-muted">
            <span>
              {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of{" "}
              {data.total.toLocaleString()} students
            </span>
            {data.total > PAGE_SIZE && (
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(offset - PAGE_SIZE)}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  disabled={offset + PAGE_SIZE >= data.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
