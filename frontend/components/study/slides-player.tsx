'use client';

/**
 * SlidesPlayer — PF-03 Interactive Slides
 *
 * Renders PPTX slide images one at a time with:
 * - Per-slide MCQ / True-False quiz overlay (auto-appears when slide loads)
 * - Slide strip thumbnail navigation
 * - Progress tracking (marks complete on last slide)
 * - Keyboard arrow key navigation
 */

import { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import {
  ChevronLeft, ChevronRight, Loader2, CheckCircle2, XCircle,
  Maximize2, Grid, Layers,
} from 'lucide-react';

interface Interaction {
  index: number;
  slide_num?: number;
  page_num?: number;
  type: 'mcq' | 'truefalse' | 'callout';
  question?: string;
  options?: string[];
  correct_index?: number;
  correct_answer?: boolean;
  explanation?: string;
  text?: string;
}

interface Slide {
  index: number;
  image_url: string;
  thumbnail_url: string;
  width: number;
  height: number;
  interaction: Interaction | null;
}

interface SlidesData {
  content_id: string;
  title: string;
  slide_count: number;
  slides: Slide[];
}

interface Response {
  interaction_index: number;
  is_correct: boolean | null;
  selected_answer: string;
}

interface Props {
  contentId: string;
  spaceId: string;
  onProgressUpdate?: (pct: number) => void;
}

export function SlidesPlayer({ contentId, spaceId, onProgressUpdate }: Props) {
  const [currentIndex, setCurrentIndex] = useState(0); // 0-based
  const [showStrip, setShowStrip] = useState(true);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [answeredResult, setAnsweredResult] = useState<{ is_correct: boolean | null; explanation?: string } | null>(null);
  const [answeredSlides, setAnsweredSlides] = useState<Set<number>>(new Set());

  const { data: slidesData, isLoading } = useQuery<SlidesData>({
    queryKey: ['slides', contentId],
    queryFn: async () => {
      const res = await fetch(`/api/library/${contentId}/slides`);
      if (!res.ok) throw new Error('Failed to load slides');
      return res.json();
    },
  });

  const slides = slidesData?.slides ?? [];
  const currentSlide = slides[currentIndex] ?? null;

  // Reset question state when slide changes
  useEffect(() => {
    setSelectedAnswer(null);
    setAnsweredResult(null);
  }, [currentIndex]);

  // Progress update
  useEffect(() => {
    if (!slides.length) return;
    const pct = Math.round(((currentIndex + 1) / slides.length) * 100);
    onProgressUpdate?.(pct);
  }, [currentIndex, slides.length, onProgressUpdate]);

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        setCurrentIndex((i) => Math.min(slides.length - 1, i + 1));
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        setCurrentIndex((i) => Math.max(0, i - 1));
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [slides.length]);

  const submitResponse = useMutation({
    mutationFn: async (body: { interaction_index: number; selected_answer: string }) => {
      const res = await fetch(`/api/library/${contentId}/slide-respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return res.json();
    },
    onSuccess: (data) => {
      setAnsweredResult({ is_correct: data.is_correct, explanation: data.explanation });
      if (currentSlide?.interaction) {
        setAnsweredSlides((s) => new Set(s).add(currentSlide.interaction!.index));
      }
    },
  });

  const handleSubmit = () => {
    if (!currentSlide?.interaction || !selectedAnswer) return;
    submitResponse.mutate({
      interaction_index: currentSlide.interaction.index,
      selected_answer: selectedAnswer,
    });
  };

  const goTo = (index: number) => {
    setCurrentIndex(Math.max(0, Math.min(slides.length - 1, index)));
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Loading slides…</p>
      </div>
    );
  }

  if (!slides.length) {
    return (
      <div className="py-16 text-center text-muted-foreground text-sm">
        No slides available yet. Processing may still be in progress.
      </div>
    );
  }

  const aspectRatio = currentSlide
    ? `${currentSlide.width} / ${currentSlide.height}`
    : '16 / 9';

  return (
    <div className="flex gap-4">
      {/* ── Slide thumbnail strip ── */}
      {showStrip && (
        <div className="w-28 flex-shrink-0 overflow-y-auto max-h-[600px] space-y-1.5 pr-1">
          {slides.map((slide, i) => (
            <button
              key={slide.index}
              onClick={() => goTo(i)}
              className={cn(
                'w-full rounded overflow-hidden border-2 transition-all relative',
                i === currentIndex ? 'border-primary' : 'border-transparent hover:border-border',
              )}
            >
              <img
                src={slide.thumbnail_url}
                alt={`Slide ${slide.index}`}
                className="w-full object-cover"
                loading="lazy"
              />
              <span className="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-[9px] text-center py-0.5">
                {slide.index}
              </span>
              {slide.interaction && answeredSlides.has(slide.interaction.index) && (
                <div className="absolute top-1 right-1">
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                </div>
              )}
              {slide.interaction && !answeredSlides.has(slide.interaction.index) && (
                <div className="absolute top-1 right-1 w-2 h-2 rounded-full bg-primary" />
              )}
            </button>
          ))}
        </div>
      )}

      {/* ── Main area ── */}
      <div className="flex-1 min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-muted/30 rounded-t-[var(--radius)]">
          <button
            onClick={() => goTo(currentIndex - 1)}
            disabled={currentIndex <= 0}
            className="p-1.5 rounded hover:bg-muted disabled:opacity-40"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-sm font-medium text-muted-foreground">
            {currentIndex + 1} / {slides.length}
          </span>
          <button
            onClick={() => goTo(currentIndex + 1)}
            disabled={currentIndex >= slides.length - 1}
            className="p-1.5 rounded hover:bg-muted disabled:opacity-40"
          >
            <ChevronRight className="w-4 h-4" />
          </button>

          <div className="flex-1" />

          {/* Progress bar */}
          <div className="w-32 h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all"
              style={{ width: `${((currentIndex + 1) / slides.length) * 100}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground">
            {Math.round(((currentIndex + 1) / slides.length) * 100)}%
          </span>

          <button
            onClick={() => setShowStrip((s) => !s)}
            className="p-1.5 rounded hover:bg-muted text-muted-foreground"
            title="Toggle slide strip"
          >
            <Grid className="w-4 h-4" />
          </button>
        </div>

        {/* Slide image */}
        <div className="bg-black rounded-b-[var(--radius)] relative overflow-hidden" style={{ aspectRatio }}>
          {currentSlide && (
            <img
              key={currentSlide.index}
              src={currentSlide.image_url}
              alt={`Slide ${currentSlide.index}`}
              className="w-full h-full object-contain"
            />
          )}

          {/* Callout overlay */}
          {currentSlide?.interaction?.type === 'callout' && (
            <div className="absolute bottom-4 left-4 right-4 bg-black/70 text-white text-sm rounded-[var(--radius)] px-4 py-3 backdrop-blur-sm">
              💡 {currentSlide.interaction.text}
            </div>
          )}
        </div>

        {/* Quiz question (below slide) */}
        {currentSlide?.interaction && currentSlide.interaction.type !== 'callout' && (
          <div className="mt-4 p-4 border-2 border-primary/30 rounded-[var(--radius)] bg-primary/5">
            <div className="flex items-center gap-2 mb-3">
              <Layers className="w-4 h-4 text-primary" />
              <p className="text-xs font-semibold uppercase tracking-widest text-primary">
                Slide {currentSlide.index} — {currentSlide.interaction.type === 'truefalse' ? 'True or False' : 'Question'}
              </p>
            </div>
            <p className="text-sm font-medium text-foreground mb-4">{currentSlide.interaction.question}</p>

            {currentSlide.interaction.type === 'mcq' && (
              <div className="space-y-2">
                {(currentSlide.interaction.options ?? []).map((opt, i) => {
                  const isSelected = selectedAnswer === String(i);
                  const isCorrectAns = answeredResult && i === currentSlide.interaction!.correct_index;
                  const isWrongSelected = answeredResult && isSelected && !answeredResult.is_correct;
                  return (
                    <button
                      key={i}
                      disabled={!!answeredResult}
                      onClick={() => setSelectedAnswer(String(i))}
                      className={cn(
                        'w-full text-left text-sm px-3 py-2.5 rounded border transition-colors',
                        isCorrectAns ? 'border-emerald-500 bg-emerald-50 text-emerald-800' :
                        isWrongSelected ? 'border-red-400 bg-red-50 text-red-700' :
                        isSelected ? 'border-primary bg-primary/10 text-primary' :
                        'border-border hover:bg-muted',
                      )}
                    >
                      <span className="font-medium mr-2">{String.fromCharCode(65 + i)}.</span> {opt}
                    </button>
                  );
                })}
              </div>
            )}

            {currentSlide.interaction.type === 'truefalse' && (
              <div className="flex gap-3">
                {['true', 'false'].map((val) => (
                  <button
                    key={val}
                    disabled={!!answeredResult}
                    onClick={() => setSelectedAnswer(val)}
                    className={cn(
                      'flex-1 py-2.5 rounded border text-sm font-medium capitalize transition-colors',
                      selectedAnswer === val && !answeredResult ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:bg-muted',
                    )}
                  >
                    {val}
                  </button>
                ))}
              </div>
            )}

            {!answeredResult ? (
              <button
                disabled={!selectedAnswer || submitResponse.isPending}
                onClick={handleSubmit}
                className="mt-4 w-full py-2 bg-primary text-white rounded font-medium text-sm disabled:opacity-50"
              >
                {submitResponse.isPending ? 'Submitting…' : 'Submit Answer'}
              </button>
            ) : (
              <div className={cn('mt-4 p-3 rounded flex items-start gap-2',
                answeredResult.is_correct ? 'bg-emerald-50 border border-emerald-200' : 'bg-red-50 border border-red-200')}>
                {answeredResult.is_correct
                  ? <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
                  : <XCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />}
                <div>
                  <p className={cn('text-sm font-semibold', answeredResult.is_correct ? 'text-emerald-700' : 'text-red-600')}>
                    {answeredResult.is_correct ? 'Correct!' : 'Incorrect'}
                  </p>
                  {answeredResult.explanation && (
                    <p className="text-xs text-muted-foreground mt-1">{answeredResult.explanation}</p>
                  )}
                  <button
                    onClick={() => goTo(currentIndex + 1)}
                    disabled={currentIndex >= slides.length - 1}
                    className="mt-2 text-xs text-primary font-medium disabled:opacity-40"
                  >
                    Next slide →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
