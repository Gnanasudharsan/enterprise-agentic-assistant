import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://gnanasudharsan.vercel.app",
  build: { inlineStylesheets: "auto" },
  compressHTML: true,
});
