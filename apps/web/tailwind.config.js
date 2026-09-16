/**
 * Tailwind CSS v4 configuration.
 *
 * Tailwind v4 is CSS-first: the design tokens live in
 * `src/app/globals.css` inside an `@theme { ... }` block.  This file is kept
 * for editor/tooling hints and future `@config` usage.
 */
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {},
  },
  plugins: [],
};
