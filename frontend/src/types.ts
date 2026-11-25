export type Role = 'admin' | 'reviewer' | 'operator' | 'approver';

export interface AuthUser {
  username: string;
  full_name: string;
  role: Role;
  access_token: string;
}

export interface Report {
  reference_id: string;
  report_type: string;
  product_name: string;
  batch_lot_number: string;
  date_received: string;
  reporter_type: string;
  description: string;
  event_description?: string | null;
  event_onset_date?: string | null;
  status: string;
  pending_close: boolean;
  reviewer_notes?: string | null;
  approver_comment?: string | null;
  created_by: string;
  updated_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RagDocument {
  doc_id: string;
  title: string;
  source_type: string;
  original_filename: string;
  chunk_strategy: string;
  chunk_size: number;
  chunk_overlap: number;
  chunk_count: number;
  status: string;
  uploaded_by: string;
  created_at?: string | null;
}
