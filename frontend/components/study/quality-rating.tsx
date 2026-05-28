'use client';

import { useState } from 'react';
import { ThumbsUp, ThumbsDown, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface QualityRatingProps {
  spaceId: string;
  contentItemId: string;
  outputType: string;
}

/**
 * C-12: Thumbs up / thumbs down rating for an AI output tab.
 * Submits to PATCH /api/spaces/{id}/content/{contentId}/outputs/{outputType}
 */
export function QualityRating({ spaceId, contentItemId, outputType }: QualityRatingProps) {
  const [rating, setRating] = useState<1 | -1 | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (value: 1 | -1) => {
    if (loading) return;
    setLoading(true);
    try {
      const res = await fetch(
        `/api/spaces/${spaceId}/content/${contentItemId}/outputs/${outputType}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rating: value }),
        },
      );
      if (!res.ok) throw new Error('Failed');
      setRating(value);
      toast.success(value === 1 ? 'Thanks for the feedback!' : 'Noted — we\'ll use this to improve.');
    } catch {
      toast.error('Could not save rating');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-1">
      <span className="text-[10px] text-muted-foreground mr-0.5">Rate</span>
      <button
        onClick={() => submit(1)}
        disabled={loading || rating !== null}
        title="Good quality"
        className={cn(
          'w-7 h-7 rounded-[var(--radius)] flex items-center justify-center transition-colors',
          rating === 1
            ? 'bg-green-100 text-green-600'
            : 'text-muted-foreground hover:text-green-600 hover:bg-green-50 disabled:opacity-40',
        )}
      >
        {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <ThumbsUp className="w-3.5 h-3.5" />}
      </button>
      <button
        onClick={() => submit(-1)}
        disabled={loading || rating !== null}
        title="Poor quality — flag for improvement"
        className={cn(
          'w-7 h-7 rounded-[var(--radius)] flex items-center justify-center transition-colors',
          rating === -1
            ? 'bg-red-100 text-red-600'
            : 'text-muted-foreground hover:text-red-600 hover:bg-red-50 disabled:opacity-40',
        )}
      >
        <ThumbsDown className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
