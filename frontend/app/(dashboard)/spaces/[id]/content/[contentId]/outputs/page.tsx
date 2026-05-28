'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft, BookOpen, FileQuestion, Layers, AlignLeft,
  HelpCircle, Brain, CheckCircle2, XCircle, ChevronDown,
  ChevronUp, AlertCircle, Loader2, BookMarked, Tag,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────────
interface QuizQuestion {
  id: string;
  question_type: string;
  question_text: string;
  options: Array<{ text: string; is_correct: boolean; feedback?: string }> | null;
  correct_answer: string | null;
  explanation: string | null;
  blooms_level: string | null;
  difficulty_label: string | null;
  topic_primary: string | null;
  is_active: boolean;
}

interface Flashcard {
  id: string;
  front: string;
  back: string;
  hint: string | null;
  card_type: string | null;
  difficulty: string | null;
  topic: string | null;
}

interface GlossaryTerm {
  id: string;
  term: string;
  definition: string;
  context: string | null;
  category: string | null;
}

interface AIOutputEntry {
  output_type: string;
  payload: Record<string, any>;
  is_teacher_edited: boolean;
  created_at: string | null;
}

interface CreatorOutputs {
  content_item_id: string;
  content_title: string;
  content_type: string;
  content_status: string;
  stats: {
    quiz_questions: number;
    flashcards: number;
    glossary_terms: number;
    ai_output_types: string[];
  };
  quiz_questions: QuizQuestion[];
  flashcards: Flashcard[];
  glossary_terms: GlossaryTerm[];
  ai_outputs: Record<string, AIOutputEntry>;
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

function BloomsBadge({ level }: { level: string | null }) {
  if (!level) return null;
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-purple-50 text-purple-700 border-purple-200 font-medium">
      {level}
    </span>
  );
}

// ── Quiz Question card ─────────────────────────────────────────────────────────
function QuizCard({ q, index }: { q: QuizQuestion; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-border rounded-xl bg-white overflow-hidden">
      <button
        className="w-full text-left p-4 flex items-start gap-3 hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded(v => !v)}
      >
        <span className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground leading-snug">{q.question_text}</p>
          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-blue-50 text-blue-700 border-blue-200 font-medium uppercase">
              {q.question_type}
            </span>
            <DiffBadge level={q.difficulty_label} />
            <BloomsBadge level={q.blooms_level} />
            {q.topic_primary && (
              <span className="text-[10px] text-muted-foreground">{q.topic_primary}</span>
            )}
          </div>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-1" /> : <ChevronDown className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-1" />}
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-border bg-muted/20">
          {/* MCQ options */}
          {q.options && q.options.length > 0 && (
            <div className="mt-3 space-y-2">
              {q.options.map((opt, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-2 p-2.5 rounded-lg text-sm ${
                    opt.is_correct
                      ? 'bg-green-50 border border-green-200'
                      : 'bg-white border border-border'
                  }`}
                >
                  {opt.is_correct
                    ? <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" />
                    : <XCircle className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                  }
                  <span className={opt.is_correct ? 'text-green-800 font-medium' : 'text-foreground'}>
                    {opt.text}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* True/False correct answer */}
          {q.question_type === 'truefalse' && q.correct_answer && (
            <div className="mt-3 flex items-center gap-2 p-2.5 rounded-lg bg-green-50 border border-green-200 text-sm">
              <CheckCircle2 className="w-4 h-4 text-green-600" />
              <span className="text-green-800 font-medium">Correct: {q.correct_answer}</span>
            </div>
          )}

          {/* Explanation */}
          {q.explanation && (
            <div className="mt-3 p-2.5 rounded-lg bg-blue-50 border border-blue-100 text-sm text-blue-800">
              <span className="font-medium">Explanation: </span>{q.explanation}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Flashcard card ─────────────────────────────────────────────────────────────
function FlashcardCard({ card, index }: { card: Flashcard; index: number }) {
  const [flipped, setFlipped] = useState(false);
  return (
    <div
      className="border border-border rounded-xl bg-white cursor-pointer hover:border-primary/40 transition-colors overflow-hidden"
      onClick={() => setFlipped(v => !v)}
    >
      <div className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            {flipped ? 'Back (Answer)' : 'Front (Question)'}
          </span>
          <div className="flex items-center gap-1.5">
            {card.difficulty && <DiffBadge level={card.difficulty} />}
            <span className="text-[10px] text-muted-foreground">tap to flip</span>
          </div>
        </div>
        <p className="text-sm font-medium text-foreground leading-snug min-h-[2.5rem]">
          {flipped ? card.back : card.front}
        </p>
        {flipped && card.hint && (
          <p className="mt-2 text-xs text-muted-foreground italic">Hint: {card.hint}</p>
        )}
      </div>
      {card.topic && (
        <div className="px-4 py-2 border-t border-border bg-muted/20">
          <span className="text-[10px] text-muted-foreground">{card.topic}</span>
        </div>
      )}
    </div>
  );
}

// ── Summary section ────────────────────────────────────────────────────────────
function SummarySection({ entry }: { entry: AIOutputEntry }) {
  const p = entry.payload;
  return (
    <div className="space-y-4">
      {p.summary && (
        <div className="p-4 rounded-xl border border-border bg-white">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-2">Summary</p>
          <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{p.summary}</p>
        </div>
      )}
      {p.key_points && p.key_points.length > 0 && (
        <div className="p-4 rounded-xl border border-border bg-white">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">Key Points</p>
          <ul className="space-y-1.5">
            {p.key_points.map((pt: string, i: number) => (
              <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                <span className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0 mt-1.5" />
                {pt}
              </li>
            ))}
          </ul>
        </div>
      )}
      {p.key_concepts && p.key_concepts.length > 0 && (
        <div className="p-4 rounded-xl border border-border bg-white">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">Key Concepts</p>
          <div className="flex flex-wrap gap-2">
            {p.key_concepts.map((c: string, i: number) => (
              <span key={i} className="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary font-medium">
                {c}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── FAQ section ────────────────────────────────────────────────────────────────
function FAQSection({ entry }: { entry: AIOutputEntry }) {
  const faqs: Array<{ question: string; answer: string; topic?: string }> = entry.payload?.faqs ?? [];
  return (
    <div className="space-y-3">
      {faqs.map((faq, i) => (
        <details key={i} className="group border border-border rounded-xl bg-white overflow-hidden">
          <summary className="flex items-center justify-between p-4 cursor-pointer list-none hover:bg-muted/30 transition-colors">
            <span className="text-sm font-medium text-foreground pr-4">{faq.question}</span>
            <ChevronDown className="w-4 h-4 text-muted-foreground flex-shrink-0 group-open:rotate-180 transition-transform" />
          </summary>
          <div className="px-4 pb-4 border-t border-border bg-muted/20">
            <p className="text-sm text-foreground leading-relaxed mt-3">{faq.answer}</p>
            {faq.topic && (
              <span className="inline-block mt-2 text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded">
                {faq.topic}
              </span>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}

// ── TABS ───────────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'quiz',      label: 'Quiz',      icon: FileQuestion,  countKey: 'quiz_questions'  },
  { id: 'flashcard', label: 'Flashcards', icon: Layers,       countKey: 'flashcards'       },
  { id: 'glossary',  label: 'Glossary',  icon: BookMarked,    countKey: 'glossary_terms'   },
  { id: 'summary',   label: 'Summary',   icon: AlignLeft,     countKey: null               },
  { id: 'faq',       label: 'FAQ',       icon: HelpCircle,    countKey: null               },
] as const;

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function CreatorOutputsPage() {
  const { id: spaceId, contentId } = useParams<{ id: string; contentId: string }>();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<string>('quiz');

  const { data, isLoading, error } = useQuery<CreatorOutputs>({
    queryKey: ['creator-outputs', spaceId, contentId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/content/${contentId}/outputs`);
      if (!res.ok) throw new Error('Failed to load outputs');
      return res.json();
    },
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center text-center p-8">
        <div>
          <AlertCircle className="w-10 h-10 text-red-500 mx-auto mb-3" />
          <p className="text-foreground font-medium">Could not load outputs</p>
          <button onClick={() => router.back()} className="mt-4 text-sm text-primary hover:underline">
            Go back
          </button>
        </div>
      </div>
    );
  }

  const stats = data.stats;

  function tabCount(tab: typeof TABS[number]): number | null {
    if (!tab.countKey) return null;
    return stats[tab.countKey as keyof typeof stats] as number ?? null;
  }

  function hasContent(tabId: string): boolean {
    if (!data) return false;
    if (tabId === 'quiz') return data.quiz_questions.length > 0;
    if (tabId === 'flashcard') return data.flashcards.length > 0;
    if (tabId === 'glossary') return data.glossary_terms.length > 0;
    if (tabId === 'summary') return !!data.ai_outputs['summary'];
    if (tabId === 'faq') return !!data.ai_outputs['faq'];
    return false;
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-white sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
            <Link
              href={`/spaces/${spaceId}`}
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to space
            </Link>
          </div>
          <div className="mt-3 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-foreground">{data.content_title || 'Content'}</h1>
              <p className="text-sm text-muted-foreground mt-0.5">AI-generated outputs · creator preview</p>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              <div className="flex items-center gap-3 text-center">
                <Stat label="Quiz Qs" value={stats.quiz_questions} color="text-blue-600" />
                <Stat label="Flashcards" value={stats.flashcards} color="text-emerald-600" />
                <Stat label="Glossary" value={stats.glossary_terms} color="text-purple-600" />
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-4xl mx-auto px-6">
          <div className="flex gap-0 border-b border-transparent -mb-px overflow-x-auto">
            {TABS.map(tab => {
              const Icon = tab.icon;
              const count = tabCount(tab);
              const active = activeTab === tab.id;
              const has = hasContent(tab.id);
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                    active
                      ? 'border-primary text-primary'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  } ${!has ? 'opacity-40' : ''}`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.label}
                  {count !== null && (
                    <span className={`text-xs px-1.5 py-0.5 rounded-full font-semibold ${
                      active ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground'
                    }`}>
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-6 py-6">
        {activeTab === 'quiz' && (
          <div className="space-y-3">
            {data.quiz_questions.length === 0 ? (
              <EmptyState label="No quiz questions generated yet" />
            ) : (
              data.quiz_questions.map((q, i) => <QuizCard key={q.id} q={q} index={i} />)
            )}
          </div>
        )}

        {activeTab === 'flashcard' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {data.flashcards.length === 0 ? (
              <div className="col-span-2"><EmptyState label="No flashcards generated yet" /></div>
            ) : (
              data.flashcards.map((card, i) => <FlashcardCard key={card.id} card={card} index={i} />)
            )}
          </div>
        )}

        {activeTab === 'glossary' && (
          <div className="space-y-3">
            {data.glossary_terms.length === 0 ? (
              <EmptyState label="No glossary terms generated yet" />
            ) : (
              data.glossary_terms.map(term => (
                <div key={term.id} className="border border-border rounded-xl bg-white p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-foreground">{term.term}</span>
                        {term.category && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-medium">
                            {term.category}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-foreground leading-relaxed">{term.definition}</p>
                      {term.context && (
                        <p className="mt-2 text-xs text-muted-foreground italic border-l-2 border-border pl-3">
                          {term.context}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {activeTab === 'summary' && (
          <>
            {!data.ai_outputs['summary'] ? (
              <EmptyState label="No summary generated yet" />
            ) : (
              <SummarySection entry={data.ai_outputs['summary']} />
            )}
          </>
        )}

        {activeTab === 'faq' && (
          <>
            {!data.ai_outputs['faq'] ? (
              <EmptyState label="No FAQ generated yet" />
            ) : (
              <FAQSection entry={data.ai_outputs['faq']} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="text-center">
      <p className={`text-xl font-bold ${color}`}>{value}</p>
      <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <BookOpen className="w-10 h-10 text-muted-foreground/40 mb-3" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}
