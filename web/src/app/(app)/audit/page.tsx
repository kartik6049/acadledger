"use client";

import useSWR from "swr";
import { Alert, Button, PageHeader, Spinner, TableCard } from "@/components/ui";
import {
  type AuditEntry,
  type ChainReport,
  errorMessage,
  fetcher,
  formatDateTime,
  type Page,
} from "@/lib/api";

const LIMIT = 100;

function ChainStatus() {
  const { data, error, isValidating, mutate } = useSWR<ChainReport>("/audit/verify", fetcher, {
    revalidateOnFocus: false,
  });
  if (error) return <Alert tone="danger">{errorMessage(error)}</Alert>;
  if (!data) return <Spinner label="Verifying the hash chain…" />;
  return (
    <Alert tone={data.ok ? "success" : "danger"}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>
          {data.ok ? (
            <>
              <strong>Chain intact.</strong> All {data.entries_checked.toLocaleString()} entries
              link to the one before and match their stored hash.
            </>
          ) : (
            <>
              <strong>Chain broken at entry #{data.first_broken_id}.</strong> It {data.reason}.
              Entries from that point on cannot be trusted.
            </>
          )}
        </span>
        <Button variant="secondary" disabled={isValidating} onClick={() => mutate()}>
          {isValidating ? "Verifying…" : "Verify again"}
        </Button>
      </div>
    </Alert>
  );
}

export default function AuditPage() {
  const { data, error } = useSWR<Page<AuditEntry>>(`/audit?limit=${LIMIT}`, fetcher);

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every significant action, in an append-only log where each entry carries the hash of the one before it."
      />
      <div className="mb-6">
        <ChainStatus />
      </div>
      {error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : !data ? (
        <Spinner label="Loading entries…" />
      ) : (
        <>
          <TableCard>
            <thead>
              <tr>
                <th className="text-right">#</th>
                <th>When</th>
                <th>Action</th>
                <th>By</th>
                <th>Details</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((entry) => (
                <tr key={entry.id} className="align-top">
                  <td className="text-right tabular-nums text-muted">{entry.id}</td>
                  <td className="whitespace-nowrap text-muted">
                    {formatDateTime(entry.occurred_at)}
                  </td>
                  <td className="font-mono text-xs whitespace-nowrap">{entry.action}</td>
                  <td className="whitespace-nowrap">{entry.actor_role ?? "system"}</td>
                  <td className="max-w-80 font-mono text-xs break-words text-muted">
                    {Object.entries(entry.payload)
                      .map(([key, value]) => `${key}=${String(value)}`)
                      .join("  ")}
                  </td>
                  <td className="font-mono text-xs text-muted" title={entry.hash}>
                    {entry.hash.slice(0, 10)}…
                  </td>
                </tr>
              ))}
            </tbody>
          </TableCard>
          {data.total > LIMIT && (
            <p className="mt-3 text-sm text-muted">
              Showing the latest {LIMIT} of {data.total.toLocaleString()} entries.
            </p>
          )}
        </>
      )}
    </>
  );
}
