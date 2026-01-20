import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../utils/api";

interface StatusResponse {
  last_refreshed: string | null;
}

async function fetchStatus(): Promise<StatusResponse> {
  const response = await apiFetch("/api/status");
  if (!response.ok) {
    throw new Error("Failed to load status");
  }
  return response.json();
}

async function triggerRefresh(): Promise<void> {
  const response = await apiFetch("/api/tasks/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  if (!response.ok) {
    throw new Error("Refresh request failed");
  }
}

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: fetchStatus,
    staleTime: 1000 * 60
  });
}

export function useRefresh() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: triggerRefresh,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["status"] });
      await queryClient.invalidateQueries({ queryKey: ["symbols"] });
      await queryClient.invalidateQueries({ queryKey: ["candles"] });
    },
    onError: (error) => {
      console.error("Manual refresh failed", error);
    }
  });
}
