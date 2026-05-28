'use client';

/**
 * /create/course — Auto-Course Builder
 *
 * A 4-step wizard:
 *   Step 1 — Upload PDF
 *   Step 2 — Review & edit lesson plan (chapters, YouTube videos)
 *   Step 3 — Live progress (polls every 3s until all chapters done)
 *   Step 4 — Done (link to the new Learning Space)
 */

import { useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import {
  Upload, Loader2, ChevronRight, ChevronLeft, Check,
  BookOpen, Youtube, X, FileText, Zap, Eye, EyeOff,
  RefreshCw, ExternalLink, CheckCircle2, Clock, AlertCircle,
  GripVertical, Plus, Minus, Film,
} from 'lucide-react';
import { toast } from 'sonner';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChapterPlan {
  title: string;
  page_start: number;
  page_end: number;
  key_topics: string[];
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  include: boolean;
  youtube_search_query: string;
}

const DIFFICULTY_STYLES: Record<string, { label: string; className: string }> = {
  beginner:     { label: 'Beginner',     className: 'bg-green-50 text-green-700 border-green-200' },
  intermediate: { label: 'Intermediate', className: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
  advanced:     { label: 'Advanced',     className: 'bg-red-50 text-red-700 border-red-200' },
};

interface LessonPlan {
  course_title: string;
  description: string;
  estimated_duration: string;
  objectives: string[];
  chapters: ChapterPlan[];
  redis_token: string;
  total_pages: number;
}

interface YouTubeVideo {
  video_id: string;
  title: string;
  channel: string;
  thumbnail_url: string;
  embed_url: string;
}

interface YouTubeAttachment {
  chapter_index: number;
  video_id: string;
  title: string;
  thumbnail_url: string;
}

interface ChapterConfig {
  title: string;
  page_start: number;
  page_end: number;
  include: boolean;
  generate_tasks: string[];
  quiz_count: number;
}

interface ChapterJobStatus {
  chapter_title: string;
  content_item_id: string;
  job_id: string | null;
  status: string;
  progress_pct: number;
}

interface ProgressResponse {
  space_id: string;
  chapters: ChapterJobStatus[];
  completed: number;
  total: number;
  done: boolean;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const ALL_TASKS = ['summary', 'quiz', 'flashcards', 'glossary'];
const TASK_LABELS: Record<string, string> = {
  summary: 'Summary',
  quiz: 'Quiz',
  flashcards: 'Flashcards',
  glossary: 'Glossary',
};

const STEP_LABELS = ['Upload PDF', 'Review Plan', 'Generate', 'Done'];

// ─── Sub-components ───────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {STEP_LABELS.map((label, i) => (
        <div key={i} className="flex items-center">
          <div className="flex flex-col items-center">
            <div
              className={cn(
                'w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold transition-colors',
                i < current
                  ? 'bg-primary text-white'
                  : i === current
                  ? 'bg-primary/10 text-primary border-2 border-primary'
                  : 'bg-muted text-muted-foreground',
              )}
            >
              {i < current ? <Check className="w-4 h-4" /> : i + 1}
            </div>
            <span
              className={cn(
                'text-[10px] mt-1 font-medium whitespace-nowrap',
                i === current ? 'text-primary' : 'text-muted-foreground',
              )}
            >
              {label}
            </span>
          </div>
          {i < STEP_LABELS.length - 1 && (
            <div
              className={cn(
                'h-px w-16 mx-1 mb-4 transition-colors',
                i < current ? 'bg-primary' : 'bg-border',
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  if (status === 'completed') {
    return (
      <span className="flex items-center gap-1 text-xs text-green-700 bg-green-50 border border-green-200 rounded-full px-2 py-0.5">
        <CheckCircle2 className="w-3 h-3" /> Done
      </span>
    );
  }
  if (status === 'processing') {
    return (
      <span className="flex items-center gap-1 text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5">
        <Loader2 className="w-3 h-3 animate-spin" /> Processing
      </span>
    );
  }
  if (status === 'failed') {
    return (
      <span className="flex items-center gap-1 text-xs text-red-700 bg-red-50 border border-red-200 rounded-full px-2 py-0.5">
        <AlertCircle className="w-3 h-3" /> Failed
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-xs text-muted-foreground bg-muted border border-border rounded-full px-2 py-0.5">
      <Clock className="w-3 h-3" /> Queued
    </span>
  );
}

// ─── YouTube picker for a chapter ────────────────────────────────────────────

function YouTubePicker({
  chapterIndex,
  searchQuery,
  attached,
  onAttach,
  onDetach,
}: {
  chapterIndex: number;
  searchQuery: string;
  attached: YouTubeAttachment | null;
  onAttach: (v: YouTubeAttachment) => void;
  onDetach: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<YouTubeVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setSearched(false);
    try {
      const r = await fetch(`/api/course-builder/youtube?query=${encodeURIComponent(q)}`);
      const data = await r.json();
      setResults(Array.isArray(data) ? data : []);
      setSearched(true);
    } catch (e: any) {
      const isNotConfigured = e?.status === 503 || String(e?.detail ?? '').includes('not configured');
      toast.error(isNotConfigured
        ? 'YouTube search not configured — ask admin to add YOUTUBE_API_KEY to server .env'
        : 'YouTube search failed — try again');
    } finally {
      setLoading(false);
    }
  }, []);

  if (attached) {
    return (
      <div className="flex items-center gap-2 mt-2 p-2 bg-red-50 border border-red-100 rounded-lg">
        <img
          src={attached.thumbnail_url}
          alt=""
          className="w-14 h-10 object-cover rounded"
        />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium truncate text-foreground">{attached.title}</p>
          <p className="text-[10px] text-muted-foreground">YouTube video</p>
        </div>
        <button
          onClick={onDetach}
          className="text-muted-foreground hover:text-foreground"
          title="Remove video"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="mt-2">
      {!open ? (
        <button
          onClick={() => {
            setOpen(true);
            if (!searched) search(searchQuery);
          }}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors"
        >
          <Youtube className="w-3.5 h-3.5 text-red-500" />
          Add YouTube video (optional)
        </button>
      ) : (
        <div className="border border-border rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-foreground">Pick a YouTube video</span>
            <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          {loading && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Searching YouTube…
            </div>
          )}
          {!loading && searched && results.length === 0 && (
            <p className="text-xs text-muted-foreground py-2">No videos found</p>
          )}
          <div className="space-y-1.5 max-h-56 overflow-y-auto">
            {results.map((v) => (
              <button
                key={v.video_id}
                onClick={() => {
                  onAttach({
                    chapter_index: chapterIndex,
                    video_id: v.video_id,
                    title: v.title,
                    thumbnail_url: v.thumbnail_url,
                  });
                  setOpen(false);
                }}
                className="w-full flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 text-left transition-colors"
              >
                <img
                  src={v.thumbnail_url}
                  alt=""
                  className="w-16 h-11 object-cover rounded flex-shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-foreground line-clamp-2">{v.title}</p>
                  <p className="text-[10px] text-muted-foreground">{v.channel}</p>
                </div>
              </button>
            ))}
          </div>
          <button
            onClick={() => search(searchQuery)}
            className="text-xs text-primary hover:underline flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" /> Refresh results
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function CourseBuilderPage() {
  const router = useRouter();

  // Wizard state
  const [step, setStep] = useState(0);

  // Step 1
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Step 2
  const [lessonPlan, setLessonPlan] = useState<LessonPlan | null>(null);
  const [chapters, setChapters] = useState<ChapterConfig[]>([]);
  const [spaceTitle, setSpaceTitle] = useState('');
  const [spaceDesc, setSpaceDesc] = useState('');
  const [ytAttachments, setYtAttachments] = useState<Map<number, YouTubeAttachment>>(new Map());
  const [generating, setGenerating] = useState(false);

  // Step 3
  const [spaceId, setSpaceId] = useState('');
  const [progressData, setProgressData] = useState<ProgressResponse | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Step 1: Upload + Analyze ─────────────────────────────────────────────

  const handleFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('Please upload a PDF file');
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      toast.error('PDF must be under 50 MB');
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await fetch('/api/course-builder/analyze', { method: 'POST', body: form });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || err.error || `Error ${r.status}`);
      }
      const plan: LessonPlan = await r.json();
      setLessonPlan(plan);
      setSpaceTitle(plan.course_title);
      setSpaceDesc(plan.description);
      setChapters(
        plan.chapters.map((ch) => ({
          title: ch.title,
          page_start: ch.page_start,
          page_end: ch.page_end,
          include: ch.include,
          generate_tasks: [...ALL_TASKS],
          quiz_count: 8,
        })),
      );
      setStep(1);
      toast.success(`Lesson plan ready — ${plan.chapters.length} chapters identified`);
    } catch (e: any) {
      toast.error(e.message || 'Analysis failed — please try again');
    } finally {
      setUploading(false);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  // ── Step 2 helpers ────────────────────────────────────────────────────────

  const toggleChapter = (i: number) => {
    setChapters((prev) =>
      prev.map((ch, idx) => (idx === i ? { ...ch, include: !ch.include } : ch)),
    );
  };

  const toggleTask = (chIdx: number, task: string) => {
    setChapters((prev) =>
      prev.map((ch, idx) => {
        if (idx !== chIdx) return ch;
        const has = ch.generate_tasks.includes(task);
        const updated = has
          ? ch.generate_tasks.filter((t) => t !== task)
          : [...ch.generate_tasks, task];
        return { ...ch, generate_tasks: updated };
      }),
    );
  };

  const setQuizCount = (chIdx: number, val: number) => {
    setChapters((prev) =>
      prev.map((ch, idx) => (idx === chIdx ? { ...ch, quiz_count: val } : ch)),
    );
  };

  const attachYt = (v: YouTubeAttachment) => {
    setYtAttachments((prev) => new Map(prev).set(v.chapter_index, v));
  };

  const detachYt = (chIdx: number) => {
    setYtAttachments((prev) => {
      const m = new Map(prev);
      m.delete(chIdx);
      return m;
    });
  };

  // ── Step 2 → Step 3: Generate ────────────────────────────────────────────

  const handleGenerate = async () => {
    if (!lessonPlan) return;
    const included = chapters.filter((ch) => ch.include);
    if (included.length === 0) {
      toast.error('Please include at least one chapter');
      return;
    }
    setGenerating(true);
    try {
      const r = await fetch('/api/course-builder/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          redis_token: lessonPlan.redis_token,
          space_title: spaceTitle || lessonPlan.course_title,
          space_description: spaceDesc,
          chapters: included,
          youtube_videos: Array.from(ytAttachments.values()),
        }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        // 410 = Redis session expired (2h TTL) — guide user to re-upload
        if (r.status === 410) {
          throw new Error('Your session expired (2-hour limit). Please go back and re-upload your PDF.');
        }
        throw new Error(err.detail || err.error || `Error ${r.status}`);
      }
      const data = await r.json();
      setSpaceId(data.space_id);
      setProgressData(null);
      setStep(2);
      startPolling(data.space_id);
    } catch (e: any) {
      toast.error(e.message || 'Generation failed — please try again');
    } finally {
      setGenerating(false);
    }
  };

  // ── Step 3: Poll progress ─────────────────────────────────────────────────

  const startPolling = useCallback((sid: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    const poll = async () => {
      try {
        const r = await fetch(`/api/course-builder/progress/${sid}`);
        if (!r.ok) return;
        const data: ProgressResponse = await r.json();
        setProgressData(data);
        if (data.done) {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          setTimeout(() => setStep(3), 1000);
        }
      } catch {}
    };
    poll();
    pollRef.current = setInterval(poll, 3000);
  }, []);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div>
      <Header
        title="Course Builder"
        subtitle="Upload a PDF → AI designs your lesson plan → generate a full Learning Space in minutes"
      />
      <div className="max-w-4xl mx-auto px-4 py-8">

      <StepIndicator current={step} />

      {/* ── STEP 0: Upload ── */}
      {step === 0 && (
        <div className="bg-card border border-border rounded-[var(--radius)] p-8">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              'border-2 border-dashed rounded-xl p-16 flex flex-col items-center justify-center cursor-pointer transition-colors',
              dragOver
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/50 hover:bg-muted/30',
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
              }}
            />
            {uploading ? (
              <>
                <Loader2 className="w-10 h-10 text-primary animate-spin mb-3" />
                <p className="text-sm font-medium text-foreground">Analyzing your PDF…</p>
                <p className="text-xs text-muted-foreground mt-1">
                  AI is reading your document and designing chapters
                </p>
              </>
            ) : (
              <>
                <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
                  <FileText className="w-7 h-7 text-primary" />
                </div>
                <p className="text-sm font-semibold text-foreground">
                  Drop your PDF here, or click to browse
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Supports up to 300 pages · 50 MB · Text-based PDFs only
                </p>
              </>
            )}
          </div>

          <div className="mt-6 grid grid-cols-3 gap-4">
            {[
              { icon: BookOpen, label: 'AI Chapter Plan', desc: 'Intelligent chapter breakdown with objectives' },
              { icon: Youtube, label: 'YouTube Videos', desc: 'Free educational videos per chapter' },
              { icon: Zap, label: 'Full Generation', desc: 'Summary, quiz, flashcards, glossary in parallel' },
            ].map(({ icon: Icon, label, desc }) => (
              <div key={label} className="p-4 rounded-xl border border-border bg-muted/20 flex flex-col gap-1.5">
                <Icon className="w-5 h-5 text-primary" />
                <p className="text-xs font-semibold text-foreground">{label}</p>
                <p className="text-[11px] text-muted-foreground leading-snug">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── STEP 1: Review Plan ── */}
      {step === 1 && lessonPlan && (
        <div className="space-y-5">
          {/* Space info */}
          <div className="bg-card border border-border rounded-[var(--radius)] p-5 space-y-4">
            <h2 className="text-sm font-semibold text-foreground">Course Details</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Course Title
                </label>
                <input
                  value={spaceTitle}
                  onChange={(e) => setSpaceTitle(e.target.value)}
                  className="mt-1 w-full px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Description
                </label>
                <textarea
                  value={spaceDesc}
                  onChange={(e) => setSpaceDesc(e.target.value)}
                  rows={2}
                  className="mt-1 w-full px-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                />
              </div>
            </div>
            <div className="flex gap-4 text-[11px] text-muted-foreground border-t border-border pt-3">
              <span>📄 {lessonPlan.total_pages} pages</span>
              <span>⏱ {lessonPlan.estimated_duration || 'estimated duration'}</span>
              <span>📚 {chapters.filter((c) => c.include).length} / {chapters.length} chapters included</span>
            </div>
          </div>

          {/* Objectives */}
          {lessonPlan.objectives.length > 0 && (
            <div className="bg-card border border-border rounded-[var(--radius)] p-5">
              <h2 className="text-sm font-semibold text-foreground mb-3">Learning Objectives</h2>
              <ul className="space-y-1.5">
                {lessonPlan.objectives.map((obj, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-foreground">
                    <span className="w-4 h-4 rounded-full bg-primary/10 text-primary flex-shrink-0 flex items-center justify-center text-[9px] font-bold mt-0.5">
                      {i + 1}
                    </span>
                    {obj}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Chapters */}
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-foreground">
              Chapters ({chapters.filter((c) => c.include).length} included)
            </h2>
            {chapters.map((ch, i) => {
              const plan = lessonPlan.chapters[i];
              return (
                <div
                  key={i}
                  className={cn(
                    'bg-card border rounded-[var(--radius)] transition-colors',
                    ch.include ? 'border-border' : 'border-border/50 opacity-60',
                  )}
                >
                  {/* Chapter header */}
                  <div className="p-4 flex items-start gap-3">
                    <button
                      onClick={() => toggleChapter(i)}
                      className={cn(
                        'mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 transition-colors',
                        ch.include
                          ? 'border-primary bg-primary text-white'
                          : 'border-border bg-background',
                      )}
                    >
                      {ch.include && <Check className="w-3 h-3" />}
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-semibold text-foreground">{ch.title}</span>
                        <span className="text-[10px] text-muted-foreground">
                          pp. {ch.page_start}–{ch.page_end}
                        </span>
                        {plan.difficulty && (() => {
                          const d = DIFFICULTY_STYLES[plan.difficulty] ?? DIFFICULTY_STYLES.intermediate;
                          return (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${d.className}`}>
                              {d.label}
                            </span>
                          );
                        })()}
                      </div>
                      {plan.key_topics.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {plan.key_topics.map((t) => (
                            <span
                              key={t}
                              className="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => toggleChapter(i)}
                      className="text-muted-foreground hover:text-foreground ml-2"
                      title={ch.include ? 'Exclude chapter' : 'Include chapter'}
                    >
                      {ch.include ? (
                        <Eye className="w-4 h-4" />
                      ) : (
                        <EyeOff className="w-4 h-4" />
                      )}
                    </button>
                  </div>

                  {/* Chapter options (only if included) */}
                  {ch.include && (
                    <div className="border-t border-border px-4 pb-4 pt-3 space-y-3">
                      {/* Generate tasks */}
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
                          Generate
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {ALL_TASKS.map((task) => (
                            <button
                              key={task}
                              onClick={() => toggleTask(i, task)}
                              className={cn(
                                'text-xs px-2.5 py-1 rounded-lg border transition-colors',
                                ch.generate_tasks.includes(task)
                                  ? 'bg-primary text-white border-primary'
                                  : 'bg-background text-muted-foreground border-border hover:border-primary/50',
                              )}
                            >
                              {TASK_LABELS[task]}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Quiz count (only if quiz is selected) */}
                      {ch.generate_tasks.includes('quiz') && (
                        <div className="flex items-center gap-2">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                            Quiz questions:
                          </p>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => setQuizCount(i, Math.max(1, ch.quiz_count - 1))}
                              className="w-5 h-5 rounded border border-border flex items-center justify-center hover:bg-muted"
                            >
                              <Minus className="w-3 h-3" />
                            </button>
                            <span className="text-xs font-medium w-6 text-center">{ch.quiz_count}</span>
                            <button
                              onClick={() => setQuizCount(i, Math.min(25, ch.quiz_count + 1))}
                              className="w-5 h-5 rounded border border-border flex items-center justify-center hover:bg-muted"
                            >
                              <Plus className="w-3 h-3" />
                            </button>
                          </div>
                        </div>
                      )}

                      {/* YouTube picker */}
                      <YouTubePicker
                        chapterIndex={i}
                        searchQuery={plan.youtube_search_query}
                        attached={ytAttachments.get(i) || null}
                        onAttach={attachYt}
                        onDetach={() => detachYt(i)}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between pt-2">
            <button
              onClick={() => setStep(0)}
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronLeft className="w-4 h-4" /> Back
            </button>
            <button
              onClick={handleGenerate}
              disabled={generating || chapters.filter((c) => c.include).length === 0}
              className="flex items-center gap-2 px-5 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {generating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Creating space…
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  Generate Course →
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 2: Progress ── */}
      {step === 2 && (
        <div className="bg-card border border-border rounded-[var(--radius)] p-6 space-y-5">
          <div className="flex items-center gap-3">
            <Loader2 className="w-5 h-5 text-primary animate-spin flex-shrink-0" />
            <div>
              <h2 className="text-sm font-semibold text-foreground">
                Generating your Learning Space…
              </h2>
              <p className="text-xs text-muted-foreground">
                AI is processing each chapter in parallel. This typically takes 2–5 minutes.
              </p>
            </div>
          </div>

          {/* Overall progress bar */}
          {progressData && (
            <div>
              <div className="flex justify-between text-[11px] text-muted-foreground mb-1">
                <span>{progressData.completed} of {progressData.total} chapters complete</span>
                <span>
                  {progressData.total > 0
                    ? Math.round((progressData.completed / progressData.total) * 100)
                    : 0}%
                </span>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-500"
                  style={{
                    width: `${
                      progressData.total > 0
                        ? (progressData.completed / progressData.total) * 100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>
          )}

          {/* Per-chapter status */}
          <div className="space-y-2">
            {(progressData?.chapters || []).map((ch, i) => (
              <div
                key={i}
                className="flex items-center justify-between gap-3 py-2 border-b border-border last:border-0"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-foreground truncate">{ch.chapter_title}</p>
                  {ch.status === 'processing' && ch.progress_pct > 0 && (
                    <div className="mt-1 h-1 bg-muted rounded-full overflow-hidden w-32">
                      <div
                        className="h-full bg-primary/60 rounded-full transition-all"
                        style={{ width: `${ch.progress_pct}%` }}
                      />
                    </div>
                  )}
                </div>
                <StatusPill status={ch.status} />
              </div>
            ))}
            {(!progressData || progressData.chapters.length === 0) && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground py-4">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Waiting for jobs to start…
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── STEP 3: Done ── */}
      {step === 3 && (
        <div className="bg-card border border-border rounded-[var(--radius)] p-10 text-center space-y-5">
          <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto">
            <CheckCircle2 className="w-8 h-8 text-green-600" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-foreground mb-1">
              Your course is ready! 🎉
            </h2>
            <p className="text-sm text-muted-foreground">
              All chapters have been generated with summaries, quizzes, flashcards, and glossary.
            </p>
          </div>

          {progressData && (
            <div className="inline-flex items-center gap-4 bg-muted/30 rounded-xl px-6 py-3 text-sm">
              <div className="text-center">
                <p className="text-lg font-bold text-foreground">{progressData.completed}</p>
                <p className="text-[11px] text-muted-foreground">Chapters</p>
              </div>
              <div className="w-px h-8 bg-border" />
              <div className="text-center">
                <p className="text-lg font-bold text-foreground">
                  {progressData.chapters.filter((c) => c.status === 'completed').length * 4}
                </p>
                <p className="text-[11px] text-muted-foreground">AI Outputs</p>
              </div>
            </div>
          )}

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
            <button
              onClick={() => router.push(`/spaces/${spaceId}`)}
              className="flex items-center gap-2 px-6 py-2.5 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <BookOpen className="w-4 h-4" />
              Open Learning Space
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => {
                setStep(0);
                setLessonPlan(null);
                setChapters([]);
                setSpaceTitle('');
                setSpaceDesc('');
                setYtAttachments(new Map());
                setProgressData(null);
                setSpaceId('');
              }}
              className="flex items-center gap-2 px-5 py-2.5 border border-border text-foreground rounded-lg text-sm font-medium hover:bg-muted/50 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Build another course
            </button>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}