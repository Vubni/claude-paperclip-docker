import { useState } from "react";

export function LanguageSwitch({ disabled = false }: { disabled?: boolean }) {
  const russian = document.documentElement.lang === "ru";
  const [storageError, setStorageError] = useState(false);

  function changeLanguage() {
    try {
      localStorage.setItem("paperclip.workspace.language", russian ? "en" : "ru");
    } catch {
      setStorageError(true);
      return;
    }
    window.location.reload();
  }

  return (
    <div>
      <button
        type="button"
        lang={russian ? "en" : "ru"}
        aria-label={russian ? "Switch to English" : "Переключить на русский"}
        className="rounded-md px-2.5 py-1.5 text-sm font-medium hover:bg-accent"
        disabled={disabled}
        onClick={changeLanguage}
      >
        {russian ? "English" : "Русский"}
      </button>
      {storageError && <span role="alert">{russian
        ? "Разрешите сайту сохранять настройки языка."
        : "Allow this site to store your language preference."}</span>}
    </div>
  );
}
