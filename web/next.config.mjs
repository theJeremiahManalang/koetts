/** @type {import('next').NextConfig} */
const nextConfig = {
  async redirects() {
    return process.env.MANGA_FRONTEND_ONLY === "1"
      ? [{ source: "/", destination: "/browse", permanent: false }]
      : [];
  },
};

export default nextConfig;
