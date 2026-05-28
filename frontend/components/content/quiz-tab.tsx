'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Save, Loader2, Trash2, Plus, ChevronDown, ChevronUp } from 'lucide-react';

interface Question {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
  bloom_level: string;
}

interface QuizTabProps { contentId: string; questions: Question[] }

const BLOOM_COLORS: Record<string, string> = {
  remember:   'border-blue-400 text-blue-600 bg-blue-50',
  understand: 'border-teal-400 text-teal-600 bg-teal-50',
  apply:      'border-green-400 text-green-600 bg-green-50',
  analyze:    'border-yellow-400 text-yellow-700 bg-yellow-50',
  evaluate:   'border-orange-400 text-orange-600 bg-orange-50',
  create:     'border-red-400 text-red-600 bg-red-50',
};

function QuestionCard({
  q,
  idx,
  onUpdate,
  onDelete,
}: {
  q: Question;
  idx: number;
  onUpdate: (idx: number, updated: Question) => void;
  onDelete: (idx: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState(q);
  const [isEditing, setIsEditing] = useState(false);

  const bloomClass = BLOOM_COLORS[q.bloom_level?.toLowerCase()] ?? 'border-border text-muted-foreground bg-muted';

  return (
    <div className="enterprise-card">
      <div className="flex items-start gap-3">
        <span className="text-xs font-bold text-muted-foreground w-6 flex-shrink-0 mt-0.5">
          {idx + 1}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <p className="font-medium text-sm text-foreground leading-snug">{q.question}</p>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {q.bloom_level && (
                <span className={cn('text-xs px-2 py-0.5 rounded-full border capitalize', bloomClass)}>
                  {q.bloom_level}
                </span>
              )}
              <button
                onClick={() => setExpanded((e) => !e)}
                className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground"
              >
                {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
              <button
                onClick={() => onDelete(idx)}
                className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-red-600"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {expanded && (
            <div className="mt-3 space-y-2">
              {/* Options */}
              <div className="space-y-1.5">
                {q.options.map((opt, oi) => (
                  <div
                    key={oi}
                    className={cn(
                      'flex items-center gap-2 px-3 py-2 rounded-[var(--radius)] text-sm',
                      oi === q.correct_index
                        ? 'bg-green-50 border border-green-300 text-green-800'
                        : 'bg-muted text-muted-foreground'
                    )}
                  >
                    <span className="font-semibold w-5 flex-shrink-0">
                      {String.fromCharCode(65 + oi)}.
                    </span>
                    <span>{opt}</span>
                    {oi === q.correct_index && (
                      <span className="ml-auto text-xs font-semibold text-green-700">✓ Correct</span>
                    )}
                  </div>
                ))}
              </div>
              {q.explanation && (
                <div className="bg-muted px-3 py-2 rounded-[var(--radius)]">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Explanation</p>
                  <p className="text-sm text-foreground">{q.explanation}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function QuizTab({ contentId, questions: initialQs }: QuizTabProps) {
  const queryClient = useQueryClient();
  const [questions, setQuestions] = useState<Question[]>(initialQs);
  const [isDirty, setIsDirty] = useState(false);

  const saveMutation = useMutation({
    mutationFn: async (data: Question[]) => {
      const res = await fetch(`/api/content/${contentId}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_type: 'quiz', content: data, action: 'update' }),
      });
      if (!res.ok) throw new Error('Failed');
    },
    onSuccess: () => {
      toast.success('Quiz saved');
      queryClient.invalidateQueries({ queryKey: ['content', contentId, 'outputs'] });
      setIsDirty(false);
    },
    onError: () => toast.error('Failed to save'),
  });

  const deleteQuestion = (idx: number) => {
    setQuestions((prev) => prev.filter((_, i) => i !== idx));
    setIsDirty(true);
  };

  const updateQuestion = (idx: number, updated: Question) => {
    setQuestions((prev) => prev.map((q, i) => (i === idx ? updated : q)));
    setIsDirty(true);
  };

  // Bloom distribution summary
  const bloomCounts = questions.reduce<Record<string, number>>((acc, q) => {
    const l = q.bloom_level?.toLowerCase() ?? 'unknown';
    acc[l] = (acc[l] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <p className="section-label">{questions.length} Questions</p>
        {isDirty && (
          <button
            onClick={() => saveMutation.mutate(questions)}
            disabled={saveMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {saveMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            Save Changes
          </button>
        )}
      </div>

      {/* Bloom taxonomy summary */}
      {Object.keys(bloomCounts).length > 0 && (
        <div className="enterprise-card mb-4">
          <p className="section-label mb-3">Bloom's Taxonomy Distribution</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(bloomCounts).map(([level, count]) => (
              <span
                key={level}
                className={cn(
                  'text-xs px-2.5 py-1 rounded-full border capitalize',
                  BLOOM_COLORS[level] ?? 'border-border text-muted-foreground bg-muted'
                )}
              >
                {level} · {count}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Questions */}
      <div className="space-y-3">
        {questions.map((q, idx) => (
          <QuestionCard
            key={idx}
            q={q}
            idx={idx}
            onUpdate={updateQuestion}
            onDelete={deleteQuestion}
          />
        ))}
      </div>
      {questions.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-sm">No quiz questions yet.</p>
        </div>
      )}
    </div>
  );
}
