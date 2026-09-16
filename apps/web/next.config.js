/**
 * Next.js configuration for the AxiomForge-Engine dashboard.
 *
 * `turbopack.root` is pinned to this app directory so Next.js resolves the
 * correct workspace root when more than one lockfile exists in the monorepo.
 */
const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: path.resolve(__dirname),
  },
};

module.exports = nextConfig;