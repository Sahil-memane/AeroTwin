import { api } from "@/services/apiClient";
import type { CopilotResponse } from "@/types";

export const copilotApi = {
  query: (message: string, engineId?: string) =>
    api.post<CopilotResponse>("/copilot/query", { message, engine_id: engineId }),
};
