import react from "@vitejs/plugin-react";
import { defineConfig, splitVendorChunkPlugin } from "vite";
import svgr from "vite-plugin-svgr";
import { visualizer } from "rollup-plugin-visualizer";
import tsconfigPaths from "vite-tsconfig-paths";

// https://vitejs.dev/config/
export default defineConfig({
  define: {
    // Locale JSONs are fetched from a fixed URL, unlike the hashed JS
    // bundles, so browsers keep serving a stale copy after an update.
    // Appended to their URL to force a fresh fetch once per build.
    __BUILD_ID__: JSON.stringify(Date.now().toString(36)),
  },
  plugins: [
    tsconfigPaths(),
    react({
      include: "**/*.tsx",
    }),
    svgr(),
    visualizer(),
    splitVendorChunkPlugin(),
  ],
});
