import type { ComponentProps, ReactNode } from "react";

type Tone = "neutral" | "accent" | "success" | "warning" | "danger";

const toneClasses: Record<Tone, string> = {
  neutral: "bg-background text-muted border-line",
  accent: "bg-accent-soft text-accent border-transparent",
  success: "bg-success-soft text-success border-transparent",
  warning: "bg-warning-soft text-warning border-transparent",
  danger: "bg-danger-soft text-danger border-transparent",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}

const statusTones: Record<string, Tone> = {
  queued: "neutral",
  validating: "accent",
  validated: "accent",
  committed: "success",
  failed: "danger",
  pending: "warning",
  active: "success",
  suspended: "danger",
  rejected: "danger",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTones[status] ?? "neutral"}>{status}</Badge>;
}

export function Alert({ tone, children }: { tone: Exclude<Tone, "neutral">; children: ReactNode }) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={`rounded-lg border px-4 py-3 text-sm ${toneClasses[tone]}`}
    >
      {children}
    </div>
  );
}

export function Card({ className = "", ...props }: ComponentProps<"section">) {
  return (
    <section className={`rounded-xl border border-line bg-surface ${className}`} {...props} />
  );
}

type ButtonProps = ComponentProps<"button"> & { variant?: "primary" | "secondary" | "danger" };

const buttonClasses = {
  primary: "bg-accent text-surface hover:opacity-90",
  secondary: "border border-line bg-surface text-foreground hover:bg-background",
  danger: "border border-line bg-surface text-danger hover:bg-danger-soft",
};

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex h-9 items-center justify-center gap-2 rounded-lg px-3.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${buttonClasses[variant]} ${className}`}
      {...props}
    />
  );
}

export const inputClass =
  "h-9 w-full rounded-lg border border-line bg-surface px-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20";

export function Field({
  label,
  hint,
  ...props
}: ComponentProps<"input"> & { label: string; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block font-medium">{label}</span>
      <input className={inputClass} {...props} />
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-3 text-sm text-muted">
      <span className="size-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight break-words">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/** A horizontally scrollable table inside a card, so wide tables never break the page. */
export function TableCard({ children }: { children: ReactNode }) {
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-left text-sm [&_td]:px-4 [&_td]:py-2.5 [&_th]:px-4 [&_th]:py-2.5 [&_th]:text-xs [&_th]:font-medium [&_th]:text-muted [&_thead]:border-b [&_thead]:border-line [&_tbody_tr+tr]:border-t [&_tbody_tr+tr]:border-line">
        {children}
      </table>
    </Card>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <Card className="px-6 py-10 text-center text-sm text-muted">
      <div className="mx-auto max-w-md">{children}</div>
    </Card>
  );
}
