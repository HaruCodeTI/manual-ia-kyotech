"use client";

import { useEffect, useState } from "react";
import { FileText, ChevronLeft, ChevronRight, Pencil, Eye, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useViewer } from "@/lib/viewer-context";
import { listDocuments, updateDocumentFilename } from "@/lib/api";
import type { DocumentVersionItem } from "@/types";

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
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  const PAGE_SIZE = 20;

  async function fetchPage(p: number) {
    setLoading(true);
    setError(null);
    try {
      const data = await listDocuments(p, PAGE_SIZE);
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
    fetchPage(1);
  }, []);

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

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Documentos</h2>
          {!loading && (
            <p className="text-sm text-muted-foreground">{total} documento{total !== 1 ? "s" : ""} no total</p>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : versions.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          Nenhum documento encontrado.
        </p>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                <th className="px-4 py-3">Nome</th>
                <th className="px-4 py-3 hidden md:table-cell">Equipamento</th>
                <th className="px-4 py-3 hidden sm:table-cell">Tipo</th>
                <th className="px-4 py-3 hidden lg:table-cell">Ingerido em</th>
                <th className="px-4 py-3 text-right">Chunks</th>
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
                        <span className="truncate max-w-[220px]" title={v.source_filename}>
                          {v.source_filename}
                        </span>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell text-muted-foreground">
                    {v.equipment_key ?? "—"}
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell text-muted-foreground capitalize">
                    {v.doc_type ?? "—"}
                  </td>
                  <td className="px-4 py-3 hidden lg:table-cell text-muted-foreground">
                    {formatDate(v.ingested_at)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                    {v.total_chunks}
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

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>Página {page} de {totalPages}</span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => fetchPage(page - 1)}
              disabled={page <= 1 || loading}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => fetchPage(page + 1)}
              disabled={page >= totalPages || loading}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
