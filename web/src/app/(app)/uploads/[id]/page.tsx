import { Suspense } from "react";
import { Spinner } from "@/components/ui";
import { UploadDetail } from "./upload-detail";

export const metadata = { title: "Upload" };

// The upload id is only known at request time, so the part that reads it streams in.
export default function UploadPage() {
  return (
    <Suspense fallback={<Spinner label="Loading upload…" />}>
      <UploadDetail />
    </Suspense>
  );
}
