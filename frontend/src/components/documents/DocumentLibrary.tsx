"use client";

import { useEffect, useState } from "react";
import { FileText, ChevronLeft, ChevronRight, Pencil, Eye, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useViewer } from "@/lib/viewer-context";
import { listDocuments, updateDocumentFilename } from "@/lib/api";
import type { DocumentVersionItem } from "@/types";

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function DocumentLibrary() {
  const { openViewer } = useViewer();
  const [versions, setVersions] = useState<DocumentVersionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  async function fetchPage(p: number, size: number) {
    setLoading(true);
    setError(null);
    try {
      const data = await listDocuments(p, size);
      setVersions(data.versions);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setPage(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar documentos.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchPage(1, pageSize);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handlePageSizeChange(newSize: number) {
    setPageSize(newSize);
    fetchPage(1, newSize);
  }

  function startEdit(v: DocumentVersionItem) {
    setEditingId(v.version_id);
    setEditValue(v.source_filename);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditValue("");
  }

  async function saveEdit(versionId: string) {
    const trimmed = editValue.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await updateDocumentFilename(versionId, trimmed);
      setVersions((prev) =>
        prev.map((v) =>
          v.version_id === versionId ? { ...v, source_filename: trimmed } : v
        )
      );
      setEditingId(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Erro ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  function openDoc(v: DocumentVersionItem) {
    openViewer({
      versionId: v.version_id,
      pageNumber: 1,
      sourceFilename: v.source_filename,
      equipmentKey: v.equipment_key ?? "",
      docType: v.doc_type ?? "",
      publishedDate: v.published_date ?? "",
    });
  }

  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Documentos</h2>
          {!loading && (
            <p className="text-sm text-muted-foreground">
              {total} documento{total !== 1 ? "s" : ""} no total
            </p>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : versions.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          Nenhum documento encontrado.
        </p>
      ) : (
        <div className="overflow-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="border-b border-border bg-muted/60 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider backdrop-blur">
                <th className="px-4 py-3">Nome</th>
                <th className="px-4 py-3 hidden lg:table-cell whitespace-nowrap">Ingerido em</th>
                <th className="px-4 py-3 hidden sm:table-cell whitespace-nowrap">Publicado em</th>
                <th className="px-4 py-3 text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {versions.map((v) => (
                <tr key={v.version_id} className="hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3">
                    {editingId === v.version_id ? (
                      <div className="flex items-center gap-2">
                        <input
                          className="flex-1 rounded border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") saveEdit(v.version_id);
                            if (e.key === "Escape") cancelEdit();
                          }}
                          autoFocus
                        />
                        <Button size="sm" variant="default" onClick={() => saveEdit(v.version_id)} disabled={saving}>
                          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Salvar"}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={cancelEdit} disabled={saving}>
                          Cancelar
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="truncate max-w-[320px]" title={v.source_filename}>
                          {v.source_filename}
                        </span>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 hidden lg:table-cell text-muted-foreground whitespace-nowrap">
                    {formatDate(v.ingested_at)}
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell text-muted-foreground whitespace-nowrap">
                    {formatDate(v.published_date)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        title="Renomear"
                        onClick={() => startEdit(v)}
                        disabled={editingId !== null}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        title="Abrir documento"
                        onClick={() => openDoc(v)}
                      >
                        <Eye className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {!loading && total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <span>Exibir</span>
            <select
              value={pageSize}
              onChange={(e) => handlePageSizeChange(Number(e.target.value))}
              className="rounded border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {PAGE_SIZE_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <span>por página</span>
          </div>

          <span>
            {start}–{end} de {total}
          </span>

          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="outline"
              onClick={() => fetchPage(1, pageSize)}
              disabled={page <= 1 || loading}
              title="Primeira página"
            >
              «
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => fetchPage(page - 1, pageSize)}
              disabled={page <= 1 || loading}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="px-2">
              {page} / {totalPages}
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => fetchPage(page + 1, pageSize)}
              disabled={page >= totalPages || loading}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => fetchPage(totalPages, pageSize)}
              disabled={page >= totalPages || loading}
              title="Última página"
            >
              »
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
