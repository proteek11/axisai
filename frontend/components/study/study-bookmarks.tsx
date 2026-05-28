'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Bookmark, BookmarkCheck, Loader2, ExternalLink, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface BookmarkItem {
  id: string;
  content_item_id: string | null;
  space_id: string | null;
  output_type: string | null;
  label: string | null;
  created_at: string;
}

/** Small bookmark toggle button — shown on each tab header */
export function BookmarkToggle({
  contentItemId,
  spaceId,
  outputType,
  label,
}: {
  contentItemId: string;
  spaceId?: string;
  outputType: string;
  label: string;
}) {
  const qc = useQueryClient();

  const { data: bookmarks = [] } = useQuery<BookmarkItem[]>({
    queryKey: ['bookmarks', contentItemId],
    queryFn: async () => {
      const res = await fetch(`/api/me/bookmarks?content_item_id=${contentItemId}`);
      if (!res.ok) return [];
      return res.json();
    },
  });

  const existing = bookmarks.find((b) => b.output_type === outputType);

  const addMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/me/bookmarks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_item_id: contentItemId, space_id: spaceId, output_type: outputType, label }),
      });
      if (!res.ok) throw new Error('Failed');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bookmarks', contentItemId] }),
  });

  const removeMutation = useMutation({
    mutationFn: async (id: string) => {
      await fetch(`/api/me/bookmarks/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bookmarks', contentItemId] }),
  });

  const isPending = addMutation.isPending || removeMutation.isPending;

  const toggle = () => {
    if (existing) removeMutation.mutate(existing.id);
    else addMutation.mutate();
  };

  return (
    <button
      onClick={toggle}
      disabled={isPending}
      title={existing ? 'Remove bookmark' : `Bookmark ${label}`}
      className={cn(
        'w-7 h-7 rounded-[var(--radius)] flex items-center justify-center transition-colors',
        existing
          ? 'text-primary bg-primary/10 hover:bg-primary/20'
          : 'text-muted-foreground hover:text-primary hover:bg-muted',
        isPending && 'opacity-50'
      )}
    >
      {isPending
        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
        : existing
          ? <BookmarkCheck className="w-3.5 h-3.5" />
          : <Bookmark className="w-3.5 h-3.5" />}
    </button>
  );
}

/** Full bookmarks list — shown in a tab panel or modal */
export function StudyBookmarks({
  contentItemId,
  spaceId,
  onTabSelect,
}: {
  contentItemId: string;
  spaceId?: string;
  onTabSelect?: (tabKey: string) => void;
}) {
  const qc = useQueryClient();

  const { data: bookmarks = [], isLoading } = useQuery<BookmarkItem[]>({
    queryKey: ['bookmarks', contentItemId],
    queryFn: async () => {
      const res = await fetch(`/api/me/bookmarks?content_item_id=${contentItemId}`);
      if (!res.ok) return [];
      return res.json();
    },
  });

  const removeMutation = useMutation({
    mutationFn: async (id: string) => {
      await fetch(`/api/me/bookmarks/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bookmarks', contentItemId] }),
  });

  const TAB_LABELS: Record<string, string> = {
    summary: 'Summary', glossary: 'Glossary', flashcards: 'Flashcards',
    quiz: 'Quiz', faq: 'FAQ', infographic: 'Infographic',
    transcript: 'Transcript', chapters: 'Chapters',
  };

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-2 mb-4">
        <Bookmark className="w-4 h-4 text-primary" />
        <p className="section-label">Bookmarks</p>
        <span className="text-xs text-muted-foreground ml-auto">
          {bookmarks.length} bookmark{bookmarks.length !== 1 ? 's' : ''}
        </span>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
        </div>
      ) : bookmarks.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          <Bookmark className="w-8 h-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">No bookmarks yet.</p>
          <p className="text-xs mt-1">Click the bookmark icon on any study tab to save it here.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {bookmarks.map((bm) => (
            <div key={bm.id} className="enterprise-card flex items-center gap-3 p-3 group">
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                <BookmarkCheck className="w-4 h-4 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {bm.label ?? TAB_LABELS[bm.output_type ?? ''] ?? bm.output_type ?? 'Bookmark'}
                </p>
                {bm.output_type && (
                  <p className="text-xs text-muted-foreground capitalize">{bm.output_type} tab</p>
                )}
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                {onTabSelect && bm.output_type && (
                  <button
                    onClick={() => onTabSelect(bm.output_type!)}
                    className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
                    title="Go to tab"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  onClick={() => removeMutation.mutate(bm.id)}
                  disabled={removeMutation.isPending}
                  className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                  title="Remove bookmark"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
