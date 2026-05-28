'use client';

/**
 * ScormConfigModal
 *
 * Shown after a SCORM package is attached to a learning space.
 * Lets the creator configure:
 *   • Completion trigger (completion_only | pass_required)
 *   • Max attempts (unlimited | 1–10)
 *   • Grade aggregation (highest | average | latest)
 *
 * Calls PUT /api/spaces/[id]/items/[itemId] which already accepts
 * scorm_completion_trigger, scorm_max_attempts, scorm_grade_aggregation.
 */

import { useState } from 'react';
import { X, Package, Settings, CheckCircle, Trophy, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface ScormConfigModalProps {
  spaceId: string;
  spaceItemId: string;
  packageTitle: string;
  onClose: () => void;
  onSaved: () => void;
}

type CompletionTrigger = 'completion_only' | 'pass_required';
type GradeAggregation = 'highest' | 'average' | 'latest';

export function ScormConfigModal({
  spaceId,
  spaceItemId,
  packageTitle,
  onClose,
  onSaved,
}: ScormConfigModalProps) {
  const [completionTrigger, setCompletionTrigger] = useState<CompletionTrigger>('completion_only');
  const [maxAttempts, setMaxAttempts] = useState<number | null>(null); // null = unlimited
  const [gradeAggregation, setGradeAggregation] = useState<GradeAggregation>('highest');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`/api/spaces/${spaceId}/items/${spaceItemId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scorm_completion_trigger: completionTrigger,
          scorm_max_attempts: maxAttempts,
          scorm_grade_aggregation: gradeAggregation,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { error?: string }).error ?? 'Failed to save');
      }
      toast.success('SCORM settings saved');
      onSaved();
      onClose();
    } catch (err: unknown) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const COMPLETION_OPTIONS: { value: CompletionTrigger; label: string; desc: string }[] = [
    {
      value: 'completion_only',
      label: 'Completion',
      desc: 'Marked complete when the learner finishes all SCO content',
    },
    {
      value: 'pass_required',
      label: 'Pass required',
      desc: 'Must pass the built-in quiz/score threshold to be marked complete',
    },
  ];

  const AGGREGATION_OPTIONS: { value: GradeAggregation; label: string; desc: string }[] = [
    { value: 'highest', label: 'Highest score', desc: 'Best score across all attempts' },
    { value: 'average', label: 'Average score', desc: 'Mean of all attempt scores' },
    { value: 'latest',  label: 'Latest score',  desc: 'Most recent attempt score' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-md shadow-lg max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <Package className="w-4 h-4 text-primary" />
            </div>
            <div>
              <p className="font-semibold text-sm text-primary">SCORM Settings</p>
              <p className="text-xs text-muted-foreground truncate max-w-[220px]">{packageTitle}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-5 overflow-y-auto">

          {/* Completion trigger */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Completion trigger</p>
            </div>
            <div className="space-y-2">
              {COMPLETION_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setCompletionTrigger(opt.value)}
                  className={cn(
                    'w-full text-left px-3 py-2.5 rounded-[var(--radius)] border transition-colors',
                    completionTrigger === opt.value
                      ? 'border-primary bg-primary/5 text-primary'
                      : 'border-border hover:bg-muted/50'
                  )}
                >
                  <p className="text-sm font-medium">{opt.label}</p>
                  <p className="text-xs text-muted-foreground">{opt.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Max attempts */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <RotateCcw className="w-3.5 h-3.5 text-blue-600" />
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Max attempts</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {[null, 1, 2, 3, 5, 10].map((n) => (
                <button
                  key={n ?? 'unlimited'}
                  onClick={() => setMaxAttempts(n)}
                  className={cn(
                    'px-3 py-1.5 text-sm rounded-[var(--radius)] border transition-colors',
                    maxAttempts === n
                      ? 'border-primary bg-primary/5 text-primary font-semibold'
                      : 'border-border hover:bg-muted/50 text-foreground'
                  )}
                >
                  {n === null ? 'Unlimited' : n}
                </button>
              ))}
            </div>
            {maxAttempts !== null && maxAttempts > 1 && (
              <p className="text-xs text-muted-foreground mt-1.5">
                Learner can try up to {maxAttempts} times. Grade policy applies across attempts.
              </p>
            )}
          </div>

          {/* Grade aggregation — only relevant if max attempts > 1 */}
          {(maxAttempts === null || maxAttempts > 1) && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Trophy className="w-3.5 h-3.5 text-yellow-500" />
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Grade policy</p>
              </div>
              <div className="space-y-2">
                {AGGREGATION_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setGradeAggregation(opt.value)}
                    className={cn(
                      'w-full text-left px-3 py-2 rounded-[var(--radius)] border transition-colors',
                      gradeAggregation === opt.value
                        ? 'border-primary bg-primary/5 text-primary'
                        : 'border-border hover:bg-muted/50'
                    )}
                  >
                    <p className="text-sm font-medium">{opt.label}</p>
                    <p className="text-xs text-muted-foreground">{opt.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 p-5 border-t border-border flex-shrink-0">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted/50 transition-colors"
          >
            Skip for now
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {saving && <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
            {saving ? 'Saving…' : 'Save settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
