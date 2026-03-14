/* ─────────────────────────────────────────────
 * AuraGen — SSE (Server-Sent Events) Hook
 * Connects to the backend SSE endpoint with
 * browser-native EventSource API and automatic
 * reconnection.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export type ConnectionStatus = "connected" | "connecting" | "disconnected";

interface SSEMessage {
  type: string;
  [key: string]: unknown;
}

interface UseSSEOptions {
  /** Base URL for SSE endpoint. Default: derived from NEXT_PUBLIC_API_URL or http://localhost:8000 */
  baseUrl?: string;
  /** Called for every SSE message */
  onMessage?: (message: SSEMessage) => void;
}

interface UseSSEReturn {
  status: ConnectionStatus;
  lastMessage: SSEMessage | null;
  reconnect: () => void;
}

function generateClientId(): string {
  return `auragen-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useSSE(options: UseSSEOptions = {}): UseSSEReturn {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [lastMessage, setLastMessage] = useState<SSEMessage | null>(null);
  const sourceRef = useRef<EventSource | null>(null);
  const clientIdRef = useRef<string>(generateClientId());
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    // Close existing connection
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }

    const base = options.baseUrl
      ?? process.env.NEXT_PUBLIC_API_URL
      ?? "http://localhost:8000";
    const url = `${base}/api/events/${clientIdRef.current}`;

    if (!mountedRef.current) return;
    setStatus("connecting");

    const source = new EventSource(url);
    sourceRef.current = source;

    source.onopen = () => {
      if (!mountedRef.current) return;
      console.log("[SSE] Connected");
      setStatus("connected");
    };

    source.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const data: SSEMessage = JSON.parse(event.data);
        if (data.type === "progress" || data.type === "complete" || data.type === "error") {
          const d = data.data as Record<string, unknown> | undefined;
          console.log(`[SSE] ${data.type} | job=${String(data.job_id ?? "?").slice(0, 8)}… | progress=${d?.progress ?? "—"}%`);
        }
        setLastMessage(data);
        options.onMessage?.(data);
      } catch {
        console.warn("[SSE] Failed to parse message:", event.data);
      }
    };

    source.onerror = () => {
      if (!mountedRef.current) return;
      // EventSource automatically reconnects — we just update status
      // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
      if (source.readyState === EventSource.CLOSED) {
        console.log("[SSE] Connection closed");
        setStatus("disconnected");
      } else {
        // readyState === CONNECTING means browser is auto-reconnecting
        console.log("[SSE] Reconnecting...");
        setStatus("connecting");
      }
    };
  }, [options.baseUrl]);

  const reconnect = useCallback(() => {
    console.log("[SSE] Manual reconnect");
    clientIdRef.current = generateClientId();
    connect();
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };
  }, [connect]);

  return { status, lastMessage, reconnect };
}
