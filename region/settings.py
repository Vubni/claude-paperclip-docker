"""Edit regional settings from the macOS app menu. User input never enters AppleScript source."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
from profile import COUNTRIES, PROFILE, settings
from locked import profile_lock

HERE = Path(__file__).resolve().parent
SCRIPT = """
on run argv
    set operation to item 1 of argv
    set promptText to item 2 of argv
    if operation is "list" then
        set selection to choose from list (items 3 thru -1 of argv) with prompt promptText
        if selection is false then error number -128
        return item 1 of selection
    else if operation is "text" then
        return text returned of (display dialog promptText default answer (item 3 of argv) with title "Регион рабочих пространств")
    else
        display dialog promptText buttons {"OK"} default button "OK" with title "Регион рабочих пространств"
    end if
end run
"""


def dialog(kind, prompt, *values):
    response = subprocess.run(["/usr/bin/osascript", "-", kind, prompt, *values], input=SCRIPT,
                              capture_output=True, text=True)
    if response.returncode:
        raise SystemExit(0)
    return response.stdout.strip()


def workspaces_running():
    docker = ["/Applications/Docker.app/Contents/Resources/bin/docker", "--context", "desktop-linux"]
    for project in ("claude-english", "paperclip-workspace", "paperclip-browser"):
        result = subprocess.run(docker + ["ps", "-q", "--filter", "label=com.docker.compose.project=" + project],
                                capture_output=True, timeout=8)
        if result.returncode:
            status = subprocess.run(docker + ["desktop", "status", "--format", "json"],
                                    capture_output=True, timeout=8)
            if not status.returncode and json.loads(status.stdout).get("Status") == "stopped":
                return False
            raise OSError("Docker status unavailable")
        if result.stdout.strip():
            return True
    return False


def activate(source, destination):
    with profile_lock() as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            dialog("notice", "Сейчас запускается рабочее пространство или открыт его Linux shell. Повторите смену режима после завершения.")
            return
        if workspaces_running():
            dialog("notice", "Профиль не изменён. Сначала остановите контейнеры Claude Workspace, Paperclip Workspace и Paperclip Browser в Docker Desktop.")
            return
        os.replace(source, destination)


def editor():
    mode = dialog("list", "Настройки общие для Claude, Paperclip и браузера.",
                  "Настроить строгий режим", "Открыть папку настроек", "Вернуть обычный режим")
    PROFILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if mode == "Открыть папку настроек":
        subprocess.run(["/usr/bin/open", str(PROFILE.parent)], check=True)
        return
    if mode == "Вернуть обычный режим":
        if not PROFILE.exists() and not PROFILE.is_symlink():
            dialog("notice", "Уже используется обычный режим.")
            return
        if dialog("list", "Завершите контейнеры этих рабочих пространств перед сменой режима. Профиль сохранится рядом как region.disabled.json.", "Отмена", "Отключить профиль") == "Отключить профиль":
            activate(PROFILE, PROFILE.with_name("region.disabled.json"))
        return
    try:
        prior = settings() or {}
    except (ValueError, TypeError, OSError):
        prior = {}
    countries = {}
    for line in Path("/usr/share/zoneinfo/iso3166.tab").read_text().splitlines():
        if line and not line.startswith("#"):
            code, label = line.split(None, 1)
            if code in COUNTRIES:
                countries[f"{code} — {label}"] = code
    country = countries[dialog("list", "Страна выхода VPN на Mac и выделенного HTTPS-прокси", *sorted(countries))]
    zones = [line.split()[2] for line in Path("/usr/share/zoneinfo/zone.tab").read_text().splitlines()
             if line.startswith(country + "\t")]
    if not zones:
        raise ValueError()
    timezone = zones[0] if len(zones) == 1 else dialog("list", "Часовой пояс Linux", *zones)
    data = {"country": country, "timezone": timezone}
    for key, label, default in (
        ("proxy_host", "Имя фиксированного HTTPS-прокси из его TLS-сертификата", ""),
        ("proxy_ipv4", "Публичный IPv4 самого HTTPS-прокси", ""),
        ("proxy_port", "Порт HTTPS-прокси", "443"),
        ("exit_ipv4", "Постоянный публичный IPv4 выхода этого прокси", ""),
    ):
        value = dialog("text", label, str(prior.get(key, default)))
        data[key] = int(value) if key == "proxy_port" else value
    defaults = ["claude.ai", "*.claude.ai", "anthropic.com", "*.anthropic.com"]
    data["allow_hosts"] = dialog("text", "Разрешённые HTTPS-домены через пробел", " ".join(prior.get("allow_hosts", defaults))).split()
    with tempfile.NamedTemporaryFile(mode="w", dir=PROFILE.parent, delete=False) as f:
        json.dump(data, f, ensure_ascii=True, indent=2)
        f.write("\n")
    candidate = Path(f.name)
    try:
        settings(candidate)
        if dialog("list", "Перед применением остановите три рабочих пространства и их прежние шлюзы в Docker Desktop. Тома и входы сохраняются. Применить профиль при следующем запуске?", "Отмена", "Сохранить") == "Сохранить":
            activate(candidate, PROFILE)
    finally:
        candidate.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        editor()
    except (ValueError, TypeError, OSError, subprocess.SubprocessError):
        dialog("notice", "Не удалось сохранить настройки. Проверьте страну, часовой пояс, адреса и список доменов.")
