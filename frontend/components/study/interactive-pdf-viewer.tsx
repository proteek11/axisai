'use client';

/**
 * InteractivePDFViewer — PF-05
 *
 * Renders a PDF page-by-page using pdf.js (CDN), with:
 * - Embedded quiz questions at configured pages (from content_items.interactions)
 * - Learner annotations (highlight / note) saved to backend
 * - Progress tracking (marks content complete when last page reached)
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import {
  ChevronLeft, ChevronRight, Loader2, Highlighter, MessageSquare,
  CheckCircle2, XCircle, Trash2, ZoomIn, ZoomOut, RotateCcw,
} from 'lucide-react';

interface Interaction {
  index: number;
  page_num: number;
  type: 'mcq' | 'truefalse' | 'callout';
  question?: string;
  options?: string[];
  correct_index?: number;
  correct_answer?: boolean;
  explanation?: string;
  text?: string;
}

interface Annotation {
  id: string;
  page_num: number;
  annotation_type: string;
  content: string;
  position_data: Record<string, unknown>;
  color: string;
}

interface Response {
  interaction_index: number;
  is_correct: boolean | null;
  selected_answer: string;
}

interface Props {
  contentId: string;
  spaceId: string;
  interactions: Interaction[];
  onProgressUpdate?: (pct: number) => void;
}

declare global {
  interface Window {
    pdfjsLib: any;
  }
}

const PDF_JS_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
const PDF_JS_WORKER = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

export function InteractivePDFViewer({ contentId, spaceId, interactions, onProgressUpdate }: Props) {
  const [pdfDoc, setPdfDoc] = useState<any>(null);
  const [totalPages, setTotalPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1.2);
  const [loading, setLoading] = useState(true);
  const [pdfLibLoaded, setPdfLibLoaded] = useState(false);
  const [activeAnnotationMode, setActiveAnnotationMode] = useState<'off' | 'highlight' | 'note'>('off');
  const [activeQuestion, setActiveQuestion] = useState<Interaction | null>(null);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [answeredResult, setAnsweredResult] = useState<{ is_correct: boolean | null; explanation?: string } | null>(null);
  const [noteText, setNoteText] = useState('');
  const [showNoteInput, setShowNoteInput] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderTaskRef = useRef<any>(null);
  const qc = useQueryClient();

  // Load pdf.js from CDN
  useEffect(() => {
    if (window.pdfjsLib) { setPdfLibLoaded(true); return; }
    const script = document.createElement('script');
    script.src = PDF_JS_CDN;
    script.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_JS_WORKER;
      setPdfLibLoaded(true);
    };
    document.head.appendChild(script);
    return () => { document.head.removeChild(script); };
  }, []);

  // Load PDF once lib is ready
  useEffect(() => {
    if (!pdfLibLoaded) return;
    setLoading(true);

    window.pdfjsLib.getDocument({
      url: `/api/library/${contentId}/pdf-serve`,
      withCredentials: true,
    }).promise.then((doc: any) => {
      setPdfDoc(doc);
      setTotalPages(doc.numPages);
      setLoading(false);
    }).catch((err: Error) => {
      console.error('PDF load error:', err);
      setLoading(false);
    });
  }, [pdfLibLoaded, contentId]);

  // Render current page onto canvas
  const renderPage = useCallback(async (pageNum: number, sc: number) => {
    if (!pdfDoc || !canvasRef.current) return;
    if (renderTaskRef.current) {
      renderTaskRef.current.cancel();
    }

    const page = await pdfDoc.getPage(pageNum);
    const viewport = page.getViewport({ scale: sc });
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    canvas.height = viewport.height;
    canvas.width = viewport.width;

    const renderContext = { canvasContext: ctx!, viewport };
    renderTaskRef.current = page.render(renderContext);
    try {
      await renderTaskRef.current.promise;
    } catch (e: any) {
      if (e?.name !== 'RenderingCancelledException') throw e;
    }
  }, [pdfDoc]);

  useEffect(() => {
    renderPage(currentPage, scale);
  }, [renderPage, currentPage, scale]);

  // Update progress when page changes
  useEffect(() => {
    if (!totalPages) return;
    const pct = Math.round((currentPage / totalPages) * 100);
    onProgressUpdate?.(pct);

    // Auto-show embedded question for this page
    const q = interactions.find((i) => i.page_num === currentPage && i.type !== 'callout');
    if (q) {
      setActiveQuestion(q);
      setSelectedAnswer(null);
      setAnsweredResult(null);
    } else {
      setActiveQuestion(null);
    }

    // Callout for this page
    const callout = interactions.find((i) => i.page_num === currentPage && i.type === 'callout');
    if (callout) {
      // We'll show it as a toast-style banner (handled in JSX below)
    }
  }, [currentPage, totalPages, interactions, onProgressUpdate]);

  // Annotations query
  const { data: annotations = [] } = useQuery<Annotation[]>({
    queryKey: ['pdf-annotations', contentId],
    queryFn: async () => {
      const res = await fetch(`/api/library/${contentId}/pdf-annotations`);
      if (!res.ok) return [];
      return res.json();
    },
  });

  const createAnnotation = useMutation({
    mutationFn: async (body: {
      page_num: number; annotation_type: string; content: string; position_data?: Record<string, unknown>; color?: string;
    }) => {
      const res = await fetch(`/api/library/${contentId}/pdf-annotations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return res.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pdf-annotations', contentId] }),
  });

  const deleteAnnotation = useMutation({
    mutationFn: async (annId: string) => {
      await fetch(`/api/library/${contentId}/pdf-annotations/${annId}`, { method: 'DELETE' });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pdf-annotations', contentId] }),
  });

  const submitResponse = useMutation({
    mutationFn: async (body: { interaction_index: number; selected_answer: string }) => {
      const res = await fetch(`/api/library/${contentId}/pdf-respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return res.json();
    },
    onSuccess: (data) => {
      setAnsweredResult({ is_correct: data.is_correct, explanation: data.explanation });
    },
  });

  const handleCanvasMouseUp = useCallback(() => {
    if (activeAnnotationMode === 'off') return;
    const selection = window.getSelection();
    const selectedText = selection?.toString().trim();

    if (activeAnnotationMode === 'highlight' && selectedText && selectedText.length > 2) {
      createAnnotation.mutate({
        page_num: currentPage,
        annotation_type: 'highlight',
        content: selectedText,
        color: '#FFF176',
      });
      selection?.removeAllRanges();
    } else if (activeAnnotationMode === 'note') {
      setNoteText('');
      setShowNoteInput(true);
    }
  }, [activeAnnotationMode, currentPage, createAnnotation]);

  const handleSubmitAnswer = () => {
    if (!activeQuestion || !selectedAnswer) return;
    submitResponse.mutate({
      interaction_index: activeQuestion.index,
      selected_answer: selectedAnswer,
    });
  };

  const pageAnnotations = annotations.filter((a) => a.page_num === currentPage);
  const callout = interactions.find((i) => i.page_num === currentPage && i.type === 'callout');

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Loading PDF…</p>
      </div>
    );
  }

  return (
    <div className="flex gap-4">
      {/* ── Main PDF column ── */}
      <div className="flex-1 min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-muted/30 rounded-t-[var(--radius)]">
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
            className="p-1.5 rounded hover:bg-muted disabled:opacity-40"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-sm font-medium text-muted-foreground">
            {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
            className="p-1.5 rounded hover:bg-muted disabled:opacity-40"
          >
            <ChevronRight className="w-4 h-4" />
          </button>

          <div className="w-px h-4 bg-border mx-1" />

          <button onClick={() => setScale((s) => Math.min(2.5, s + 0.2))} className="p-1.5 rounded hover:bg-muted">
            <ZoomIn className="w-4 h-4" />
          </button>
          <button onClick={() => setScale((s) => Math.max(0.5, s - 0.2))} className="p-1.5 rounded hover:bg-muted">
            <ZoomOut className="w-4 h-4" />
          </button>
          <button onClick={() => setScale(1.2)} className="p-1.5 rounded hover:bg-muted">
            <RotateCcw className="w-4 h-4" />
          </button>

          <div className="w-px h-4 bg-border mx-1" />

          <button
            onClick={() => setActiveAnnotationMode((m) => m === 'highlight' ? 'off' : 'highlight')}
            className={cn('flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors',
              activeAnnotationMode === 'highlight'
                ? 'bg-yellow-200 text-yellow-800'
                : 'hover:bg-muted text-muted-foreground')}
          >
            <Highlighter className="w-3.5 h-3.5" />
            Highlight
          </button>
          <button
            onClick={() => setActiveAnnotationMode((m) => m === 'note' ? 'off' : 'note')}
            className={cn('flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors',
              activeAnnotationMode === 'note'
                ? 'bg-blue-200 text-blue-800'
                : 'hover:bg-muted text-muted-foreground')}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            Note
          </button>
        </div>

        {/* Callout banner */}
        {callout && (
          <div className="mx-4 mt-3 px-4 py-3 bg-blue-50 border border-blue-200 rounded-[var(--radius)] text-sm text-blue-800">
            💡 {callout.text}
          </div>
        )}

        {/* Canvas */}
        <div className="overflow-auto bg-gray-100 rounded-b-[var(--radius)] p-4">
          <canvas
            ref={canvasRef}
            className="mx-auto shadow-md rounded cursor-text"
            onMouseUp={handleCanvasMouseUp}
          />
        </div>

        {/* Note input */}
        {showNoteInput && (
          <div className="mt-3 p-3 border border-border rounded-[var(--radius)] bg-white">
            <p className="text-xs font-medium text-muted-foreground mb-2">Add a note for page {currentPage}</p>
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              rows={3}
              placeholder="Type your note here…"
              className="w-full text-sm border border-border rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <div className="flex justify-end gap-2 mt-2">
              <button onClick={() => setShowNoteInput(false)} className="text-xs text-muted-foreground hover:text-foreground">
                Cancel
              </button>
              <button
                onClick={() => {
                  if (!noteText.trim()) return;
                  createAnnotation.mutate({ page_num: currentPage, annotation_type: 'note', content: noteText.trim() });
                  setShowNoteInput(false);
                }}
                className="text-xs bg-primary text-white px-3 py-1 rounded font-medium"
              >
                Save Note
              </button>
            </div>
          </div>
        )}

        {/* Embedded question */}
        {activeQuestion && (
          <div className="mt-4 p-4 border-2 border-primary/30 rounded-[var(--radius)] bg-primary/5">
            <p className="text-xs font-semibold uppercase tracking-widest text-primary mb-3">
              {activeQuestion.type === 'truefalse' ? 'True or False' : 'Question'}
            </p>
            <p className="text-sm font-medium text-foreground mb-4">{activeQuestion.question}</p>

            {activeQuestion.type === 'mcq' && (
              <div className="space-y-2">
                {(activeQuestion.options ?? []).map((opt, i) => (
                  <button
                    key={i}
                    disabled={!!answeredResult}
                    onClick={() => setSelectedAnswer(String(i))}
                    className={cn(
                      'w-full text-left text-sm px-3 py-2.5 rounded border transition-colors',
                      selectedAnswer === String(i) && !answeredResult ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:bg-muted',
                      answeredResult && String(i) === String(activeQuestion.correct_index) ? 'border-emerald-500 bg-emerald-50 text-emerald-800' : '',
                      answeredResult && selectedAnswer === String(i) && !answeredResult?.is_correct ? 'border-red-400 bg-red-50 text-red-700' : '',
                    )}
                  >
                    <span className="font-medium mr-2">{String.fromCharCode(65 + i)}.</span> {opt}
                  </button>
                ))}
              </div>
            )}

            {activeQuestion.type === 'truefalse' && (
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
                onClick={handleSubmitAnswer}
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
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Annotations sidebar ── */}
      <div className="w-64 flex-shrink-0 hidden lg:block">
        <div className="enterprise-card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-border bg-muted/30">
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Page {currentPage} Notes
            </p>
          </div>

          {pageAnnotations.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <Highlighter className="w-6 h-6 text-muted-foreground mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">
                Select text and click <strong>Highlight</strong> to annotate this page.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {pageAnnotations.map((ann) => (
                <div key={ann.id} className="px-3 py-3 group">
                  <div className="flex items-start gap-2">
                    <div
                      className="w-3 h-3 rounded-sm flex-shrink-0 mt-0.5"
                      style={{ backgroundColor: ann.color }}
                    />
                    <p className="text-xs text-foreground flex-1 leading-relaxed">{ann.content}</p>
                    <button
                      onClick={() => deleteAnnotation.mutate(ann.id)}
                      className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-500 transition-opacity"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-1 ml-5 capitalize">{ann.annotation_type}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* All annotations summary */}
        {annotations.length > 0 && (
          <div className="mt-3 enterprise-card p-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-2">
              All Notes ({annotations.length})
            </p>
            <div className="space-y-1">
              {Array.from(new Set(annotations.map((a) => a.page_num))).sort((a, b) => a - b).map((pg) => (
                <button
                  key={pg}
                  onClick={() => setCurrentPage(pg)}
                  className={cn(
                    'w-full text-left text-xs py-1 px-2 rounded transition-colors',
                    pg === currentPage ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:bg-muted'
                  )}
                >
                  Page {pg} · {annotations.filter((a) => a.page_num === pg).length} note{annotations.filter((a) => a.page_num === pg).length !== 1 ? 's' : ''}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
