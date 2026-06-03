/** @type {import('next').NextConfig} */

// Two build targets from one codebase:
//   * default            -> "standalone" (Docker image, served by Node)
//   * BUILD_TARGET=static -> "export" (static files for GitHub Pages)
const isStatic = process.env.BUILD_TARGET === "static";
const basePath = process.env.PAGES_BASE_PATH || "";

const nextConfig = {
  reactStrictMode: true,
  output: isStatic ? "export" : "standalone",
  ...(isStatic
    ? {
        // GitHub Pages serves under /<repo>, so assets need the basePath.
        basePath,
        assetPrefix: basePath || undefined,
        trailingSlash: true, // emit /page/index.html -> no 404 on refresh
        images: { unoptimized: true },
        // Expose basePath to client code (hard redirects in lib/api).
        env: { NEXT_PUBLIC_BASE_PATH: basePath },
      }
    : {}),
};

module.exports = nextConfig;
