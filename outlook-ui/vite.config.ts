import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import * as devCerts from "office-addin-dev-certs";

// Outlook on the web loads the taskpane as an iframe to https://localhost:5173
// inside the browser, so the *browser* must trust the localhost cert.
// office-addin-dev-certs installs a trusted localhost CA (Chrome/Safari/Edge
// read it from the macOS keychain at startup), so the iframe and the ribbon
// icon load without a cert warning. A self-signed cert (basic-ssl) would be
// blocked inside the iframe.
export default defineConfig(async ({ command }) => {
  // Only the dev server needs HTTPS; `vite build` must not touch certificates.
  const https =
    command === "serve"
      ? await devCerts
          .getHttpsServerOptions()
          .then(({ cert, key, ca }) => ({ cert, key, ca }))
      : undefined;

  return {
    plugins: [react()],
    server: {
      // Dual-stack so `localhost` reaches it on both 127.0.0.1 and ::1.
      host: "::",
      port: 5173,
      strictPort: true,
      https,
    },
  };
});
