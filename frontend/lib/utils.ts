import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Merge Tailwind classes safely. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format bytes to human-readable size. */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/** Format a date to a readable string. */
export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/** Truncate text to a max length. */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

/** Get initials from a name or email. */
export function getInitials(nameOrEmail: string): string {
  const parts = nameOrEmail.split(/[\s@.]+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

/** Content type badge color map. */
export const CONTENT_TYPE_COLORS: Record<string, string> = {
  pdf: 'text-red-600 bg-red-50 border-red-200',
  youtube: 'text-red-500 bg-red-50 border-red-200',
  vimeo: 'text-blue-500 bg-blue-50 border-blue-200',
  vimeo_upload: 'text-blue-500 bg-blue-50 border-blue-200',
  html_page: 'text-green-600 bg-green-50 border-green-200',
  scorm: 'text-purple-600 bg-purple-50 border-purple-200',
  unknown: 'text-gray-500 bg-gray-50 border-gray-200',
};

/** Status badge color map. */
export const STATUS_COLORS: Record<string, string> = {
  ready: 'text-green-600 border-green-400 bg-green-50',
  processing: 'text-blue-600 border-blue-400 bg-blue-50',
  pending: 'text-amber-600 border-amber-400 bg-amber-50',
  failed: 'text-red-600 border-red-400 bg-red-50',
  stale: 'text-orange-600 border-orange-400 bg-orange-50',
};

/** Role badge color map. */
export const ROLE_COLORS: Record<string, string> = {
  admin: 'text-purple-600 border-purple-400 bg-purple-50',
  creator: 'text-blue-600 border-blue-400 bg-blue-50',
  learner: 'text-green-600 border-green-400 bg-green-50',
};

/** Bloom's level badge colors. */
export const BLOOMS_COLORS: Record<string, string> = {
  remember: 'bg-sky-50 text-sky-700 border-sky-200',
  understand: 'bg-teal-50 text-teal-700 border-teal-200',
  apply: 'bg-lime-50 text-lime-700 border-lime-200',
  analyze: 'bg-amber-50 text-amber-700 border-amber-200',
  evaluate: 'bg-orange-50 text-orange-700 border-orange-200',
  create: 'bg-rose-50 text-rose-700 border-rose-200',
};
