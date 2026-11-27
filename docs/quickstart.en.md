# Claude and Paperclip in Docker

Run the Linux Claude Desktop client and a local Paperclip server with a shared projects folder. A separate Firefox container handles confirmed external links. The host displays the windows. Bring your own Claude account and any provider credentials you choose to use.

## Install

| Platform | Prerequisites | Installer |
| --- | --- | --- |
| macOS 14+ on Apple Silicon | Running Docker Desktop and Xcode Command Line Tools | `./Install.command` |
| Ubuntu Desktop 24.04 on amd64 or arm64 | Local Docker Engine with Compose v2, or Docker Desktop, and Qt WebEngine | `./linux/install.sh` |
| Windows 11 | Docker Desktop running Linux containers, Ubuntu 24.04 in WSL 2, WSLg and Docker's Ubuntu integration | Run the Ubuntu installer **inside Ubuntu** |

On Windows, install the distribution with `wsl --install -d Ubuntu-24.04` in PowerShell. Enable the distribution in Docker Desktop under **Settings → Resources → WSL Integration**. [Docker WSL setup](https://docs.docker.com/desktop/features/wsl/)

On Ubuntu or WSL, install the launcher dependencies first.

```sh
sudo apt update
sudo apt install git curl openssl tzdata libdigest-sha-perl python3-pyqt6.qtwebengine
```

Clone the repository and run the installer from the table as your normal desktop user.

```sh
git clone https://github.com/Vubni/claude-paperclip-docker.git
cd claude-paperclip-docker
```

Open **Paperclip Workspace** from Applications or Start and create a local Paperclip account. Open **Claude Workspace** to sign in inside Linux. Both apps can access `/home/developer/projects`. Keep the checkout in place for Linux and WSL shortcuts. To launch directly there, run `/usr/bin/python3 linux/viewer.py paperclip` or replace `paperclip` with `claude`.

## Operation

Paperclip listens on loopback port 43107. Data lives in Docker volumes `claude-english_home` and `paperclip-workspace_data`. Closing a viewer keeps the service running. Stop individual containers in Docker. To upgrade, run `git pull --ff-only` and repeat the installer. Keep the volumes and the local server secrets.

Launchers check the host and Docker exit country and block RU and unknown results. WSL checks the Windows route as well. The default mode checks at startup. An optional strict profile requires a fixed HTTPS CONNECT proxy, pins its exit address and filters destinations while running. Linux and WSL read `~/.config/claude-paperclip-workspace/region.json` by default. [Profile example](../region/region.example.json) · [Region guide in Russian](region.md)

The Qt viewer was exercised under Ubuntu 24.04 with a virtual display. A physical Windows desktop, real account sign-in and paid provider calls were outside that test. The launcher downloads upstream software during setup. Upstream terms apply independently.

The original launcher code and documentation use the [MIT License](../LICENSE). Third-party software, marks and assets retain their own terms.
