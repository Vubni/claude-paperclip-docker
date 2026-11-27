FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates curl git locales nano ripgrep \
    && localedef -i en_US -f UTF-8 en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash developer \
    && install -d -o developer -g developer /home/developer/projects
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 LANGUAGE=en_US:en PATH=/home/developer/.local/bin:$PATH
USER developer
WORKDIR /home/developer/projects
CMD ["bash"]
