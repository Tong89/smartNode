import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';

/**
 * Vitest configuration for smartNode frontend unit tests.
 *
 * - Uses jsdom environment to emulate browser APIs (window, localStorage, etc.)
 * - @vitejs/plugin-vue enables SFC (.vue) compilation in the test runner
 * - Coverage collected via v8 provider, reported as text + lcov
 * - Test files may be *.test.ts (src/) or *.test.js (tests/) — both are included
 */
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['src/**/*.test.ts', 'tests/**/*.test.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html'],
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.test.ts', 'src/main.ts', 'src/vendor.js'],
    },
  },
});
