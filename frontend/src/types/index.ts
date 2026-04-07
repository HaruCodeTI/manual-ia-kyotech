export interface Citation {
  source_index: number;
  source_filename: string;
  page_number: number;
  equipment_key: string;
  doc_type: "manual" | "informativo";
  published_date: string;
  document_version_id?: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  query_original: string;
  query_rewritten: string;
  total_sources: number;
  model_used: string;
  session_id: string;
  message_id: string;
}

export interface ChatRequest {
  question: string;
  equipment_filter?: string | null;
  session_id?: string | null;
}

export interface UploadResponse {
  success: boolean;
  message: string;
  document_id?: string;   // None quando was_duplicate=true
  version_id?: string;    // None quando was_duplicate=true
  total_pages: number;
  total_chunks: number;
  was_duplicate: boolean;
  retryable?: boolean;
}

export interface StatsResponse {
  equipments: number;
  documents: number;
  versions: number;
  chunks: number;
  docs_without_chunks: number; // novo
}

export interface UsageStatsResponse {
  total_sessions: number;
  total_messages: number;
  thumbs_up: number;
  thumbs_down: number;
}

export interface Message {
  id: string;
  message_id?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isLoading?: boolean;
}

export interface ChatSession {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionDetail {
  id: string;
  title: string | null;
  created_at: string;
  messages: {
    id: string;
    role: "user" | "assistant";
    content: string;
    citations: Citation[] | null;
    metadata: Record<string, unknown> | null;
    created_at: string;
  }[];
}

// Tipo para o rating de feedback
export type FeedbackRating = "thumbs_up" | "thumbs_down";

export interface DuplicateVersionInfo {
  version_id: string;
  document_id: string;
  filename: string;
  equipment_key: string | null;
  doc_type: string | null;
  published_date: string | null;
  created_at: string | null;
  storage_path: string;
  chunk_count: number;
}

export interface DuplicateGroup {
  source_hash: string;
  keep: DuplicateVersionInfo;
  duplicates: DuplicateVersionInfo[];
}

export interface DuplicateScanResponse {
  groups: DuplicateGroup[];
  total_groups: number;
  total_removable: number;
}

export interface DeleteDuplicatesResponse {
  deleted: number;
  skipped: number;
  orphan_documents_deleted: number;
  message: string;
}

export interface DocumentVersionItem {
  version_id: string;
  source_filename: string;
  published_date: string | null;
  ingested_at: string | null;
  total_pages: number;
  total_chunks: number;
  equipment_key: string | null;
  doc_type: string | null;
  storage_path: string | null;
}

export interface DocumentListResponse {
  versions: DocumentVersionItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
