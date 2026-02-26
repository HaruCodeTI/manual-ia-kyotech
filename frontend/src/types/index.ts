export interface Citation {
  source_index: number;
  source_filename: string;
  page_number: number;
  equipment_key: string;
  doc_type: "manual" | "informativo";
  published_date: string;
  storage_path: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  query_original: string;
  query_rewritten: string;
  total_sources: number;
  model_used: string;
}

export interface ChatRequest {
  question: string;
  equipment_filter?: string | null;
}

export interface UploadResponse {
  success: boolean;
  message: string;
  document_id: string;
  version_id: string;
  total_pages: number;
  total_chunks: number;
  was_duplicate: boolean;
}

export interface StatsResponse {
  equipments: number;
  documents: number;
  versions: number;
  chunks: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isLoading?: boolean;
}
