FROM debian:bookworm-slim
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg locales git bash ripgrep nano libglib2.0-bin libasound2 \
      xvfb openbox x11-utils dbus-x11 gnome-keyring firefox-esr fonts-dejavu-core \
      x11vnc novnc websockify python3 \
    && curl -fsSLo /usr/share/keyrings/claude-desktop.asc https://downloads.claude.ai/claude-desktop/key.asc \
    && test "$(gpg --show-keys --with-colons /usr/share/keyrings/claude-desktop.asc | awk -F: '$1=="fpr"{print $10;exit}')" = 31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/claude-desktop.asc] https://downloads.claude.ai/claude-desktop/apt/stable stable main" > /etc/apt/sources.list.d/claude-desktop.list \
    && apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends claude-desktop \
    && localedef -i en_US -f UTF-8 en_US.UTF-8 \
    && useradd --create-home --shell /bin/bash developer \
    && install -d -o developer -g developer /home/developer/projects \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 LANGUAGE=en_US:en TZ=UTC DISPLAY=:1 \
    XDG_RUNTIME_DIR=/tmp/claude-runtime PATH=/home/developer/.local/bin:$PATH
USER developer
WORKDIR /home/developer/projects
COPY start-desktop /opt/workspace/start-desktop
COPY openbox.xml /opt/workspace/openbox.xml
COPY viewer.html /usr/share/novnc/workspace.html
CMD ["/opt/workspace/start-desktop"]
COPY ready /opt/workspace/ready
COPY mimeapps.list /etc/xdg/mimeapps.list
