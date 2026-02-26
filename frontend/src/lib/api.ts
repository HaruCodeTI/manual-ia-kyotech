import type { ChatResponse, UploadResponse, StatsResponse } from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function handleFetchError(err: unknown): never {
  if (err instanceof DOMException && err.name === "AbortError") {
    throw new Error(
      "A operação demorou mais que o esperado. Para documentos grandes, isso pode levar alguns minutos — tente novamente."
    );
  }
  if (err instanceof TypeError) {
    throw new Error(
      "Não foi possível conectar ao servidor. Verifique se o backend está rodando."
    );
  }
  throw err;
}

function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...options, signal: controller.signal }).finally(() =>
    clearTimeout(timer)
  );
}

async function parseApiError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body.detail) {
      if (typeof body.detail === "string") return body.detail;
      if (Array.isArray(body.detail)) {
        return body.detail
          .map((d: { msg?: string }) => d.msg ?? JSON.stringify(d))
          .join("; ");
      }
    }
  } catch {
    /* resposta não é JSON */
  }
  const STATUS_MAP: Record<number, string> = {
    400: "Requisição inválida.",
    404: "Recurso não encontrado.",
    413: "Arquivo muito grande.",
    422: "Erro ao processar documento.",
    500: "Erro interno do servidor.",
    503: "Serviço temporariamente indisponível.",
  };
  return STATUS_MAP[res.status] ?? `Erro inesperado (código ${res.status}).`;
}

export async function askQuestion(
  question: string,
  equipmentFilter?: string | null
): Promise<ChatResponse> {
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/chat/ask`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          equipment_filter: equipmentFilter || null,
        }),
      },
      120_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function uploadDocument(
  formData: FormData
): Promise<UploadResponse> {
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/document`,
      { method: "POST", body: formData },
      600_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function getPdfUrl(
  storagePath: string,
  page: number
): Promise<string> {
  const params = new URLSearchParams({
    storage_path: storagePath,
    page: String(page),
  });
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/chat/pdf-url?${params}`,
      {},
      15_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  const data = await res.json();
  return data.url;
}

export interface Equipment {
  key: string;
  name: string;
}

export async function getEquipments(): Promise<Equipment[]> {
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/equipments`,
      {},
      15_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function getStats(): Promise<StatsResponse> {
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/stats`,
      {},
      30_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}
