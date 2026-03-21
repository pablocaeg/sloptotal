import { getBarColor } from '../lib/score-utils';

interface Props {
  score: number; // 0-1 range
  pending?: boolean;
}

export default function ScoreBar({ score, pending }: Props) {
  const pct = (score * 100).toFixed(1);
  const color = getBarColor(score);

  return (
    <>
      <div class="score-bar-container">
        <div
          class="score-bar"
          style={{
            width: pending ? '0%' : `${pct}%`,
            background: pending ? undefined : color,
          }}
        />
      </div>
      <span class="score-value">{pending ? '\u2014' : `${pct}%`}</span>
    </>
  );
}
