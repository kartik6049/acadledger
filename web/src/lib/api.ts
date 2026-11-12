export type Role = "aicte_officer" | "institute_admin" | "verifier";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  institute_id: string | null;
}

export type InstituteStatus = "pending" | "active" | "suspended" | "rejected";

export interface Institute {
  id: string;
  aicte_id: string;
  name: string;
  state: string;
  status: InstituteStatus;
  created_at: string;
}

export interface Programme {
  id: string;
  institute_id: string;
  code: string;
  name: string;
  level: "diploma" | "ug" | "pg";
  intakes: { academic_year: string; approved_intake: number }[];
}

export type UploadStatus = "queued" | "validating" | "validated" | "failed" | "committed";

export interface IntakeFinding {
  programme_code: string;
  programme_name: string;
  approved_intake: number;
  already_enrolled: number;
  in_this_upload: number;
  excess: number;
}

export interface Upload {
  id: string;
  institute_id: string;
  academic_year: string;
  original_filename: string;
  status: UploadStatus;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  summary: {
    intake?: IntakeFinding[];
    errors_by_code?: Record<string, number>;
    validation_ms?: number;
  };
  failure_reason: string | null;
  created_at: string;
  finished_at: string | null;
  committed_at: string | null;
}

export interface RowError {
  stage: string;
  field: string;
  code: string;
  message: string;
}

export interface UploadRow {
  row_number: number;
  data: Record<string, string>;
  is_valid: boolean;
  errors: RowError[];
}

export interface AuditEntry {
  id: number;
  occurred_at: string;
  actor_role: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  hash: string;
}

export interface ChainReport {
  ok: boolean;
  entries_checked: number;
  first_broken_id: number | null;
  reason: string | null;
}

export interface Student {
  id: string;
  apaar_id: string;
  programme_code: string;
  academic_year: string;
  enrolment_no: string;
  full_name: string;
}

export interface DashboardSummary {
  academic_year: string;
  institutes_active: number;
  institutes_pending: number;
  programmes: number;
  approved_intake: number;
  enrolled: number;
  programmes_over_intake: number;
  excess_students: number;
}

export interface IntakeRow {
  institute_id: string;
  institute_name: string;
  aicte_id: string;
  state: string;
  programme_code: string;
  programme_name: string;
  approved_intake: number;
  enrolled: number;
  excess: number;
}

export interface VerificationLink {
  id: string;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  lookup_count: number;
  last_used_at: string | null;
}

export interface VerifiedRecord {
  full_name: string;
  apaar_last4: string;
  enrolment_no: string;
  academic_year: string;
  programme_code: string;
  programme_name: string;
  institute_name: string;
  institute_aicte_id: string;
  institute_state: string;
  institute_status: InstituteStatus;
  verified_at: string;
  link_expires_at: string;
}

export interface Verifier {
  id: string;
  email: string;
  full_name: string;
  organisation: string | null;
  created_at: string;
}

export interface Page<T> {
  total: number;
  items: T[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// FastAPI sends `detail` as a string for our own errors and as a list for validation errors.
function describe(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) => {
        const field = item.loc?.filter((part) => part !== "body").join(".");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }
  return fallback;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...init,
      // The API refuses state-changing requests without this header. Another site can
      // make a browser send our session cookie, but it cannot add a custom header.
      headers: { ...init?.headers, "X-Requested-With": "acadledger-web" },
    });
  } catch {
    throw new ApiError(0, "Could not reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      describe(body?.detail, `Request failed (${response.status})`),
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export function postJson<T>(path: string, body: unknown, method = "POST"): Promise<T> {
  return api<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** For SWR: the cache key is the API path. */
export const fetcher = <T,>(path: string) => api<T>(path);

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

/** Academic years start in July: November 2026 falls in 2026-27. */
export function academicYears(today: Date): string[] {
  const start = today.getMonth() >= 6 ? today.getFullYear() : today.getFullYear() - 1;
  return [start, start - 1].map((year) => `${year}-${String((year + 1) % 100).padStart(2, "0")}`);
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}
