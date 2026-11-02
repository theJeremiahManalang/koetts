import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.dirname(fileURLToPath(import.meta.url));
// The deployment stage contains only this app; local builds retain workspace roots.
const buildRoot = process.env.MANGA_STANDALONE_WEB === "1"
  ? appRoot
  : path.resolve(appRoot, "../..");

/** @type {import('next').NextConfig} */
const nextConfig = {
  turbopack: { root: buildRoot },
  outputFileTracingRoot: buildRoot,
  async redirects() {
    return process.env.MANGA_FRONTEND_ONLY === "1"
      ? [{ source: "/", destination: "/browse", permanent: false }]
      : [];
  },
};

export default nextConfig;
