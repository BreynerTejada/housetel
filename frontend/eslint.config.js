import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import { reactRefresh } from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

// Named exports that the app's auto-discovery reads from feature files (see src/app/extensions.ts).
const FEATURE_EXPORTS = [
  'routes',
  'nav',
  'widgets',
  'reservationTabs',
  'reservationActions',
  'guestTabs',
  'topbarItems',
  'commands',
]

export default defineConfig([
  globalIgnores(['dist', 'coverage', 'node_modules']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat['recommended-latest'],
      reactRefresh.configs.vite(),
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    rules: {
      'react-refresh/only-export-components': [
        'error',
        { allowConstantExport: true, allowExportNames: FEATURE_EXPORTS },
      ],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],
      // Only relevant with the React Compiler, which this app does not enable. TanStack Table/Virtual
      // (DataTable, calendar, rates grid) would otherwise warn on every use. Re-enable with the compiler.
      'react-hooks/incompatible-library': 'off',
    },
  },
  {
    // Primitive/library modules export hooks, variants and providers next to components by design.
    files: ['src/components/ui/**', 'src/lib/**', 'src/test/**', 'src/**/__tests__/**'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  {
    // Route table and router modules are not component modules (a full reload on edit is fine).
    files: ['src/app/routes.tsx', 'src/app/router.ts'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  {
    files: ['*.config.{js,ts}'],
    languageOptions: { globals: globals.node },
  },
])
