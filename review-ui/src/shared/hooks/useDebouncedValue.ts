import { useEffect, useState } from "react";

/**
 * Returns `value` only after it has been stable for `delayMs`.
 *
 * Standard pattern — the timer is reset on every change to the input,
 * so we only emit when the user pauses typing.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(handle);
  }, [value, delayMs]);

  return debounced;
}
