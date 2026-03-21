import { API_BASE } from './config';
import type { ReportData, RecentReport, WebAnalyzeResponse, QueueTicketResponse } from '../types/api';

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    const err = new Error(body.error || `HTTP ${res.status}`) as Error & { status: number; body: unknown };
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json();
}

export async function submitAnalysis(
  data: { url?: string; text?: string },
  signal?: AbortSignal,
): Promise<{ status: number; data: WebAnalyzeResponse }> {
  const res = await fetch(`${API_BASE}/api/web/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal,
  });
  const json = await res.json();
  return { status: res.status, data: json };
}

export async function pollQueueTicket(
  ticketId: string,
  signal?: AbortSignal,
): Promise<{ status: number; data: QueueTicketResponse }> {
  const res = await fetch(`${API_BASE}/api/queue/ticket/${ticketId}`, { signal });
  const json = await res.json();
  return { status: res.status, data: json };
}

export async function fetchReport(reportId: string): Promise<ReportData> {
  return fetchJSON<ReportData>(`/api/report/${reportId}`);
}

export async function fetchRecent(): Promise<RecentReport[]> {
  return fetchJSON<RecentReport[]>('/api/recent');
}
