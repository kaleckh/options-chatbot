export function CompactStat({
  label,
  value,
  help,
}: {
  label: string;
  value: string;
  help?: string;
}) {
  return (
    <div className="bg-bg-2 border border-border rounded-lg px-3 py-1.5 min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.09em] text-text-2">
        {label}
        {help && <span className="sr-only">: {help}</span>}
      </div>
      <div className="font-mono text-[0.95rem] text-text-0 mt-0.5">{value}</div>
    </div>
  );
}
