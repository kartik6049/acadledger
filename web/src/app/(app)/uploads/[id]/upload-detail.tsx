"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  Alert,
  Badge,
  Button,
  Card,
  PageHeader,
  Spinner,
  StatusBadge,
  TableCard,
} from "@/components/ui";
import {
  type ApiError,
  api,
  errorMessage,
  fetcher,
  formatDateTime,
  type Page,
  type Upload,
  type UploadRow,
} from "@/lib/api";
import { useSession } from "@/lib/session";

const PAGE_SIZE = 50;

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <Card className="px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${tone ?? ""}`}>
        {value.toLocaleString()}
      </div>
    </Card>
  );
}

function CommitPanel({ upload }: { upload: Upload }) {
  const { mutate } = useSWRConfig();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function commit() {
    setBusy(true);
    setError(null);
    try {
      await api<Upload>(`/uploads/${upload.id}/commit`, { method: "POST" });
    } catch (err) {
      setError(errorMessage(err));
      setConfirming(false);
    } finally {
      setBusy(false);
      // success or not, the upload and its rows may have changed on the server
      await mutate((key) => typeof key === "string" && key.startsWith(`/uploads/${upload.id}`));
    }
  }

  return (
    <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
      <div className="min-w-0 flex-1 basis-72">
        <h2 className="font-medium">Ready to commit</h2>
        <p className="mt-1 text-sm text-muted">
          All {upload.total_rows.toLocaleString()} rows passed validation. Committing adds them to
          the central repository as verified student records. This cannot be undone from here.
        </p>
        {error && (
          <div className="mt-3">
            <Alert tone="danger">{error}</Alert>
          </div>
        )}
      </div>
      {confirming ? (
        <div className="flex gap-2">
          <Button variant="secondary" disabled={busy} onClick={() => setConfirming(false)}>
            Cancel
          </Button>
          <Button disabled={busy} onClick={commit}>
            {busy ? "Committing…" : `Yes, commit ${upload.total_rows.toLocaleString()} students`}
          </Button>
        </div>
      ) : (
        <Button onClick={() => setConfirming(true)}>Commit to repository</Button>
      )}
    </Card>
  );
}

function IntakeTable({ upload }: { upload: Upload }) {
  const findings = upload.summary.intake ?? [];
  if (findings.length === 0) return null;
  const committed = upload.status === "committed";
  return (
    <section>
      <h2 className="mb-1 font-medium">Enrolment against approved intake</h2>
      <p className="mb-3 text-sm text-muted">
        Counts valid rows only{committed ? ", as they stood when this file was validated" : ""}.
        Enrolment above the approved intake is accepted but flagged to AICTE.
      </p>
      <TableCard>
        <thead>
          <tr>
            <th>Programme</th>
            <th className="text-right">Approved intake</th>
            <th className="text-right">Already enrolled</th>
            <th className="text-right">In this file</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((finding) => (
            <tr key={finding.programme_code}>
              <td>
                <span className="font-medium">{finding.programme_code}</span>{" "}
                <span className="text-muted">{finding.programme_name}</span>
              </td>
              <td className="text-right tabular-nums">{finding.approved_intake}</td>
              <td className="text-right tabular-nums">{finding.already_enrolled}</td>
              <td className="text-right tabular-nums">{finding.in_this_upload}</td>
              <td>
                {finding.excess > 0 ? (
                  <Badge tone="warning">{finding.excess} over intake</Badge>
                ) : (
                  <Badge tone="success">within intake</Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </TableCard>
    </section>
  );
}

function ErrorRows({ upload }: { upload: Upload }) {
  const [offset, setOffset] = useState(0);
  const { data, error } = useSWR<Page<UploadRow>>(
    `/uploads/${upload.id}/rows?limit=${PAGE_SIZE}&offset=${offset}`,
    fetcher,
    { keepPreviousData: true },
  );
  const codes = Object.entries(upload.summary.errors_by_code ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-medium">Rows to fix</h2>
        <a
          href={`/api/v1/uploads/${upload.id}/errors.csv`}
          className="inline-flex h-9 items-center rounded-lg border border-line bg-surface px-3.5 text-sm font-medium hover:bg-background"
        >
          Download error report (CSV)
        </a>
      </div>
      <div className="mb-3 flex flex-wrap gap-2">
        {codes.map(([code, count]) => (
          <Badge key={code} tone="danger">
            {code} × {count}
          </Badge>
        ))}
      </div>
      {error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : !data ? (
        <Spinner label="Loading rows…" />
      ) : (
        <>
          <TableCard>
            <thead>
              <tr>
                <th className="text-right">Row</th>
                <th>Column</th>
                <th>Value in file</th>
                <th>Problem</th>
              </tr>
            </thead>
            <tbody>
              {data.items.flatMap((row) =>
                row.errors.map((rowError, index) => (
                  <tr key={`${row.row_number}-${index}`}>
                    <td className="text-right tabular-nums text-muted">
                      {index === 0 ? row.row_number : ""}
                    </td>
                    <td className="font-mono text-xs">{rowError.field}</td>
                    <td className="max-w-56 truncate font-mono text-xs">
                      {row.data[rowError.field] || <span className="text-muted">(empty)</span>}
                    </td>
                    <td>{rowError.message}</td>
                  </tr>
                )),
              )}
            </tbody>
          </TableCard>
          {data.total > PAGE_SIZE && (
            <div className="mt-3 flex items-center justify-between text-sm text-muted">
              <span>
                Rows {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of{" "}
                {data.total.toLocaleString()} with errors
              </span>
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
            </div>
          )}
        </>
      )}
    </section>
  );
}

export function UploadDetail() {
  const { id } = useParams<{ id: string }>();
  const user = useSession();
  const { data: upload, error } = useSWR<Upload, ApiError>(`/uploads/${id}`, fetcher, {
    refreshInterval: (latest) =>
      !latest || latest.status === "queued" || latest.status === "validating" ? 1000 : 0,
    shouldRetryOnError: false,
  });

  if (error) {
    return (
      <Alert tone="danger">
        <div>{error.message}</div>
        <Link href="/uploads" className="mt-1 inline-block font-medium underline">
          Back to uploads
        </Link>
      </Alert>
    );
  }
  if (!upload) return <Spinner label="Loading upload…" />;

  const pending = upload.status === "queued" || upload.status === "validating";
  const isAdmin = user.role === "institute_admin";

  return (
    <div className="space-y-6">
      <div>
        <Link href="/uploads" className="text-sm text-muted hover:text-foreground">
          ← Uploads
        </Link>
        <div className="mt-2">
          <PageHeader
            title={upload.original_filename}
            description={`Academic year ${upload.academic_year} · uploaded ${formatDateTime(upload.created_at)}`}
            action={<StatusBadge status={upload.status} />}
          />
        </div>
      </div>

      {pending && (
        <Card className="p-5">
          <Spinner label="Validating every row. This page updates by itself." />
        </Card>
      )}

      {upload.status === "failed" && (
        <Alert tone="danger">
          <strong>This file could not be processed.</strong> {upload.failure_reason}{" "}
          {isAdmin && (
            <Link href="/uploads" className="font-medium underline">
              Upload a corrected file
            </Link>
          )}
        </Alert>
      )}

      {(upload.status === "validated" || upload.status === "committed") && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Rows in file" value={upload.total_rows} />
            <Stat label="Valid" value={upload.valid_rows} tone="text-success" />
            <Stat
              label="With errors"
              value={upload.error_rows}
              tone={upload.error_rows ? "text-danger" : undefined}
            />
          </div>

          {upload.status === "committed" && upload.committed_at && (
            <Alert tone="success">
              {upload.total_rows.toLocaleString()} students were added to the central repository on{" "}
              {formatDateTime(upload.committed_at)}.
            </Alert>
          )}
          {upload.status === "validated" && upload.error_rows > 0 && (
            <Alert tone="warning">
              <strong>Nothing has been saved.</strong> Fix the {upload.error_rows.toLocaleString()}{" "}
              {upload.error_rows === 1 ? "row" : "rows"} listed below in your spreadsheet, then
              upload the whole file again. A file is committed only when every row is valid.
            </Alert>
          )}
          {upload.status === "validated" && upload.error_rows === 0 && isAdmin && (
            <CommitPanel upload={upload} />
          )}

          <IntakeTable upload={upload} />
          {upload.error_rows > 0 && <ErrorRows upload={upload} />}
        </>
      )}
    </div>
  );
}
