"use client";

import { type FormEvent, useState } from "react";
import { Alert, Button, Card, Field, PageHeader } from "@/components/ui";
import { errorMessage, postJson } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/nav";
import { useSession } from "@/lib/session";

export default function AccountPage() {
  const user = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setChanged(false);
    if (form.get("new_password") !== form.get("confirm")) {
      setError("The two new passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await postJson("/auth/change-password", {
        current_password: form.get("current_password"),
        new_password: form.get("new_password"),
      });
      formElement.reset();
      setChanged(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Account"
        description={`${user.full_name} · ${user.email} · ${ROLE_LABEL[user.role]}`}
      />
      <Card className="max-w-md p-5">
        <h2 className="font-medium">Change password</h2>
        <p className="mt-1 text-sm text-muted">
          If someone else set your password for you, replace it with one only you know.
        </p>
        <form onSubmit={submit} className="mt-4 space-y-4">
          {error && <Alert tone="danger">{error}</Alert>}
          {changed && <Alert tone="success">Your password has been changed.</Alert>}
          <Field
            label="Current password"
            name="current_password"
            type="password"
            autoComplete="current-password"
            required
          />
          <Field
            label="New password"
            name="new_password"
            type="password"
            autoComplete="new-password"
            minLength={10}
            maxLength={128}
            hint="At least 10 characters."
            required
          />
          <Field
            label="Repeat new password"
            name="confirm"
            type="password"
            autoComplete="new-password"
            required
          />
          <Button type="submit" disabled={busy}>
            {busy ? "Changing…" : "Change password"}
          </Button>
        </form>
      </Card>
    </>
  );
}
