"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  PageHeader,
  Spinner,
  TableCard,
  inputClass,
} from "@/components/ui";
import {
  academicYears,
  type DashboardSummary,
  errorMessage,
  fetcher,
  type IntakeRow,
  type Page,
} from "@/lib/api";

const LIMIT = 100;

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <Card className="px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value.toLocaleString()}</div>
      {note && <div className="mt-0.5 text-xs text-muted">{note}</div>}
    </Card>
  );
}

/**
 * Enrolment as a share of approved intake. The fill carries the state (accent while
 * within intake, danger once over) and the track is the soft step of the same colour.
 * The number beside it and the Status column say the same thing in words.
 */
function IntakeMeter({ row }: { row: IntakeRow }) {
  const over = row.excess > 0;
  const percent = row.approved_intake ? (row.enrolled / row.approved_intake) * 100 : over ? 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <div
        className={`h-2 w-28 overflow-hidden rounded-full ${over ? "bg-danger-soft" : "bg-accent-soft"}`}
      >
        <div
          className={`h-full rounded-full ${over ? "bg-danger" : "bg-accent"}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
      <span className="w-12 text-right text-xs tabular-nums text-muted">
        {row.approved_intake ? `${Math.round(percent)}%` : "—"}
      </span>
    </div>
  );
}

export default function DashboardPage() {
  const [years] = useState(() => academicYears(new Date()));
  const [year, setYear] = useState(years[0]);
  const [onlyExcess, setOnlyExcess] = useState(false);
  const { data: summary, error: summaryError } = useSWR<DashboardSummary>(
    `/dashboard/summary?academic_year=${year}`,
    fetcher,
  );
  const { data: rows, error: rowsError } = useSWR<Page<IntakeRow>>(
    `/dashboard/intake?academic_year=${year}&only_excess=${onlyExcess}&limit=${LIMIT}`,
    fetcher,
    { keepPreviousData: true },
  );
  const error = summaryError ?? rowsError;

  return (
    <>
      <PageHeader
        title="Enrolment dashboard"
        description="Students in the central repository, measured against each programme's approved intake."
        action={
          <label className="flex items-center gap-2 text-sm">
            <span className="whitespace-nowrap text-muted">Academic year</span>
            <select
              value={year}
              onChange={(event) => setYear(event.target.value)}
              className={`${inputClass} w-auto`}
            >
              {years.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
        }
      />

      {error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : !summary || !rows ? (
        <Spinner label="Loading dashboard…" />
      ) : (
        <div className="space-y-6">
          {summary.programmes_over_intake > 0 ? (
            <Alert tone="danger">
              <strong>
                {summary.programmes_over_intake}{" "}
                {summary.programmes_over_intake === 1 ? "programme has" : "programmes have"}{" "}
                enrolled more students than AICTE approved.
              </strong>{" "}
              {summary.excess_students.toLocaleString()}{" "}
              {summary.excess_students === 1 ? "student is" : "students are"} above the approved
              intake in {summary.academic_year}.
            </Alert>
          ) : (
            <Alert tone="success">
              No programme is over its approved intake in {summary.academic_year}.
            </Alert>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat
              label="Programmes over intake"
              value={summary.programmes_over_intake}
              note={`of ${summary.programmes.toLocaleString()} with an approved intake`}
            />
            <Stat label="Students above intake" value={summary.excess_students} />
            <Stat
              label="Students enrolled"
              value={summary.enrolled}
              note={`approved intake ${summary.approved_intake.toLocaleString()}`}
            />
            <Stat
              label="Active institutes"
              value={summary.institutes_active}
              note={
                summary.institutes_pending
                  ? `${summary.institutes_pending} awaiting approval`
                  : undefined
              }
            />
          </div>

          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-medium">Programmes</h2>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={onlyExcess}
                  onChange={(event) => setOnlyExcess(event.target.checked)}
                  className="size-4 accent-accent"
                />
                Only programmes over intake
              </label>
            </div>
            {rows.items.length === 0 ? (
              <EmptyState>
                {onlyExcess
                  ? "No programme is over its approved intake."
                  : `No programme has an approved intake for ${year} yet.`}
              </EmptyState>
            ) : (
              <TableCard>
                <thead>
                  <tr>
                    <th>Institute</th>
                    <th>Programme</th>
                    <th className="text-right">Approved</th>
                    <th className="text-right">Enrolled</th>
                    <th>Intake used</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.items.map((row) => (
                    <tr key={`${row.institute_id}-${row.programme_code}`}>
                      <td className="max-w-64">
                        <Link
                          href={`/institutes/${row.institute_id}`}
                          className="block truncate font-medium text-accent hover:underline"
                        >
                          {row.institute_name}
                        </Link>
                        <span className="text-xs text-muted">
                          {row.aicte_id} · {row.state}
                        </span>
                      </td>
                      <td>
                        <span className="font-medium">{row.programme_code}</span>
                        <span className="block max-w-56 truncate text-xs text-muted">
                          {row.programme_name}
                        </span>
                      </td>
                      <td className="text-right tabular-nums">
                        {row.approved_intake.toLocaleString()}
                      </td>
                      <td className="text-right tabular-nums">{row.enrolled.toLocaleString()}</td>
                      <td>
                        <IntakeMeter row={row} />
                      </td>
                      <td>
                        {row.excess > 0 ? (
                          <Badge tone="danger">▲ {row.excess.toLocaleString()} over intake</Badge>
                        ) : (
                          <Badge>Within intake</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </TableCard>
            )}
            {rows.total > LIMIT && (
              <p className="mt-3 text-sm text-muted">
                Showing the first {LIMIT} of {rows.total.toLocaleString()} programmes, the ones
                furthest over intake first.
              </p>
            )}
          </section>
        </div>
      )}
    </>
  );
}
