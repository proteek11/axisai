'use client';

/**
 * InteractivePDFEditor — creator tool for adding questions to Interactive PDFs.
 *
 * Renders inside /library/[id] (detail page) when content_type === 'interactive_pdf'.
 * Allows creators to add MCQ, True/False, and Callout blocks at specific PDF pages.
 * Questions are stored in content_items.interactions (JSONB) via PUT /pdf-interactions.
 */

import { useState, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  Plus, Trash2, Save, ChevronDown, ChevronRight,
  HelpCircle, ToggleLeft, MessageSquare, Loader2, Sparkles,
} from 'lucide-react';

interface Interaction {
  index?: number;
  page_num: number;
  type: 'mcq' | 'truefalse' | 'callout';
  question?: string;
  options?: string[];
  correct_index?: number;
  correct_answer?: boolean;
  explanation?: string;
  text?: string;
}

interface Props {
  contentId: string;
  interactions: Interaction[];
  onSaved: () => void;
}

const TYPE_LABELS = {
  mcq: 'Multiple Choice',
  truefalse: 'True / False',
  callout: 'Callout / Info',
};

function emptyQuestion(): Interaction {
  return {
    page_num: 1,
    type: 'mcq',
    question: '',
    options: ['', '', '', ''],
    correct_index: 0,
    explanation: '',
  };
}

function QuestionCard({
  q,
  index,
  onChange,
  onDelete,
}: {
  q: Interaction;
  index: number;
  onChange: (updated: Interaction) => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(true);

  const updateOption = (i: number, val: string) => {
    const opts = [...(q.options ?? ['', '', '', ''])];
    opts[i] = val;
    onChange({ ...q, options: opts });
  };

  const ensureOptions = (type: Interaction['type']): Interaction => {
    if (type === 'mcq') return { ...q, type, options: q.options?.length ? q.options : ['', '', '', ''], correct_index: q.correct_index ?? 0, question: q.question ?? '', explanation: q.explanation ?? '' };
    if (type === 'truefalse') return { ...q, type, correct_answer: q.correct_answer ?? true, question: q.question ?? '', explanation: q.explanation ?? '' };
    return { ...q, type, text: q.text ?? '' };
  };

  return (
    <div className="border border-border rounded-[var(--radius)] overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 bg-muted/30 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
          <HelpCircle className="w-3.5 h-3.5 text-primary" />
        </div>
        <span className="text-xs font-semibold text-foreground flex-1">
          Q{index + 1} · Page {q.page_num} · {TYPE_LABELS[q.type]}
        </span>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="text-muted-foreground hover:text-red-500 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
        {expanded
          ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
          : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
      </div>

      {expanded && (
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">PDF Page</label>
              <input
                type="number"
                min={1}
                value={q.page_num}
                onChange={(e) => onChange({ ...q, page_num: Math.max(1, parseInt(e.target.value) || 1) })}
                className="w-full px-2 py-1.5 text-sm border border-border rounded-[calc(var(--radius)-2px)] bg-background focus:outline-none focus:ring-1 focus:ring-primary/40"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Type</label>
              <select
                value={q.type}
                onChange={(e) => onChange(ensureOptions(e.target.value as Interaction['type']))}
                className="w-full px-2 py-1.5 text-sm border border-border rounded-[calc(var(--radius)-2px)] bg-background focus:outline-none focus:ring-1 focus:ring-primary/40"
              >
                <option value="mcq">Multiple Choice</option>
                <option value="truefalse">True / False</option>
                <option value="callout">Callout / Info</option>
              </select>
            </div>
          </div>

          {q.type === 'mcq' && (
            <>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Question</label>
                <input
                  type="text"
                  value={q.question ?? ''}
                  onChange={(e) => onChange({ ...q, question: e.target.value })}
                  placeholder="What is...?"
                  className="w-full px-2 py-1.5 text-sm border border-border rounded-[calc(var(--radius)-2px)] bg-background focus:outline-none focus:ring-1 focus:ring-primary/40"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground block">Options — select radio to mark correct answer</label>
                {(q.options ?? ['', '', '', '']).map((opt, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      type="radio"
                      name={`correct-${index}`}
                      checked={q.correct_index === i}
                      onChange={() => onChange({ ...q, correct_index: i })}
                      className="accent-primary"
                    />
                    <input
                      type="text"
                      value={opt}
                      onChange={(e) => updateOption(i, e.target.value)}
                      placeholder={`Option ${i + 1}`}
                      className="flex-1 px-2 py-1 text-sm border border-border rounded-[calc(var(--radius)-2px)] bg-background focus:outline-none focus:ring-1 focus:ring-primary/40"
                    />
                  </div>
                ))}
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Explanation (shown after answer)</label>
                <input
                  type="text"
                  value={q.explanation ?? ''}
                  onChange={(e) => onChange({ ...q, explanation: e.target.value })}
                  placeholder="Why is this the correct answer?"
                  className="w-full px-2 py-1.5 text-sm border border-border rounded-[calc(var(--radius)-2px)] bg-background focus:outline-none focus:ring-1 focus:ring-primary/40"
                />
              </div>
            </>
          )}

          {q.type === 'truefalse' && (
            <>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Statement</label>
                <input
                  type="text"
                  value={q.question ?? ''}
                  onChange={(e) => onChange({ ...q, question: e.target.value })}
                  placeholder="This statement is true..."
                  className="w-full px-2 py-1.5 text-sm border border-border rounded-[calc(var(--radius)-2px)] bg-background focus:outline-none focus:ring-1 focus:ring-primary/40"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Correct Answer</label>
                <div className="flex gap-3">
                  {([true, false] as const).map((val) => (
                    <button
                      key={String(val)}
                      type="button"
                      onClick={() => onChange({ ...q, correct_answer: val })}
                      className={cn(
                        'px-4 py-1.5 text-xs font-semibold rounded-[calc(var(--radius)-2px)] border transition-colors',
                        q.correct_answer === val
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border text-muted-foreground hover:bg-muted'
                      )}
                    >
                      {val ? 'True' : 'False'}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">Explanation</label>
                <input
                  type="text"
                  value={q.explanation ?? ''}
                  onChange={(e) => onChange({ ...q, explanation: e.target.value })}
                  placeholder="Why is this true/false?"
                  className="w-full px-2 py-1.5 text-sm border border-border rounded-[calc(var(--radius)-2px)] bg-background focus:outline-none focus:ring-1 focus:ring-primary/40"
                />
              </div>
            </>
          )}

          {q.type === 'callout' && (
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">Callout Text</label>
              <textarea
                value={q.text ?? ''}
                onChange={(e) => onChange({ ...q, text: e.target.value })}
                placeholder="Key insight or important note to show on this page..."
                rows={3}
                className="w-full px-2 py-1.5 text-sm border border-border rounded-[calc(var(--radius)-2px)] bg-background focus:outline-none focus:ring-1 focus:ring-primary/40 resize-none"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function InteractivePDFEditor({ contentId, interactions: initial, onSaved }: Props) {
  const [questions, setQuestions] = useState<Interaction[]>([]);
  const [initialised, setInitialised] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [suggestCount, setSuggestCount] = useState(5);

  // One-time sync from prop when server data first arrives
  useEffect(() => {
    if (!initialised && initial.length > 0) {
      setQuestions([...initial]);
      setInitialised(true);
    }
  }, [initial, initialised]);

  const saveMutation = useMutation({
    mutationFn: async (qs: Interaction[]) => {
      // Strip the index field (added server-side for display) before saving
      const clean = qs.map(({ index: _idx, ...q }) => q);
      const res = await fetch(`/api/library/${contentId}/pdf-interactions`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interactions: clean }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || err.detail || 'Save failed');
      }
      return res.json();
    },
    onSuccess: () => {
      toast.success(`${questions.length} question${questions.length !== 1 ? 's' : ''} saved`);
      setInitialised(false); // allow re-sync from server on next load
      onSaved();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const suggestQuestions = async () => {
    setIsSuggesting(true);
    try {
      const res = await fetch(`/api/content/${contentId}/suggest-questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: suggestCount }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || err.detail || 'AI suggestion failed');
      }
      const data = await res.json();
      const suggested: Interaction[] = (data.questions || []).map((q: any, i: number) => ({
        page_num: q.page_num ?? 1,
        type: 'mcq' as const,
        question: q.question ?? '',
        options: q.options ?? ['', '', '', ''],
        correct_index: q.correct_index ?? 0,
        explanation: q.explanation ?? '',
      }));
      if (suggested.length === 0) {
        toast.error('No questions generated — check that the content has been processed.');
        return;
      }
      setQuestions((prev) => [...prev, ...suggested]);
      toast.success(`${suggested.length} AI questions added — review and save when ready`);
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setIsSuggesting(false);
    }
  };

  const addQuestion = () => {
    const lastPage = questions.length > 0 ? Math.max(...questions.map((q) => q.page_num)) : 0;
    setQuestions([...questions, { ...emptyQuestion(), page_num: lastPage + 1 }]);
  };

  const updateQuestion = (i: number, updated: Interaction) => {
    const next = [...questions];
    next[i] = updated;
    setQuestions(next);
  };

  const deleteQuestion = (i: number) => {
    setQuestions(questions.filter((_, idx) => idx !== i));
  };

  // Sort display by page number
  const displayOrder = [...questions]
    .map((q, i) => ({ q, i }))
    .sort((a, b) => a.q.page_num - b.q.page_num);

  return (
    <div className="enterprise-card overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-border">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Embedded Questions
          </span>
          <span className="ml-2 text-xs text-muted-foreground">
            {questions.length} question{questions.length !== 1 ? 's' : ''} · shown to learners as they read each page
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 border border-border rounded-[calc(var(--radius)-2px)] overflow-hidden">
            <button
              type="button"
              onClick={() => setSuggestCount((n) => Math.max(1, n - 1))}
              disabled={isSuggesting}
              className="px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted transition-colors disabled:opacity-40"
              title="Fewer questions"
            >−</button>
            <span className="px-1 text-xs font-medium text-foreground min-w-[18px] text-center">{suggestCount}</span>
            <button
              type="button"
              onClick={() => setSuggestCount((n) => Math.min(25, n + 1))}
              disabled={isSuggesting}
              className="px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted transition-colors disabled:opacity-40"
              title="More questions"
            >+</button>
          </div>
          <button
            onClick={suggestQuestions}
            disabled={isSuggesting}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-primary/40 rounded-[calc(var(--radius)-2px)] text-primary hover:bg-primary/5 transition-colors disabled:opacity-50"
          >
            {isSuggesting ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" />Generating…</>
            ) : (
              <><Sparkles className="w-3.5 h-3.5" />Suggest with AI</>
            )}
          </button>
          <button
            onClick={addQuestion}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border rounded-[calc(var(--radius)-2px)] text-muted-foreground hover:bg-muted transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Question
          </button>
          <button
            onClick={() => saveMutation.mutate(questions)}
            disabled={saveMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-[calc(var(--radius)-2px)] hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {saveMutation.isPending ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" />Saving…</>
            ) : (
              <><Save className="w-3.5 h-3.5" />Save Questions</>
            )}
          </button>
        </div>
      </div>

      <div className="p-5">
        {questions.length === 0 ? (
          <div className="text-center py-10 text-muted-foreground">
            <HelpCircle className="w-8 h-8 mx-auto mb-3 opacity-30" />
            <p className="text-sm font-medium">No questions yet</p>
            <p className="text-xs mt-1 max-w-xs mx-auto">
              Add questions to specific PDF pages — learners will see them as they reach each page.
            </p>
            <button
              onClick={addQuestion}
              className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Add First Question
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {displayOrder.map(({ q, i }) => (
              <QuestionCard
                key={i}
                q={q}
                index={displayOrder.findIndex((d) => d.i === i)}
                onChange={(updated) => updateQuestion(i, updated)}
                onDelete={() => deleteQuestion(i)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
