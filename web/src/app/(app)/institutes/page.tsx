"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import {
  Alert,
  Button,
  EmptyState,
  PageHeader,
  Spinner,
  StatusBadge,
  TableCard,
} from "@/components/ui";
import {
  errorMessage,
  fetcher,
  formatDateTime,
  type Institute,
  type InstituteStatus,
  postJson,
} from "@/lib/api";

// what an officer can do next from each status
const ACTIONS: Record<
  InstituteStatus,
  { label: string; to: InstituteStatus; variant: "primary" | "secondary" | "danger" }[]
> = {
  pending: [
    { label: "Approve", to: "active", variant: "primary" },
    { label: "Reject", to: "rejected", variant: "danger" },
  ],
  active: [{ label: "Suspend", to: "suspended", variant: "danger" }],
  suspended: [{ label: "Reactivate", to: "active", variant: "secondary" }],
  rejected: [{ label: "Approve", to: "active", variant: "secondary" }],
};

export default function InstitutesPage() {
  const { data: institutes, error, mutate } = useSWR<Institute[]>("/institutes", fetcher);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function setStatus(institute: Institute, status: InstituteStatus) {
    setBusyId(institute.id);
    setActionError(null);
    try {
      await postJson(`/institutes/${institute.id}/status`, { status });
    } catch (err) {
      setActionError(`${institute.name}: ${errorMessage(err)}`);
    } finally {
      await mutate();
      setBusyId(null);
    }
  }

  const waiting = institutes?.filter((institute) => institute.status === "pending").length ?? 0;

  return (
    <>
      <PageHeader
        title="Institutes"
        description={
          waiting > 0
            ? `${waiting} ${waiting === 1 ? "registration is" : "registrations are"} waiting for your review.`
            : "Approve registrations and manage each institute's programmes and approved intake."
        }
      />
      {actionError && (
        <div className="mb-4">
          <Alert tone="danger">{actionError}</Alert>
        </div>
      )}
      {error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : !institutes ? (
        <Spinner label="Loading institutes…" />
      ) : institutes.length === 0 ? (
        <EmptyState>No institute has registered yet.</EmptyState>
      ) : (
        <TableCard>
          <thead>
            <tr>
              <th>Institute</th>
              <th>AICTE ID</th>
              <th>State</th>
              <th>Status</th>
              <th>Registered</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {institutes.map((institute) => (
              <tr key={institute.id}>
                <td className="max-w-72">
                  <Link
                    href={`/institutes/${institute.id}`}
                    className="block truncate font-medium text-accent hover:underline"
                  >
                    {institute.name}
                  </Link>
                </td>
                <td className="font-mono text-xs whitespace-nowrap">{institute.aicte_id}</td>
                <td className="whitespace-nowrap">{institute.state}</td>
                <td>
                  <StatusBadge status={institute.status} />
                </td>
                <td className="whitespace-nowrap text-muted">
                  {formatDateTime(institute.created_at)}
                </td>
                <td>
                  <div className="flex justify-end gap-2">
                    {ACTIONS[institute.status].map((action) => (
                      <Button
                        key={action.to}
                        variant={action.variant}
                        disabled={busyId === institute.id}
                        onClick={() => setStatus(institute, action.to)}
                      >
                        {action.label}
                      </Button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </TableCard>
      )}
    </>
  );
}
