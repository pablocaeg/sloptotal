import { getScoreColor } from '../lib/score-utils';

interface Props {
  score: number;
}

export default function Gauge({ score }: Props) {
  const color = getScoreColor(score);
  const dashLen = (score / 100) * 534;

  return (
    <div class="rh-gauge">
      <svg class="gauge" viewBox="0 0 200 200" aria-hidden="true">
        <circle class="gauge-track" cx="100" cy="100" r="85" />
        <circle
          class="gauge-fill"
          cx="100"
          cy="100"
          r="85"
          style={{
            strokeDasharray: `${dashLen} 534`,
            stroke: color,
          }}
        />
      </svg>
      <div class="gauge-center">
        <span class="gauge-number" style={{ color }}>
          {score.toFixed(1)}
        </span>
        <span class="gauge-of">/&thinsp;100</span>
      </div>
    </div>
  );
}
