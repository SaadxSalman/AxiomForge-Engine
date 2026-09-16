/**
 * PostCSS configuration for Tailwind CSS v4.
 *
 * Tailwind v4 moved the PostCSS plugin into the dedicated
 * `@tailwindcss/postcss` package; the `tailwindcss` package can no longer be
 * used directly as a PostCSS plugin.
 */
module.exports = {
  plugins: {
    "@tailwindcss/postcss": {},
    autoprefixer: {},
  },
};
