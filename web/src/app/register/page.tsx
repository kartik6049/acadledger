"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { AuthCard } from "@/components/auth-card";
import { Alert, Button, Field } from "@/components/ui";
import { errorMessage, type Institute, postJson } from "@/lib/api";

export default function RegisterPage() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [registered, setRegistered] = useState<Institute | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const institute = await postJson<Institute>("/institutes/register", {
        aicte_id: form.get("aicte_id"),
        name: form.get("name"),
        state: form.get("state"),
        admin: {
          full_name: form.get("full_name"),
          email: form.get("email"),
          password: form.get("password"),
        },
      });
      setRegistered(institute);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const signIn = (
    <>
      Already registered?{" "}
      <Link href="/login" className="font-medium text-accent hover:underline">
        Sign in
      </Link>
    </>
  );

  if (registered) {
    return (
      <AuthCard
        title="Registration received"
        subtitle="One more step before you can upload."
        footer={signIn}
      >
        <Alert tone="success">
          <strong>{registered.name}</strong> is registered and waiting for approval by an AICTE
          officer. You can sign in now and will be able to upload student records once it is
          approved.
        </Alert>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Register your institute"
      subtitle="An AICTE officer reviews each registration before uploads are enabled."
      footer={signIn}
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert tone="danger">{error}</Alert>}
        <Field label="Institute name" name="name" maxLength={300} required />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="AICTE permanent ID" name="aicte_id" maxLength={30} required />
          <Field label="State" name="state" maxLength={100} required />
        </div>
        <hr className="border-line" />
        <Field label="Your name" name="full_name" autoComplete="name" maxLength={200} required />
        <Field label="Work email" name="email" type="email" autoComplete="username" required />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={10}
          maxLength={128}
          hint="At least 10 characters."
          required
        />
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Registering…" : "Register"}
        </Button>
      </form>
    </AuthCard>
  );
}
