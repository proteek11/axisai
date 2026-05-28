'use client';

import { useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import {
  CheckCircle2, XCircle, RotateCcw, ChevronRight, ChevronLeft, Trophy,
  Loader2, Plus, Lock, Shuffle,
} from 'lucide-react';
import { toast } from 'sonner';

interface Question {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
  bloom_level: string;
}

interface GenSettings {
  allow_learner_regen: boolean;
  max_quiz_count: number;
  current_quiz_count: number;
  quiz_regen_available: boolean;
}

interface StudyQuizProps {
  questions: Question[];
  contentId: string;
  spaceId: string;
  genSettings?: GenSettings;
  onRegen?: () => void;
}

const BLOOM_COLORS: Record<string, string> = {
  remember:   'border-blue-400 text-blue-600 bg-blue-50',
  understand: 'border-teal-400 text-teal-600 bg-teal-50',
  apply:      'border-green-400 text-green-600 bg-green-50',
  analyze:    'border-yellow-400 text-yellow-700 bg-yellow-50',
  evaluate:   'border-orange-400 text-orange-600 bg-orange-50',
  create:     'border-red-400 text-red-600 bg-red-50',
};

const ADD_COUNT = 5;

/** Fisher-Yates in-place shuffle — returns a new shuffled array */
function fisherYates<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function isTrueFalseQuestion(q: Question): boolean {
  const startsWithTF = /^true or false[:\s]/i.test(q.question.trim());
  const hasTFOptions = q.options.length === 2 && q.options.every((o) => /^(true|false)$/i.test(o.trim()));
  return startsWithTF || hasTFOptions;
}
function stripTFPrefix(text: string): string { return text.replace(/^true or false[:\s]+/i, '').trim(); }
function getTFOptions(q: Question): string[] { return q.options.length === 2 ? q.options : ['True', 'False']; }
function isOpenEnded(q: Question): boolean { return !q.options || q.options.length === 0; }

export function StudyQuiz({ questions, contentId, spaceId, genSettings, onRegen }: StudyQuizProps) {
  const [qIdx, setQIdx]             = useState(0);
  const [answers, setAnswers]       = useState<number[]>(() => questions.map((q) => (isOpenEnded(q) ? -2 : -1)));
  const [showResult, setShowResult] = useState(false);
  const [generating, setGenerating] = useState(false);

  // ── Shuffle state ─────────────────────────────────────────────────────────
  // shuffledQOrder[displayIdx] = originalQuestionIndex
  // shuffledOptOrders[displayIdx] = [originalOptionIndices in display order]
  const [isShuffled, setIsShuffled]             = useState(false);
  const [shuffledQOrder, setShuffledQOrder]     = useState<number[]>([]);
  const [shuffledOptOrders, setShuffledOptOrders] = useState<number[][]>([]);

  const generateMore = async () => {
    setGenerating(true);
    try {
      const res = await fetch(`/api/spaces/${spaceId}/content/${contentId}/generate-more`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ output_type: 'quiz', count: ADD_COUNT }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Generation failed');
      toast.success(`${data.added} new question${data.added !== 1 ? 's' : ''} added!`);
      onRegen?.();
    } catch (err: any) {
      toast.error(err.message ?? 'Could not generate more questions');
    } finally {
      setGenerating(false);
    }
  };

  const canRegen = genSettings?.quiz_regen_available && !generating;
  const remaining = genSettings
    ? genSettings.max_quiz_count - (genSettings.current_quiz_count ?? questions.length)
    : 0;

  /** Reset to ordered mode */
  const reset = () => {
    setQIdx(0);
    setAnswers(questions.map((q) => (isOpenEnded(q) ? -2 : -1)));
    setShowResult(false);
    setIsShuffled(false);
    setShuffledQOrder([]);
    setShuffledOptOrders([]);
  };

  /** Start a new shuffled attempt */
  const startShuffled = () => {
    const newQOrder = fisherYates(questions.map((_, i) => i));
    // Build per-display-position option shuffle maps
    const newOptOrders = newQOrder.map((origQIdx) => {
      const oq = questions[origQIdx];
      // Don't shuffle True/False or Open-Ended options — only MCQ
      if (isOpenEnded(oq) || isTrueFalseQuestion(oq)) {
        return oq.options.map((_, i) => i);
      }
      return fisherYates(oq.options.map((_, i) => i));
    });
    setShuffledQOrder(newQOrder);
    setShuffledOptOrders(newOptOrders);
    setIsShuffled(true);
    setQIdx(0);
    // Init answers based on question type at each display position
    setAnswers(newQOrder.map((origQIdx) => (isOpenEnded(questions[origQIdx]) ? -2 : -1)));
    setShowResult(false);
  };

  if (questions.length === 0) {
    return <p className="text-center text-sm text-muted-foreground py-12">No quiz questions available.</p>;
  }

  const scorableCount = questions.filter((q) => !isOpenEnded(q)).length;
  if (scorableCount === 0) {
    return <p className="text-center text-sm text-muted-foreground py-12">This quiz contains only open-ended questions.</p>;
  }

  // ── Derive current question (respects shuffle) ───────────────────────────
  const qOrigIdx = isShuffled ? shuffledQOrder[qIdx] : qIdx;
  const q        = questions[qOrigIdx];
  const selected = answers[qIdx];
  const hasAnswered = selected !== -1;
  const isTF    = isTrueFalseQuestion(q);
  const isOE    = isOpenEnded(q);

  // Option display order (only MCQ options are shuffled)
  const displayOptOrder: number[] | null =
    isShuffled && !isTF && !isOE ? (shuffledOptOrders[qIdx] ?? null) : null;

  const options = isTF
    ? getTFOptions(q)
    : displayOptOrder
    ? displayOptOrder.map((i) => q.options[i])
    : q.options;

  // Where does the correct answer appear in the displayed options?
  const effectiveCorrectIdx = displayOptOrder
    ? displayOptOrder.indexOf(q.correct_index)
    : q.correct_index;

  const isCorrect = selected === effectiveCorrectIdx;

  // Score across all answered questions (handles shuffle)
  const score = answers.reduce((acc, ans, i) => {
    if (!isShuffled) {
      return acc + (ans === questions[i].correct_index ? 1 : 0);
    }
    const oIdx = shuffledQOrder[i];
    const oQ   = questions[oIdx];
    if (isOpenEnded(oQ)) return acc;
    const oOptOrder = isTrueFalseQuestion(oQ) ? null : (shuffledOptOrders[i] ?? null);
    const effCorr   = oOptOrder ? oOptOrder.indexOf(oQ.correct_index) : oQ.correct_index;
    return acc + (ans === effCorr ? 1 : 0);
  }, 0);

  const allAnswered    = answers.every((a) => a !== -1);
  const answeredCount  = answers.filter((a) => a !== -1).length;

  const recordAttempt = (displayOptIdx: number) => {
    if (!spaceId || !contentId) return;
    // Send original (un-shuffled) indices for analytics
    const origOptIdx = displayOptOrder ? displayOptOrder[displayOptIdx] : displayOptIdx;
    fetch(`/api/spaces/${spaceId}/content/${contentId}/quiz-attempt`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
      body: JSON.stringify({
        question_index: qOrigIdx,
        question_text: q.question.slice(0, 500),
        selected_index: origOptIdx,
        correct_index: q.correct_index,
        is_correct: origOptIdx === q.correct_index,
        bloom_level: q.bloom_level || null,
      }),
    }).catch(() => {});
  };

  const selectOption = (displayOptIdx: number) => {
    if (hasAnswered) return;
    setAnswers((prev) => { const n = [...prev]; n[qIdx] = displayOptIdx; return n; });
    recordAttempt(displayOptIdx);
  };

  const goNext = () => { if (qIdx < questions.length - 1) setQIdx(qIdx + 1); else setShowResult(true); };
  const goPrev = () => { if (qIdx > 0) setQIdx(qIdx - 1); };

  // ── Regen banner ─────────────────────────────────────────────────────────
  const RegenBanner = () => {
    if (!genSettings) return null;
    if (!genSettings.allow_learner_regen) return null;
    const atMax = remaining <= 0;
    return (
      <div className={cn(
        'flex items-center justify-between px-4 py-2.5 rounded-[var(--radius)] border text-xs mt-4',
        atMax ? 'bg-muted/50 border-border text-muted-foreground' : 'bg-violet-50 border-violet-200',
      )}>
        <span className={atMax ? '' : 'text-violet-700'}>
          {atMax
            ? `Max questions reached (${genSettings.max_quiz_count})`
            : `${questions.length} of ${genSettings.max_quiz_count} questions · ${remaining} more available`}
        </span>
        {!atMax && (
          <button
            onClick={generateMore}
            disabled={!canRegen}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 text-white rounded-[var(--radius)] font-medium hover:bg-violet-700 disabled:opacity-50 transition-colors"
          >
            {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            {generating ? 'Generating…' : `Add ${Math.min(ADD_COUNT, remaining)} More`}
          </button>
        )}
      </div>
    );
  };

  // ── Results screen ──────────────────────────────────────────────────────
  if (showResult) {
    const pct = Math.round((score / scorableCount) * 100);
    return (
      <div className="max-w-md mx-auto text-center py-8">
        <div className="enterprise-card">
          <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
            <Trophy className="w-8 h-8 text-primary" />
          </div>
          {isShuffled && (
            <span className="inline-flex items-center gap-1 text-xs text-violet-600 bg-violet-50 border border-violet-200 px-2 py-0.5 rounded-full mb-3">
              <Shuffle className="w-3 h-3" /> Shuffled mode
            </span>
          )}
          <h2 className="text-2xl font-bold text-primary mb-1">{pct}%</h2>
          <p className="text-muted-foreground mb-1">{score} / {scorableCount} correct</p>
          <p className="text-sm text-muted-foreground mb-6">
            {pct >= 80 ? '🎉 Great work!' : pct >= 60 ? '👍 Good effort — keep studying!' : '📚 Review the material and try again'}
          </p>
          <div className="flex items-center justify-center gap-3">
            <button onClick={reset}
              className="flex items-center gap-2 px-4 py-2 border border-border text-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-muted transition-colors">
              <RotateCcw className="w-4 h-4" /> Try Again
            </button>
            <button onClick={startShuffled}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors">
              <Shuffle className="w-4 h-4" /> Retake (Shuffled)
            </button>
          </div>
        </div>
        <RegenBanner />
      </div>
    );
  }

  // ── Open-ended card ────────────────────────────────────────────────────
  if (isOE) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm text-muted-foreground">{qIdx + 1} / {questions.length}</p>
          <span className="text-xs text-muted-foreground italic">Open-ended — no scoring</span>
        </div>
        <div className="enterprise-card">
          <p className="font-semibold text-foreground mb-4">{q.question}</p>
          <p className="text-sm text-muted-foreground italic">Reflect on your answer, then continue.</p>
        </div>
        <div className="flex justify-between mt-4">
          <button onClick={goPrev} disabled={qIdx === 0}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground disabled:opacity-30">
            <ChevronLeft className="w-4 h-4" /> Prev
          </button>
          <button onClick={goNext}
            className="flex items-center gap-1 text-sm font-medium text-primary hover:text-primary/80">
            {qIdx < questions.length - 1 ? <><span>Next</span><ChevronRight className="w-4 h-4" /></> : <span>Finish</span>}
          </button>
        </div>
        <RegenBanner />
      </div>
    );
  }

  // ── Normal question card ───────────────────────────────────────────────
  const displayQuestion = isTF ? stripTFPrefix(q.question) : q.question;
  const bloomClass = BLOOM_COLORS[q.bloom_level?.toLowerCase()] ?? 'border-border text-muted-foreground bg-muted';

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <p className="text-sm text-muted-foreground">{qIdx + 1} / {questions.length}</p>
          {isShuffled && (
            <span className="inline-flex items-center gap-0.5 text-xs text-violet-600">
              <Shuffle className="w-3 h-3" /> Shuffled
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {q.bloom_level && (
            <span className={cn('text-xs px-2 py-0.5 rounded-full border capitalize', bloomClass)}>
              {q.bloom_level}
            </span>
          )}
          <span className="text-xs text-muted-foreground">{answeredCount} answered</span>
        </div>
      </div>
      <div className="h-1.5 bg-muted rounded-full mb-5">
        <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${((qIdx + 1) / questions.length) * 100}%` }} />
      </div>
      <div className="enterprise-card mb-4">
        {isTF && (
          <span className="inline-block text-xs font-semibold uppercase tracking-wide text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full mb-3">
            True or False
          </span>
        )}
        <p className="font-semibold text-foreground text-base leading-snug">{displayQuestion}</p>
      </div>
      <div className={cn('grid gap-2 mb-5', isTF ? 'grid-cols-2' : 'grid-cols-1')}>
        {options.map((opt, oi) => {
          const isSelected    = selected === oi;
          const isCorrectOpt  = oi === effectiveCorrectIdx;
          let style = 'border-border bg-background hover:bg-muted/50 cursor-pointer';
          if (hasAnswered) {
            if (isCorrectOpt)  style = 'border-green-400 bg-green-50 cursor-default';
            else if (isSelected) style = 'border-red-400 bg-red-50 cursor-default';
            else style = 'border-border bg-muted/30 cursor-default opacity-60';
          } else if (isSelected) style = 'border-primary bg-primary/5 cursor-pointer';
          return (
            <button key={oi} onClick={() => selectOption(oi)} disabled={hasAnswered}
              className={cn('flex items-center gap-3 w-full text-left px-4 py-3 rounded-[var(--radius)] border text-sm transition-colors', style)}>
              <span className={cn('w-6 h-6 rounded-full border-2 flex items-center justify-center flex-shrink-0 text-xs font-bold',
                hasAnswered && isCorrectOpt  ? 'border-green-500 bg-green-500 text-white' :
                hasAnswered && isSelected    ? 'border-red-500 bg-red-500 text-white' : 'border-current')}>
                {hasAnswered && isCorrectOpt  ? <CheckCircle2 className="w-3.5 h-3.5" /> :
                 hasAnswered && isSelected    ? <XCircle className="w-3.5 h-3.5" /> :
                 String.fromCharCode(65 + oi)}
              </span>
              <span className="flex-1">{opt}</span>
            </button>
          );
        })}
      </div>
      {hasAnswered && q.explanation && (
        <div className={cn('rounded-[var(--radius)] px-4 py-3 text-sm mb-4',
          isCorrect ? 'bg-green-50 border border-green-200 text-green-800' : 'bg-red-50 border border-red-200 text-red-800')}>
          <span className="font-semibold">{isCorrect ? '✓ Correct! ' : '✗ Incorrect. '}</span>
          {q.explanation}
        </div>
      )}
      <div className="flex justify-between">
        <button onClick={goPrev} disabled={qIdx === 0}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground disabled:opacity-30">
          <ChevronLeft className="w-4 h-4" /> Prev
        </button>
        <button onClick={goNext} disabled={!hasAnswered}
          className="flex items-center gap-1 text-sm font-medium bg-primary text-white px-4 py-1.5 rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-30 disabled:cursor-not-allowed">
          {qIdx < questions.length - 1 ? <><span>Next</span><ChevronRight className="w-4 h-4" /></> : <span>Finish →</span>}
        </button>
      </div>
      <RegenBanner />
    </div>
  );
}
