import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

/**
 * Sensible defaults for a quoting workflow:
 *
 * - 30s `staleTime` so navigation between dashboard and detail doesn't
 *   trigger redundant refetches.
 * - Retries off for mutations (the user should see a clear failure and
 *   decide to retry; silent retries can corrupt the persisted review).
 */
function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(makeQueryClient);

  return (
    <QueryClientProvider client={client}>
      {children}
      {/* {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />} */}
    </QueryClientProvider>
  );
}
