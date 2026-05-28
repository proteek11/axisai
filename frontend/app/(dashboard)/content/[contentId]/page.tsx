'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Loader2, AlertCircle, RefreshCw, Zap,
  AlignLeft, BookOpen, Layers, HelpCircle, Image,
  MessageCircleQuestion, MessageSquare, ListVideo, GitBranch, Target, Brain,
  CheckCircle2, ChevronDown, ChevronUp, PlayCircle,
} from 'lucide-react';
import { toast } from 'sonner';

// Reusable study components
import { SummaryTab } from '@/components/content/summary-tab';
import { GlossaryTab } from '@/components/content/glossary-tab';
import { FlashcardsTab } from '@/components/content/flashcards-tab';
import { QuizTab } from '@/components/content/quiz-tab';
import { InfographicTab } from '@/components/content/infographic-tab';
import { StudyFAQ } from '@/components/study/study-faq';
import { StudyChapters } from '@/components/study/study-chapters';
import { StudyDiscussionPrompts } from '@/components/study/study-discussion-prompts';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ContentItem {
  id: string;
  title: string;
  content_type: string;
  status: string;
  has_outputs: boolean;
}

/** Raw backend AIOutputResponse (array format returned by creator path) */
interface RawOutput {
  output_type: string;
  payload: Record<string, unknown>;
  created_at?: string;
}

/** Keyed outputs used by the page */
interface AIOutputs {
  summary?: string | null;
  glossary?: Array<{ term: string; definition: string }> | null;
  flashcards?: Array<{ front: string; back: string }> | null;
  quiz?: Array<{
    question: string; options: string[];
    correct_index: number; explanation: string; bloom_level: string;
  }> | null;
  infographic?: string | null;
  faq?: Array<{ question: string; answer: string }> | null;
  chapters?: { chapters: Array<{ title: string; start_sec: number; end_sec: number; summary: string }>; total_duration_sec?: number } | null;
  mindmap?: Record<string, unknown> | null;
  objectives?: string[] | null;
  blooms?: Record<string, unknown> | null;
  discussion_prompts?: Array<{ question: string; theme?: string; challenge_level?: string }> | null;
}

// ── Tab definitions ────────────────────────────────────────────────────────────

const ALL_TABS = [
  { key: 'summary',           label: 'Summary',    icon: AlignLeft,             outputType: 'summary'            },
  { key: 'glossary',          label: 'Glossary',   icon: BookOpen,              outputType: 'glossary'           },
  { key: 'flashcards',        label: 'Flashcards', icon: Layers,                outputType: 'flashcards'         },
  { key: 'quiz',              label: 'Quiz',       icon: HelpCircle,            outputType: 'quiz'               },
  { key: 'faq',               label: 'FAQ',        icon: MessageCircleQuestion, outputType: 'faq'                },
  { key: 'infographic',       label: 'Infographic',icon: Image,                 outputType: 'infographic'        },
  { key: 'chapters',          label: 'Chapters',   icon: ListVideo,             outputType: 'chapters'           },
  { key: 'mindmap',           label: 'Mind Map',   icon: GitBranch,             outputType: 'mindmap'            },
  { key: 'objectives',        label: 'Objectives', icon: Target,                outputType: 'objectives'         },
  { key: 'blooms',            label: "Bloom's",    icon: Brain,                 outputType: 'blooms'             },
  { key: 'discussion_prompts',label: 'Discuss',    icon: MessageSquare,         outputType: 'discussion_prompts' },
] as const;

type TabKey = typeof ALL_TABS[number]['key'];

// ── Helper: parse raw backend array → keyed AIOutputs ────────────────────────

function parseOutputs(raw: RawOutput[]): AIOutputs {
  const out: AIOutputs = {};
  for (const item of raw) {
    const p = item.payload ?? {};
    switch (item.output_type) {
      case 'summary':
        out.summary = (p as { summary?: string }).summary ?? null;
        break;
      case 'glossary':
        out.glossary = (p as { terms?: Array<{ term: string; definition: string }> }).terms ?? null;
        break;
      case 'flashcards':
        out.flashcards = (p as { cards?: Array<{ front: string; back: string }> }).cards ?? null;
        break;
      case 'quiz': {
        type RawOpt = { text?: string; is_correct?: boolean; feedback?: string };
        type RawQ = {
          question?: string; question_text?: string;
          options?: RawOpt[];
          explanation?: string;
          blooms_level?: string; bloom_level?: string;
          difficulty?: string;
        };
        const rawQs = (p as { questions?: RawQ[] }).questions ?? null;
        out.quiz = rawQs
          ? rawQs.map((q) => {
              const opts = q.options ?? [];
              const correctIdx = opts.findIndex((o) => o.is_correct === true);
              return {
                question: q.question ?? q.question_text ?? '',
                options: opts.map((o) => o.text ?? ''),
                correct_index: correctIdx >= 0 ? correctIdx : 0,
                explanation: q.explanation ?? '',
                bloom_level: q.bloom_level ?? q.blooms_level ?? '',
                difficulty: q.difficulty ?? '',
              };
            })
          : null;
        break;
      }
      case 'infographic':
        out.infographic = (p as { html?: string }).html ?? null;
        break;
      case 'faq':
        out.faq = (p as { faqs?: Array<{ question: string; answer: string }> }).faqs ?? null;
        break;
      case 'chapters':
        out.chapters = p as { chapters: Array<{ title: string; start_sec: number; end_sec: number; summary: string }>; total_duration_sec?: number };
        break;
      case 'mindmap':
        out.mindmap = p as Record<string, unknown>;
        break;
      case 'objectives':
        out.objectives = (p as { objectives?: string[] }).objectives ?? null;
        break;
      case 'blooms':
        out.blooms = p as Record<string, unknown>;
        break;
      case 'discussion_prompts':
        out.discussion_prompts = (p as { prompts?: Array<{ question: string; theme?: string; challenge_level?: string }> }).prompts ?? null;
        break;
    }
  }
  return out;
}

// ── MindMap renderer (inline — same as learner page) ─────────────────────────

interface MindMapNodeData {
  label?: string; name?: string; text?: string;
  children?: MindMapNodeData[];
  subtopics?: MindMapNodeData[];
  items?: MindMapNodeData[];
}

const DEPTH_COLORS = ['text-primary', 'text-violet-600', 'text-teal-600', 'text-amber-600'];

function MindMapNode({ node, depth }: { node: MindMapNodeData; depth: number }) {
  const label = node.label ?? node.name ?? node.text ?? '';
  const children = node.children ?? node.subtopics ?? node.items ?? [];
  const color = DEPTH_COLORS[Math.min(depth, DEPTH_COLORS.length - 1)];
  return (
    <div className={cn('ml-4', depth === 0 && 'ml-0')}>
      <div className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium mb-1',
        depth === 0 ? 'bg-primary/10 text-primary text-base' : 'bg-muted',
        color,
      )}>
        {label}
      </div>
      {children.length > 0 && (
        <div className="border-l-2 border-border pl-3 mt-1 mb-2 space-y-1">
          {children.map((child, i) => (
            <MindMapNode key={i} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function MindMapViewer({ data }: { data: Record<string, unknown> }) {
  const root = (data.root ?? data) as MindMapNodeData;
  if (!root) return <p className="text-sm text-muted-foreground">No mind map data available.</p>;
  return (
    <div className="max-h-[500px] overflow-y-auto enterprise-card">
      <MindMapNode node={root} depth={0} />
    </div>
  );
}

// ── Bloom's level colour helpers ──────────────────────────────────────────────

const BLOOMS_COLORS: Record<string, string> = {
  remember:  'bg-blue-50 text-blue-700 border-blue-200',
  understand:'bg-teal-50 text-teal-700 border-teal-200',
  apply:     'bg-green-50 text-green-700 border-green-200',
  analyze:   'bg-amber-50 text-amber-700 border-amber-200',
  evaluate:  'bg-orange-50 text-orange-700 border-orange-200',
  create:    'bg-violet-50 text-violet-700 border-violet-200',
};

// ── Generate button for a missing output type ─────────────────────────────────

function GenerateButton({ contentId, outputType, onDone }: {
  contentId: string; outputType: string; onDone: () => void;
}) {
  const [generating, setGenerating] = useState(false);
  const handle = async () => {
    setGenerating(true);
    try {
      const res = await fetch(`/api/content/${contentId}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_types: [outputType] }),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.error || 'Generation failed');
      }
      toast.success(`${outputType} generation started — refresh in ~30 seconds`);
      setTimeout(onDone, 8000);
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setGenerating(false);
    }
  };
  return (
    <button
      onClick={handle}
      disabled={generating}
      className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
        rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
    >
      {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
      {generating ? 'Generating…' : `Generate ${outputType}`}
    </button>
  );
}

// ── Empty state shown when an output hasn't been generated yet ────────────────

function NotGenerated({ contentId, outputType, onDone }: {
  contentId: string; outputType: string; onDone: () => void;
}) {
  return (
    <div className="enterprise-card text-center py-16 space-y-4">
      <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto">
        <Zap className="w-5 h-5 text-primary" />
      </div>
      <div>
        <p className="font-medium text-primary mb-1">Not generated yet</p>
        <p className="text-sm text-muted-foreground">
          Click Generate to produce this AI output from the content.
        </p>
      </div>
      <GenerateButton contentId={contentId} outputType={outputType} onDone={onDone} />
    </div>
  );
}

// ── Chapters content type guard ───────────────────────────────────────────────

const VIDEO_TYPES = new Set(['youtube', 'vimeo', 'peertube', 'video_upload']);

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ContentWorkspacePage() {
  const { contentId } = useParams<{ contentId: string }>();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabKey>('summary');

  const { data: content, isLoading: loadingContent } = useQuery<ContentItem>({
    queryKey: ['content', contentId],
    queryFn: async () => {
      const res = await fetch(`/api/content/${contentId}`);
      if (!res.ok) throw new Error('Not found');
      return res.json();
    },
  });

  const { data: rawOutputs, isLoading: loadingOutputs, refetch } = useQuery<RawOutput[]>({
    queryKey: ['content', contentId, 'outputs-raw'],
    queryFn: async () => {
      const res = await fetch(`/api/content/${contentId}/outputs`);
      if (!res.ok) throw new Error('Failed');
      const data = await res.json();
      // Creator path returns array from backend
      return Array.isArray(data) ? data : [];
    },
    enabled: !!content,
  });

  const outputs: AIOutputs = rawOutputs ? parseOutputs(rawOutputs) : {};

  // Regenerate a specific output type
  const regenerateMutation = useMutation({
    mutationFn: async (outputType: string) => {
      const res = await fetch(`/api/content/${contentId}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_types: [outputType] }),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.error || 'Regeneration failed');
      }
      return res.json();
    },
    onSuccess: (_data, outputType) => {
      toast.success(`${outputType} regeneration started — refreshing in ~30s`);
      setTimeout(() => refetch(), 30_000);
    },
    onError: (err: any) => toast.error(err.message),
  });

  if (loadingContent || loadingOutputs) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!content) {
    return (
      <div className="page-padding flex flex-col items-center py-16">
        <AlertCircle className="w-8 h-8 text-muted-foreground mb-3" />
        <p className="text-muted-foreground">Content not found.</p>
      </div>
    );
  }

  // Filter tabs: hide Chapters if not a video type
  const visibleTabs = ALL_TABS.filter((t) => {
    if (t.key === 'chapters') return VIDEO_TYPES.has(content.content_type);
    return true;
  });

  // Check which tab currently has an output
  function hasOutput(key: TabKey): boolean {
    const v = outputs[key as keyof AIOutputs];
    if (v == null) return false;
    if (Array.isArray(v) && v.length === 0) return false;
    if (typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0) return false;
    return true;
  }

  const activeTabDef = visibleTabs.find((t) => t.key === activeTab) ?? visibleTabs[0];

  return (
    <div>
      <Header
        title={content.title}
        subtitle={`${content.content_type} · AI Workspace`}
        backHref="/library"
        backLabel="Back to Library"
      />

      <div className="page-padding">
        {/* Tab nav + Regenerate button */}
        <div className="flex items-center justify-between mb-6 border-b border-border">
          <div className="flex items-center gap-0.5 overflow-x-auto">
            {visibleTabs.map((tab) => {
              const Icon = tab.icon;
              const active = activeTab === tab.key;
              const has = hasOutput(tab.key);
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap',
                    active
                      ? 'border-primary text-primary'
                      : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border',
                  )}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.label}
                  {!has && (
                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40" title="Not generated" />
                  )}
                </button>
              );
            })}
          </div>

          {/* Regenerate button for current tab */}
          {hasOutput(activeTab) && (
            <button
              onClick={() => regenerateMutation.mutate(activeTabDef.outputType)}
              disabled={regenerateMutation.isPending}
              className="ml-4 flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[var(--radius)]
                text-xs text-muted-foreground hover:text-primary hover:border-primary transition-colors flex-shrink-0"
            >
              {regenerateMutation.isPending
                ? <Loader2 className="w-3 h-3 animate-spin" />
                : <RefreshCw className="w-3 h-3" />
              }
              Regenerate
            </button>
          )}
        </div>

        {/* Tab content */}
        <div>
          {/* Summary */}
          {activeTab === 'summary' && (
            hasOutput('summary')
              ? <SummaryTab contentId={contentId} summary={outputs.summary ?? ''} />
              : <NotGenerated contentId={contentId} outputType="summary" onDone={() => refetch()} />
          )}

          {/* Glossary */}
          {activeTab === 'glossary' && (
            hasOutput('glossary')
              ? <GlossaryTab contentId={contentId} terms={outputs.glossary ?? []} />
              : <NotGenerated contentId={contentId} outputType="glossary" onDone={() => refetch()} />
          )}

          {/* Flashcards */}
          {activeTab === 'flashcards' && (
            hasOutput('flashcards')
              ? <FlashcardsTab contentId={contentId} cards={outputs.flashcards ?? []} />
              : <NotGenerated contentId={contentId} outputType="flashcards" onDone={() => refetch()} />
          )}

          {/* Quiz */}
          {activeTab === 'quiz' && (
            hasOutput('quiz')
              ? <QuizTab contentId={contentId} questions={outputs.quiz ?? []} />
              : <NotGenerated contentId={contentId} outputType="quiz" onDone={() => refetch()} />
          )}

          {/* FAQ */}
          {activeTab === 'faq' && (
            hasOutput('faq')
              ? <StudyFAQ items={outputs.faq ?? []} />
              : <NotGenerated contentId={contentId} outputType="faq" onDone={() => refetch()} />
          )}

          {/* Infographic */}
          {activeTab === 'infographic' && (
            hasOutput('infographic')
              ? <InfographicTab contentId={contentId} html={outputs.infographic ?? ''} />
              : <NotGenerated contentId={contentId} outputType="infographic" onDone={() => refetch()} />
          )}

          {/* Chapters */}
          {activeTab === 'chapters' && (
            hasOutput('chapters')
              ? <StudyChapters
                  chapters={outputs.chapters?.chapters ?? []}
                  totalDurationSec={outputs.chapters?.total_duration_sec}
                />
              : <NotGenerated contentId={contentId} outputType="chapters" onDone={() => refetch()} />
          )}

          {/* Mind Map */}
          {activeTab === 'mindmap' && (
            hasOutput('mindmap')
              ? <MindMapViewer data={outputs.mindmap!} />
              : <NotGenerated contentId={contentId} outputType="mindmap" onDone={() => refetch()} />
          )}

          {/* Objectives */}
          {activeTab === 'objectives' && (
            hasOutput('objectives') ? (
              <div className="enterprise-card space-y-3">
                <p className="section-label mb-4">Learning Objectives</p>
                <ul className="space-y-2">
                  {(outputs.objectives ?? []).map((obj, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary
                        flex items-center justify-center text-xs font-bold mt-0.5">
                        {i + 1}
                      </span>
                      <span className="text-sm text-foreground leading-relaxed">{obj}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <NotGenerated contentId={contentId} outputType="objectives" onDone={() => refetch()} />
            )
          )}

          {/* Bloom's */}
          {activeTab === 'blooms' && (
            hasOutput('blooms') ? (
              <div className="space-y-4">
                <p className="section-label mb-2">Bloom's Taxonomy Analysis</p>
                {Object.entries(outputs.blooms as Record<string, unknown>).map(([level, items]) => {
                  const arr = Array.isArray(items) ? items as string[] : [];
                  if (arr.length === 0) return null;
                  const colorClass = BLOOMS_COLORS[level.toLowerCase()] ?? 'bg-muted text-foreground border-border';
                  return (
                    <div key={level} className={cn('enterprise-card border', colorClass, 'p-0 overflow-hidden')}>
                      <div className={cn('px-4 py-2 border-b font-semibold text-xs uppercase tracking-wide', colorClass)}>
                        {level}
                      </div>
                      <ul className="divide-y divide-border">
                        {arr.map((item, i) => (
                          <li key={i} className="px-4 py-2.5 text-sm">{item}</li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            ) : (
              <NotGenerated contentId={contentId} outputType="blooms" onDone={() => refetch()} />
            )
          )}

          {/* Discussion Prompts */}
          {activeTab === 'discussion_prompts' && (
            hasOutput('discussion_prompts')
              ? <StudyDiscussionPrompts prompts={outputs.discussion_prompts ?? []} />
              : <NotGenerated contentId={contentId} outputType="discussion_prompts" onDone={() => refetch()} />
          )}
        </div>
      </div>
    </div>
  );
}
