export function ShortcutHint({ keys }: { keys: string[] }) {
  return (
    <span className="pointer-events-none absolute -bottom-6 left-1/2 flex -translate-x-1/2 items-center gap-0.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
      {keys.map((k) => (
        <kbd
          key={k}
          className="inline-flex h-5 items-center rounded border border-border bg-muted px-1.5 font-mono text-[10px] font-semibold text-muted-foreground"
        >
          {k}
        </kbd>
      ))}
    </span>
  );
}
