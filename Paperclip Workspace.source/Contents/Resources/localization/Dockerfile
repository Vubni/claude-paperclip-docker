ARG BASE=ghcr.io/paperclipai/paperclip@sha256:bdf38d10544dc6c831e16dc027f23ad586353ef3be1a1b2c6979e63b956aceb1
FROM ${BASE} AS codex
ARG CODEX_CLI_VERSION=0.172.0
RUN npm install --global --omit=dev @openai/codex@${CODEX_CLI_VERSION} && npm cache clean --force

FROM codex AS catalog
WORKDIR /app
COPY build-codex-catalog.cjs codex-catalog.patch /tmp/
RUN node /tmp/build-codex-catalog.cjs packages/adapters/codex-local/src/workspace-catalog.ts \
    && git apply /tmp/codex-catalog.patch

FROM catalog AS server
RUN node server/scripts/bundle-runtime.mjs

FROM catalog AS ui
WORKDIR /app/ui
COPY workspace-ui.patch /tmp/workspace-ui.patch
RUN git apply /tmp/workspace-ui.patch
COPY task-language.patch /tmp/task-language.patch
RUN git apply /tmp/task-language.patch
COPY inbox-language.patch /tmp/inbox-language.patch
RUN git apply /tmp/inbox-language.patch
COPY workspaceTaskText.ts useWorkspaceStarter.ts src/lib/
COPY model-picker.patch /tmp/model-picker.patch
RUN git apply /tmp/model-picker.patch
COPY LanguageSwitch.tsx WorkspaceEffort.tsx workspace-effort.css src/components/
COPY useAuthCooldown.ts src/hooks/
COPY vite.workspace.config.ts ./
COPY localize.cjs static-copy.cjs ru.tsv ru-extra.json workspace-localization/
RUN node_modules/.bin/vite build --config vite.workspace.config.ts

FROM codex
COPY --from=catalog /app/packages/adapters/codex-local/src/ /app/packages/adapters/codex-local/src/
COPY --from=server /app/server/dist-runtime/ /app/server/dist-runtime/
COPY --from=ui /app/ui/dist/ /app/ui/dist/
