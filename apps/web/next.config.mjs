import path from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  turbopack: { root: path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..") },
  async redirects() {
    return process.env.MANGA_FRONTEND_ONLY === "1"
      ? [{ source: "/", destination: "/browse", permanent: false }]
      : [];
  },
};

export default nextConfig;
