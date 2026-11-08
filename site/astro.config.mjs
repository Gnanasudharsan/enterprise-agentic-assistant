import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://helio-case-study.vercel.app",
  build: { inlineStylesheets: "auto" },
  compressHTML: true,
});
