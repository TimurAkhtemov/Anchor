import { defineConfig } from "@playwright/test";

// The webServer only serves — it does not build. Run `npm run build` first
// so out/ exists (next start cannot serve an output:'export' app).
export default defineConfig({
  testDir: "./tests",
  forbidOnly: !!process.env.CI,
  use: { baseURL: "http://127.0.0.1:4173" },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: {
    command: "npx serve out -l 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
  },
});
