'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { ChevronLeft, ChevronRight, RotateCcw, ThumbsUp, ThumbsDown, Plus, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

interface Card { front: string; back: string }

interface GenSettings {
  allow_learner_regen: boolean;
  max_flashcard_count: number;
  current_flashcard_count: number;
  flashcard_regen_available: boolean;
}

interface StudyFlashcardsProps {
  cards: Card[];
  contentId?: string;
  spaceId?: string;
  genSettings?: GenSettings;
  onRegen?: () => void;
}

const ADD_COUNT = 5;

export function StudyFlashcards({ cards, contentId, spaceId, genSettings, onRegen }: StudyFlashcardsProps) {
  // ── SM-2 queue-based state ────────────────────────────────────────────────
  // queue: ordered list of original card indices to present in this pass
  const [queue, setQueue]               = useState<number[]>(() => cards.map((_, i) => i));
  const [qPos, setQPos]                 = useState(0);
  // grades: per original card index, most recent grade
  const [grades, setGrades]             = useState<Record<number, 'known' | 'unknown'>>({});
  const [flipped, setFlipped]           = useState(false);
  const [done, setDone]                 = useState(false);
  const [isReviewPass, setIsReviewPass] = useState(false);
  const [generating, setGenerating]     = useState(false);

  const cardIdx      = queue[qPos] ?? -1;
  const card         = cardIdx >= 0 ? cards[cardIdx] : null;
  const totalInQueue = queue.length;

  const knownCount   = Object.values(grades).filter((g) => g === 'known').length;
  const unknownCount = Object.values(grades).filter((g) => g === 'unknown').length;

  const canRegen  = genSettings?.flashcard_regen_available && !generating;
  const remaining = genSettings
    ? genSettings.max_flashcard_count - (genSettings.current_flashcard_count ?? cards.length)
    : 0;

  const generateMore = async () => {
    setGenerating(true);
    try {
      const res = await fetch(`/api/spaces/${spaceId}/content/${contentId}/generate-more`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
        body: JSON.stringify({ output_type: 'flashcards', count: ADD_COUNT }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Generation failed');
      toast.success(`${data.added} new card${data.added !== 1 ? 's' : ''} added!`);
      onRegen?.();
    } catch (err: any) {
      toast.error(err.message ?? 'Could not generate more flashcards');
    } finally {
      setGenerating(false);
    }
  };

  const recordReview = (origIdx: number, isKnown: boolean) => {
    if (!spaceId || !contentId) return;
    fetch(`/api/spaces/${spaceId}/content/${contentId}/flashcard-review`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
      body: JSON.stringify({
        card_index: origIdx,
        front_text: cards[origIdx]?.front?.slice(0, 500) ?? null,
        known: isKnown,
      }),
    }).catch(() => {});
  };

  /** Grade current card and advance */
  const grade = (g: 'known' | 'unknown') => {
    if (cardIdx < 0) return;
    setGrades((prev) => ({ ...prev, [cardIdx]: g }));
    recordReview(cardIdx, g === 'known');
    const nextPos = qPos + 1;
    if (nextPos >= queue.length) {
      setDone(true);
    } else {
      setQPos(nextPos);
      setFlipped(false);
    }
  };

  /** Skip without grading */
  const skip = () => {
    if (qPos < queue.length - 1) { setQPos(qPos + 1); setFlipped(false); }
    else { setDone(true); }
  };

  const prev = () => {
    if (qPos > 0) { setQPos(qPos - 1); setFlipped(false); }
  };

  /** SM-2: start a focused pass on cards still marked unknown */
  const startReviewPass = () => {
    const toReview = Object.entries(grades)
      .filter(([, v]) => v === 'unknown')
      .map(([k]) => Number(k));
    if (toReview.length === 0) return;
    setQueue(toReview);
    setQPos(0);
    setFlipped(false);
    setDone(false);
    setIsReviewPass(true);
  };

  /** Full reset — all cards in original order */
  const reset = () => {
    setQueue(cards.map((_, i) => i));
    setQPos(0);
    setFlipped(false);
    setGrades({});
    setDone(false);
    setIsReviewPass(false);
  };

  const RegenBanner = () => {
    if (!genSettings?.allow_learner_regen) return null;
    const atMax = remaining <= 0;
    return (
      <div className={cn(
        'flex items-center justify-between px-4 py-2.5 rounded-[var(--radius)] border text-xs mt-4',
        atMax ? 'bg-muted/50 border-border text-muted-foreground' : 'bg-sky-50 border-sky-200',
      )}>
        <span className={atMax ? '' : 'text-sky-700'}>
          {atMax
            ? `Max cards reached (${genSettings.max_flashcard_count})`
            : `${cards.length} of ${genSettings.max_flashcard_count} cards · ${remaining} more available`}
        </span>
        {!atMax && (
          <button onClick={generateMore} disabled={!canRegen}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-sky-600 text-white rounded-[var(--radius)] font-medium hover:bg-sky-700 disabled:opacity-50 transition-colors">
            {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            {generating ? 'Generating…' : `Add ${Math.min(ADD_COUNT, remaining)} More`}
          </button>
        )}
      </div>
    );
  };

  if (cards.length === 0) {
    return <p className="text-center text-sm text-muted-foreground py-12">No flashcards available.</p>;
  }

  // ── Done / summary screen ────────────────────────────────────────────────
  if (done) {
    const remainingUnknown = Object.values(grades).filter((v) => v === 'unknown').length;
    return (
      <div className="max-w-md mx-auto text-center py-12">
        <div className="enterprise-card">
          <div className="w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-4">
            <ThumbsUp className="w-7 h-7 text-green-600" />
          </div>
          <h2 className="text-xl font-bold text-primary mb-1">
            {isReviewPass ? 'Review Pass Complete!' : 'Session Complete!'}
          </h2>
          <p className="text-muted-foreground mb-6">
            You&apos;ve reviewed {queue.length} card{queue.length !== 1 ? 's' : ''}.
          </p>
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="bg-green-50 rounded-[var(--radius)] p-4">
              <p className="text-2xl font-bold text-green-700">{knownCount}</p>
              <p className="text-sm text-green-600">Known</p>
            </div>
            <div className="bg-red-50 rounded-[var(--radius)] p-4">
              <p className="text-2xl font-bold text-red-700">{unknownCount}</p>
              <p className="text-sm text-red-600">Need review</p>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            {remainingUnknown > 0 && (
              <button onClick={startReviewPass}
                className="flex items-center justify-center gap-2 w-full px-4 py-2.5 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors">
                <RefreshCw className="w-4 h-4" />
                Review {remainingUnknown} Unknown Card{remainingUnknown !== 1 ? 's' : ''}
              </button>
            )}
            <button onClick={reset}
              className="flex items-center justify-center gap-2 w-full px-4 py-2.5 border border-border rounded-[var(--radius)] text-sm font-medium text-foreground hover:bg-muted transition-colors">
              <RotateCcw className="w-4 h-4" />
              {remainingUnknown > 0 ? 'Start Over (All Cards)' : 'Study Again'}
            </button>
          </div>
        </div>
        <RegenBanner />
      </div>
    );
  }

  if (!card) return null;

  const currentGrade = grades[cardIdx];

  return (
    <div className="max-w-lg mx-auto">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <p className="text-sm text-muted-foreground">{qPos + 1} / {totalInQueue}</p>
          {isReviewPass && (
            <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
              Review pass
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-green-600 font-medium">✓ {knownCount}</span>
          <span className="text-red-600 font-medium">✗ {unknownCount}</span>
        </div>
      </div>
      <div className="h-1.5 bg-muted rounded-full mb-6">
        <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${(qPos / totalInQueue) * 100}%` }} />
      </div>

      {/* Flip card */}
      <div
        className="relative h-64 mb-6 cursor-pointer"
        style={{ perspective: '1200px' }}
        onClick={() => setFlipped((f) => !f)}
      >
        <div className="absolute inset-0 transition-transform duration-500"
          style={{ transformStyle: 'preserve-3d', transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)' }}>
          {/* Front */}
          <div
            className={cn(
              'absolute inset-0 rounded-[var(--radius)] border-2 bg-card flex flex-col items-center justify-center p-8 text-center select-none',
              currentGrade === 'known'   ? 'border-green-300' :
              currentGrade === 'unknown' ? 'border-red-300'   : 'border-border',
            )}
            style={{ backfaceVisibility: 'hidden' }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-4">Question</p>
            <p className="text-lg font-semibold text-primary leading-snug">{card.front}</p>
            <p className="text-xs text-muted-foreground mt-6">Tap to reveal answer</p>
          </div>
          {/* Back */}
          <div
            className="absolute inset-0 rounded-[var(--radius)] border-2 border-primary/30 bg-primary/5 flex flex-col items-center justify-center p-8 text-center select-none"
            style={{ backfaceVisibility: 'hidden', transform: 'rotateY(180deg)' }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-primary/60 mb-4">Answer</p>
            <p className="text-base text-foreground leading-relaxed">{card.back}</p>
          </div>
        </div>
      </div>

      {/* Controls */}
      {flipped ? (
        <div className="flex items-center justify-center gap-3">
          <button onClick={() => grade('unknown')}
            className="flex items-center gap-2 px-5 py-2.5 border border-red-400 text-red-600 bg-red-50 rounded-[var(--radius)] text-sm font-medium hover:bg-red-100 transition-colors">
            <ThumbsDown className="w-4 h-4" /> Need Review
          </button>
          <button onClick={() => grade('known')}
            className="flex items-center gap-2 px-5 py-2.5 border border-green-400 text-green-600 bg-green-50 rounded-[var(--radius)] text-sm font-medium hover:bg-green-100 transition-colors">
            <ThumbsUp className="w-4 h-4" /> Got It
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <button onClick={prev} disabled={qPos === 0}
            className="flex items-center gap-1 px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted disabled:opacity-30 transition-colors">
            <ChevronLeft className="w-4 h-4" /> Prev
          </button>
          <p className="text-sm text-muted-foreground">Flip to self-assess</p>
          <button onClick={skip}
            className="flex items-center gap-1 px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors">
            Skip <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
      <RegenBanner />
    </div>
  );
}
