'use client';

import { useState, useEffect, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useUser } from '@/lib/hooks/use-user';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { InteractivePDFEditor } from '@/components/library/interactive-pdf-editor';
import { toast } from 'sonner';
import {
  ArrowLeft, FileText, Youtube, Globe, Video, Loader2,
  CheckCircle2, AlertCircle, Clock, Loader, Zap,
  Eye, EyeOff, BookOpen, RefreshCw, ChevronDown, ChevronUp,
  Brain, ClipboardList, Layers, Book, HelpCircle, BarChart2, Tag, CheckCheck, XCircle,
  Pencil, X, Upload, Plus, Sparkles,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface LibraryItem {
  id: string;
  title: string | null;
  content_type: string;
  experience_mode: string;
  is_public: boolean;
  status: string;
  source_url: string | null;
  language: string;
  word_count: number | null;
  chunk_count: number;
  creator_id: string | null;
  creator_name: string | null;
  space_count: number;
  created_at: string;
  updated_at: string;
  interactions?: string[];
}

interface AIOutput {
  content_item_id: string;
  output_type: string;
  language: string;
  status: string;
  payload: Record<string, any> | null;
  model: string | null;
  provider: string | null;
  created_at: string;
  updated_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function typeIcon(ct: string, cls = 'w-5 h-5') {
  if (ct === 'youtube' || ct === 'vimeo') return <Youtube className={cls} />;
  if (ct === 'video_upload') return <Video className={cls} />;
  if (ct === 'html_page') return <Globe className={cls} />;
  return <FileText className={cls} />;
}

function typeColor(ct: string): string {
  if (ct === 'pdf')          return 'text-red-700 bg-red-50 border-red-200';
  if (ct === 'youtube')      return 'text-red-700 bg-red-50 border-red-200';
  if (ct === 'vimeo')        return 'text-blue-700 bg-blue-50 border-blue-200';
  if (ct === 'video_upload') return 'text-purple-700 bg-purple-50 border-purple-200';
  if (ct === 'html_page')    return 'text-teal-700 bg-teal-50 border-teal-200';
  return 'text-muted-foreground bg-muted border-border';
}

function fmtDate(ts: string) {
  return new Date(ts).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
  });
}

function fmtDateTime(ts: string) {
  return new Date(ts).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

const OUTPUT_META: Record<string, { label: string; icon: React.ComponentType<any>; color: string }> = {
  summary:     { label: 'Summary',     icon: Brain,        color: 'text-blue-600 bg-blue-50 border-blue-200' },
  quiz:        { label: 'Quiz',        icon: ClipboardList, color: 'text-purple-600 bg-purple-50 border-purple-200' },
  flashcards:  { label: 'Flashcards',  icon: Layers,       color: 'text-amber-600 bg-amber-50 border-amber-200' },
  glossary:    { label: 'Glossary',    icon: Book,         color: 'text-teal-600 bg-teal-50 border-teal-200' },
  faq:         { label: 'FAQ',         icon: HelpCircle,   color: 'text-rose-600 bg-rose-50 border-rose-200' },
  infographic: { label: 'Infographic', icon: BarChart2,    color: 'text-green-600 bg-green-50 border-green-200' },
};

// ── Output renderers ──────────────────────────────────────────────────────────

function SummaryView({ payload }: { payload: Record<string, any> }) {
  const text: string = payload?.summary || payload?.text || JSON.stringify(payload, null, 2);
  return (
    <div className="prose prose-sm max-w-none text-foreground whitespace-pre-wrap leading-relaxed text-sm">
      {text}
    </div>
  );
}

function QuizView({ payload }: { payload: Record<string, any> }) {
  const questions: any[] = payload?.questions || [];
  const [revealed, setRevealed] = useState<Set<number>>(new Set());

  if (!questions.length) {
    return <p className="text-sm text-muted-foreground">No questions available.</p>;
  }

  return (
    <div className="space-y-4">
      {questions.map((q: any, i: number) => (
        <div key={i} className="border border-border rounded-[var(--radius)] p-4">
          <p className="font-medium text-sm text-primary mb-3">
            {i + 1}. {q.question || q.text || q.stem}
          </p>
          {(q.options || q.choices || []).map((opt: any, j: number) => {
            const text = typeof opt === 'string' ? opt : opt.text || opt.label;
            return (
              <div key={j} className="flex items-start gap-2 py-1">
                <span className="w-5 h-5 rounded-full border border-border flex-shrink-0 flex items-center justify-center text-[10px] font-semibold text-muted-foreground mt-0.5">
                  {String.fromCharCode(65 + j)}
                </span>
                <span className="text-sm text-foreground">{text}</span>
              </div>
            );
          })}
          <button
            onClick={() => setRevealed((prev) => {
              const next = new Set(prev);
              next.has(i) ? next.delete(i) : next.add(i);
              return next;
            })}
            className="mt-3 text-xs text-primary hover:underline flex items-center gap-1"
          >
            {revealed.has(i) ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {revealed.has(i) ? 'Hide answer' : 'Show answer'}
          </button>
          {revealed.has(i) && (
            <div className="mt-2 p-3 rounded-lg bg-green-50 border border-green-200">
              <p className="text-xs font-semibold text-green-700">Correct Answer</p>
              <p className="text-sm text-green-800 mt-0.5">
                {q.correct_answer ?? q.answer ?? q.correct ?? '—'}
              </p>
              {q.explanation && (
                <p className="text-xs text-green-700 mt-1">{q.explanation}</p>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function FlashcardsView({ payload }: { payload: Record<string, any> }) {
  const cards: any[] = payload?.flashcards || payload?.cards || [];
  const [flipped, setFlipped] = useState<Set<number>>(new Set());

  if (!cards.length) {
    return <p className="text-sm text-muted-foreground">No flashcards available.</p>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {cards.map((card: any, i: number) => {
        const front = card.front || card.term || card.question;
        const back  = card.back  || card.definition || card.answer;
        const isFlipped = flipped.has(i);
        return (
          <button
            key={i}
            onClick={() => setFlipped((prev) => {
              const next = new Set(prev);
              next.has(i) ? next.delete(i) : next.add(i);
              return next;
            })}
            className={cn(
              'border rounded-[var(--radius)] p-4 text-left transition-all cursor-pointer',
              isFlipped
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/40 hover:bg-muted/50'
            )}
          >
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
              {isFlipped ? 'Answer' : 'Question'}
            </p>
            <p className="text-sm text-foreground leading-relaxed">
              {isFlipped ? back : front}
            </p>
            <p className="text-[10px] text-muted-foreground mt-2">
              {isFlipped ? '↩ Click to flip back' : '→ Click to reveal answer'}
            </p>
          </button>
        );
      })}
    </div>
  );
}

function GlossaryView({ payload }: { payload: Record<string, any> }) {
  const terms: any[] = payload?.terms || payload?.glossary || [];

  if (!terms.length) {
    return <p className="text-sm text-muted-foreground">No glossary terms available.</p>;
  }

  return (
    <div className="space-y-3">
      {terms.map((item: any, i: number) => (
        <div key={i} className="border border-border rounded-[var(--radius)] p-3">
          <p className="font-semibold text-sm text-primary">
            {item.term || item.word || item.name}
          </p>
          <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
            {item.definition || item.description || item.meaning}
          </p>
        </div>
      ))}
    </div>
  );
}

function FaqView({ payload }: { payload: Record<string, any> }) {
  const faqs: any[] = payload?.faqs || payload?.faq || [];
  const [open, setOpen] = useState<Set<number>>(new Set([0]));

  if (!faqs.length) {
    return <p className="text-sm text-muted-foreground">No FAQ available.</p>;
  }

  return (
    <div className="space-y-2">
      {faqs.map((item: any, i: number) => {
        const isOpen = open.has(i);
        return (
          <div key={i} className="border border-border rounded-[var(--radius)] overflow-hidden">
            <button
              onClick={() => setOpen((prev) => {
                const next = new Set(prev);
                next.has(i) ? next.delete(i) : next.add(i);
                return next;
              })}
              className="w-full flex items-center justify-between p-3 text-left hover:bg-muted/50 transition-colors"
            >
              <p className="font-medium text-sm text-primary pr-4">
                {item.question || item.q}
              </p>
              {isOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-muted-foreground flex-shrink-0" />}
            </button>
            {isOpen && (
              <div className="px-3 pb-3 text-sm text-muted-foreground leading-relaxed border-t border-border pt-2">
                {item.answer || item.a}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function InfographicView({ payload }: { payload: Record<string, any> }) {
  const sections: any[] = payload?.sections || payload?.points || [];
  const title = payload?.title || 'Infographic';

  return (
    <div className="space-y-3">
      {title && <h3 className="font-semibold text-primary text-base">{title}</h3>}
      {sections.length > 0 ? sections.map((s: any, i: number) => (
        <div key={i} className="flex gap-3 p-3 border border-border rounded-[var(--radius)]">
          <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 text-xs font-bold text-primary mt-0.5">
            {i + 1}
          </div>
          <div>
            {(s.heading || s.title) && (
              <p className="font-semibold text-sm text-primary">{s.heading || s.title}</p>
            )}
            <p className="text-sm text-muted-foreground mt-0.5 leading-relaxed">
              {s.content || s.description || s.text || (typeof s === 'string' ? s : JSON.stringify(s))}
            </p>
          </div>
        </div>
      )) : (
        <pre className="text-xs text-muted-foreground whitespace-pre-wrap bg-muted p-3 rounded-[var(--radius)]">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

function OutputPanel({ output }: { output: AIOutput }) {
  const { payload, output_type } = output;
  if (!payload) {
    return <p className="text-sm text-muted-foreground">No content available for this output.</p>;
  }

  switch (output_type) {
    case 'summary':     return <SummaryView payload={payload} />;
    case 'quiz':        return <QuizView payload={payload} />;
    case 'flashcards':  return <FlashcardsView payload={payload} />;
    case 'glossary':    return <GlossaryView payload={payload} />;
    case 'faq':         return <FaqView payload={payload} />;
    case 'infographic': return <InfographicView payload={payload} />;
    default:
      return (
        <pre className="text-xs text-muted-foreground whitespace-pre-wrap bg-muted p-4 rounded-[var(--radius)] overflow-x-auto">
          {JSON.stringify(payload, null, 2)}
        </pre>
      );
  }
}

// ── Edit modal (inline) ───────────────────────────────────────────────────────

function EditModal({
  item,
  existingOutputTypes,
  onClose,
  onUpdated,
}: {
  item: LibraryItem;
  existingOutputTypes: Set<string>;
  onClose: () => void;
  onUpdated: () => void;
}) {
  type EditSection = 'meta' | 'outputs' | 'file';
  const [section, setSection] = useState<EditSection>('meta');

  // ── Meta section ──────────────────────────────────────────────────────────
  const [title, setTitle] = useState(item.title ?? '');
  const [isPublic, setIsPublic] = useState(item.is_public);
  const [experienceMode, setExperienceMode] = useState(item.experience_mode ?? 'standard');
  const [isSaving, setIsSaving] = useState(false);

  const handleSaveMeta = async () => {
    setIsSaving(true);
    try {
      const res = await fetch(`/api/library/${item.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title.trim() || null,
          is_public: isPublic,
          experience_mode: experienceMode,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || 'Update failed');
      }
      toast.success('Content updated');
      onUpdated();
      onClose();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setIsSaving(false);
    }
  };

  // ── Generate outputs section ──────────────────────────────────────────────
  const ALL_OUTPUT_TYPES = [
    { key: 'summary',     label: 'Summary',     desc: 'AI-generated summary of the content' },
    { key: 'quiz',        label: 'Quiz',        desc: 'Multiple-choice quiz questions' },
    { key: 'flashcards',  label: 'Flashcards',  desc: 'Study flashcard deck' },
    { key: 'glossary',    label: 'Glossary',    desc: 'Key terms and definitions' },
    { key: 'faq',         label: 'FAQ',         desc: 'Frequently asked questions' },
    { key: 'infographic', label: 'Infographic', desc: 'Visual summary of key points' },
  ];
  const missingTypes = ALL_OUTPUT_TYPES.filter(o => !existingOutputTypes.has(o.key));
  const [selectedOutputs, setSelectedOutputs] = useState<string[]>(missingTypes.map(o => o.key));
  const [isGenerating, setIsGenerating] = useState(false);

  const toggleOutput = (key: string) =>
    setSelectedOutputs(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);

  const handleGenerate = async () => {
    if (!selectedOutputs.length) { toast.error('Select at least one output type'); return; }
    setIsGenerating(true);
    try {
      const res = await fetch(`/api/library/${item.id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_types: selectedOutputs }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.error || 'Generation failed'); }
      toast.success(`Generating: ${selectedOutputs.join(', ')} — check back in a minute`);
      onUpdated();
      onClose();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setIsGenerating(false);
    }
  };

  // ── Replace file section ──────────────────────────────────────────────────
  const isFileBased = item.source_url?.startsWith('file://') ?? false;
  const [newFile, setNewFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFileReplace = async () => {
    if (!newFile) { toast.error('Select a file first'); return; }
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', newFile);
      const res = await fetch(`/api/library/${item.id}/replace-file`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.error || 'Upload failed'); }
      toast.success('File replaced — re-processing started. Outputs will update shortly.');
      onUpdated();
      onClose();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setIsUploading(false);
    }
  };

  const SECTIONS: Array<{ key: EditSection; label: string }> = [
    { key: 'meta',    label: 'Details'       },
    { key: 'outputs', label: 'Generate More' },
    { key: 'file',    label: 'Replace File'  },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-lg shadow-lg max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <Pencil className="w-4 h-4 text-primary" />
            </div>
            <p className="font-semibold text-sm text-primary">Edit Content</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Section tabs */}
        <div className="flex border-b border-border flex-shrink-0">
          {SECTIONS.map(s => (
            <button
              key={s.key}
              onClick={() => setSection(s.key)}
              className={cn(
                'flex-1 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors',
                section === s.key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="overflow-y-auto flex-1 p-5">

          {/* ── SECTION: Details ─────────────────────────────────────── */}
          {section === 'meta' && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">Title</label>
                <input
                  type="text"
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="Leave blank to use filename"
                  className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">Experience Mode</label>
                <select
                  value={experienceMode}
                  onChange={e => setExperienceMode(e.target.value)}
                  className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                >
                  <option value="standard">Standard — AI outputs with tabs</option>
                  <option value="interactive">Interactive — quiz-first engagement</option>
                </select>
                <p className="text-[11px] text-muted-foreground mt-1.5">
                  Controls how learners experience this content (tab layout, default view).
                </p>
              </div>
              <div className="flex items-center justify-between p-3 rounded-[var(--radius)] bg-muted">
                <div>
                  <p className="text-xs font-medium text-primary">Share with all creators</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {isPublic ? 'Visible to all creators in this workspace' : 'Only visible to you'}
                  </p>
                </div>
                <button
                  onClick={() => setIsPublic(v => !v)}
                  className={cn(
                    'relative inline-flex h-5 w-9 items-center rounded-full transition-colors flex-shrink-0',
                    isPublic ? 'bg-primary' : 'bg-muted-foreground/30',
                  )}
                >
                  <span className={cn(
                    'inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform',
                    isPublic ? 'translate-x-4' : 'translate-x-0.5',
                  )} />
                </button>
              </div>
            </div>
          )}

          {/* ── SECTION: Generate More Outputs ───────────────────────── */}
          {section === 'outputs' && (
            <div className="space-y-4">
              {missingTypes.length === 0 ? (
                <div className="text-center py-8">
                  <Sparkles className="w-8 h-8 text-primary/40 mx-auto mb-2" />
                  <p className="text-sm font-semibold text-primary">All output types generated!</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Every available output type has already been generated for this content.
                    Use the Regenerate button on any tab to refresh a specific output.
                  </p>
                </div>
              ) : (
                <>
                  <p className="text-xs text-muted-foreground">
                    Select additional output types to generate. Only missing types are shown.
                    Already-generated outputs can be refreshed with the Regenerate button on each tab.
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {missingTypes.map(o => {
                      const selected = selectedOutputs.includes(o.key);
                      return (
                        <button
                          key={o.key}
                          onClick={() => toggleOutput(o.key)}
                          className={cn(
                            'flex flex-col items-start gap-0.5 p-3 rounded-[var(--radius)] border text-left transition-colors',
                            selected
                              ? 'border-primary bg-primary/5 text-primary'
                              : 'border-border hover:bg-muted text-foreground',
                          )}
                        >
                          <span className="text-xs font-semibold">{o.label}</span>
                          <span className="text-[10px] text-muted-foreground">{o.desc}</span>
                        </button>
                      );
                    })}
                  </div>
                  {ALL_OUTPUT_TYPES.filter(o => existingOutputTypes.has(o.key)).length > 0 && (
                    <div className="text-xs text-muted-foreground pt-1 border-t border-border">
                      Already generated:{' '}
                      {ALL_OUTPUT_TYPES.filter(o => existingOutputTypes.has(o.key)).map(o => o.label).join(', ')}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ── SECTION: Replace File ────────────────────────────────── */}
          {section === 'file' && (
            <div className="space-y-4">
              {!isFileBased ? (
                <div className="text-center py-8">
                  <Upload className="w-8 h-8 text-muted-foreground/40 mx-auto mb-2" />
                  <p className="text-sm font-semibold text-primary">Not an uploaded file</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    This content was ingested from a URL and cannot be replaced by uploading a file.
                  </p>
                </div>
              ) : (
                <>
                  <div className="p-3 rounded-[var(--radius)] bg-amber-50 border border-amber-200 text-xs text-amber-700">
                    <strong>Heads up:</strong> Replacing the file will re-run the full processing pipeline.
                    All AI outputs will be regenerated from the new file. This may take a few minutes.
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-2">New File</label>
                    <input
                      ref={fileRef}
                      type="file"
                      accept=".pdf,.txt,.pptx,.ppt,.mp4,.mov"
                      className="hidden"
                      onChange={e => setNewFile(e.target.files?.[0] ?? null)}
                    />
                    <div
                      onClick={() => fileRef.current?.click()}
                      className={cn(
                        'border-2 border-dashed rounded-[var(--radius)] p-6 text-center cursor-pointer transition-colors',
                        newFile
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/50 hover:bg-muted/30',
                      )}
                    >
                      {newFile ? (
                        <div>
                          <Upload className="w-5 h-5 text-primary mx-auto mb-1" />
                          <p className="text-sm font-medium text-primary">{newFile.name}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {(newFile.size / 1024 / 1024).toFixed(1)} MB — click to change
                          </p>
                        </div>
                      ) : (
                        <div>
                          <Upload className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                          <p className="text-sm text-muted-foreground">Click to select a new file</p>
                          <p className="text-xs text-muted-foreground mt-0.5">PDF, PPTX, TXT, MP4</p>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

        </div>

        {/* Footer actions */}
        <div className="flex gap-2 justify-end px-5 py-4 border-t border-border flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted"
          >
            Cancel
          </button>

          {section === 'meta' && (
            <button
              onClick={handleSaveMeta}
              disabled={isSaving}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
              Save Changes
            </button>
          )}

          {section === 'outputs' && missingTypes.length > 0 && (
            <button
              onClick={handleGenerate}
              disabled={isGenerating || !selectedOutputs.length}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {isGenerating
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Sparkles className="w-4 h-4" />}
              Generate ({selectedOutputs.length})
            </button>
          )}

          {section === 'file' && isFileBased && (
            <button
              onClick={handleFileReplace}
              disabled={isUploading || !newFile}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {isUploading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Upload className="w-4 h-4" />}
              {isUploading ? 'Uploading…' : 'Replace & Reprocess'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Content Skill Tag Panel ───────────────────────────────────────────────────

interface SkillTag {
  id: string;
  skill_id: string;
  skill_name: string;
  skill_category: string | null;
  proficiency_level_id: string | null;
  proficiency_label: string | null;
  source: 'ai' | 'confirmed_ai' | 'manual';
  confidence: number | null;
}

interface SkillOption {
  id: string;
  name: string;
  category_name: string | null;
}

interface ProficiencyOption {
  id: string;
  label: string;
  level_order: number;
}

function ContentSkillTagPanel({
  contentItemId,
  userRole,
}: {
  contentItemId: string;
  userRole: string;
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [newSkillId, setNewSkillId] = useState('');
  const [newLevelId, setNewLevelId] = useState('');
  const qc = useQueryClient();

  const canEdit = ['admin', 'creator', 'teacher'].includes(userRole);

  const { data: tags = [], isLoading } = useQuery<SkillTag[]>({
    queryKey: ['content-skill-tags', contentItemId],
    queryFn: async () => {
      const r = await fetch(`/api/skills/content/${contentItemId}/tags`);
      if (!r.ok) return [];
      return r.json();
    },
    enabled: !!contentItemId,
  });

  const { data: skillOptions = [] } = useQuery<SkillOption[]>({
    queryKey: ['skills-list-options'],
    queryFn: async () => {
      const r = await fetch('/api/skills/?limit=200');
      if (!r.ok) return [];
      const d = await r.json();
      return d.items ?? d ?? [];
    },
    enabled: canEdit,
  });

  const { data: levelOptions = [] } = useQuery<ProficiencyOption[]>({
    queryKey: ['proficiency-levels-options'],
    queryFn: async () => {
      const r = await fetch('/api/org-setup/proficiency-levels');
      if (!r.ok) return [];
      return r.json();
    },
    enabled: canEdit,
  });

  const taggedSkillIds = new Set(tags.map((t) => t.skill_id));
  const untaggedSkills = skillOptions.filter((s) => !taggedSkillIds.has(s.id));

  const confirmTag = useMutation({
    mutationFn: async (tagId: string) => {
      await fetch(`/api/skills/content/${contentItemId}/tags/${tagId}/confirm`, {
        method: 'POST',
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['content-skill-tags', contentItemId] }),
  });

  const removeTag = useMutation({
    mutationFn: async (tagId: string) => {
      await fetch(`/api/skills/content/${contentItemId}/tags/${tagId}`, {
        method: 'DELETE',
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['content-skill-tags', contentItemId] }),
  });

  const addTag = useMutation({
    mutationFn: async () => {
      await fetch(`/api/skills/content/${contentItemId}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_id: newSkillId,
          proficiency_level_id: newLevelId || null,
          source: 'manual',
        }),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['content-skill-tags', contentItemId] });
      setNewSkillId('');
      setNewLevelId('');
      setAddOpen(false);
    },
  });

  if (isLoading) {
    return (
      <div className="enterprise-card p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
          <Tag className="w-3.5 h-3.5" /> Skills
        </p>
        <p className="text-xs text-muted-foreground">Loading…</p>
      </div>
    );
  }

  return (
    <div className="enterprise-card p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3 flex items-center gap-1.5">
        <Tag className="w-3.5 h-3.5" /> Skills
      </p>

      {tags.length === 0 && (
        <p className="text-xs text-muted-foreground italic mb-2">No skills tagged yet.</p>
      )}

      <div className="space-y-1.5 mb-3">
        {tags.map((tag) => (
          <div key={tag.id} className="flex items-center justify-between gap-2 group">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-xs font-medium text-foreground truncate">{tag.skill_name}</span>
              {tag.proficiency_label && (
                <span className="text-[10px] text-muted-foreground">· {tag.proficiency_label}</span>
              )}
              {tag.source === 'ai' && (
                <span className="text-[10px] px-1 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
                  AI {tag.confidence != null ? `${Math.round(tag.confidence * 100)}%` : ''}
                </span>
              )}
              {tag.source === 'confirmed_ai' && (
                <span className="text-[10px] px-1 py-0.5 rounded bg-green-50 text-green-700 border border-green-200">✓ AI</span>
              )}
              {tag.source === 'manual' && (
                <span className="text-[10px] px-1 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">Manual</span>
              )}
            </div>
            {canEdit && (
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                {tag.source === 'ai' && (
                  <button onClick={() => confirmTag.mutate(tag.id)} title="Confirm tag" className="p-0.5 rounded text-green-600 hover:bg-green-50">
                    <CheckCheck className="w-3.5 h-3.5" />
                  </button>
                )}
                <button onClick={() => removeTag.mutate(tag.id)} title="Remove tag" className="p-0.5 rounded text-red-500 hover:bg-red-50">
                  <XCircle className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {canEdit && (
        <>
          {!addOpen ? (
            <button onClick={() => setAddOpen(true)} className="text-xs text-primary hover:underline flex items-center gap-1">
              <Plus className="w-3 h-3" /> Add skill
            </button>
          ) : (
            <div className="space-y-2 pt-2 border-t border-border">
              <select value={newSkillId} onChange={(e) => setNewSkillId(e.target.value)} className="w-full text-xs border border-border rounded px-2 py-1.5 bg-background text-foreground">
                <option value="">Select skill…</option>
                {untaggedSkills.map((s) => (
                  <option key={s.id} value={s.id}>{s.category_name ? `${s.category_name} / ` : ''}{s.name}</option>
                ))}
              </select>
              <select value={newLevelId} onChange={(e) => setNewLevelId(e.target.value)} className="w-full text-xs border border-border rounded px-2 py-1.5 bg-background text-foreground">
                <option value="">Level (optional)…</option>
                {levelOptions.map((l) => (
                  <option key={l.id} value={l.id}>{l.label}</option>
                ))}
              </select>
              <div className="flex gap-2">
                <button disabled={!newSkillId || addTag.isPending} onClick={() => addTag.mutate()} className="text-xs px-3 py-1.5 bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50">
                  {addTag.isPending ? 'Adding…' : 'Add'}
                </button>
                <button onClick={() => { setAddOpen(false); setNewSkillId(''); setNewLevelId(''); }} className="text-xs px-3 py-1.5 border border-border rounded hover:bg-muted">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Main detail page ──────────────────────────────────────────────────────────

export default function LibraryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const user = useUser();
  const id = params.id as string;
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<string>('');
  const [showEdit, setShowEdit] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);

  // Fetch item metadata
  const { data: item, isLoading: itemLoading, error: itemError } = useQuery<LibraryItem>({
    queryKey: ['library-item', id],
    queryFn: async () => {
      const res = await fetch(`/api/library/${id}`);
      if (!res.ok) throw new Error('Content not found');
      return res.json();
    },
    retry: false,
  });

  // Fetch AI outputs
  const { data: outputs, isLoading: outputsLoading, refetch: refetchOutputs } = useQuery<AIOutput[]>({
    queryKey: ['library-outputs', id],
    queryFn: async () => {
      const res = await fetch(`/api/library/${id}/outputs`);
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    },
    enabled: !!item,
  });

  // Fetch embedded PDF interactions (for interactive_pdf type)
  const { data: pdfInteractions, refetch: refetchInteractions } = useQuery<{ interactions: Array<any> }>({
    queryKey: ['library-pdf-interactions', id],
    queryFn: async () => {
      const res = await fetch(`/api/library/${id}/pdf-interactions`);
      if (!res.ok) return { interactions: [] };
      return res.json();
    },
    enabled: !!item && item.content_type === 'interactive_pdf',
  });

  // Set default active tab when outputs first load
  useEffect(() => {
    if (outputs && outputs.length > 0 && !activeTab) {
      setActiveTab(outputs[0].output_type);
    }
  }, [outputs, activeTab]);

  const handleRegenerate = async (outputType: string) => {
    setIsRegenerating(true);
    try {
      const res = await fetch(`/api/library/${id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_types: [outputType] }),
      });
      if (!res.ok) throw new Error('Regeneration failed');
      toast.success(`${outputType} regeneration queued`);
      setTimeout(() => refetchOutputs(), 3000);
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setIsRegenerating(false);
    }
  };

  // ── Loading / error states ─────────────────────────────────────────────────

  if (itemLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (itemError || !item) {
    return (
      <div className="page-padding">
        <div className="enterprise-card flex flex-col items-center py-16 text-center">
          <AlertCircle className="w-10 h-10 text-red-400 mb-3" />
          <p className="font-semibold text-primary">Content not found</p>
          <p className="text-sm text-muted-foreground mt-1 mb-4">
            This item may have been deleted or you don't have access.
          </p>
          <button
            onClick={() => router.push('/library')}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium"
          >
            <ArrowLeft className="w-4 h-4" /> Back to Library
          </button>
        </div>
      </div>
    );
  }

  const activeOutput = outputs?.find((o) => o.output_type === activeTab);
  const tabsToShow = outputs ?? [];

  return (
    <div>
      {/* Back + title bar */}
      <div className="border-b border-border bg-background/95 sticky top-0 z-10 backdrop-blur-sm">
        <div className="page-padding py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => router.push('/library')}
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors flex-shrink-0"
            >
              <ArrowLeft className="w-4 h-4" />
              Library
            </button>
            <span className="text-muted-foreground/40">/</span>
            <div className={cn(
              'w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 border',
              typeColor(item.content_type)
            )}>
              {typeIcon(item.content_type, 'w-3.5 h-3.5')}
            </div>
            <p className="font-semibold text-sm text-primary truncate">
              {item.title || 'Untitled'}
            </p>
          </div>

          <button
            onClick={() => setShowEdit(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[var(--radius)] text-xs text-muted-foreground hover:text-primary hover:bg-muted transition-colors flex-shrink-0"
          >
            <Pencil className="w-3.5 h-3.5" />
            Edit
          </button>
        </div>
      </div>

      <div className="page-padding py-6 grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
        {/* ── Sidebar metadata ─────────────────────────────────────────────── */}
        <div className="space-y-4">
          {/* Status card */}
          <div className="enterprise-card p-4">
            <div className="flex items-center gap-2 mb-3">
              {item.status === 'ready' && <CheckCircle2 className="w-4 h-4 text-green-500" />}
              {item.status === 'processing' && <Loader className="w-4 h-4 text-yellow-500 animate-spin" />}
              {item.status === 'failed' && <AlertCircle className="w-4 h-4 text-red-500" />}
              {!['ready','processing','failed'].includes(item.status) && <Clock className="w-4 h-4 text-muted-foreground" />}
              <span className={cn(
                'text-sm font-semibold capitalize',
                item.status === 'ready' ? 'text-green-600' :
                item.status === 'processing' ? 'text-yellow-600' :
                item.status === 'failed' ? 'text-red-600' : 'text-muted-foreground'
              )}>
                {item.status}
              </span>
            </div>

            <div className="space-y-2 text-xs text-muted-foreground">
              <div className="flex justify-between">
                <span>Type</span>
                <span className={cn('font-medium px-1.5 py-0.5 rounded-full border', typeColor(item.content_type))}>
                  {item.content_type}
                </span>
              </div>
              {item.language && (
                <div className="flex justify-between">
                  <span>Language</span>
                  <span className="font-medium text-foreground uppercase">{item.language}</span>
                </div>
              )}
              {item.word_count != null && (
                <div className="flex justify-between">
                  <span>Words</span>
                  <span className="font-medium text-foreground">{item.word_count.toLocaleString()}</span>
                </div>
              )}
              {item.chunk_count > 0 && (
                <div className="flex justify-between">
                  <span>Chunks</span>
                  <span className="font-medium text-foreground">{item.chunk_count}</span>
                </div>
              )}
              {item.space_count > 0 && (
                <div className="flex justify-between">
                  <span>Spaces</span>
                  <span className="font-medium text-foreground flex items-center gap-1">
                    <BookOpen className="w-3 h-3" />
                    {item.space_count}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span>Mode</span>
                <span className="font-medium text-foreground capitalize flex items-center gap-1">
                  {item.experience_mode === 'interactive' && <Zap className="w-3 h-3 text-purple-500" />}
                  {item.experience_mode}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Visibility</span>
                <span className={cn('font-medium flex items-center gap-1', item.is_public ? 'text-teal-600' : 'text-muted-foreground')}>
                  {item.is_public ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                  {item.is_public ? 'Shared' : 'Private'}
                </span>
              </div>
            </div>
          </div>

          {/* Creator + dates */}
          <div className="enterprise-card p-4 space-y-2 text-xs text-muted-foreground">
            {item.creator_name && (
              <div>
                <p className="font-semibold uppercase tracking-wide text-[10px] mb-0.5">Created by</p>
                <p className="text-foreground">{item.creator_name}</p>
              </div>
            )}
            <div>
              <p className="font-semibold uppercase tracking-wide text-[10px] mb-0.5">Added</p>
              <p className="text-foreground">{fmtDate(item.created_at)}</p>
            </div>
            <div>
              <p className="font-semibold uppercase tracking-wide text-[10px] mb-0.5">Last updated</p>
              <p className="text-foreground">{fmtDateTime(item.updated_at)}</p>
            </div>
          </div>

          {/* Source file / URL */}
          {item.source_url && (
            <div className="enterprise-card p-4">
              <p className="font-semibold uppercase tracking-wide text-[10px] text-muted-foreground mb-1.5">Source</p>
              {item.source_url.startsWith('file://') ? (
                <p className="text-xs text-muted-foreground italic">
                  Uploaded file — preview available below.
                </p>
              ) : (
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-primary hover:underline break-all"
                >
                  {item.source_url}
                </a>
              )}
            </div>
          )}

          {/* ── Skill tag panel ─────────────────────────────────────────────── */}
          <ContentSkillTagPanel contentItemId={id} userRole={user?.role ?? ''} />
        </div>

        {/* ── File preview (PDF / interactive_pdf / PPTX) ─────────────────── */}
        <div className="min-w-0 space-y-6">
          {(item.content_type === 'pdf' || item.content_type === 'interactive_pdf') &&
            item.source_url && (
            <div className="enterprise-card overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3 border-b border-border">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {item.content_type === 'interactive_pdf' ? 'Interactive PDF Preview' : 'PDF Preview'}
                </span>
              </div>
              <div className="p-0">
                <iframe
                  src={`/api/files/${item.id}`}
                  title={item.title || 'PDF Preview'}
                  className="w-full"
                  style={{ height: '600px', border: 'none' }}
                />
              </div>
            </div>
          )}


          {/* ── Interactive PDF Question Editor (creator only) ─────────────────── */}
          {item.content_type === 'interactive_pdf' && (
            <InteractivePDFEditor
              contentId={id}
              interactions={pdfInteractions?.interactions ?? []}
              onSaved={() => refetchInteractions()}
            />
          )}

          {/* ── AI outputs panel ─────────────────────────────────────────────── */}
          <div>
          {outputsLoading ? (
            <div className="enterprise-card flex items-center justify-center h-48">
              <div className="text-center">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">Loading AI outputs…</p>
              </div>
            </div>
          ) : tabsToShow.length === 0 ? (
            <div className="enterprise-card flex flex-col items-center py-16 text-center">
              <Brain className="w-10 h-10 text-muted-foreground/40 mb-3" />
              <p className="font-semibold text-primary">No AI outputs yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                {item.status === 'processing'
                  ? 'Content is still being processed. Check back in a moment.'
                  : 'This content has no generated outputs.'}
              </p>
              {item.status === 'processing' && (
                <button
                  onClick={() => refetchOutputs()}
                  className="mt-4 flex items-center gap-2 text-sm text-primary hover:underline"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Refresh
                </button>
              )}
            </div>
          ) : (
            <div className="enterprise-card overflow-hidden">
              {/* Tabs */}
              <div className="flex items-center gap-1 p-3 border-b border-border overflow-x-auto">
                {tabsToShow.map((out) => {
                  const meta = OUTPUT_META[out.output_type];
                  const Icon = meta?.icon ?? Brain;
                  const isActive = activeTab === out.output_type;
                  return (
                    <button
                      key={out.output_type}
                      onClick={() => setActiveTab(out.output_type)}
                      className={cn(
                        'flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius)] text-xs font-medium whitespace-nowrap transition-colors',
                        isActive
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                      )}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {meta?.label ?? out.output_type}
                    </button>
                  );
                })}

                <div className="ml-auto flex-shrink-0">
                  <button
                    onClick={() => refetchOutputs()}
                    className="p-1.5 text-muted-foreground hover:text-primary transition-colors rounded-lg hover:bg-muted"
                    title="Refresh outputs"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Output content */}
              {activeOutput ? (
                <div className="p-5">
                  {/* Output meta row */}
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                      {activeOutput.model && (
                        <span className="px-1.5 py-0.5 rounded border border-border bg-muted">
                          {activeOutput.model}
                        </span>
                      )}
                      <span>Updated {fmtDateTime(activeOutput.updated_at)}</span>
                    </div>
                    <button
                      onClick={() => handleRegenerate(activeOutput.output_type)}
                      disabled={isRegenerating}
                      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors disabled:opacity-50"
                      title="Regenerate this output"
                    >
                      <RefreshCw className={cn('w-3 h-3', isRegenerating && 'animate-spin')} />
                      Regenerate
                    </button>
                  </div>

                  <OutputPanel output={activeOutput} />
                </div>
              ) : (
                <div className="p-5 text-sm text-muted-foreground">Select a tab to view content.</div>
              )}
            </div>
          )}
          </div>
        </div>
      </div>

      {showEdit && (
        <EditModal
          item={item}
          existingOutputTypes={new Set((outputs ?? []).map((o) => o.output_type))}
          onClose={() => setShowEdit(false)}
          onUpdated={() => {
            queryClient.invalidateQueries({ queryKey: ['library-item', id] });
            queryClient.invalidateQueries({ queryKey: ['library'] });
            refetchOutputs();
          }}
        />
      )}
    </div>
  );
}
