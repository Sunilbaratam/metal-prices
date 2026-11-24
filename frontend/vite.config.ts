import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" lets the built site work under any path, e.g. https://user.github.io/repo-name/
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5173 },
});
