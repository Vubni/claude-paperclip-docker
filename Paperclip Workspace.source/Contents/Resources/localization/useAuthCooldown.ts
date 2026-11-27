import { useEffect, useState } from "react";

type Mode = "sign_in" | "sign_up";

function readDeadline(mode: Mode) {
  try {
    const value = Number(sessionStorage.getItem("paperclip.auth.retry." + mode));
    return Number.isFinite(value) ? value : 0;
  } catch {
    return 0;
  }
}

export function useAuthCooldown(mode: Mode) {
  const [deadlines, setDeadlines] = useState(() => ({
    sign_in: readDeadline("sign_in"),
    sign_up: readDeadline("sign_up"),
  }));
  const [now, setNow] = useState(Date.now);
  const secondsLeft = Math.max(0, Math.ceil((deadlines[mode] - now) / 1000));
  const waiting = secondsLeft > 0;

  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [waiting]);

  function startCooldown(duration: number) {
    const start = Date.now();
    const until = start + duration;
    setNow(start);
    setDeadlines(previous => ({ ...previous, [mode]: until }));
    try {
      sessionStorage.setItem("paperclip.auth.retry." + mode, String(until));
    } catch {
      // The current form still observes the deadline if storage is unavailable.
    }
  }

  return { secondsLeft, startCooldown };
}
