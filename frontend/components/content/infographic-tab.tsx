'use client';

import { useRef } from 'react';
import { RotateCcw, Download, Loader2, ExternalLink } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

interface InfographicTabProps {
  contentId: string;
  html: string;
}

export function InfographicTab({ contentId, html }: InfographicTabProps) {
  const queryClient = useQueryClient();
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const regenerateMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/content/${contentId}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_type: 'infographic', action: 'regenerate' }),
      });
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    onSuccess: () => {
      toast.success('Infographic regeneration started');
      queryClient.invalidateQueries({ queryKey: ['content', contentId, 'outputs'] });
    },
    onError: () => toast.error('Failed to regenerate'),
  });

  const openFullscreen = () => {
    const win = window.open('', '_blank');
    if (win) {
      win.document.write(html);
      win.document.close();
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="section-label">AI-Generated Infographic</p>
        <div className="flex items-center gap-2">
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
            onClick={openFullscreen}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90 transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            Full Screen
          </button>
        </div>
      </div>

      {html ? (
        <div className="border border-border rounded-[var(--radius)] overflow-hidden bg-white">
          <iframe
            ref={iframeRef}
            srcDoc={html}
            className="w-full"
            style={{ height: '700px', border: 'none' }}
            title="Infographic preview"
            sandbox="allow-scripts allow-same-origin"
          />
        </div>
      ) : (
        <div className="enterprise-card flex flex-col items-center py-16 text-center">
          <p className="text-sm text-muted-foreground">No infographic generated yet. Click Regenerate to create one.</p>
        </div>
      )}
    </div>
  );
}
