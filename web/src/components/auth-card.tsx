import type { ReactNode } from "react";
import { Card } from "@/components/ui";

export function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-12">
      <div className="mb-6">
        <div className="text-sm font-semibold tracking-tight text-accent">AcadLedger</div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-muted">{subtitle}</p>
      </div>
      <Card className="p-6">{children}</Card>
      <p className="mt-4 text-center text-sm text-muted">{footer}</p>
    </main>
  );
}
