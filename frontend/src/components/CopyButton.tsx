import { useState } from 'preact/hooks';

export default function CopyButton() {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button class="btn btn-ghost" onClick={handleCopy}>
      {!copied && (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <rect x="5" y="5" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.3" />
          <path d="M11 3H4.5A1.5 1.5 0 003 4.5V11" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
        </svg>
      )}
      {copied ? ' Copied!' : ' Copy Link'}
    </button>
  );
}
