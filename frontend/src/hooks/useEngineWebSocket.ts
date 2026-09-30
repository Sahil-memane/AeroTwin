import { useEffect, useRef } from "react";
import { useAuthStore } from "@/store/authStore";
import { useTelemetryStore } from "@/store/telemetryStore";
import type { LiveMessage } from "@/types";

const WS_URL = import.meta.env.VITE_WS_URL;

/**
 * Opens the live WebSocket for one engine (`/engines/{id}/live`) and
 * routes every message into the shared telemetry store by its `type`,
 * per the ML spec doc's store-keyed-by-message-type design. Reconnects
 * with backoff on drop; closes cleanly on unmount or engine change.
 */
export function useEngineWebSocket(engineId: string | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const store = useTelemetryStore();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedIntentionally = useRef(false);

  useEffect(() => {
    if (!engineId || !accessToken) return;
    closedIntentionally.current = false;

    let attempt = 0;

    function connect() {
      if (!engineId || !accessToken) return;
      const ws = new WebSocket(`${WS_URL}/engines/${engineId}/live?token=${accessToken}`);
      wsRef.current = ws;

      ws.onopen = () => {
        attempt = 0;
      };

      ws.onmessage = (event) => {
        let msg: LiveMessage;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return;
        }
        switch (msg.type) {
          case "telemetry":
            store.setTelemetry(engineId, msg.payload as never);
            break;
          case "rul_prediction":
            store.setRul(engineId, msg.payload as never);
            break;
          case "fault_prediction":
            store.setFault(engineId, msg.payload as never);
            break;
          case "bearing_prediction":
            store.setBearing(engineId, msg.payload as never);
            break;
          case "aux_prediction":
            store.setAux(engineId, msg.payload as never);
            break;
          case "health_score":
            store.setHealthScore(engineId, msg.payload as never);
            break;
          case "physics_consistency": {
            const p = msg.payload as { parameters: never[] };
            store.setPhysicsConsistency(engineId, p.parameters);
            break;
          }
          case "alert": {
            const p = msg.payload as Record<string, unknown>;
            store.pushLiveAlert({
              id: p.id as string,
              engine_id: p.engine_id as string,
              source: p.source as string,
              severity: p.severity as "warning" | "critical",
              message: p.message as string,
              created_at: p.created_at as string,
              is_acknowledged: false,
              acknowledged_by: null,
              acknowledged_at: null,
            });
            break;
          }
        }
      };

      ws.onclose = () => {
        if (closedIntentionally.current) return;
        attempt += 1;
        const delay = Math.min(1000 * 2 ** attempt, 15000);
        reconnectTimer.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      closedIntentionally.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engineId, accessToken]);
}
