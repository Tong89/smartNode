import { defineConfig } from 'vitest/config';

/**
 * Vitest configuration for smartNode frontend unit tests.
 *
 * - Uses jsdom environment to emulate browser APIs (window, localStorage, etc.)
 * - Coverage collected via v8 provider, reported as text + lcov
 * - Test files must match *.test.ts pattern
 */
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html'],
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.test.ts', 'src/main.ts', 'src/vendor.js'],
    },
  },
});
