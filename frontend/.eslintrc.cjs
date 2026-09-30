/* ESLint 8 config. Deliberately modest: catches real bugs (hooks misuse,
 * unused code, `any` creep) without restyling a codebase that already has
 * its own conventions. Formatting is not linted. */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: "latest", sourceType: "module", ecmaFeatures: { jsx: true } },
  plugins: ["@typescript-eslint", "react-hooks"],
  extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended"],
  ignorePatterns: ["dist", "node_modules", "*.cjs", "vite.config.ts", "tailwind.config.ts"],
  rules: {
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",
    "@typescript-eslint/no-explicit-any": "error",
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    "no-empty": ["error", { allowEmptyCatch: true }],
  },
  overrides: [
    { files: ["src/**/*.test.ts", "src/**/*.test.tsx", "src/test/**"], rules: { "@typescript-eslint/no-non-null-assertion": "off" } },
  ],
};
