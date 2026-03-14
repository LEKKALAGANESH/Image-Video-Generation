/* ─────────────────────────────────────────────
 * AuraGen — WebSocket Hook
 * Connects to the backend WS endpoint with
 * auto-reconnect, circuit breaker, exponential
 * backoff, and a client-side keepalive ping.
 * ───────────────────────────────────────────── */

"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { WebSocketMessage } from "@/types";

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

/** Keepalive ping interval — must be shorter than server's 600 s timeout. */
const PING_INTERVAL_MS = 25_000;

/** Maximum backoff delay between reconnect attempts. */
const MAX_BACKOFF_MS = 30_000;

/** Base delay for the first reconnect attempt. */
const BASE_DELAY_MS = 1_000;

/** Circuit breaker: if this many failures occur within CIRCUIT_WINDOW_MS,
 *  enter cooldown for CIRCUIT_COOLDOWN_MS before retrying. */
const CIRCUIT_MAX_FAILURES = 3;
const CIRCUIT_WINDOW_MS = 5_000;
const CIRCUIT_COOLDOWN_MS = 30_000;

function generateClientId(): string {
  return `auragen-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export type ConnectionStatus = "disconnected" | "connecting" | "connected";

interface UseWebSocketReturn {
  isConnected: boolean;
  status: ConnectionStatus;
  lastMessage: WebSocketMessage | null;
  sendMessage: (data: unknown) => void;
  reconnect: () => void;
  clientId: string;
}

export function useWebSocket(): UseWebSocketReturn {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const clientIdRef = useRef<string>(generateClientId());
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  // Circuit breaker state — tracks timestamps of recent failures
  const failureTimestampsRef = useRef<number[]>([]);

  /** Stop the keepalive ping interval. */
  const stopPing = useCallback(() => {
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  /** Start the keepalive ping interval. */
  const startPing = useCallback(() => {
    stopPing();
    pingTimerRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, PING_INTERVAL_MS);
  }, [stopPing]);

  /** Record a failure and return the delay to use before the next attempt.
   *  If the circuit breaker trips (3+ failures in 5s), returns cooldown. */
  const getReconnectDelay = useCallback((): number => {
    const now = Date.now();
    failureTimestampsRef.current.push(now);

    // Prune failures older than the window
    failureTimestampsRef.current = failureTimestampsRef.current.filter(
      (ts) => now - ts < CIRCUIT_WINDOW_MS
    );

    // Circuit breaker: too many rapid failures → long cooldown
    if (failureTimestampsRef.current.length >= CIRCUIT_MAX_FAILURES) {
      console.warn(
        `[AuraGen WS] Circuit breaker tripped: ${failureTimestampsRef.current.length} failures in ${CIRCUIT_WINDOW_MS}ms — cooling down ${CIRCUIT_COOLDOWN_MS / 1000}s`
      );
      // Clear the window so the cooldown only fires once
      failureTimestampsRef.current = [];
      reconnectAttemptRef.current = 0;
      return CIRCUIT_COOLDOWN_MS;
    }

    // Normal exponential backoff: 1s, 2s, 4s, 8s… capped at 30s
    const delay = Math.min(
      BASE_DELAY_MS * Math.pow(2, reconnectAttemptRef.current),
      MAX_BACKOFF_MS,
    );
    reconnectAttemptRef.current += 1;
    return delay;
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // Clean up any existing connection
    stopPing();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setStatus("connecting");
    const url = `${WS_BASE}/${clientIdRef.current}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setStatus("connected");
        reconnectAttemptRef.current = 0;
        // Clear circuit breaker on successful connection
        failureTimestampsRef.current = [];
        startPing();
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const data = JSON.parse(event.data);
          // Silently consume server pings — reply with pong
          if (data.type === "ping") {
            ws.send(JSON.stringify({ type: "pong" }));
            return;
          }
          // Silently consume pong responses
          if (data.type === "pong") return;
          setLastMessage(data as WebSocketMessage);
        } catch {
          console.warn("[AuraGen WS] Failed to parse message:", event.data);
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setStatus("disconnected");
        wsRef.current = null;
        stopPing();

        const delay = getReconnectDelay();

        reconnectTimerRef.current = setTimeout(() => {
          if (mountedRef.current) connect();
        }, delay);
      };

      ws.onerror = () => {
        // onclose will fire after this, triggering reconnect
        ws.close();
      };
    } catch {
      // Connection failed entirely — schedule retry
      const delay = getReconnectDelay();
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, delay);
    }
  }, [startPing, stopPing, getReconnectDelay]);

  /** Manual reconnect — resets the backoff counter and circuit breaker. */
  const reconnect = useCallback(() => {
    reconnectAttemptRef.current = 0;
    failureTimestampsRef.current = [];
    connect();
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      stopPing();
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, stopPing]);

  const sendMessage = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      console.warn("[AuraGen WS] Cannot send — not connected");
    }
  }, []);

  return {
    isConnected: status === "connected",
    status,
    lastMessage,
    sendMessage,
    reconnect,
    clientId: clientIdRef.current,
  };
}
