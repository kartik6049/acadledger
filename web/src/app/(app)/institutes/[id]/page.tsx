import { Suspense } from "react";
import { Spinner } from "@/components/ui";
import { InstituteDetail } from "./institute-detail";

export const metadata = { title: "Institute" };

// The institute id is only known at request time, so the part that reads it streams in.
export default function InstitutePage() {
  return (
    <Suspense fallback={<Spinner label="Loading institute…" />}>
      <InstituteDetail />
    </Suspense>
  );
}
