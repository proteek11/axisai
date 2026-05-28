/**
 * Vitest global setup
 *
 * Note: @testing-library/jest-dom is intentionally NOT imported here.
 * Our current tests are all server-side (API routes, middleware, API client)
 * and don't render React components, so DOM matchers aren't needed.
 *
 * When you add component tests in the future, import jest-dom in those
 * specific test files or add it back here once the package is installed
 * locally with a compatible dom-accessibility-api version.
 */
import { vi, beforeEach, afterEach } from 'vitest';

// Reset all mocks between tests — prevents state leakage across test cases
beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});
