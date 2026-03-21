interface Props {
  verdict: string;
  pending?: boolean;
}

export default function VerdictBadge({ verdict, pending }: Props) {
  if (pending) {
    return (
      <span class="verdict-badge verdict-badge-pending">
        <span class="mini-spinner"></span>
        PENDING
      </span>
    );
  }

  return (
    <span class={`verdict-badge verdict-badge-${verdict}`}>
      {verdict.toUpperCase()}
    </span>
  );
}
