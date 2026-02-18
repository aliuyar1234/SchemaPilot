import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const controlPlaneTarget = env.VITE_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";
  const gatewayTarget = env.VITE_GATEWAY_URL ?? "http://127.0.0.1:8001";
  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api/v1/gateway": {
          target: gatewayTarget,
          changeOrigin: true
        },
        "/api/v1": {
          target: controlPlaneTarget,
          changeOrigin: true
        }
      }
    }
  };
});
