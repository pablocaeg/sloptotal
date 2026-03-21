import { useState, useRef } from 'preact/hooks';
import { submitAnalysis, pollQueueTicket } from '../lib/api';
import QueueOverlay from './QueueOverlay';

export default function AnalyzeForm() {
  const [activeTab, setActiveTab] = useState<'url' | 'text'>('url');
  const [urlValue, setUrlValue] = useState('');
  const [textValue, setTextValue] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [queue, setQueue] = useState<{
    ticketId: string;
    position: number;
    waitMs: number;
    status: string;
  } | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  function switchTab(tab: 'url' | 'text') {
    setActiveTab(tab);
    if (tab === 'url') setTextValue('');
    else setUrlValue('');
  }

  async function handleSubmit(e: Event) {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    const body: { url?: string; text?: string } = {};
    if (activeTab === 'url' && urlValue.trim()) {
      body.url = urlValue.trim();
    } else if (activeTab === 'text' && textValue.trim()) {
      body.text = textValue.trim();
    } else {
      setError('Please provide a URL or paste some text to analyze.');
      setSubmitting(false);
      return;
    }

    abortRef.current = new AbortController();

    try {
      const { status, data } = await submitAnalysis(body, abortRef.current.signal);

      if (status === 200 && data.report_id) {
        window.location.href = `/report?id=${data.report_id}`;
        return;
      }

      if (status === 202 && data.ticket_id) {
        setQueue({
          ticketId: data.ticket_id,
          position: data.position || 1,
          waitMs: data.estimated_wait_ms || 5000,
          status: 'queued',
        });
        startPolling(data.ticket_id);
        return;
      }

      setError(data.error || 'Something went wrong. Please try again.');
      setSubmitting(false);
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setError('Could not reach the server. Is it running?');
      setSubmitting(false);
    }
  }

  function startPolling(ticketId: string) {
    let attempts = 0;
    const maxAttempts = 120;

    function poll() {
      if (attempts >= maxAttempts) {
        setQueue(null);
        setError('Queue timed out. Please try again.');
        setSubmitting(false);
        return;
      }
      attempts++;

      pollQueueTicket(ticketId, abortRef.current?.signal)
        .then(({ status, data }) => {
          if (status === 200 && data.report_id) {
            window.location.href = `/report?id=${data.report_id}`;
            return;
          }
          if (status === 202) {
            setQueue(prev => prev ? {
              ...prev,
              position: data.position || prev.position,
              waitMs: data.estimated_wait_ms || prev.waitMs,
              status: data.status || 'queued',
            } : prev);
            setTimeout(poll, 500);
            return;
          }
          if (status === 404) {
            setQueue(null);
            setError('Queue ticket expired. Please try again.');
            setSubmitting(false);
          }
        })
        .catch((err: any) => {
          if (err.name === 'AbortError') return;
          setTimeout(poll, 1000);
        });
    }

    setTimeout(poll, 500);
  }

  function handleCancel() {
    abortRef.current?.abort();
    setQueue(null);
    setSubmitting(false);
  }

  return (
    <>
      {error && (
        <div class="error-banner" role="alert">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5" />
            <path d="M8 4.5v4M8 10.5v1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
          {error}
        </div>
      )}

      {queue && (
        <QueueOverlay
          position={queue.position}
          waitMs={queue.waitMs}
          status={queue.status}
          onCancel={handleCancel}
        />
      )}

      <div class="input-card input-card--hero">
        <div class="tabs" role="tablist">
          <button
            class={`tab ${activeTab === 'url' ? 'active' : ''}`}
            role="tab"
            aria-selected={activeTab === 'url'}
            onClick={() => switchTab('url')}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M6.5 11.5L3.7 11.5a3.2 3.2 0 010-6.4h2.8M9.5 4.5h2.8a3.2 3.2 0 010 6.4H9.5M5.3 8h5.4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
            </svg>
            URL
          </button>
          <button
            class={`tab ${activeTab === 'text' ? 'active' : ''}`}
            role="tab"
            aria-selected={activeTab === 'text'}
            onClick={() => switchTab('text')}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M3 4h10M3 7h10M3 10h7M3 13h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
            </svg>
            Text
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {activeTab === 'url' ? (
            <div class="tab-content active" role="tabpanel">
              <label for="url-input" class="sr-only">URL to analyse</label>
              <input
                type="url"
                id="url-input"
                placeholder="https://example.com/article"
                autocomplete="off"
                value={urlValue}
                onInput={(e) => setUrlValue((e.target as HTMLInputElement).value)}
              />
            </div>
          ) : (
            <div class="tab-content active" role="tabpanel">
              <label for="text-input" class="sr-only">Text to analyse</label>
              <textarea
                id="text-input"
                rows={6}
                maxLength={50000}
                placeholder="Paste the text you want to analyse..."
                value={textValue}
                onInput={(e) => setTextValue((e.target as HTMLTextAreaElement).value)}
              />
            </div>
          )}
          <div class="form-bottom">
            <button type="submit" class="submit-btn" disabled={submitting}>
              {submitting ? (
                <span class="btn-loading">
                  <span class="spinner"></span>
                  {' '}Submitting&hellip;
                </span>
              ) : (
                <span class="btn-text">
                  Run Analysis
                  <svg class="btn-arrow" width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </span>
              )}
            </button>
            <span class="form-hint">Free &amp; private. All analysis runs locally on our servers.</span>
          </div>
        </form>
      </div>
    </>
  );
}
