'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Pencil, Save, X, RotateCcw, Loader2 } from 'lucide-react';

interface SummaryTabProps {
  contentId: string;
  summary: string;
}

export function SummaryTab({ contentId, summary }: SummaryTabProps) {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(summary);

  const saveMutation = useMutation({
    mutationFn: async (text: string) => {
      const res = await fetch(`/api/content/${contentId}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_type: 'summary', content: text, action: 'update' }),
      });
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    onSuccess: () => {
      toast.success('Summary saved');
      queryClient.invalidateQueries({ queryKey: ['content', contentId, 'outputs'] });
      setIsEditing(false);
    },
    onError: () => toast.error('Failed to save summary'),
  });

  const regenerateMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/content/${contentId}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_type: 'summary', action: 'regenerate' }),
      });
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    onSuccess: () => {
      toast.success('Summary regeneration started');
      queryClient.invalidateQueries({ queryKey: ['content', contentId, 'outputs'] });
    },
    onError: () => toast.error('Failed to regenerate'),
  });

  return (
    <div className="max-w-3xl">
      <div className="enterprise-card">
        {/* Toolbar */}
        <div className="flex items-center justify-between mb-4 pb-4 border-b border-border">
          <p className="section-label">AI Summary</p>
          <div className="flex items-center gap-2">
            {!isEditing ? (
              <>
                <button
                  onClick={() => regenerateMutation.mutate()}
                  disabled={regenerateMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[var(--radius)]
                    text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
                >
                  {regenerateMutation.isPending
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <RotateCcw className="w-3 h-3" />
                  }
                  Regenerate
                </button>
                <button
                  onClick={() => { setDraft(summary); setIsEditing(true); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground
                    rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90 transition-colors"
                >
                  <Pencil className="w-3 h-3" />
                  Edit
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => setIsEditing(false)}
                  className="flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[var(--radius)]
                    text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
                >
                  <X className="w-3 h-3" />
                  Cancel
                </button>
                <button
                  onClick={() => saveMutation.mutate(draft)}
                  disabled={saveMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground
                    rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {saveMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                  Save
                </button>
              </>
            )}
          </div>
        </div>

        {/* Content */}
        {isEditing ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={20}
            className="w-full px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background
              text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-none"
          />
        ) : (
          <div className="prose prose-sm max-w-none text-foreground leading-relaxed whitespace-pre-wrap">
            {summary}
          </div>
        )}
      </div>
    </div>
  );
}
