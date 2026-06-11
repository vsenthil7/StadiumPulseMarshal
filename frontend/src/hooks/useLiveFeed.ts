import { useEffect, useRef, useState } from 'react';

export interface LiveProblem {
  id: string;
  title: string;
  severity: string;
  phase: string | null;
}

export interface LiveFeed {
  connected: boolean;
  count: number;
  problems: LiveProblem[];
}

/**
 * Subscribes to the backend WebSocket problem feed. Reconnects on close.
 * Falls back silently (connected=false) if the socket cannot be opened.
 */
export function useLiveFeed(enabled = true): LiveFeed {
  const [feed, setFeed] = useState<LiveFeed>({
    connected: false,
    count: 0,
    problems: [],
  });
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let closed = false;

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const url = `${proto}://${window.location.host}/api/v1/stream`;
      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch {
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => setFeed((f) => ({ ...f, connected: true }));
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.type === 'problem_feed') {
            setFeed({
              connected: true,
              count: data.count,
              problems: data.problems ?? [],
            });
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        setFeed((f) => ({ ...f, connected: false }));
        if (!closed) {
          retryRef.current = setTimeout(connect, 3000);
        }
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      closed = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [enabled]);

  return feed;
}
