'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  ArrowLeft, Search, CheckSquare, Square, ChevronDown, ChevronUp,
  Loader2, FileQuestion, Clock, Target, Shuffle, Eye, Save,
  AlertCircle, Filter, GraduationCap,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────────
interface PoolQuestion {
  id: string;
  content_item_id: string;
  content_title: string | null;
  question_type: string;
  question_text: string;
  options: Array<{ text: string; is_correct: boolean }> | null;
  correct_answer: string | null;
  explanation: string | null;
  blooms_level: string | null;
  difficulty_label: string | null;
  topic_primary: string | null;
}

// ── Difficulty badge ───────────────────────────────────────────────────────────
function DiffBadge({ level }: { level: string | null }) {
  if (!level) return null;
  const map: Record<string, string> = {
    easy: 'bg-green-50 text-green-700 border-green-200',
    medium: 'bg-amber-50 text-amber-700 border-amber-200',
    hard: 'bg-red-50 text-red-700 border-red-200',
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${map[level] ?? 'bg-muted text-muted-foreground border-border'}`}>
      {level}
    </span>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function NewAssessmentPage() {
  const { id: spaceId } = useParams<{ id: string }>();
  const router = useRouter();

  // Pool
  const [poolQuestions, setPoolQuestions] = useState<PoolQuestion[]>([]);
  const [loadingPool, setLoadingPool] = useState(true);

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Config
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [timeLimitMinutes, setTimeLimitMinutes] = useState<string>('');
  const [maxAttempts, setMaxAttempts] = useState('1');
  const [passPct, setPassPct] = useState('70');
  const [shuffleQ, setShuffleQ] = useState(true);
  const [shuffleOpts, setShuffleOpts] = useState(true);
  const [showAnswers, setShowAnswers] = useState(true);

  // Filter / search
  const [search, setSearch] = useState('');
  const [filterContent, setFilterContent] = useState('');
  const [filterDiff, setFilterDiff] = useState('');
  const [expandedQ, setExpandedQ] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [publishNow, setPublishNow] = useState(true);  // default ON — creator intent is to publish

  useEffect(() => {
    fetch(`/api/spaces/${spaceId}/quiz-pool`, { credentials: 'include' })
      .then(r => r.json())
      .then(d => setPoolQuestions(d.questions ?? []))
      .catch(() => toast.error('Could not load question pool'))
      .finally(() => setLoadingPool(false));
  }, [spaceId]);

  const contentTitles = Array.from(new Set(poolQuestions.map(q => q.content_title).filter(Boolean))) as string[];

  const filtered = poolQuestions.filter(q => {
    if (search && !q.question_text.toLowerCase().includes(search.toLowerCase())) return false;
    if (filterContent && q.content_title !== filterContent) return false;
    if (filterDiff && q.difficulty_label !== filterDiff) return false;
    return true;
  });

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelectedIds(new Set(filtered.map(q => q.id)));
  const clearAll = () => setSelectedIds(new Set());

  const handleCreate = async () => {
    if (!title.trim()) { toast.error('Give the assessment a title'); return; }
    if (selectedIds.size === 0) { toast.error('Select at least one question'); return; }

    setSaving(true);
    try {
      const r = await fetch(`/api/spaces/${spaceId}/assessments`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim() || undefined,
          question_ids: Array.from(selectedIds),
          time_limit_minutes: timeLimitMinutes ? parseInt(timeLimitMinutes) : null,
          max_attempts: parseInt(maxAttempts) || 1,
          pass_pct: parseFloat(passPct) || 70,
          shuffle_questions: shuffleQ,
          shuffle_options: shuffleOpts,
          show_answers_after: showAnswers,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || 'Failed to create assessment');

      // Auto-publish if requested (default ON) — backend returns "id" not "assessment_id"
      const newAssessmentId = data.id || data.assessment_id;
      if (publishNow && newAssessmentId) {
        await fetch(`/api/spaces/${spaceId}/assessments/${newAssessmentId}/publish`, {
          method: 'POST',
          credentials: 'include',
        }).catch(() => {});
      }

      toast.success(publishNow ? 'Assessment created and published! Students can now take it.' : 'Assessment created as draft. Publish it from the space page when ready.');
      router.push(`/spaces/${spaceId}`);
    } catch (e: any) {
      toast.error(e.message);
    } finally { setSaving(false); }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-white sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link href={`/spaces/${spaceId}`} className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="w-4 h-4" /> Back to space
            </Link>
            <span className="text-border">·</span>
            <span className="text-sm font-semibold text-foreground flex items-center gap-1.5">
              <GraduationCap className="w-4 h-4 text-primary" /> New Assessment
            </span>
          </div>
          <button
            onClick={handleCreate}
            disabled={saving || selectedIds.size === 0 || !title.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Create Assessment
          </button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-6 flex gap-6">
        {/* LEFT: Question picker */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-foreground">
              Question Pool
              <span className="ml-2 text-sm text-muted-foreground font-normal">
                {selectedIds.size} selected of {poolQuestions.length}
              </span>
            </h2>
            <div className="flex gap-2">
              <button onClick={selectAll} className="text-xs text-primary hover:underline">Select all visible</button>
              <span className="text-border">·</span>
              <button onClick={clearAll} className="text-xs text-muted-foreground hover:underline">Clear</button>
            </div>
          </div>

          {/* Filters */}
          <div className="flex gap-2 mb-4 flex-wrap">
            <div className="relative flex-1 min-w-[180px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search questions…"
                className="w-full pl-8 pr-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-muted focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <select
              value={filterContent}
              onChange={e => setFilterContent(e.target.value)}
              className="text-sm border border-border rounded-[var(--radius)] bg-muted px-2 py-2 focus:outline-none"
            >
              <option value="">All content</option>
              {contentTitles.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <select
              value={filterDiff}
              onChange={e => setFilterDiff(e.target.value)}
              className="text-sm border border-border rounded-[var(--radius)] bg-muted px-2 py-2 focus:outline-none"
            >
              <option value="">All difficulty</option>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </div>

          {loadingPool ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16">
              <AlertCircle className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">
                {poolQuestions.length === 0
                  ? 'No quiz questions found. Generate quiz content for items in this space first.'
                  : 'No questions match your filters.'}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filtered.map(q => {
                const sel = selectedIds.has(q.id);
                const exp = expandedQ === q.id;
                return (
                  <div
                    key={q.id}
                    className={`border rounded-xl bg-white overflow-hidden transition-colors ${sel ? 'border-primary/40 bg-primary/5' : 'border-border'}`}
                  >
                    <div className="flex items-start gap-3 p-3">
                      <button onClick={() => toggleSelect(q.id)} className="flex-shrink-0 mt-0.5">
                        {sel
                          ? <CheckSquare className="w-5 h-5 text-primary" />
                          : <Square className="w-5 h-5 text-muted-foreground" />
                        }
                      </button>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground leading-snug">{q.question_text}</p>
                        <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                          {q.content_title && (
                            <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                              {q.content_title}
                            </span>
                          )}
                          <span className="text-[10px] px-1.5 py-0.5 rounded border bg-blue-50 text-blue-700 border-blue-200 font-medium uppercase">
                            {q.question_type}
                          </span>
                          <DiffBadge level={q.difficulty_label} />
                          {q.blooms_level && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-purple-50 text-purple-700 border-purple-200 font-medium">
                              {q.blooms_level}
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => setExpandedQ(exp ? null : q.id)}
                        className="text-muted-foreground flex-shrink-0"
                      >
                        {exp ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                    </div>
                    {exp && q.options && (
                      <div className="px-3 pb-3 border-t border-border bg-muted/20 space-y-1.5 pt-2">
                        {q.options.map((opt, i) => (
                          <div key={i} className={`flex items-start gap-2 text-xs p-2 rounded ${opt.is_correct ? 'bg-green-50 text-green-800' : 'text-foreground'}`}>
                            <span className="font-medium">{String.fromCharCode(65 + i)}.</span>
                            <span>{opt.text}</span>
                            {opt.is_correct && <span className="ml-auto font-semibold text-green-700">✓ correct</span>}
                          </div>
                        ))}
                        {q.explanation && (
                          <p className="text-xs text-blue-700 bg-blue-50 p-2 rounded mt-1">{q.explanation}</p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* RIGHT: Config panel */}
        <div className="w-80 flex-shrink-0">
          <div className="border border-border rounded-xl bg-white p-5 space-y-5 sticky top-24">
            <h3 className="font-semibold text-foreground">Assessment Settings</h3>

            {/* Title */}
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">Title *</label>
              <input
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="e.g. Module 1 Final Test"
                className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            {/* Description */}
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">Description <span className="text-muted-foreground font-normal">(optional)</span></label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={2}
                placeholder="Instructions for learners…"
                className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary resize-none"
              />
            </div>

            {/* Time limit */}
            <div>
              <label className="text-xs font-medium text-foreground flex items-center gap-1 mb-1">
                <Clock className="w-3.5 h-3.5" /> Time Limit
                <span className="text-muted-foreground font-normal">(optional)</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={1}
                  value={timeLimitMinutes}
                  onChange={e => setTimeLimitMinutes(e.target.value)}
                  placeholder="No limit"
                  className="flex-1 text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <span className="text-xs text-muted-foreground">min</span>
              </div>
            </div>

            {/* Attempts + pass */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">Max Attempts</label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={maxAttempts}
                  onChange={e => setMaxAttempts(e.target.value)}
                  className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-foreground flex items-center gap-1 mb-1">
                  <Target className="w-3 h-3" /> Pass %
                </label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={passPct}
                  onChange={e => setPassPct(e.target.value)}
                  className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>

            {/* Toggles */}
            <div className="space-y-2 border-t border-border pt-4">
              {[
                { label: 'Shuffle questions', val: shuffleQ, set: setShuffleQ },
                { label: 'Shuffle answer options', val: shuffleOpts, set: setShuffleOpts },
                { label: 'Show answers after submit', val: showAnswers, set: setShowAnswers },
              ].map(({ label, val, set }) => (
                <label key={label} className="flex items-center justify-between cursor-pointer">
                  <span className="text-sm text-foreground">{label}</span>
                  <button
                    onClick={() => set(!val)}
                    className={`w-10 h-5 rounded-full transition-colors relative ${val ? 'bg-primary' : 'bg-muted border border-border'}`}
                  >
                    <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${val ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </button>
                </label>
              ))}

              {/* Publish toggle — highlighted */}
              <div className={`flex items-center justify-between p-2 rounded-[var(--radius)] border ${publishNow ? 'border-emerald-300 bg-emerald-50' : 'border-amber-300 bg-amber-50'}`}>
                <div>
                  <p className={`text-sm font-semibold ${publishNow ? 'text-emerald-800' : 'text-amber-800'}`}>
                    {publishNow ? '✓ Publish immediately' : 'Save as draft'}
                  </p>
                  <p className={`text-xs ${publishNow ? 'text-emerald-700' : 'text-amber-700'}`}>
                    {publishNow ? 'Students can take this assessment right away' : 'Only you can see it — publish later from the space'}
                  </p>
                </div>
                <button
                  onClick={() => setPublishNow(!publishNow)}
                  className={`w-10 h-5 rounded-full transition-colors relative flex-shrink-0 ${publishNow ? 'bg-emerald-600' : 'bg-muted border border-border'}`}
                >
                  <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${publishNow ? 'translate-x-5' : 'translate-x-0.5'}`} />
                </button>
              </div>
            </div>

            {/* Summary */}
            <div className="bg-muted rounded-[var(--radius)] p-3 text-sm">
              <p className="text-foreground font-medium">{selectedIds.size} questions selected</p>
              <p className="text-muted-foreground text-xs mt-0.5">
                Pass at {passPct}% · {maxAttempts} attempt{parseInt(maxAttempts) !== 1 ? 's' : ''} ·{' '}
                {timeLimitMinutes ? `${timeLimitMinutes} min` : 'No time limit'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
