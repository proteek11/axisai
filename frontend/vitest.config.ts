import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  // Override PostCSS so Vite doesn't try to load postcss.config.js
  // (tailwindcss isn't needed for server-side API/middleware tests)
  css: {
    postcss: { plugins: [] },
  },

  test: {
    environment: 'node',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['app/api/**/*.ts', 'lib/**/*.ts', 'middleware.ts'],
      exclude: ['node_modules', '.next', '**/*.d.ts'],
    },
    include: ['__tests__/**/*.test.ts', '__tests__/**/*.test.tsx'],
  },

  resolve: {
    alias: {
      // '@' maps to project root — mirrors tsconfig paths: { "@/*": ["./*"] }
      '@': path.resolve(__dirname, '.'),

      /**
       * next/server and next/headers stubs.
       *
       * The Next.js package uses conditional exports and complex internal
       * bundling that Vite cannot resolve in a plain Node test environment.
       * We alias them to minimal stubs that replicate the exact surface area
       * our routes and middleware use:
       *   - NextRequest / NextResponse  (from next/server)
       *   - cookies()                   (from next/headers)
       *
       * This keeps all tests self-contained and runnable anywhere — no full
       * Next.js runtime required.
       */
      'next/server': path.resolve(
        __dirname,
        './__tests__/__mocks__/next-server-mock.ts'
      ),
      'next/headers': path.resolve(
        __dirname,
        './__tests__/__mocks__/next-headers-mock.ts'
      ),
    },
  },
});
