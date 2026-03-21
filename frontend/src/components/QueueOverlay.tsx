interface Props {
  position: number;
  waitMs: number;
  status: string;
  onCancel: () => void;
}

export default function QueueOverlay({ position, waitMs, status, onCancel }: Props) {
  const waitSec = Math.ceil(waitMs / 1000);
  const isProcessing = status === 'processing';
  const title = isProcessing
    ? 'Processing\u2026'
    : position === 1
      ? 'You\u2019re next'
      : `Position #${position} in queue`;
  const desc = isProcessing
    ? 'Your analysis is running now.'
    : 'Your analysis will start shortly.';

  return (
    <div class="queue-overlay" role="status" aria-live="polite">
      <div class="queue-card">
        <div class="queue-spinner-ring">
          <svg class="queue-ring" viewBox="0 0 80 80">
            <circle class="queue-ring-track" cx="40" cy="40" r="34" />
            <circle class="queue-ring-fill" cx="40" cy="40" r="34" />
          </svg>
          <span class="queue-position">{position}</span>
        </div>
        <div class="queue-info">
          <h3 class="queue-title">{title}</h3>
          <p class="queue-desc">{desc}</p>
          <div class="queue-meta">
            {!isProcessing && (
              <span class="queue-wait">Estimated wait: ~{waitSec}s</span>
            )}
          </div>
        </div>
        <button type="button" class="queue-cancel" title="Cancel" onClick={onCancel}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
