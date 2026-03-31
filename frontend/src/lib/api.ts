import type { ChatResponse, UploadResponse, StatsResponse, UsageStatsResponse, ChatSession, FeedbackRating, DuplicateScanResponse, DeleteDuplicatesResponse } from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  if (typeof window !== "undefined" && window.Clerk?.session) {
    const token = await window.Clerk.session.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

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
    401: "Sessão expirada. Faça login novamente.",
    403: "Acesso negado.",
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
  equipmentFilter?: string | null,
  sessionId?: string | null,
): Promise<ChatResponse> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/chat/ask`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({
          question,
          equipment_filter: equipmentFilter || null,
          session_id: sessionId || null,
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
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/document`,
      { method: "POST", body: formData, headers: auth },
      600_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

// --- Viewer API ---

export interface ViewerInfo {
  version_id: string;
  source_filename: string;
  equipment_key: string;
  doc_type: string;
  published_date: string;
  total_pages: number;
}

export async function getViewerInfo(versionId: string): Promise<ViewerInfo> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/viewer/info/${versionId}`,
      { headers: auth },
      30_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export function getPageImageUrl(versionId: string, pageNumber: number): string {
  return `${API_BASE}/api/v1/viewer/page/${versionId}/${pageNumber}`;
}

export interface Equipment {
  key: string;
  name: string;
}

export async function getEquipments(): Promise<Equipment[]> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/equipments`,
      { headers: auth },
      15_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function getStats(): Promise<StatsResponse> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/stats`,
      { headers: auth },
      30_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function getUsageStats(): Promise<UsageStatsResponse> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/stats/usage`,
      { headers: auth },
      30_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

// --- Sessions API ---

export async function getSessions(): Promise<ChatSession[]> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/sessions`,
      { headers: auth },
      15_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function getSessionMessages(sessionId: string) {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/sessions/${sessionId}`,
      { headers: auth },
      15_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/sessions/${sessionId}`,
      { method: "DELETE", headers: auth },
      15_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
}

export async function uploadDocumentWithProgress(
  formData: FormData,
  onProgress: (percent: number) => void,
  onProcessing: () => void,
  signal?: AbortSignal, // reservado — sem lógica de cancelamento nesta versão
): Promise<UploadResponse> {
  const auth = await authHeaders();

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        // Cap em 99% — 100% sinaliza que o servidor está processando
        onProgress(Math.min(99, Math.round((e.loaded / e.total) * 100)));
      }
    });

    xhr.upload.addEventListener("load", () => {
      onProgress(100);
      onProcessing(); // Muda status para "processando" no componente
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResponse);
        } catch {
          reject(new Error("Resposta inválida do servidor."));
        }
      } else {
        // Reutiliza parseApiError criando um Response sintético a partir do XHR
        const fakeResponse = new Response(xhr.responseText, {
          status: xhr.status,
        });
        parseApiError(fakeResponse).then((msg) => reject(new Error(msg)));
      }
    });

    xhr.addEventListener("error", () => {
      reject(
        new Error(
          "Não foi possível conectar ao servidor. Verifique se o backend está rodando.",
        ),
      );
    });

    xhr.addEventListener("timeout", () => {
      reject(
        new Error(
          "A operação demorou mais que o esperado. Para documentos grandes, isso pode levar alguns minutos — tente novamente.",
        ),
      );
    });

    xhr.timeout = 600_000;
    xhr.open("POST", `${API_BASE}/api/v1/upload/document`);

    if (auth["Authorization"]) {
      xhr.setRequestHeader("Authorization", auth["Authorization"]);
    }

    xhr.send(formData);
  });
}

export async function submitFeedback(
  messageId: string,
  rating: FeedbackRating,
): Promise<void> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/chat/feedback`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ message_id: messageId, rating }),
      },
      10_000,
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
}

// --- Duplicates API ---

export async function scanDuplicates(): Promise<DuplicateScanResponse> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/duplicates`,
      { headers: auth },
      30_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function deleteDuplicates(
  versionIds: string[]
): Promise<DeleteDuplicatesResponse> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/duplicates`,
      {
        method: "DELETE",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ version_ids: versionIds }),
      },
      60_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}
