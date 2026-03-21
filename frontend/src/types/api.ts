export interface WebAnalyzeResponse {
  status?: string;
  report_id?: string;
  ticket_id?: string;
  position?: number;
  estimated_wait_ms?: number;
  error?: string;
  retry_after?: number;
}

export interface QueueTicketResponse {
  status?: string;
  report_id?: string;
  position?: number;
  estimated_wait_ms?: number;
}

export interface RecentReport {
  id: string;
  source: string;
  source_type: string;
  overall_score: number;
  overall_verdict: string;
  word_count: number;
  created_at: string;
}

export interface ReportData {
  id: string;
  text_excerpt: string;
  source: string;
  source_type: string;
  word_count: number;
  overall_score: number;
  overall_verdict: string;
  engines_total: number;
  engines_flagged: number;
  engine_results: EngineResult[];
}

export interface EngineResult {
  engine_name: string;
  score: number;
  verdict: string;
  details: string;
  description: string;
}
