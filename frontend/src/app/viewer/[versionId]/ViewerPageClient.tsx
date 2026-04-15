"use client";

import { ViewerProvider } from "@/lib/viewer-context";
import { DocumentViewer } from "@/components/viewer/DocumentViewer";

interface Props {
  versionId: string;
  initialPage: number;
}

export function ViewerPageClient({ versionId, initialPage }: Props) {
  return (
    <ViewerProvider>
      <DocumentViewer
        standalone
        versionId={versionId}
        initialPage={initialPage}
      />
    </ViewerProvider>
  );
}
