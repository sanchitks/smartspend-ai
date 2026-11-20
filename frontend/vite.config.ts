import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { copyFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, loadEnv, type Plugin } from "vite";

/** Production-only Content-Security-Policy (the dev server needs inline scripts for hot reload). */
function securityPolicy(apiUrl: string): Plugin {
  const api = new URL(apiUrl).origin;
  const csp = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'", // charts and progress bars set inline sizes
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src 'self' ${api}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");
  return {
    name: "smartspend-security-policy",
    apply: "build",
    transformIndexHtml: (html) =>
      html.replace(
        "<head>",
        `<head>\n    <meta http-equiv="Content-Security-Policy" content="${csp}" />\n    <meta name="referrer" content="no-referrer" />`,
      ),
  };
}

/** GitHub Pages serves 404.html for unknown paths, so a copy of index.html makes deep links work. */
function spaFallback(): Plugin {
  return {
    name: "smartspend-spa-fallback",
    apply: "build",
    closeBundle() {
      const out = resolve(process.cwd(), "dist");
      copyFileSync(resolve(out, "index.html"), resolve(out, "404.html"));
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    base: env.VITE_BASE || "/",
    plugins: [react(), tailwindcss(), securityPolicy(env.VITE_API_URL || "http://localhost:8000"), spaFallback()],
    server: { port: 5173, strictPort: true },
    preview: { port: 4173 },
  };
});
