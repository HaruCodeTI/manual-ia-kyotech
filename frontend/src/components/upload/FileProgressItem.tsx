// frontend/src/components/upload/FileProgressItem.tsx
"use client";

import { FileText, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { UploadResponse } from "@/types";

export type FileStatus =
  | "pendente"
  | "enviando"
  | "processando"
  | "concluído"
  | "erro";

export interface FileUploadState {
  id: string; // crypto.randomUUID() — chave de UI, não enviada ao backend
  file: File;
  status: FileStatus;
  progress: number; // 0–100, usado apenas em "enviando"
  result?: UploadResponse;
  error?: string;
}

const STATUS_LABELS: Record<FileStatus, string> = {
  pendente: "Pendente",
  enviando: "Enviando",
  processando: "Processando",
  concluído: "Concluído",
  erro: "Erro",
};

const STATUS_BADGE_CLASS: Record<FileStatus, string> = {
  pendente: "bg-muted text-muted-foreground",
  enviando: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  processando:
    "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300",
  concluído:
    "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  erro: "bg-destructive/10 text-destructive",
};

function truncateFilename(name: string, maxLen = 40): string {
  if (name.length <= maxLen) return name;
  const half = Math.floor((maxLen - 3) / 2);
  return `${name.slice(0, half)}...${name.slice(name.length - half)}`;
}

interface Props {
  state: FileUploadState;
}

export function FileProgressItem({ state }: Props) {
  const { file, status, progress, result, error } = state;

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border p-3">
      <div className="flex items-center gap-3">
        <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
        <span
          className="flex-1 truncate text-sm font-medium"
          title={file.name}
        >
          {truncateFilename(file.name)}
        </span>
        <span
          className={cn(
            "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
            STATUS_BADGE_CLASS[status],
          )}
        >
          {status === "processando" && (
            <Loader2 className="h-3 w-3 animate-spin" />
          )}
          {STATUS_LABELS[status]}
        </span>
      </div>

      {status === "enviando" && (
        <div className="ml-8">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-blue-500 transition-all duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="mt-0.5 text-right text-xs text-muted-foreground">
            {progress}%
          </p>
        </div>
      )}

      {status === "concluído" && result && (
        <p className="ml-8 text-xs text-muted-foreground">
          {result.total_chunks} chunks · {result.total_pages} página
          {result.total_pages !== 1 ? "s" : ""}
          {result.was_duplicate && " · (duplicata)"}
        </p>
      )}

      {status === "erro" && error && (
        <p className="ml-8 text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}
