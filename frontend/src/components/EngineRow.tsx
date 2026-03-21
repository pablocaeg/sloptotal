import VerdictBadge from './VerdictBadge';
import ScoreBar from './ScoreBar';

interface Props {
  engineKey: string;
  name: string;
  description: string;
  score?: number;
  verdict?: string;
  details?: string;
  done: boolean;
}

export default function EngineRow({ engineKey, name, description, score, verdict, details, done }: Props) {
  return (
    <div class={`engine-row ${done ? 'engine-row-done' : 'engine-row-pending'}`}>
      <div class="er-identity">
        <span class="er-code">{engineKey.toUpperCase()}</span>
        <div class="er-names">
          <span class="engine-name">{name}</span>
          <span class="engine-desc">{description}</span>
        </div>
      </div>
      <div class="er-result">
        <VerdictBadge verdict={verdict || ''} pending={!done} />
        <ScoreBar score={score || 0} pending={!done} />
      </div>
      {done && details && (
        <div class="er-details details-cell">{details}</div>
      )}
      {!done && (
        <div class="er-details">
          <span class="waiting-text">waiting&hellip;</span>
        </div>
      )}
    </div>
  );
}
