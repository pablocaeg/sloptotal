import { API_BASE } from './config';

export interface SSEEngineEvent {
  key: string;
  engine_name: string;
  score: number;
  verdict: string;
  details: string;
  description: string;
  overall_score: number;
  overall_verdict: string;
  engines_flagged: number;
  engines_total: number;
  engines_done: number;
}

export interface SSEDoneEvent {
  done: true;
}

export type SSEEvent = SSEEngineEvent | SSEDoneEvent;

export function connectSSE(
  reportId: string,
  callbacks: {
    onEngineResult: (data: SSEEngineEvent) => void;
    onDone: () => void;
    onError: () => void;
  },
): () => void {
  const url = `${API_BASE}/api/stream/${reportId}`;
  const source = new EventSource(url);

  source.onmessage = (event) => {
    try {
      const data: SSEEvent = JSON.parse(event.data);
      if ('done' in data && data.done) {
        source.close();
        callbacks.onDone();
      } else {
        callbacks.onEngineResult(data as SSEEngineEvent);
      }
    } catch {
      // ignore parse errors
    }
  };

  source.onerror = () => {
    source.close();
    callbacks.onError();
  };

  return () => source.close();
}
