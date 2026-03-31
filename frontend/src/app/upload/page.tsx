import { BulkUploadForm } from "@/components/upload/BulkUploadForm";
import { DuplicateScanner } from "@/components/upload/DuplicateScanner";

export default function UploadPage() {
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-xl space-y-6">
        <BulkUploadForm />
        <DuplicateScanner />
      </div>
    </div>
  );
}
