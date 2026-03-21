export function getScoreColor(score: number): string {
  if (score <= 20) return 'var(--c-clean)';
  if (score <= 40) return 'var(--c-low)';
  if (score <= 60) return 'var(--c-warn)';
  if (score <= 80) return 'var(--c-danger)';
  return 'var(--c-slop)';
}

export function getBarColor(score: number): string {
  if (score < 0.4) return 'var(--c-clean)';
  if (score < 0.65) return 'var(--c-warn)';
  return 'var(--c-slop)';
}

export function getVerdictClass(score: number): string {
  if (score <= 20) return 'verdict-clean';
  if (score <= 40) return 'verdict-low';
  if (score <= 60) return 'verdict-suspicious';
  if (score <= 80) return 'verdict-likely';
  return 'verdict-slop';
}

export function getTickerScoreClass(score: number): string {
  if (score <= 20) return 'ti-clean';
  if (score <= 40) return 'ti-low';
  if (score <= 60) return 'ti-warn';
  if (score <= 80) return 'ti-danger';
  return 'ti-slop';
}
