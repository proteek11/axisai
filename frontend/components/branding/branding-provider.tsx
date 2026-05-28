'use client';

/**
 * BrandingProvider
 * Loads tenant branding from the API once (on mount), stores it in
 * localStorage as a cache, and applies all CSS custom properties to :root.
 * Place this inside the dashboard layout so it runs whenever the app is open.
 *
 * ⚠️  CSS var format:
 *   globals.css + Tailwind expect HSL *channel* strings: "H S% L%"
 *   (used inside hsl(var(--token)) in tailwind.config.js).
 *   Branding values are stored as hex (#rrggbb) in the DB and state.
 *   applyBranding() converts hex → HSL channels before writing to :root.
 *
 * ⚠️  Derived variables:
 *   globals.css defines 25 CSS vars. The branding UI exposes 10 of them.
 *   The remaining 15 are "derived" — they must mirror a parent token.
 *   e.g. --input mirrors --border, --ring mirrors --primary, etc.
 *   DERIVED_FROM maps every branding key → extra CSS vars to keep in sync.
 */

import { useEffect } from 'react';

interface BrandingTokens {
  primary?: string | null;
  primary_foreground?: string | null;
  background?: string | null;
  foreground?: string | null;
  card?: string | null;
  muted?: string | null;
  muted_foreground?: string | null;
  border?: string | null;
  sidebar_background?: string | null;
  sidebar_primary?: string | null;
  radius?: string | null;
  site_name?: string | null;
  logo_url?: string | null;
}

/** Map branding key → primary CSS custom-property name */
const TOKEN_TO_CSS: Record<string, string> = {
  primary:            '--primary',
  primary_foreground: '--primary-foreground',
  background:         '--background',
  foreground:         '--foreground',
  card:               '--card',
  muted:              '--muted',
  muted_foreground:   '--muted-foreground',
  border:             '--border',
  sidebar_background: '--sidebar-background',
  sidebar_primary:    '--sidebar-primary',
  radius:             '--radius',
};

/**
 * Derived CSS vars that must mirror a branding token.
 * When a token changes, all vars listed here are set to the same value.
 *
 * globals.css vars covered here (15 total):
 *   --card-foreground, --popover, --popover-foreground,
 *   --secondary, --secondary-foreground,
 *   --accent, --accent-foreground,
 *   --input, --ring,
 *   --sidebar-foreground, --sidebar-primary-foreground,
 *   --sidebar-accent, --sidebar-border
 */
const DERIVED_FROM: Record<string, string[]> = {
  primary:            ['--ring'],
  primary_foreground: ['--sidebar-primary-foreground'],
  foreground:         ['--card-foreground', '--popover-foreground', '--secondary-foreground', '--accent-foreground', '--sidebar-foreground'],
  card:               ['--popover'],
  muted:              ['--secondary', '--accent', '--sidebar-accent'],
  border:             ['--input', '--sidebar-border'],
};

/**
 * Convert a hex colour string (#rrggbb) → HSL channel string ("H S% L%").
 * This is the format Tailwind expects inside hsl(var(--token)).
 * Passes non-hex values through unchanged (already HSL, rem, etc.).
 */
function hexToHslChannels(hex: string): string {
  if (!hex || !hex.startsWith('#')) return hex;
  const clean = hex.replace('#', '');
  if (clean.length < 6) return hex;
  const r = parseInt(clean.slice(0, 2), 16) / 255;
  const g = parseInt(clean.slice(2, 4), 16) / 255;
  const b = parseInt(clean.slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

/**
 * Apply a branding token map to the document's :root CSS variables.
 *
 * - Colour values (hex #rrggbb) are converted to HSL channel strings so
 *   Tailwind's hsl(var(--x)) pattern computes correctly.
 * - Non-colour values (radius rem strings) are written as-is.
 * - Derived vars (--ring, --input, --card-foreground, etc.) are kept in
 *   sync with their parent token so the full globals.css var set is correct.
 */
export function applyBranding(tokens: BrandingTokens) {
  const root = document.documentElement;

  for (const [key, cssVar] of Object.entries(TOKEN_TO_CSS)) {
    const val = tokens[key as keyof BrandingTokens];

    if (val && val !== '') {
      if (key === 'radius') {
        root.style.setProperty(cssVar, val);
      } else {
        const hslVal = hexToHslChannels(val);
        // Set the primary var
        root.style.setProperty(cssVar, hslVal);
        // Set all derived vars that mirror this token
        for (const derived of DERIVED_FROM[key] ?? []) {
          root.style.setProperty(derived, hslVal);
        }
      }
    } else {
      // No override — remove inline style so globals.css default takes over
      root.style.removeProperty(cssVar);
      for (const derived of DERIVED_FROM[key] ?? []) {
        root.style.removeProperty(derived);
      }
    }
  }

  if (tokens.site_name) {
    document.title = tokens.site_name;
  }
}

const CACHE_KEY = 'axis_branding_v1';

export function BrandingProvider() {
  useEffect(() => {
    // 1. Apply cached branding immediately (zero flicker)
    try {
      const cached = localStorage.getItem(CACHE_KEY);
      if (cached) applyBranding(JSON.parse(cached));
    } catch {}

    // 2. Fetch fresh branding from API
    fetch('/api/branding')
      .then((r) => (r.ok ? r.json() : null))
      .then((data: BrandingTokens | null) => {
        if (!data) return;
        applyBranding(data);
        localStorage.setItem(CACHE_KEY, JSON.stringify(data));
      })
      .catch(() => {});
  }, []);

  return null;
}
