import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  experimental: {
    // Every signed-in page waits for the session before rendering anything, by design,
    // so validating all of them for instant navigation only produces dev-console noise.
    // Validate just the segments that opt in with `export const instant = true`.
    instantInsights: { validationLevel: "manual-warning" },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // never let another site put this app in a frame (clickjacking)
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
  // The browser only ever talks to this origin; /api is forwarded to the FastAPI
  // service. That keeps the session cookie same-origin, so no CORS setup is needed.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
