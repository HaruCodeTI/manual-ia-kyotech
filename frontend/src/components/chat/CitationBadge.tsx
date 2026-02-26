"use client";

import { useState, useRef, useEffect } from "react";
import type { Citation } from "@/types";
import { getPdfUrl } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { FileText, ExternalLink, Loader2 } from "lucide-react";

interface CitationBadgeProps {
  citation: Citation;
}

export function CitationBadge({ citation }: CitationBadgeProps) {
  const [showDetail, setShowDetail] = useState(false);
  const [loadingPdf, setLoadingPdf] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

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

  async function handleOpenPdf(e: React.MouseEvent) {
    e.stopPropagation();
    setLoadingPdf(true);
    try {
      const url = await getPdfUrl(citation.storage_path, citation.page_number);
      window.open(url, "_blank");
    } catch {
      alert("Não foi possível gerar o link do PDF.");
    } finally {
      setLoadingPdf(false);
    }
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
              className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline disabled:opacity-50"
              onClick={handleOpenPdf}
              disabled={loadingPdf}
            >
              {loadingPdf ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <ExternalLink className="h-3 w-3" />
              )}
              Ver PDF na página {citation.page_number}
            </button>
          </div>
        </div>
      )}
    </span>
  );
}
