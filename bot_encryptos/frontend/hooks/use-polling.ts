import useSWR from "swr"

export function usePolling<T>(key: string | null, fetcher: () => Promise<T>, intervalMs = 3000) {
  return useSWR<T>(key, fetcher, {
    refreshInterval: intervalMs,
    revalidateOnFocus: false,
  })
}
