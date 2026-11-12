import { expect, type Page, test } from "@playwright/test";

/**
 * The demo script from plan.md, driven through the real UI: register an
 * institute, have AICTE approve it, upload a file with deliberate errors, fix
 * and commit it, watch a second institute get stopped when it tries to enrol
 * the same student, see the over-intake flag on the AICTE dashboard, and verify
 * one student from their QR link.
 *
 * Every run uses fresh random identifiers, so it can be repeated against the
 * same database.
 */

const SEED_PASSWORD = process.env.SEED_PASSWORD ?? "acadledger-demo-1";
const OFFICER = "officer@aicte.example";
const OTHER_INSTITUTE_ADMIN = "admin@kaveri.example"; // seeded, active, offers CSE

const run = Date.now().toString(36);
const institute = {
  name: `E2E Institute ${run}`,
  aicteId: `9-${run}`,
  email: `admin-${run}@e2e.example`,
  password: "correct-horse-battery",
};
const verifier = { email: `verifier-${run}@e2e.example`, password: "correct-horse-battery" };

// Verhoeff check digit: the mock APAAR registry only knows IDs that carry one.
const D = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
  [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
  [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
  [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
  [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
  [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
  [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
  [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
  [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
];
const P = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
  [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
  [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
  [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
  [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
  [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
  [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
];
const INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9];

function apaarId(): string {
  const body = Array.from({ length: 11 }, (_, i) =>
    Math.floor(Math.random() * (i === 0 ? 9 : 10) + (i === 0 ? 1 : 0)),
  );
  let c = 0;
  [...body].reverse().forEach((digit, i) => {
    c = D[c][P[(i + 1) % 8][digit]];
  });
  return body.join("") + INV[c];
}

type Student = { apaar_id: string; full_name: string; enrolment_no: string };

function student(n: number, overrides: Partial<Student> = {}): Student {
  return {
    apaar_id: apaarId(),
    full_name: `Test Student ${n}`,
    enrolment_no: `${run}-${n}`,
    ...overrides,
  };
}

function csv(students: Student[]) {
  const lines = students.map(
    (s) => `${s.apaar_id},${s.full_name},2007-04-18,female,CSE,${s.enrolment_no}`,
  );
  return {
    name: "students.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      ["apaar_id,full_name,date_of_birth,gender,programme_code,enrolment_no", ...lines].join("\n"),
    ),
  };
}

/**
 * A form field by its label, ignoring hidden ones. Next.js keeps recently visited
 * pages in the DOM (hidden) to preserve their state, so a label such as "Email"
 * can exist more than once.
 */
function field(page: Page, label: string | RegExp, exact = false) {
  return page.getByLabel(label, { exact }).filter({ visible: true });
}

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await field(page, "Email").fill(email);
  await field(page, "Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
}

async function uploadFile(page: Page, students: Student[]) {
  await page.goto("/uploads");
  await field(page, "File").setInputFiles(csv(students));
  await page.getByRole("button", { name: "Upload and validate" }).click();
  await expect(page.getByRole("heading", { name: "students.csv" })).toBeVisible();
}

test("institute onboarding, upload with errors, fix, commit, cross-institute duplicate", async ({
  page,
}) => {
  const good = [student(1), student(2), student(3), student(4)];

  await test.step("a new institute registers and is pending", async () => {
    await page.goto("/register");
    await field(page, "Institute name").fill(institute.name);
    await field(page, "AICTE permanent ID").fill(institute.aicteId);
    await field(page, "State").fill("Kerala");
    await field(page, "Your name").fill("E2E Admin");
    await field(page, "Work email").fill(institute.email);
    await field(page, "Password").fill(institute.password);
    await page.getByRole("button", { name: "Register" }).click();
    await expect(page.getByRole("heading", { name: "Registration received" })).toBeVisible();

    await signIn(page, institute.email, institute.password);
    await expect(page.getByText("waiting for approval by an AICTE officer")).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload and validate" })).toHaveCount(0);
    await signOut(page);
  });

  await test.step("an AICTE officer approves it and sets an approved intake of 3", async () => {
    await signIn(page, OFFICER, SEED_PASSWORD);
    await page.getByRole("link", { name: "Institutes" }).click();
    const row = page.getByRole("row", { name: new RegExp(institute.name) });
    await expect(row.getByText("pending")).toBeVisible();
    await row.getByRole("button", { name: "Approve" }).click();
    await expect(row.getByText("active")).toBeVisible();

    await row.getByRole("link", { name: institute.name }).click();
    await field(page, "Code").fill("cse");
    await field(page, "Name", true).fill("B.Tech Computer Science");
    await page.getByRole("button", { name: "Add programme" }).click();
    const intake = field(page, /Approved intake for CSE/);
    await intake.fill("3");
    await intake.press("Enter");
    await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
    await page.reload();
    await expect(field(page, /Approved intake for CSE/)).toHaveValue("3");
    await signOut(page);
  });

  await test.step("a file with deliberate errors gets a row-level report", async () => {
    await signIn(page, institute.email, institute.password);
    await uploadFile(page, [
      good[0],
      { ...good[1], apaar_id: "12345" },
      { ...good[2], full_name: "" },
      good[3],
    ]);

    await expect(page.getByText("Nothing has been saved.")).toBeVisible();
    await expect(page.getByText("apaar_id must be exactly 12 digits")).toBeVisible();
    await expect(page.getByText("full_name is required")).toBeVisible();
    await expect(page.getByRole("link", { name: /Download error report/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Commit to repository" })).toHaveCount(0);
  });

  await test.step("the corrected file is committed and excess enrolment is flagged", async () => {
    await uploadFile(page, good);

    await expect(page.getByText("Ready to commit")).toBeVisible();
    await expect(page.getByText("1 over intake")).toBeVisible();
    await page.getByRole("button", { name: "Commit to repository" }).click();
    await page.getByRole("button", { name: "Yes, commit 4 students" }).click();
    await expect(page.getByText("4 students were added to the central repository")).toBeVisible();
  });

  let verificationLink = "";

  await test.step("the institute issues a verification QR code for one student", async () => {
    await page.getByRole("link", { name: "Students" }).click();
    await page.getByRole("button", { name: "Verification link for Test Student 1" }).click();
    await page.getByRole("button", { name: "Create link and QR code" }).click();
    await expect(
      page.locator("svg", { has: page.locator("title", { hasText: "Verification QR code" }) }),
    ).toBeVisible();
    verificationLink = await field(page, "Verification link", true).inputValue();
    expect(verificationLink).toMatch(/\/verify#[\w-]{20,}$/);
    await signOut(page);
  });

  await test.step("another institute cannot enrol the same APAAR ID", async () => {
    await signIn(page, OTHER_INSTITUTE_ADMIN, SEED_PASSWORD);
    await uploadFile(page, [student(50, { apaar_id: good[0].apaar_id }), student(51)]);

    await expect(
      page.getByText("this APAAR ID is already enrolled at another institute"),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Commit to repository" })).toHaveCount(0);
    await signOut(page);
  });

  await test.step("the AICTE dashboard flags the programme that is over its intake", async () => {
    await signIn(page, OFFICER, SEED_PASSWORD);
    await expect(page.getByRole("heading", { name: "Enrolment dashboard" })).toBeVisible();
    await expect(page.getByText(/enrolled more students than AICTE approved/)).toBeVisible();
    const row = page.getByRole("row", { name: new RegExp(institute.name) });
    await expect(row.getByText("1 over intake")).toBeVisible();
  });

  await test.step("the officer authorises a verifier", async () => {
    await page.getByRole("link", { name: "Verifiers" }).click();
    await field(page, "Full name").fill("E2E Hiring Team");
    await field(page, "Organisation").fill(`Acme ${run}`);
    await field(page, "Email").fill(verifier.email);
    await field(page, "Initial password").fill(verifier.password);
    await page.getByRole("button", { name: "Authorise verifier" }).click();
    await expect(page.getByRole("cell", { name: verifier.email })).toBeVisible();
    await signOut(page);
  });

  await test.step("the verifier opens the QR link, signs in and sees the record", async () => {
    // what scanning the QR code does: open the link, signed out
    await page.goto(verificationLink);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await field(page, "Email").fill(verifier.email);
    await field(page, "Password").fill(verifier.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("heading", { name: "Record verified" })).toBeVisible();
    await expect(page.getByText("Test Student 1", { exact: true })).toBeVisible();
    await expect(page.getByText(institute.name, { exact: false })).toBeVisible();
    await expect(page.getByText(`ending ${good[0].apaar_id.slice(-4)}`)).toBeVisible();

    // a made-up code is refused
    await page.getByRole("button", { name: "Check another link" }).click();
    await field(page, "Verification link").fill("x".repeat(43));
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(page.getByText("Not verified.")).toBeVisible();
  });

  await test.step("the verifier replaces the password the officer chose", async () => {
    await page.getByTitle("Account").click();
    await field(page, "Current password").fill(verifier.password);
    await field(page, /^New password/).fill("my-own-password-1");
    await field(page, "Repeat new password").fill("my-own-password-1");
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByText("Your password has been changed.")).toBeVisible();
    await signOut(page);
  });

  await test.step("the audit chain is intact and holds the lookup", async () => {
    await signIn(page, OFFICER, SEED_PASSWORD);
    await page.getByRole("link", { name: "Audit log" }).click();
    await expect(page.getByText("Chain intact.")).toBeVisible();
    // .first(): earlier runs against the same database leave their lookups in the log too
    await expect(
      page.getByRole("cell", { name: "verification.lookup", exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByRole("cell", { name: "upload.committed" }).first()).toBeVisible();
  });
});

test("the home page explains the problem and leads to sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "One verified student record per APAAR ID" }),
  ).toBeVisible();
  await expect(page.getByText("Problem statement SIH26263")).toBeVisible();
  await expect(page.getByRole("heading", { name: "AICTE sees totals, not students" })).toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).first().click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
