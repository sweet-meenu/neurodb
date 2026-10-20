import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // This is a React Compiler-readiness rule; this app doesn't opt into
      // the compiler, and it flags the standard "fetch on mount" effect
      // pattern used throughout the dashboard even though setState only
      // ever runs after an awaited call, never synchronously in the effect
      // body. Downgraded rather than restructuring correct data-fetching
      // code around an experimental lint rule.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
