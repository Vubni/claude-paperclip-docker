ARG DESKTOP_BASE
FROM ${DESKTOP_BASE}
COPY firefox.json /usr/lib/firefox-esr/distribution/policies.json
COPY claude-desktop /opt/region/bin/claude-desktop
ENV PATH="/opt/region/bin:${PATH}"
RUN test -x /usr/bin/claude-desktop
