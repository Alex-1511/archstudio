/** @type {import('next').NextConfig} */
export default {
  transpilePackages: ["@archstudio/app-core"],   // app-core ships TypeScript source (with .ts import specifiers)
  reactStrictMode: true,
  async headers() {
    return [{ source: "/(.*)", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" }, { key: "Referrer-Policy", value: "no-referrer" }, { key: "X-Frame-Options", value: "DENY" },
    ] }];
  },
};
