"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import useSWR from "swr";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  PageHeader,
  Spinner,
  StatusBadge,
  TableCard,
  inputClass,
} from "@/components/ui";
import {
  academicYears,
  errorMessage,
  fetcher,
  type Institute,
  postJson,
  type Programme,
} from "@/lib/api";

const LEVELS = { ug: "Undergraduate", pg: "Postgraduate", diploma: "Diploma" };

function IntakeEditor({
  programme,
  year,
  onSaved,
}: {
  programme: Programme;
  year: string;
  onSaved: () => Promise<unknown>;
}) {
  const current = programme.intakes.find((intake) => intake.academic_year === year);
  const saved = current ? String(current.approved_intake) : "";
  const [value, setValue] = useState(saved);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await postJson(
        `/programmes/${programme.id}/intakes/${year}`,
        { approved_intake: Number(value) },
        "PUT",
      );
      await onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="flex items-center justify-end gap-2">
      {error && <span className="text-xs text-danger">{error}</span>}
      <input
        type="number"
        min={0}
        max={100000}
        required
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="not set"
        aria-label={`Approved intake for ${programme.code} in ${year}`}
        className={`${inputClass} w-28 text-right tabular-nums`}
      />
      <Button type="submit" variant="secondary" disabled={busy || value === saved}>
        Save
      </Button>
    </form>
  );
}

function AddProgramme({
  instituteId,
  onAdded,
}: {
  instituteId: string;
  onAdded: () => Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy(true);
    setError(null);
    try {
      await postJson(`/institutes/${instituteId}/programmes`, {
        code: form.get("code"),
        name: form.get("name"),
        level: form.get("level"),
      });
      formElement.reset();
      await onAdded();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <h2 className="font-medium">Add a programme</h2>
      <form onSubmit={submit} className="mt-4 flex flex-wrap items-end gap-4">
        <div className="w-28">
          <Field label="Code" name="code" placeholder="CSE" pattern="[A-Za-z0-9_\-]+" maxLength={20} required />
        </div>
        <div className="min-w-0 flex-1 basis-64">
          <Field label="Name" name="name" placeholder="B.Tech Computer Science" maxLength={200} required />
        </div>
        <label className="block text-sm">
          <span className="mb-1.5 block font-medium">Level</span>
          <select name="level" className={inputClass}>
            {Object.entries(LEVELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <Button type="submit" disabled={busy}>
          {busy ? "Adding…" : "Add programme"}
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

export function InstituteDetail() {
  const { id } = useParams<{ id: string }>();
  const [years] = useState(() => academicYears(new Date()));
  const [year, setYear] = useState(years[0]);
  const { data: institutes, error: instituteError } = useSWR<Institute[]>("/institutes", fetcher);
  const {
    data: programmes,
    error: programmesError,
    mutate,
  } = useSWR<Programme[]>(`/institutes/${id}/programmes`, fetcher);

  const error = instituteError ?? programmesError;
  if (error) return <Alert tone="danger">{errorMessage(error)}</Alert>;
  if (!institutes || !programmes) return <Spinner label="Loading institute…" />;

  const institute = institutes.find((item) => item.id === id);
  if (!institute) return <Alert tone="danger">Institute not found.</Alert>;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/institutes" className="text-sm text-muted hover:text-foreground">
          ← Institutes
        </Link>
        <div className="mt-2">
          <PageHeader
            title={institute.name}
            description={`AICTE ID ${institute.aicte_id} · ${institute.state}`}
            action={<StatusBadge status={institute.status} />}
          />
        </div>
      </div>

      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-medium">Programmes and approved intake</h2>
            <p className="mt-1 text-sm text-muted">
              An institute can only upload students for a programme that has an approved intake for
              that year.
            </p>
          </div>
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
        </div>
        {programmes.length === 0 ? (
          <EmptyState>This institute has no programmes yet. Add the first one below.</EmptyState>
        ) : (
          <TableCard>
            <thead>
              <tr>
                <th>Code</th>
                <th>Programme</th>
                <th>Level</th>
                <th className="text-right">Approved intake {year}</th>
              </tr>
            </thead>
            <tbody>
              {programmes.map((programme) => (
                <tr key={programme.id}>
                  <td className="font-medium">{programme.code}</td>
                  <td>{programme.name}</td>
                  <td className="text-muted">{LEVELS[programme.level]}</td>
                  <td>
                    {/* keyed by year so the input resets when the year changes */}
                    <IntakeEditor
                      key={year}
                      programme={programme}
                      year={year}
                      onSaved={() => mutate()}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </TableCard>
        )}
      </section>

      <AddProgramme instituteId={institute.id} onAdded={() => mutate()} />
    </div>
  );
}
