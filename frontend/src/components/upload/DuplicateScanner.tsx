"use client";

import { useState } from "react";
import { scanDuplicates, deleteDuplicates } from "@/lib/api";
import type { DuplicateGroup, DuplicateScanResponse } from "@/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Search, Trash2, Loader2, CheckCircle2, AlertCircle, FileText } from "lucide-react";

type Phase = "idle" | "scanning" | "results" | "deleting" | "done" | "error";

export function DuplicateScanner() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [scanResult, setScanResult] = useState<DuplicateScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  async function handleScan() {
    setPhase("scanning");
    setError(null);
    setScanResult(null);

    try {
      const result = await scanDuplicates();
      setScanResult(result);
      setPhase(result.total_groups > 0 ? "results" : "done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao buscar duplicatas.");
      setPhase("error");
    }
  }

  async function handleDelete() {
    if (!scanResult) return;
    setShowConfirm(false);
    setPhase("deleting");

    const versionIds = scanResult.groups.flatMap((g) =>
      g.duplicates.map((d) => d.version_id)
    );

    try {
      const result = await deleteDuplicates(versionIds);
      setDeleteMessage(result.message);
      setScanResult(null);
      setPhase("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao remover duplicatas.");
      setPhase("error");
    }
  }

  function handleReset() {
    setPhase("idle");
    setScanResult(null);
    setError(null);
    setDeleteMessage(null);
    setShowConfirm(false);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Search className="h-4 w-4" />
          Duplicados
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {(phase === "idle" || phase === "error") && (
          <div className="space-y-2">
            <Button variant="outline" className="w-full" onClick={handleScan}>
              <Search className="mr-2 h-4 w-4" />
              Buscar duplicados
            </Button>
            {phase === "error" && error && (
              <div className="flex items-center gap-2 rounded-lg border border-destructive p-3">
                <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
                <p className="flex-1 text-sm text-destructive">{error}</p>
              </div>
            )}
          </div>
        )}

        {phase === "scanning" && (
          <Button variant="outline" className="w-full" disabled>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Buscando...
          </Button>
        )}

        {phase === "results" && scanResult && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-lg border border-yellow-500 p-3">
              <AlertCircle className="h-4 w-4 shrink-0 text-yellow-500" />
              <p className="flex-1 text-sm font-medium">
                {scanResult.total_groups} grupo{scanResult.total_groups > 1 ? "s" : ""} de
                duplicatas &mdash; {scanResult.total_removable} arquivo{scanResult.total_removable > 1 ? "s" : ""}{" "}
                {scanResult.total_removable > 1 ? "podem" : "pode"} ser removido{scanResult.total_removable > 1 ? "s" : ""}
              </p>
            </div>

            {scanResult.groups.map((group) => (
              <DuplicateGroupCard key={group.source_hash} group={group} />
            ))}

            {!showConfirm ? (
              <Button
                variant="destructive"
                className="w-full"
                onClick={() => setShowConfirm(true)}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Remover duplicados
              </Button>
            ) : (
              <div className="space-y-2 rounded-lg border border-destructive p-3">
                <p className="text-sm font-medium">
                  Tem certeza? <strong>{scanResult.total_removable} arquivo{scanResult.total_removable > 1 ? "s" : ""}</strong>{" "}
                  {scanResult.total_removable > 1 ? "serão removidos" : "será removido"} permanentemente,
                  incluindo chunks e arquivos de armazenamento. Esta ação não pode ser desfeita.
                </p>
                <div className="flex gap-2">
                  <Button variant="destructive" size="sm" onClick={handleDelete}>
                    Confirmar remoção
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setShowConfirm(false)}>
                    Cancelar
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {phase === "deleting" && (
          <Button variant="destructive" className="w-full" disabled>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Removendo...
          </Button>
        )}

        {phase === "done" && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 rounded-lg border border-green-500 p-3">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />
              <p className="flex-1 text-sm font-medium">
                {deleteMessage || "Nenhuma duplicata encontrada."}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={handleReset}>
              Nova busca
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DuplicateGroupCard({ group }: { group: DuplicateGroup }) {
  return (
    <div className="rounded-lg border p-3 space-y-2">
      <div className="flex items-start gap-2">
        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate">{group.keep.filename}</span>
            <Badge variant="outline" className="border-green-500 text-green-600 text-xs shrink-0">
              Manter
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {group.keep.equipment_key || "Sem equipamento"} &middot; {group.keep.doc_type || "Sem tipo"} &middot; {group.keep.published_date || "\u2014"} &middot; {group.keep.chunk_count} chunks
          </p>
        </div>
      </div>

      {group.duplicates.map((dup) => (
        <div key={dup.version_id} className="flex items-start gap-2 ml-2">
          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm truncate">{dup.filename}</span>
              <Badge variant="outline" className="border-red-500 text-red-600 text-xs shrink-0">
                Remover
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {dup.equipment_key || "Sem equipamento"} &middot; {dup.doc_type || "Sem tipo"} &middot; {dup.published_date || "\u2014"} &middot; {dup.chunk_count} chunks
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
