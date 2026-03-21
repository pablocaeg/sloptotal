import { useState, useEffect, useRef } from 'preact/hooks';
import { fetchRecent } from '../lib/api';
import { getTickerScoreClass } from '../lib/score-utils';
import type { RecentReport } from '../types/api';

export default function TickerClient() {
  const [reports, setReports] = useState<RecentReport[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchRecent()
      .then((data) => {
        if (data.length > 0) setReports(data);
      })
      .catch(() => {});
  }, []);

  if (reports.length === 0) return null;

  const dur = Math.max(reports.length * 4, 16);
  // Duplicate for seamless loop
  const items = [...reports, ...reports];

  return (
    <div class="ticker" aria-label="Recent scans">
      <div class="ticker-label">
        <span class="ticker-dot"></span>
        Recent
      </div>
      <div class="ticker-track">
        <div
          ref={scrollRef}
          class="ticker-scroll"
          style={{ animationDuration: `${dur}s` }}
        >
          {items.map((r, i) => {
            const src = r.source.length > 55 ? r.source.substring(0, 55) + '\u2026' : r.source;
            return (
              <a key={`${r.id}-${i}`} href={`/report/${r.id}`} class="ticker-item">
                <span class={`ti-score ${getTickerScoreClass(r.overall_score)}`}>
                  {r.overall_score.toFixed(1)}
                </span>
                <span class="ti-source">{src}</span>
                <span class="ti-verdict">{r.overall_verdict}</span>
                <span class="ti-time">{r.created_at}</span>
              </a>
            );
          })}
        </div>
      </div>
    </div>
  );
}
