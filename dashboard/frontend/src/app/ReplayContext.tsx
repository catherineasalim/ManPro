import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { localTimestamp } from "../lib/utils";
import type { Frame, ReplayMetadata } from "../types/api";

interface ReplayContextValue {
  metadata: ReplayMetadata | null;
  current: Frame | null;
  cursor: string | null;
  playing: boolean;
  speed: number;
  loading: boolean;
  error: string | null;
  setCursor: (value: string) => void;
  setPlaying: (value: boolean) => void;
  setSpeed: (value: number) => void;
}

const ReplayContext = createContext<ReplayContextValue | null>(null);

export function ReplayProvider({ children }: { children: ReactNode }) {
  const [metadata, setMetadata] = useState<ReplayMetadata | null>(null);
  const [cursor, setCursorState] = useState<string | null>(null);
  const [current, setCurrent] = useState<Frame | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.metadata().then((info) => {
      if (!alive) return;
      setMetadata(info);
      setCursorState(info.start);
      setLoading(false);
    }).catch((err: Error) => {
      if (alive) { setError(err.message); setLoading(false); }
    });
    return () => { alive = false; };
  }, []);

  const setCursor = useCallback((value: string) => setCursorState(value), []);

  useEffect(() => {
    if (!cursor || !metadata) return;
    let alive = true;
    api.frame(cursor).then((value) => { if (alive) setCurrent(value); }).catch((err: Error) => { if (alive) setError(err.message); });
    return () => { alive = false; };
  }, [cursor, metadata]);

  useEffect(() => {
    if (!playing || !cursor || !metadata) return;
    const timer = window.setInterval(() => {
      const next = new Date(new Date(cursor).getTime() + speed * 60_000);
      const max = new Date(metadata.end);
      if (next >= max) {
        setCursorState(metadata.start);
      } else {
        setCursorState(localTimestamp(next));
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [playing, cursor, metadata, speed]);

  const value = useMemo(() => ({ metadata, current, cursor, playing, speed, loading, error, setCursor, setPlaying, setSpeed }), [metadata, current, cursor, playing, speed, loading, error, setCursor]);
  return <ReplayContext.Provider value={value}>{children}</ReplayContext.Provider>;
}

export function useReplay() {
  const value = useContext(ReplayContext);
  if (!value) throw new Error("useReplay harus digunakan di dalam ReplayProvider.");
  return value;
}
