"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useViewer } from "@/lib/viewer-context";
import { getViewerInfo, getPageImageUrl, type ViewerInfo } from "@/lib/api";
import {
  X,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  FileText,
  Loader2,
  AlertCircle,
} from "lucide-react";

interface StandaloneProps {
  standalone: true;
  versionId: string;
  initialPage?: number;
  sourceFilename?: string;
  equipmentKey?: string;
  docType?: string;
  publishedDate?: string;
}

interface PanelProps {
  standalone?: false;
}

type DocumentViewerProps = StandaloneProps | PanelProps;

export function DocumentViewer(props: DocumentViewerProps) {
  const isStandalone = props.standalone === true;
  const { viewer, isOpen, closeViewer, goToPage } = useViewer();

  // Estado local de página para modo standalone
  const [localPage, setLocalPage] = useState(
    isStandalone ? ((props as StandaloneProps).initialPage ?? 1) : 1
  );

  // Derivar valores conforme o modo
  const versionId = isStandalone
    ? (props as StandaloneProps).versionId
    : viewer?.versionId ?? "";
  const pageNumber = isStandalone ? localPage : viewer?.pageNumber ?? 1;
  const sourceFilename = isStandalone
    ? ((props as StandaloneProps).sourceFilename ?? "")
    : (viewer?.sourceFilename ?? "");
  const equipmentKey = isStandalone
    ? ((props as StandaloneProps).equipmentKey ?? "")
    : (viewer?.equipmentKey ?? "");
  const docType = isStandalone
    ? ((props as StandaloneProps).docType ?? "")
    : (viewer?.docType ?? "");
  const publishedDate = isStandalone
    ? ((props as StandaloneProps).publishedDate ?? "")
    : (viewer?.publishedDate ?? "");

  const [info, setInfo] = useState<ViewerInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [imgLoading, setImgLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const shouldRender = isStandalone || isOpen;

  // Buscar info do documento
  useEffect(() => {
    if (!versionId || !shouldRender) return;
    setLoading(true);
    setError(null);
    getViewerInfo(versionId)
      .then(setInfo)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [versionId, shouldRender]);

  // Carregar imagem da página via fetch autenticado
  useEffect(() => {
    if (!versionId || !pageNumber || !shouldRender) return;

    setImgLoading(true);
    setError(null);

    const url = getPageImageUrl(versionId, pageNumber);

    async function loadImage() {
      try {
        const headers: Record<string, string> = {};
        if (typeof window !== "undefined" && window.Clerk?.session) {
          const token = await window.Clerk.session.getToken();
          if (token) headers["Authorization"] = `Bearer ${token}`;
        }

        const res = await fetch(url, { headers });
        if (!res.ok) {
          const text = await res.text();
          try {
            const json = JSON.parse(text);
            throw new Error(json.detail || `Erro ${res.status}`);
          } catch {
            throw new Error(`Erro ao carregar página (${res.status})`);
          }
        }

        const blob = await res.blob();
        const objectUrl = URL.createObjectURL(blob);
        setImgSrc((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return objectUrl;
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erro ao carregar página");
      } finally {
        setImgLoading(false);
      }
    }

    loadImage();

    return () => {
      setImgSrc((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [versionId, pageNumber, shouldRender]);

  // Reset zoom quando muda de documento
  useEffect(() => {
    setZoom(1);
  }, [versionId]);

  const handleGoToPage = useCallback(
    (page: number) => {
      if (isStandalone) {
        setLocalPage(page);
      } else {
        goToPage(page);
      }
    },
    [isStandalone, goToPage]
  );

  const handlePrev = useCallback(() => {
    if (pageNumber > 1) handleGoToPage(pageNumber - 1);
  }, [pageNumber, handleGoToPage]);

  const handleNext = useCallback(() => {
    if (info && pageNumber < info.total_pages) handleGoToPage(pageNumber + 1);
  }, [pageNumber, info, handleGoToPage]);

  const handleZoomIn = useCallback(() => {
    setZoom((z) => Math.min(z + 0.25, 3));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom((z) => Math.max(z - 0.25, 0.5));
  }, []);

  // Keyboard navigation + proteção contra Ctrl+S, Ctrl+P
  useEffect(() => {
    if (!shouldRender) return;
    function handleKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "p")) {
        e.preventDefault();
        return;
      }
      if (e.key === "ArrowLeft") handlePrev();
      else if (e.key === "ArrowRight") handleNext();
      else if (!isStandalone && e.key === "Escape") closeViewer();
      else if (e.key === "+" || e.key === "=") handleZoomIn();
      else if (e.key === "-") handleZoomOut();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [shouldRender, isStandalone, handlePrev, handleNext, closeViewer, handleZoomIn, handleZoomOut]);

  if (!shouldRender) return null;
  if (!isStandalone && !viewer) return null;

  return (
    <div
      className={`viewer-protected flex flex-col bg-card ${
        isStandalone ? "min-h-screen w-full" : "h-full w-full border-l"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2 sm:px-4">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{sourceFilename}</p>
            {(equipmentKey || docType || publishedDate) && (
              <p className="text-xs text-muted-foreground">
                {[
                  equipmentKey,
                  docType,
                  publishedDate
                    ? new Date(publishedDate).toLocaleDateString("pt-BR")
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
          </div>
        </div>
        {!isStandalone && (
          <button
            onClick={closeViewer}
            className="rounded-md p-1 hover:bg-muted"
            title="Fechar (Esc)"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between border-b px-3 py-1.5 sm:px-4">
        <div className="flex items-center gap-1">
          <button
            onClick={handlePrev}
            disabled={pageNumber <= 1}
            className="rounded p-1.5 hover:bg-muted disabled:opacity-30 sm:p-1"
            title="Página anterior (←)"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-[80px] text-center text-xs tabular-nums">
            {info ? `${pageNumber} / ${info.total_pages}` : `${pageNumber}`}
          </span>
          <button
            onClick={handleNext}
            disabled={!info || pageNumber >= info.total_pages}
            className="rounded p-1.5 hover:bg-muted disabled:opacity-30 sm:p-1"
            title="Próxima página (→)"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={handleZoomOut}
            disabled={zoom <= 0.5}
            className="rounded p-1.5 hover:bg-muted disabled:opacity-30 sm:p-1"
            title="Diminuir zoom (-)"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <span className="min-w-[40px] text-center text-xs tabular-nums">
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={handleZoomIn}
            disabled={zoom >= 3}
            className="rounded p-1.5 hover:bg-muted disabled:opacity-30 sm:p-1"
            title="Aumentar zoom (+)"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div ref={containerRef} className="flex-1 overflow-auto bg-muted/30">
        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="flex h-64 flex-col items-center justify-center gap-2 px-4 text-center">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
          </div>
        ) : (
          <div className="flex justify-center p-4">
            <div
              className="relative transition-transform duration-150"
              style={{ transform: `scale(${zoom})`, transformOrigin: "top center" }}
            >
              {imgLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/50">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              )}
              {imgSrc && (
                <img
                  src={imgSrc}
                  alt={`Página ${pageNumber}`}
                  className="max-w-full rounded shadow-md select-none pointer-events-none"
                  draggable={false}
                  onContextMenu={(e) => e.preventDefault()}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
