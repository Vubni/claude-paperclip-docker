# Claude и Paperclip в Docker

Запускайте графический Claude Desktop и Paperclip на своём компьютере. Claude работает внутри Linux-контейнера. Paperclip хранит задачи и базу локально и видит ту же папку проектов. Для внешних ссылок есть отдельный Firefox. После установки приложения открываются из системного меню.

[English quick start](docs/quickstart.en.md) · [Настройки региона](docs/region.md) · [Устройство и обновление](docs/maintenance.md)

| Система | Что установить | Как открываются окна |
| --- | --- | --- |
| macOS 14+, Apple Silicon | Docker Desktop, Xcode Command Line Tools | Приложения в «Программах» |
| Ubuntu Desktop 24.04, amd64 или arm64 | Docker Engine или Docker Desktop, Compose v2, Qt WebEngine | Меню приложений Linux |
| Windows 11 | Docker Desktop с Linux-контейнерами, Ubuntu 24.04 в WSL 2, WSLg | Меню «Пуск» или команда в Ubuntu |

Понадобится рабочая сессия Docker с ресурсами для выбранных сервисов. У Claude и Paperclip лимиты по 1,5 CPU и 6 ГиБ, у отдельного Firefox — 1 CPU и 4 ГиБ. Аккаунт Claude и подключение платных провайдеров пользователь настраивает сам. Первая сборка скачивает пакеты и образы и может занять несколько минут.

## Начало работы

**macOS.** Запустите Docker Desktop. Если инструменты командной строки ещё не установлены, выполните `xcode-select --install` и дождитесь установки.

```sh
git clone https://github.com/Vubni/claude-paperclip-docker.git
cd claude-paperclip-docker
./Install.command
```

**Ubuntu и Windows.** На Windows сначала установите Ubuntu (`wsl --install -d Ubuntu-24.04` в PowerShell), запустите Docker Desktop и включите интеграцию Ubuntu в **Settings → Resources → WSL Integration**. Следующие команды выполните в терминале Ubuntu. На обычном Linux сначала установите Docker с плагином Compose и убедитесь, что `docker info` работает от вашего пользователя. [Docker для Ubuntu](https://docs.docker.com/engine/install/ubuntu/) · [Docker в WSL 2](https://docs.docker.com/desktop/features/wsl/) · [Графические приложения WSL](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)

```sh
sudo apt update
sudo apt install git curl openssl tzdata libdigest-sha-perl python3-pyqt6.qtwebengine
git clone https://github.com/Vubni/claude-paperclip-docker.git
cd claude-paperclip-docker
./linux/install.sh
```

Оставьте каталог на месте: ярлыки Linux и Windows используют файлы из него. Если ярлык ещё не появился, из этого каталога выполните `/usr/bin/python3 linux/viewer.py paperclip` или `/usr/bin/python3 linux/viewer.py claude`.

## Первый запуск

1. Откройте **Paperclip Workspace**. Когда сервер ответит на `/api/health`, появится локальная форма входа. На новой установке создайте пользователя Paperclip.
2. Откройте **Claude Workspace**, подтвердите вход и авторизуйтесь в окне Linux. Для совместной работы выберите каталог `/home/developer/projects`.
3. Подтверждённые внешние HTTPS-ссылки из Paperclip открываются в **Paperclip Browser**. У Firefox отдельная временная сессия.

Закрытие окна оставляет сервис в Docker. Для остановки используйте Docker Desktop или `docker stop` с именем нужного контейнера. Образы и подписки Claude и сторонних провайдеров проект не распространяет. Сборка получает клиент из подписанного APT-репозитория Anthropic, а Paperclip — из закреплённого образа upstream.

## Данные и сеть

| Что хранится | Где |
| --- | --- |
| Профиль Claude и проекты Linux | Том `claude-english_home` |
| Данные Paperclip | Том `paperclip-workspace_data`; из тома Claude доступен только подкаталог `projects` |
| Секреты локального сервера | macOS — Application Support/Paperclip Workspace; Linux и WSL — `~/.local/state/claude-paperclip-workspace/paperclip` по умолчанию |
| Интерфейс Paperclip | `http://localhost:43107`, порт опубликован только на loopback |

При запуске проверяется страна выхода хоста и Docker. В WSL дополнительно проверяется Windows. RU, неопределённые и неоднозначные ответы блокируют запуск. В обычном режиме открытая сессия может сменить маршрут после обрыва VPN. Строгий профиль закрепляет страну и IPv4 выделенного HTTPS-прокси, ограничивает домены и закрывает соединения при потере подтверждения. [Настройка строгого профиля](docs/region.md)

## Обновление и частые проблемы

- **Обновить.** Выполните `git pull --ff-only` и повторите установщик своей платформы. Существующие тома и серверные секреты сохраняются. Удаление томов или `docker compose down -v` может уничтожить данные.
- **Docker недоступен.** Проверьте `docker info` и `docker compose version`. В WSL используйте локальный Linux-движок и включите интеграцию нужного дистрибутива. Для публикации loopback-портов используйте актуальный Docker Engine.
- **Запуск заблокирован проверкой региона.** Проверьте VPN, доступность Cloudflare и выбранный профиль. При смене профиля сначала остановите рабочие пространства и шлюзы.
- **Нет окна в Windows.** Запустите `wsl --update` в PowerShell и проверьте, что Ubuntu использует WSL 2. Лаунчер требует графическую сессию WSLg.
- **Что проверялось.** Модульные тесты и Docker-тест изоляции описаны в [руководстве по проверке](docs/region.md#проверка). Окно Qt проверено в Ubuntu 24.04 с виртуальным дисплеем. Полный запуск на физической Windows и вход с личным аккаунтом в эти тесты не входили.

## Лицензия

Собственный код лаунчеров, сценарии и документация доступны по [MIT](LICENSE). Для Claude Desktop, upstream-кода, товарных знаков и сторонних материалов действуют условия их владельцев. [Paperclip](https://github.com/paperclipai/paperclip) · [Лицензия Paperclip](notices/Paperclip-MIT.txt) · [Лицензия профиля Moby](Claude%20Workspace.source/Contents/Resources/desktop-seccomp.LICENSE)
