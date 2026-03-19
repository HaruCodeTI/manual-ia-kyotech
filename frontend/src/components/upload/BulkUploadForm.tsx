// frontend/src/components/upload/BulkUploadForm.tsx
"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { uploadDocumentWithProgress } from "@/lib/api";
import { FileProgressItem } from "./FileProgressItem";
import type { FileUploadState, FileStatus } from "./FileProgressItem";
import type { UploadResponse } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Upload, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const SESSION_KEY = 'kyotech_bulk_upload';

const MAX_FILES = 10;
const MAX_FILE_SIZE_MB = 200;
const MAX_CONCURRENT = 3;

interface PersistedFileState {
  id: string;
  fileName: string;
  fileSize: number;
  status: FileStatus;
  progress: number;
  result?: UploadResponse;
  error?: string;
}

function saveToSession(files: FileUploadState[]): void {
  const serializable: PersistedFileState[] = files.map((f) => ({
    id: f.id,
    fileName: f.file.name,
    fileSize: f.file.size,
    status: f.status,
    progress: f.progress,
    result: f.result,
    error: f.error,
  }));
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(serializable));
}

function loadFromSession(): FileUploadState[] | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const persisted: PersistedFileState[] = JSON.parse(raw);
    return persisted.map((p) => ({
      id: p.id,
      file: new File([], p.fileName, { type: 'application/pdf' }) as File,
      // File vazio — só para exibição. Não pode ser reenviado.
      status: (p.status === 'enviando' || p.status === 'processando' || p.status === 'pendente')
        ? 'erro'
        : p.status,
      progress: p.progress,
      result: p.result,
      error: (p.status === 'enviando' || p.status === 'processando' || p.status === 'pendente')
        ? 'Upload interrompido — reenvie o arquivo'
        : p.error,
    }));
  } catch {
    return null;
  }
}

type Phase = "select" | "uploading" | "done";

interface FieldErrors {
  files?: string;
  equipment_key?: string;
}

function validateFiles(files: File[]): string | null {
  if (files.length === 0) return "Selecione ao menos um arquivo PDF.";
  if (files.length > MAX_FILES)
    return `Máximo de ${MAX_FILES} arquivos por envio.`;
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith(".pdf"))
      return `"${f.name}" não é um PDF.`;
    if (f.size === 0) return `"${f.name}" está vazio.`;
    if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024)
      return `"${f.name}" excede ${MAX_FILE_SIZE_MB}MB.`;
  }
  return null;
}

export function BulkUploadForm() {
  const initialFiles = loadFromSession() ?? [];
  const initialPhase: Phase = initialFiles.length > 0 && initialFiles.every(
    (f) => f.status === 'concluído' || f.status === 'erro'
  ) ? 'done' : 'select';

  const [phase, setPhase] = useState<Phase>(initialPhase);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileStates, setFileStates] = useState<FileUploadState[]>(initialFiles);
  const [docType, setDocType] = useState("");
  const [equipmentKey, setEquipmentKey] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    if (fileStates.length > 0) {
      saveToSession(fileStates);
    } else {
      sessionStorage.removeItem(SESSION_KEY);
    }
  }, [fileStates]);

  // Refs para estado mutável que não dispara re-render
  const queueRef = useRef<FileUploadState[]>([]);
  const activeCountRef = useRef(0);
  // Captura os valores de metadata no momento do submit (estáveis durante upload)
  const equipmentKeyRef = useRef("");
  const docTypeRef = useRef("");

  const updateFileState = useCallback(
    (id: string, patch: Partial<FileUploadState>) => {
      setFileStates((prev) =>
        prev.map((s) => (s.id === id ? { ...s, ...patch } : s)),
      );
    },
    [],
  );

  const checkIfDone = useCallback(() => {
    setFileStates((prev) => {
      const allDone = prev.every(
        (s) => s.status === "concluído" || s.status === "erro",
      );
      if (allDone && prev.length > 0) setPhase("done");
      return prev;
    });
  }, []);

  // processFile é memoizado com deps [updateFileState, checkIfDone].
  // A chamada recursiva `processFile(next)` dentro do próprio callback é segura:
  // em JS single-threaded, `queueRef.current.shift()` é atômico e o closure
  // captura sempre a versão atual da função. Não incluímos `processFile` nas deps
  // para evitar loop infinito de recriação.
  const processFile = useCallback(
    async (state: FileUploadState) => {
      updateFileState(state.id, { status: "enviando", progress: 0 });

      const fd = new FormData();
      fd.append("file", state.file);
      if (equipmentKeyRef.current)
        fd.append("equipment_key", equipmentKeyRef.current);
      if (docTypeRef.current) fd.append("doc_type", docTypeRef.current);

      try {
        const result = await uploadDocumentWithProgress(
          fd,
          (pct) => updateFileState(state.id, { progress: pct }),
          () =>
            updateFileState(state.id, { status: "processando", progress: 100 }),
        );
        updateFileState(state.id, { status: "concluído", result });
      } catch (err) {
        updateFileState(state.id, {
          status: "erro",
          error:
            err instanceof Error ? err.message : "Erro desconhecido.",
        });
      } finally {
        activeCountRef.current -= 1;
        const next = queueRef.current.shift();
        if (next) {
          activeCountRef.current += 1;
          processFile(next);
        }
        checkIfDone();
      }
    },
    [updateFileState, checkIfDone],
  );

  function handleFilesChange(files: FileList | null) {
    if (!files || files.length === 0) return;
    const arr = Array.from(files).slice(0, MAX_FILES);
    setSelectedFiles(arr);
    setFieldErrors({});
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (phase !== "select") return;
    handleFilesChange(e.dataTransfer?.files ?? null);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave() {
    setIsDragging(false);
  }

  async function handleSubmit() {
    const fileError = validateFiles(selectedFiles);
    if (fileError) {
      setFieldErrors({ files: fileError });
      return;
    }

    if (
      equipmentKey.trim() &&
      !/^[a-z0-9][a-z0-9-]*$/.test(equipmentKey.trim())
    ) {
      setFieldErrors({
        equipment_key: "Use apenas letras minúsculas, números e hífens.",
      });
      return;
    }

    // Capturar metadata em refs antes de iniciar (imutável durante upload)
    equipmentKeyRef.current = equipmentKey.toLowerCase().trim();
    docTypeRef.current = docType;

    const states: FileUploadState[] = selectedFiles.map((file) => ({
      id: crypto.randomUUID(),
      file,
      status: "pendente" as FileStatus,
      progress: 0,
    }));

    setFileStates(states);
    setPhase("uploading");

    // Arquivos além do limite de concorrência ficam na fila
    queueRef.current = states.slice(MAX_CONCURRENT);
    activeCountRef.current = 0;

    // Inicia o primeiro lote
    states.slice(0, MAX_CONCURRENT).forEach((s) => {
      activeCountRef.current += 1;
      processFile(s);
    });
  }

  function handleReset() {
    sessionStorage.removeItem(SESSION_KEY);
    setPhase("select");
    setSelectedFiles([]);
    setFileStates([]);
    setDocType("");
    setEquipmentKey("");
    setFieldErrors({});
    queueRef.current = [];
    activeCountRef.current = 0;
  }

  const successCount = fileStates.filter((s) => s.status === "concluído").length;
  const errorCount = fileStates.filter((s) => s.status === "erro").length;

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Upload de Documentos
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {phase === "select" && (
            <>
              {/* Dropzone */}
              <div>
                <label className="mb-1.5 block text-sm font-medium">
                  Arquivos PDF{" "}
                  <span className="text-muted-foreground">
                    (máx. {MAX_FILES}, até {MAX_FILE_SIZE_MB}MB cada)
                  </span>
                </label>
                <label
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  className={cn(
                    "flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-6 text-center transition-colors",
                    isDragging
                      ? "border-primary bg-accent"
                      : "hover:border-primary hover:bg-accent",
                    fieldErrors.files && "border-destructive",
                  )}
                >
                  <Upload className="h-8 w-8 text-muted-foreground" />
                  <div className="text-sm text-muted-foreground">
                    {selectedFiles.length > 0 ? (
                      <span className="font-medium text-foreground">
                        {selectedFiles.length} arquivo
                        {selectedFiles.length > 1 ? "s" : ""} selecionado
                        {selectedFiles.length > 1 ? "s" : ""}
                      </span>
                    ) : (
                      <>Arraste arquivos ou clique para selecionar</>
                    )}
                  </div>
                  <input
                    type="file"
                    accept=".pdf"
                    multiple
                    className="hidden"
                    onChange={(e) => handleFilesChange(e.target.files)}
                  />
                </label>
                {fieldErrors.files && (
                  <p className="mt-1 text-xs text-destructive">
                    {fieldErrors.files}
                  </p>
                )}
              </div>

              {/* Metadata opcionais */}
              <div>
                <label className="mb-1.5 block text-sm font-medium">
                  Equipamento{" "}
                  <span className="text-muted-foreground">(opcional)</span>
                </label>
                <Input
                  placeholder="ex: frontier-780"
                  value={equipmentKey}
                  className={cn(
                    fieldErrors.equipment_key && "border-destructive",
                  )}
                  onChange={(e) => {
                    setEquipmentKey(e.target.value);
                    setFieldErrors((p) => ({
                      ...p,
                      equipment_key: undefined,
                    }));
                  }}
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Letras minúsculas, números e hífens
                </p>
                {fieldErrors.equipment_key && (
                  <p className="mt-1 text-xs text-destructive">
                    {fieldErrors.equipment_key}
                  </p>
                )}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium">
                  Tipo de documento{" "}
                  <span className="text-muted-foreground">(opcional)</span>
                </label>
                <Select value={docType} onValueChange={setDocType}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione o tipo" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manual</SelectItem>
                    <SelectItem value="informativo">Informativo</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button
                className="w-full"
                onClick={handleSubmit}
                disabled={selectedFiles.length === 0}
              >
                <Upload className="mr-2 h-4 w-4" />
                Enviar{" "}
                {selectedFiles.length > 0
                  ? `${selectedFiles.length} arquivo${selectedFiles.length > 1 ? "s" : ""}`
                  : "documentos"}
              </Button>
            </>
          )}

          {(phase === "uploading" || phase === "done") && (
            <div className="space-y-2">
              {fileStates.map((s) => (
                <FileProgressItem key={s.id} state={s} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {phase === "done" && (
        <Card
          className={errorCount === 0 ? "border-green-500" : "border-yellow-500"}
        >
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              {errorCount === 0 ? (
                <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600" />
              ) : (
                <AlertCircle className="h-5 w-5 shrink-0 text-yellow-600" />
              )}
              <div className="flex-1 space-y-3">
                <p className="text-sm font-medium">
                  {successCount} de {fileStates.length} concluído
                  {fileStates.length > 1 ? "s" : ""} com sucesso
                  {errorCount > 0 && ` · ${errorCount} com erro`}
                </p>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={handleReset}
                >
                  Novo upload
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
