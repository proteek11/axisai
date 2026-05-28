'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { cn } from '@/lib/utils';
import {
  BookOpen, Loader2, AlertCircle, FileText, Youtube, Video, Upload,
  ArrowRight, Globe, Lock
} from 'lucide-react';
import Link from 'next/link';

interface SpaceItem {
  id: string;
  content_item_id: string;
  title_override: string | null;
  is_visible: boolean;
  // Flat fields from SpaceItemSummary API response
  content_type: string | null;
  content_title: string | null;
  content_status: string | null;
}

interface GuestSpace {
  id: string;
  title: string;
  description: string | null;
  tags?: string[];
  items: SpaceItem[];
}

const CONTENT_META: Record<string, { icon: React.ElementType; color: string; bg: string; label: string }> = {
  pdf:          { icon: FileText, color: 'text-orange-600', bg: 'bg-orange-50', label: 'PDF'   },
  text:         { icon: FileText, color: 'text-gray-600',   bg: 'bg-gray-50',   label: 'Text'  },
  youtube:      { icon: Youtube,  color: 'text-red-600',    bg: 'bg-red-50',    label: 'Video' },
  vimeo:        { icon: Video,    color: 'text-blue-600',   bg: 'bg-blue-50',   label: 'Video' },
  video_upload: { icon: Upload,   color: 'text-purple-600', bg: 'bg-purple-50', label: 'Video' },
};

function GuestLearnContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const [space, setSpace] = useState<GuestSpace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) { setError('Invalid share link'); setLoading(false); return; }

    fetch(`/api/learn/guest?token=${encodeURIComponent(token)}`)
      .then((r) => {
        if (!r.ok) throw new Error('This link is invalid or has expired.');
        return r.json();
      })
      .then(setSpace)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !space) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background p-6 text-center">
        <div className="w-14 h-14 rounded-full bg-red-50 flex items-center justify-center mb-4">
          <AlertCircle className="w-7 h-7 text-red-600" />
        </div>
        <h1 className="text-xl font-bold text-primary mb-2">Link Unavailable</h1>
        <p className="text-muted-foreground mb-6">{error ?? 'This link is invalid or has expired.'}</p>
        <Link
          href="/login"
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
            rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90"
        >
          Sign In Instead
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    );
  }

  const visibleItems = (space.items ?? []).filter((i) => i.is_visible && i.content_status === 'ready');

  return (
    <div className="min-h-screen bg-background">
      {/* Top bar */}
      <div className="border-b border-border bg-background px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center">
            <BookOpen className="w-3.5 h-3.5 text-primary-foreground" />
          </div>
          <span className="font-bold text-primary text-sm">axis.edzlms.com</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Globe className="w-3.5 h-3.5" />
            Guest Preview
          </span>
          <Link
            href="/login"
            className="px-3 py-1.5 bg-primary text-primary-foreground rounded-[var(--radius)]
              text-xs font-medium hover:bg-primary/90 transition-colors"
          >
            Sign In
          </Link>
        </div>
      </div>

      {/* Space header */}
      <div className="border-b border-border px-6 py-8 bg-gradient-to-r from-primary/5 to-transparent">
        <div className="max-w-4xl">
          <div className="flex items-center gap-2 mb-2">
            <span className="flex items-center gap-1.5 text-xs text-blue-600 border border-blue-300 bg-blue-50 px-2 py-0.5 rounded-full">
              <Globe className="w-3 h-3" />
              Public Space
            </span>
          </div>
          <h1 className="text-3xl font-bold text-primary mb-2">{space.title}</h1>
          {space.description && (
            <p className="text-muted-foreground text-base">{space.description}</p>
          )}
          {(space.tags?.length ?? 0) > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {(space.tags ?? []).map((tag) => (
                <span key={tag} className="text-xs px-2.5 py-1 bg-muted rounded-full text-muted-foreground">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-8 max-w-4xl">
        <p className="section-label mb-4">{visibleItems.length} Content Items</p>

        {visibleItems.length === 0 ? (
          <div className="border border-border rounded-[var(--radius)] p-12 text-center">
            <p className="text-muted-foreground">No content available in this space yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {visibleItems.map((item, idx) => {
              const meta = CONTENT_META[item.content_type ?? ''] ?? CONTENT_META.pdf;
              const Icon = meta.icon;
              return (
                <div
                  key={item.id}
                  className="border border-border rounded-[var(--radius)] bg-card p-5 flex items-start gap-4"
                >
                  <div className={cn('w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0', meta.bg)}>
                    <Icon className={cn('w-5 h-5', meta.color)} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm text-primary mb-1">
                      {item.title_override || item.content_title || 'Untitled'}
                    </p>
                    <p className="text-xs text-muted-foreground">{meta.label}</p>
                  </div>
                  {/* Guest can view but needs login to interact with AI */}
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Lock className="w-3 h-3" />
                    Login to study
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* CTA */}
        <div className="mt-8 border border-primary/30 rounded-[var(--radius)] bg-primary/5 p-6 text-center">
          <h3 className="font-bold text-primary mb-2">Ready to study?</h3>
          <p className="text-sm text-muted-foreground mb-4">
            Sign in or create a free account to access AI summaries, flashcards, quizzes, and more.
          </p>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            Get Started Free
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function GuestLearnPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    }>
      <GuestLearnContent />
    </Suspense>
  );
}
