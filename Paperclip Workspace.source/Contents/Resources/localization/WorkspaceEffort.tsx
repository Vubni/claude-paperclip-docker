import { useId, type CSSProperties, type ReactNode } from "react";
import "./workspace-effort.css";

const labels: Record<string, [string, string]> = {
  "": ["Авто", "Auto"], off: ["Выкл.", "Off"], minimal: ["Минимальное", "Minimal"],
  low: ["Низкое", "Low"], medium: ["Среднее", "Medium"], high: ["Высокое", "High"],
  xhigh: ["Очень высокое", "Extra high"], max: ["Максимальное", "Max"], ultra: ["Ультра", "Ultra"],
};

export function workspaceEffortLabel(value: string) {
  return labels[value]?.[document.documentElement.lang === "ru" ? 0 : 1] ?? value;
}

export function WorkspaceEffort({ choices, value, onChange, ariaLabel = "Thinking effort", leading, trailing, children }: {
  choices: readonly string[];
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
  leading?: ReactNode;
  trailing?: ReactNode;
  children?: ReactNode;
}) {
  const id = useId();
  const steps = ["", ...choices.filter(Boolean)];
  // A saved custom override stays visible and selectable until the user changes it.
  if (!steps.includes(value)) steps.push(value);
  const index = steps.indexOf(value);
  const label = workspaceEffortLabel(value);
  return <div className="workspace-effort">
    <div className="workspace-effort-heading">
      <div>{leading}</div>
      <label htmlFor={id} data-testid="selected-effort">{label}</label>
      <div>{trailing}</div>
    </div>
    {children}
    <div className="workspace-effort-control" style={{ "--progress": `${100 * index / Math.max(1, steps.length - 1)}%` } as CSSProperties}>
      <div className="workspace-effort-rail" aria-hidden="true">
        <div className="workspace-effort-stops">{steps.map(step => <i key={step} />)}</div>
      </div>
      <input id={id} type="range" min={0} max={steps.length - 1} step={1} value={index}
        disabled={steps.length < 2} aria-label={document.documentElement.lang === "ru" ? "Уровень рассуждения" : ariaLabel}
        aria-valuetext={label} onChange={event => onChange(steps[Number(event.currentTarget.value)]!)} />
    </div>
  </div>;
}
