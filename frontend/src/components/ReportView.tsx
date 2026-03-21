import { useState, useEffect, useRef } from 'preact/hooks';
import { connectSSE, type SSEEngineEvent } from '../lib/sse';
import { fetchReport } from '../lib/api';
import { getVerdictClass } from '../lib/score-utils';
import { engines, enginesByKey } from '../lib/engines';
import type { ReportData } from '../types/api';
import Gauge from './Gauge';
import EngineRow from './EngineRow';
import CopyButton from './CopyButton';

interface Props {
  reportId?: string;
  initialReport?: ReportData;
}

export default function ReportView({ reportId: propReportId, initialReport }: Props) {
  // Read report ID from props or URL search params
  const [reportId] = useState(() => {
    if (propReportId) return propReportId;
    if (typeof window !== 'undefined') {
      return new URLSearchParams(window.location.search).get('id') || '';
    }
    return '';
  });

  const [loading, setLoading] = useState(!initialReport);
  const [error, setError] = useState('');
  const [report, setReport] = useState<ReportData | null>(initialReport || null);
  const [overallScore, setOverallScore] = useState(initialReport?.overall_score || 0);
  const [overallVerdict, setOverallVerdict] = useState(initialReport?.overall_verdict || 'Awaiting results');
  const [enginesFlagged, setEnginesFlagged] = useState(initialReport?.engines_flagged || 0);
  const [enginesDone, setEnginesDone] = useState(
    initialReport?.engine_results?.length || 0
  );
  const [scanning, setScanning] = useState(true);
  const [engineResults, setEngineResults] = useState<Record<string, { score: number; verdict: string; details: string }>>(() => {
    const initial: Record<string, { score: number; verdict: string; details: string }> = {};
    if (initialReport?.engine_results) {
      for (const er of initialReport.engine_results) {
        const eng = engines.find(e => e.name === er.engine_name);
        if (eng) {
          initial[eng.key] = { score: er.score, verdict: er.verdict, details: er.details };
        }
      }
    }
    return initial;
  });

  const closeRef = useRef<(() => void) | null>(null);

  // Fetch report data if not provided via props
  useEffect(() => {
    if (!reportId) {
      setError('No report ID provided.');
      setLoading(false);
      return;
    }
    if (initialReport) {
      setLoading(false);
      return;
    }

    fetchReport(reportId)
      .then((data) => {
        setReport(data);
        setOverallScore(data.overall_score);
        setOverallVerdict(data.overall_verdict);
        setEnginesFlagged(data.engines_flagged);
        if (data.engine_results) {
          setEnginesDone(data.engine_results.length);
          const results: Record<string, { score: number; verdict: string; details: string }> = {};
          for (const er of data.engine_results) {
            const eng = engines.find(e => e.name === er.engine_name);
            if (eng) {
              results[eng.key] = { score: er.score, verdict: er.verdict, details: er.details };
            }
          }
          setEngineResults(results);
        }
        setLoading(false);
      })
      .catch(() => {
        setError('Report not found or failed to load.');
        setLoading(false);
      });
  }, [reportId]);

  // Connect SSE for live streaming
  useEffect(() => {
    if (!reportId) return;

    const close = connectSSE(reportId, {
      onEngineResult(data: SSEEngineEvent) {
        setEngineResults(prev => ({
          ...prev,
          [data.key]: { score: data.score, verdict: data.verdict, details: data.details },
        }));
        setOverallScore(data.overall_score);
        setOverallVerdict(data.overall_verdict);
        setEnginesFlagged(data.engines_flagged);
        setEnginesDone(data.engines_done);
      },
      onDone() {
        setScanning(false);
        fetchReport(reportId).then(r => {
          setOverallScore(r.overall_score);
          setOverallVerdict(r.overall_verdict);
          setEnginesFlagged(r.engines_flagged);
          setEnginesDone(r.engines_total);
        }).catch(() => {});
      },
      onError() {
        setScanning(false);
      },
    });
    closeRef.current = close;
    return () => close();
  }, [reportId]);

  if (!reportId) {
    return (
      <section style="text-align:center; padding:60px 20px;">
        <p style="color:var(--dim);">No report ID provided. <a href="/">Run a new scan</a></p>
      </section>
    );
  }

  if (loading) {
    return (
      <section style="text-align:center; padding:60px 20px;">
        <p style="color:var(--dim);">Loading report...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section style="text-align:center; padding:60px 20px;">
        <p style="color:var(--c-danger);">{error}</p>
        <a href="/" class="btn btn-ghost" style="margin-top:16px;">Run a new scan</a>
      </section>
    );
  }

  const total = report?.engines_total || 23;
  const verdictClass = getVerdictClass(overallScore);

  return (
    <>
      <section class="report-header">
        <Gauge score={overallScore} />
        <div class="rh-info">
          <div class="rh-status">
            <span class={`status-dot ${scanning ? 'scanning' : 'done'}`}></span>
            <span class="status-label">{scanning ? 'Scanning\u2026' : 'Complete'}</span>
          </div>
          <h1 class={`verdict-text ${verdictClass}`}>{overallVerdict}</h1>
          <p class="flagged-count">
            <strong>{scanning ? enginesDone : enginesFlagged}</strong>
            {' / '}{total}{' '}
            {scanning ? 'engines completed' : 'engines flagged this content'}
          </p>
          {report && (
            <div class="meta-pills">
              <span class="pill">{report.word_count} words</span>
              <span class="pill">{report.source_type.toUpperCase()}</span>
              <span class="pill pill-id">{reportId}</span>
            </div>
          )}
        </div>
      </section>

      {report?.source_type === 'url' && (
        <div class="source-url">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M6.5 11.5L3.7 11.5a3.2 3.2 0 010-6.4h2.8M9.5 4.5h2.8a3.2 3.2 0 010 6.4H9.5M5.3 8h5.4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
          </svg>
          {report.source}
        </div>
      )}

      <section class="engine-results" aria-labelledby="breakdown-heading">
        <div class="section-header">
          <h2 id="breakdown-heading">Engine Breakdown</h2>
          <span class="progress-text">{enginesDone} / {total}</span>
        </div>
        <div class="results-list">
          {engines.map(engine => {
            const result = engineResults[engine.key];
            return (
              <EngineRow
                key={engine.key}
                engineKey={engine.code}
                name={engine.name}
                description={engine.description}
                score={result?.score}
                verdict={result?.verdict}
                details={result?.details}
                done={!!result}
              />
            );
          })}
        </div>
      </section>

      {report?.text_excerpt && (
        <section class="text-excerpt" aria-labelledby="excerpt-heading">
          <h2 id="excerpt-heading">Analysed Text</h2>
          <div class="excerpt-box">{report.text_excerpt}</div>
        </section>
      )}

      <div class="report-actions">
        <a href="/" class="btn btn-ghost">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M13 8H3M7 4L3 8l4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          New Scan
        </a>
        <CopyButton />
      </div>
    </>
  );
}
