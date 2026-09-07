import { FlatCompat } from "@eslint/eslintrc";

// eslint-config-next is still published as a legacy (eslintrc) config, so it
// is bridged into flat config here. This replaces the deprecated `next lint`.
const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default config;
