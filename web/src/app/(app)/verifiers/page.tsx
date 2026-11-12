"use client";

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
  TableCard,
} from "@/components/ui";
import { errorMessage, fetcher, formatDateTime, postJson, type Verifier } from "@/lib/api";

export default function VerifiersPage() {
  const { data: verifiers, error, mutate } = useSWR<Verifier[]>("/verifiers", fetcher);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy(true);
    setFormError(null);
    try {
      await postJson("/verifiers", Object.fromEntries(form));
      formElement.reset();
      await mutate();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Verifiers"
        description="Employers and universities authorised to confirm student records. A verifier can only look up a student who has shared a verification link with them."
      />

      <div className="space-y-6">
        {error ? (
          <Alert tone="danger">{errorMessage(error)}</Alert>
        ) : !verifiers ? (
          <Spinner label="Loading verifiers…" />
        ) : verifiers.length === 0 ? (
          <EmptyState>No verifier has been authorised yet.</EmptyState>
        ) : (
          <TableCard>
            <thead>
              <tr>
                <th>Name</th>
                <th>Organisation</th>
                <th>Email</th>
                <th>Authorised</th>
              </tr>
            </thead>
            <tbody>
              {verifiers.map((verifier) => (
                <tr key={verifier.id}>
                  <td className="font-medium">{verifier.full_name}</td>
                  <td>{verifier.organisation ?? <span className="text-muted">—</span>}</td>
                  <td>{verifier.email}</td>
                  <td className="whitespace-nowrap text-muted">
                    {formatDateTime(verifier.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableCard>
        )}

        <Card className="p-5">
          <h2 className="font-medium">Authorise a verifier</h2>
          <p className="mt-1 text-sm text-muted">
            Creates a sign-in for one person at the organisation. Share the password with them
            through a separate channel.
          </p>
          <form onSubmit={submit} className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Full name" name="full_name" maxLength={200} required />
            <Field label="Organisation" name="organisation" maxLength={200} required />
            <Field label="Email" name="email" type="email" autoComplete="off" required />
            <Field
              label="Initial password"
              name="password"
              type="password"
              autoComplete="new-password"
              minLength={10}
              maxLength={128}
              hint="At least 10 characters."
              required
            />
            <div className="sm:col-span-2">
              <Button type="submit" disabled={busy}>
                {busy ? "Creating…" : "Authorise verifier"}
              </Button>
            </div>
          </form>
          {formError && (
            <div className="mt-4">
              <Alert tone="danger">{formError}</Alert>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
