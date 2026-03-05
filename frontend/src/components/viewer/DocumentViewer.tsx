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

export function DocumentViewer() {
  const { viewer, isOpen, closeViewer, goToPage } = useViewer();
  const [info, setInfo] = useState<ViewerInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [imgLoading, setImgLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Obter token de auth para as imagens
  useEffect(() => {
    async function getToken() {
      if (typeof window !== "undefined" && window.Clerk?.session) {
        const token = await window.Clerk.session.getToken();
        setAuthToken(token);
      }
    }
    getToken();
    // Refresh token periodicamente
    const interval = setInterval(getToken, 30_000);
    return () => clearInterval(interval);
  }, []);

  // Buscar info do documento quando viewer abre
  useEffect(() => {
    if (!viewer?.versionId || !isOpen) return;

    setLoading(true);
    setError(null);
    getViewerInfo(viewer.versionId)
      .then(setInfo)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [viewer?.versionId, isOpen]);

  // Carregar imagem da página via fetch autenticado
  useEffect(() => {
    if (!viewer?.versionId || !viewer?.pageNumber || !isOpen) return;

    setImgLoading(true);
    setError(null);

    const url = getPageImageUrl(viewer.versionId, viewer.pageNumber);

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
  }, [viewer?.versionId, viewer?.pageNumber, isOpen]);

  // Reset zoom quando muda de documento
  useEffect(() => {
    setZoom(1);
  }, [viewer?.versionId]);

  const handlePrev = useCallback(() => {
    if (viewer && viewer.pageNumber > 1) goToPage(viewer.pageNumber - 1);
  }, [viewer, goToPage]);

  const handleNext = useCallback(() => {
    if (viewer && info && viewer.pageNumber < info.total_pages)
      goToPage(viewer.pageNumber + 1);
  }, [viewer, info, goToPage]);

  const handleZoomIn = useCallback(() => {
    setZoom((z) => Math.min(z + 0.25, 3));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom((z) => Math.max(z - 0.25, 0.5));
  }, []);

  // Keyboard navigation + proteção contra Ctrl+S, Ctrl+P
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e: KeyboardEvent) {
      // Bloquear atalhos de salvar/imprimir quando viewer está aberto
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "p")) {
        e.preventDefault();
        return;
      }
      if (e.key === "ArrowLeft") handlePrev();
      else if (e.key === "ArrowRight") handleNext();
      else if (e.key === "Escape") closeViewer();
      else if (e.key === "+" || e.key === "=") handleZoomIn();
      else if (e.key === "-") handleZoomOut();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, handlePrev, handleNext, closeViewer, handleZoomIn, handleZoomOut]);

  if (!isOpen || !viewer) return null;

  return (
    <div className="viewer-protected flex h-full w-full flex-col border-l bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">
              {viewer.sourceFilename}
            </p>
            <p className="text-xs text-muted-foreground">
              {viewer.equipmentKey} · {viewer.docType} ·{" "}
              {new Date(viewer.publishedDate).toLocaleDateString("pt-BR")}
            </p>
          </div>
        </div>
        <button
          onClick={closeViewer}
          className="rounded-md p-1 hover:bg-muted"
          title="Fechar (Esc)"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between border-b px-3 py-1.5">
        <div className="flex items-center gap-1">
          <button
            onClick={handlePrev}
            disabled={!viewer || viewer.pageNumber <= 1}
            className="rounded p-1 hover:bg-muted disabled:opacity-30"
            title="Página anterior (←)"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-[80px] text-center text-xs tabular-nums">
            {info
              ? `${viewer.pageNumber} / ${info.total_pages}`
              : `${viewer.pageNumber}`}
          </span>
          <button
            onClick={handleNext}
            disabled={!info || viewer.pageNumber >= info.total_pages}
            className="rounded p-1 hover:bg-muted disabled:opacity-30"
            title="Próxima página (→)"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={handleZoomOut}
            disabled={zoom <= 0.5}
            className="rounded p-1 hover:bg-muted disabled:opacity-30"
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
            className="rounded p-1 hover:bg-muted disabled:opacity-30"
            title="Aumentar zoom (+)"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-muted/30"
      >
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
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
                  alt={`Página ${viewer.pageNumber}`}
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
