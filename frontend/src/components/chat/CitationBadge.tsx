"use client";

import { useState, useRef, useEffect } from "react";
import type { Citation } from "@/types";
import { useViewer } from "@/lib/viewer-context";
import { Badge } from "@/components/ui/badge";
import { FileText, Eye } from "lucide-react";

interface CitationBadgeProps {
  citation: Citation;
}

export function CitationBadge({ citation }: CitationBadgeProps) {
  const [showDetail, setShowDetail] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const { openViewer } = useViewer();

  useEffect(() => {
    if (!showDetail) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setShowDetail(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showDetail]);

  function handleOpenViewer(e: React.MouseEvent) {
    e.stopPropagation();
    setShowDetail(false);

    // Usar document_version_id se disponível, senão fallback para storage_path
    const versionId = citation.document_version_id || citation.storage_path;

    openViewer({
      versionId,
      pageNumber: citation.page_number,
      sourceFilename: citation.source_filename,
      equipmentKey: citation.equipment_key,
      docType: citation.doc_type,
      publishedDate: citation.published_date,
    });
  }

  return (
    <span ref={ref} className="relative inline-block">
      <Badge
        variant="secondary"
        className="cursor-pointer gap-1 font-mono text-xs hover:bg-primary hover:text-primary-foreground"
        onClick={() => setShowDetail((v) => !v)}
      >
        <FileText className="h-3 w-3" />
        Fonte {citation.source_index}
      </Badge>

      {showDetail && (
        <div className="absolute bottom-full left-0 z-50 mb-2 w-72 rounded-lg border bg-popover p-3 text-sm shadow-lg">
          <div className="space-y-1.5">
            <p className="font-medium">{citation.source_filename}</p>
            <p className="text-muted-foreground">
              Página {citation.page_number} · {citation.equipment_key} ·{" "}
              {citation.doc_type}
            </p>
            <p className="text-xs text-muted-foreground">
              Publicado em{" "}
              {new Date(citation.published_date).toLocaleDateString("pt-BR")}
            </p>
            <button
              className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
              onClick={handleOpenViewer}
            >
              <Eye className="h-3 w-3" />
              Ver página {citation.page_number}
            </button>
          </div>
        </div>
      )}
    </span>
  );
}
