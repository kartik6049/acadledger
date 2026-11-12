"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { AuthCard } from "@/components/auth-card";
import { Alert, Button, Field } from "@/components/ui";
import { errorMessage, postJson, type User } from "@/lib/api";
import { landingFor } from "@/lib/nav";

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const { user } = await postJson<{ user: User }>("/auth/login", {
        email: form.get("email"),
        password: form.get("password"),
      });
      // Go back to the page that asked for sign-in, keeping its #fragment. A full page
      // load rather than a client-side navigation, so this form (and the password typed
      // into it) is not kept alive in the background.
      const next = new URLSearchParams(window.location.search).get("next");
      const landing = landingFor(user.role, next);
      window.location.assign(landing === next ? landing + window.location.hash : landing);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Sign in"
      subtitle="Student records and verification for AICTE-approved institutions."
      footer={
        <>
          New institute?{" "}
          <Link href="/register" className="font-medium text-accent hover:underline">
            Register for access
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert tone="danger">{error}</Alert>}
        <Field label="Email" name="email" type="email" autoComplete="username" required />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthCard>
  );
}
