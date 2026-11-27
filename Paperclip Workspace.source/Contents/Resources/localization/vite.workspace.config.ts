import { defineConfig, mergeConfig } from "vite";
import baseConfig from "./vite.config";
import workspaceLabels from "./workspace-localization/localize.cjs";

import staticCopy from "./workspace-localization/static-copy.cjs";

export default defineConfig(env => mergeConfig(baseConfig(env), {
  plugins: [staticCopy(), workspaceLabels()],
}));
