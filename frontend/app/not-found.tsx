/**
 * Global 404 page — shown for any unmatched route.
 */
import Link from 'next/link';
import { FileQuestion, ArrowLeft } from 'lucide-react';

export const metadata = { title: '404 — Page not found · axis.edzlms.com' };

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-6 p-8 bg-background">
      <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
        <FileQuestion className="w-8 h-8 text-primary" />
      </div>

      <div className="text-center max-w-md">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-2">
          404
        </p>
        <h1 className="text-3xl font-bold text-primary mb-3">Page not found</h1>
        <p className="text-sm text-muted-foreground">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
      </div>

      <Link
        href="/"
        className="flex items-center gap-2 px-5 py-2.5 rounded-[var(--radius)] bg-primary
          text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to home
      </Link>
    </div>
  );
}
