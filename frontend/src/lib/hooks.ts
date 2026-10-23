import { useCallback, useEffect, useRef, useState } from "react";

// ---------- live updates over WebSocket ----------

type Listener = (msg: { type: string; rfq_id: number; reason: string }) => void;

const listeners = new Set<Listener>();
let socket: WebSocket | null = null;
let connected = false;
const connectionListeners = new Set<(c: boolean) => void>();

function setConnected(c: boolean) {
  connected = c;
  connectionListeners.forEach((l) => l(c));
}

function wsUrl(): string {
  const explicit = import.meta.env.VITE_WS_URL as string | undefined;
  if (explicit) return explicit;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

function ensureSocket(retryMs = 1000) {
  if (socket && socket.readyState <= WebSocket.OPEN) return;
  socket = new WebSocket(wsUrl());
  socket.onopen = () => {
    setConnected(true);
    retryMs = 1000;
  };
  socket.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      listeners.forEach((l) => l(msg));
    } catch {
      /* ignore malformed */
    }
  };
  socket.onclose = () => {
    setConnected(false);
    socket = null;
    // Reconnect with backoff; pages also poll, so a dropped socket only delays updates.
    setTimeout(() => ensureSocket(Math.min(retryMs * 2, 15000)), retryMs);
  };
}

/** Calls `onChange` whenever the server reports a change (optionally only for one RFQ). */
export function useLiveUpdates(onChange: (rfqId: number) => void, rfqId?: number) {
  const cb = useRef(onChange);
  cb.current = onChange;
  useEffect(() => {
    ensureSocket();
    const l: Listener = (msg) => {
      if (msg.type === "rfq_updated" && (rfqId === undefined || msg.rfq_id === rfqId)) cb.current(msg.rfq_id);
    };
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, [rfqId]);
}

export function useConnectionStatus(): boolean {
  const [c, setC] = useState(connected);
  useEffect(() => {
    ensureSocket();
    connectionListeners.add(setC);
    return () => {
      connectionListeners.delete(setC);
    };
  }, []);
  return c;
}

// ---------- server-synchronised clock ----------

let serverOffsetMs = 0; // serverTime - clientTime, learned from API responses

export function syncServerClock(serverIso: string) {
  serverOffsetMs = new Date(serverIso).getTime() - Date.now();
}

/** "Now" according to the server, re-rendering every `tickMs`. Countdowns use this, not the local clock. */
export function useNow(tickMs = 1000): number {
  const [now, setNow] = useState(() => Date.now() + serverOffsetMs);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() + serverOffsetMs), tickMs);
    return () => clearInterval(id);
  }, [tickMs]);
  return now;
}

// ---------- data loading ----------

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    try {
      const d = await fnRef.current();
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload };
}

/**
 * Re-run `fn` every `ms` while the tab is visible: a safety net behind the WebSocket. When the live
 * connection is down (e.g. a serverless host recycling it), poll every few seconds instead, so the
 * page still feels live.
 */
export function usePolling(fn: () => void, ms: number) {
  const cb = useRef(fn);
  cb.current = fn;
  const live = useConnectionStatus();
  const interval = live ? ms : Math.min(ms, 4000);
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "visible") cb.current();
    }, interval);
    return () => clearInterval(id);
  }, [interval]);
}
