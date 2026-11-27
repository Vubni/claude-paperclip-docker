import { ONBOARDING_FIRST_TASK_ORIGIN_KIND, type IssueThreadInteraction } from "@paperclipai/shared";

export function workspaceRussian() {
  return document.documentElement.lang === "ru";
}

export function taskDisplayTitle(task: { title: string; originKind?: string | null }) {
  return workspaceRussian() && task.originKind === ONBOARDING_FIRST_TASK_ORIGIN_KIND && task.title === "Paperclip onboarding"
    ? "Знакомство с Paperclip" : task.title;
}

export function greetingText(body: string) {
  const match = /^Welcome to Paperclip! I'm (?:(.+), )?your first agent teammate\. Pick how you'd like to start and I'll take it from there\.$/s.exec(body);
  if (!match) return body;
  const introduction = match[1] ? `Я ${match[1]}, ваш первый ИИ-помощник.` : "Я ваш первый ИИ-помощник.";
  return `Добро пожаловать в Paperclip! ${introduction} Выберите, с чего начнём, и я помогу со следующим шагом.`;
}

const openingText = new Map([
  ["What would you like to do?", "С чего хотите начать?"],
  ["Interview me and propose a plan and an agent team to execute it.", "Задай мне вопросы и предложи план и команду агентов"],
  ["A few questions about what you're building, then a short plan and the team to carry it out, for you to approve.", "Я спрошу, над чем вы работаете, а затем предложу на утверждение краткий план и команду для его выполнения."],
  ["I have a task in mind", "У меня уже есть задача"],
  ["Describe it and I'll propose how to get it done.", "Опишите задачу, и я предложу, как её выполнить."],
  ["Continue", "Продолжить"],
  ["Questions", "Вопросы"],
]);

function text<T extends string | null | undefined>(value: T): T | string {
  return value ? openingText.get(value) ?? value : value;
}

// These copies are for the question card. Its answer IDs stay identical in both languages.
export function openingInteraction(item: IssueThreadInteraction): IssueThreadInteraction {
  if (item.kind !== "ask_user_questions" || !item.payload.questions.some(q => q.id === "first-task-opening")) return item;
  const set = item.payload.questionSet;
  return {
    ...item,
    title: text(item.title),
    payload: {
      ...item.payload,
      submitLabel: text(item.payload.submitLabel),
      questions: item.payload.questions.map(q => q.id !== "first-task-opening" ? q : ({
        ...q, prompt: text(q.prompt),
        options: q.options.map(o => ({ ...o, label: text(o.label), description: text(o.description) })),
      })),
      ...(set ? { questionSet: {
        ...set, title: text(set.title), submitLabel: text(set.submitLabel),
        questions: set.questions.map(q => q.id !== "first-task-opening" ? q : ({
          ...q, prompt: text(q.prompt),
          ...(q.options && { options: q.options.map(o => ({ ...o, label: text(o.label), description: text(o.description) })) }),
          ...(q.customAnswer && { customAnswer: { ...q.customAnswer, label: text(q.customAnswer.label), placeholder: text(q.customAnswer.placeholder) } }),
        })),
      } } : {}),
    },
  };
}

const relative = new Intl.RelativeTimeFormat("ru", { numeric: "always" });
export function russianRelativeTime(value: Date | string, clock = Date.now()) {
  const seconds = Math.max(0, (clock - new Date(value).getTime()) / 1000);
  if (!Number.isFinite(seconds)) return "—";
  if (seconds < 60) return "Только что";
  if (seconds < 3600) return relative.format(-Math.floor(seconds / 60), "minute");
  if (seconds < 86400) return relative.format(-Math.floor(seconds / 3600), "hour");
  if (seconds < 604800) return relative.format(-Math.floor(seconds / 86400), "day");
  return new Date(value).toLocaleDateString("ru", { day: "numeric", month: "short", year: "numeric" });
}
