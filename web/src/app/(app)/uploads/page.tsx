"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import useSWR from "swr";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Spinner,
  StatusBadge,
  TableCard,
  inputClass,
} from "@/components/ui";
import {
  academicYears,
  api,
  errorMessage,
  fetcher,
  formatDateTime,
  type Institute,
  type Upload,
} from "@/lib/api";
import { useSession } from "@/lib/session";

const inProgress = (upload: Upload) => upload.status === "queued" || upload.status === "validating";

function UploadForm() {
  const router = useRouter();
  const [years] = useState(() => academicYears(new Date()));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const upload = await api<Upload>("/uploads", {
        method: "POST",
        body: new FormData(event.currentTarget),
      });
      router.push(`/uploads/${upload.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Card className="mb-8 p-5">
      <h2 className="font-medium">Upload student records</h2>
      <p className="mt-1 text-sm text-muted">
        One row per newly admitted student, as CSV or Excel. Every row is checked before anything
        is saved.{" "}
        <a href="/api/v1/uploads/template.csv" className="font-medium text-accent hover:underline">
          Download the template
        </a>
      </p>
      <form onSubmit={submit} className="mt-4 flex flex-wrap items-end gap-4">
        <label className="block text-sm">
          <span className="mb-1.5 block font-medium">Academic year of admission</span>
          <select name="academic_year" className={`${inputClass} min-w-40`}>
            {years.map((year) => (
              <option key={year}>{year}</option>
            ))}
          </select>
        </label>
        <label className="block min-w-0 flex-1 basis-64 text-sm">
          <span className="mb-1.5 block font-medium">File</span>
          <input
            name="file"
            type="file"
            accept=".csv,.xlsx"
            required
            className="block w-full text-sm text-muted file:mr-3 file:h-9 file:cursor-pointer file:rounded-lg file:border file:border-solid file:border-line file:bg-surface file:px-3 file:text-sm file:font-medium file:text-foreground"
          />
        </label>
        <Button type="submit" disabled={busy}>
          {busy ? "Uploading…" : "Upload and validate"}
        </Button>
      </form>
      {error && (
        <div className="mt-4">
          <Alert tone="danger">{error}</Alert>
        </div>
      )}
    </Card>
  );
}

export default function UploadsPage() {
  const user = useSession();
  const isAdmin = user.role === "institute_admin";
  const { data: uploads, error } = useSWR<Upload[]>("/uploads", fetcher, {
    refreshInterval: (latest) => (latest?.some(inProgress) ? 2000 : 0),
  });
  const { data: institute } = useSWR<Institute>(isAdmin ? "/institutes/me" : null, fetcher);
  const { data: institutes } = useSWR<Institute[]>(isAdmin ? null : "/institutes", fetcher);
  const instituteName = new Map(institutes?.map((item) => [item.id, item.name]));

  return (
    <>
      <PageHeader
        title="Uploads"
        description={
          isAdmin
            ? institute?.name
            : "Every file submitted by an institute, with its validation result."
        }
      />

      {isAdmin && institute && institute.status !== "active" && (
        <div className="mb-8">
          <Alert tone="warning">
            {institute.status === "pending"
              ? "Your institute is waiting for approval by an AICTE officer. You can upload student records once it is approved."
              : `Your institute is ${institute.status}, so uploads are disabled. Contact AICTE for help.`}
          </Alert>
        </div>
      )}
      {isAdmin && institute?.status === "active" && <UploadForm />}

      {error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : !uploads ? (
        <Spinner label="Loading uploads…" />
      ) : uploads.length === 0 ? (
        <EmptyState>
          {isAdmin
            ? "No uploads yet. Your files and their validation results will be listed here."
            : "No institute has uploaded a file yet."}
        </EmptyState>
      ) : (
        <TableCard>
          <thead>
            <tr>
              <th>File</th>
              {!isAdmin && <th>Institute</th>}
              <th>Year</th>
              <th>Status</th>
              <th className="text-right">Rows</th>
              <th className="text-right">With errors</th>
              <th>Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {uploads.map((upload) => (
              <tr key={upload.id}>
                <td className="max-w-64">
                  <Link
                    href={`/uploads/${upload.id}`}
                    className="block truncate font-medium text-accent hover:underline"
                  >
                    {upload.original_filename}
                  </Link>
                </td>
                {!isAdmin && (
                  <td className="max-w-56 truncate">
                    {instituteName.get(upload.institute_id) ?? "…"}
                  </td>
                )}
                <td className="whitespace-nowrap">{upload.academic_year}</td>
                <td>
                  <StatusBadge status={upload.status} />
                </td>
                <td className="text-right tabular-nums">{upload.total_rows.toLocaleString()}</td>
                <td
                  className={`text-right tabular-nums ${upload.error_rows ? "font-medium text-danger" : ""}`}
                >
                  {upload.error_rows.toLocaleString()}
                </td>
                <td className="whitespace-nowrap text-muted">
                  {formatDateTime(upload.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </TableCard>
      )}
    </>
  );
}
