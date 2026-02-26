"use client";

import { useState, useRef, type FormEvent } from "react";
import { uploadDocument } from "@/lib/api";
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
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "lucide-react";

type Status = "idle" | "uploading" | "success" | "error";

export function UploadForm() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [docType, setDocType] = useState("");
  const [fileName, setFileName] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setResult(null);

    const form = e.currentTarget;
    const fileInput = form.elements.namedItem("file") as HTMLInputElement;
    const file = fileInput?.files?.[0];

    if (!file) {
      setError("Selecione um arquivo PDF.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Apenas arquivos PDF são aceitos.");
      return;
    }

    const equipmentKey = (
      form.elements.namedItem("equipment_key") as HTMLInputElement
    ).value.trim();
    const publishedDate = (
      form.elements.namedItem("published_date") as HTMLInputElement
    ).value;
    const displayName = (
      form.elements.namedItem("equipment_display_name") as HTMLInputElement
    ).value.trim();

    if (!equipmentKey || !docType || !publishedDate) {
      setError("Preencha todos os campos obrigatórios.");
      return;
    }

    const fd = new FormData();
    fd.append("file", file);
    fd.append("equipment_key", equipmentKey);
    fd.append("doc_type", docType);
    fd.append("published_date", publishedDate);
    if (displayName) fd.append("equipment_display_name", displayName);

    setStatus("uploading");
    try {
      const data = await uploadDocument(fd);
      setResult(data);
      setStatus("success");
      formRef.current?.reset();
      setFileName("");
      setDocType("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao enviar documento");
      setStatus("error");
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Upload de Documento
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form
            ref={formRef}
            onSubmit={handleSubmit}
            className="space-y-4"
          >
            <div>
              <label className="mb-1.5 block text-sm font-medium">
                Arquivo PDF *
              </label>
              <label className="flex cursor-pointer items-center gap-3 rounded-lg border-2 border-dashed p-4 transition-colors hover:border-primary hover:bg-accent">
                <FileText className="h-8 w-8 text-muted-foreground" />
                <div className="flex-1 text-sm">
                  {fileName ? (
                    <span className="font-medium">{fileName}</span>
                  ) : (
                    <span className="text-muted-foreground">
                      Clique para selecionar um PDF
                    </span>
                  )}
                </div>
                <input
                  type="file"
                  name="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) =>
                    setFileName(e.target.files?.[0]?.name || "")
                  }
                />
              </label>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium">
                Equipamento (key) *
              </label>
              <Input
                name="equipment_key"
                placeholder="ex: frontier-780"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium">
                Tipo de documento *
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

            <div>
              <label className="mb-1.5 block text-sm font-medium">
                Data de publicação *
              </label>
              <Input type="date" name="published_date" />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium">
                Nome de exibição do equipamento
              </label>
              <Input
                name="equipment_display_name"
                placeholder="ex: Frontier 780 (opcional)"
              />
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={status === "uploading"}
            >
              {status === "uploading" ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processando…
                </>
              ) : (
                <>
                  <Upload className="mr-2 h-4 w-4" />
                  Enviar documento
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-destructive">
          <CardContent className="flex items-start gap-3 pt-6">
            <AlertCircle className="h-5 w-5 shrink-0 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {result && (
        <Card className="border-green-500">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600" />
              <div className="space-y-1 text-sm">
                <p className="font-medium text-green-700">{result.message}</p>
                <p className="text-muted-foreground">
                  {result.total_pages} páginas · {result.total_chunks} chunks
                  gerados
                  {result.was_duplicate && " (duplicata detectada)"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
