'use client';

import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Loader2, AlertCircle, CheckCircle2, XCircle, Minus, Award, Download } from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ItemRow {
  content_item_id: string;
  title: string;
  content_type: string;
  section_title?: string | null;
  studied: boolean;
  quiz_attempts: number;
  quiz_correct: number;
  flashcard_reviews: number;
  flashcard_known: number;
}

interface AssessmentRow {
  assessment_id: string;
  title: string;
  attempt_count: number;
  best_score: number | null;
  passed: boolean;
  latest_at: string;
}

interface SpaceReport {
  space_id: string;
  space_title: string;
  space_description?: string;
  learner: { user_id: string; email: string; full_name: string | null };
  summary: {
    total_items: number;
    studied_items: number;
    completion_pct: number;
    total_quiz_attempts: number;
    total_quiz_correct: number;
    total_flashcard_reviews: number;
    total_flashcard_known: number;
  };
  items: ItemRow[];
  assessments?: AssessmentRow[];
  certificate?: { issued_at: string; learner_name: string; learner_email: string } | null;
  generated_at?: string;
  /** present when creator endpoint is used */
  timeline?: unknown[];
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function pct(a: number, b: number) {
  if (!b) return '—';
  return `${Math.round((a / b) * 100)}%`;
}

function fmtDate(iso?: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
  });
}

function contentTypeLabel(t: string) {
  const map: Record<string, string> = {
    pdf: 'PDF', youtube: 'YouTube', vimeo: 'Vimeo', video_upload: 'Video',
    html_page: 'Web page', scorm: 'SCORM', h5p: 'H5P',
    interactive_pdf: 'Interactive PDF', interactive_slides: 'Slides',
  };
  return map[t] ?? t;
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SpaceReportPage() {
  const { spaceId, userId } = useParams<{ spaceId: string; userId: string }>();

  // Determine endpoint based on userId value
  const isSelf = userId === 'me';
  const endpoint = isSelf
    ? `/api/spaces/${spaceId}/me/report`
    : `/api/spaces/${spaceId}/learner-report/${userId}`;

  const { data: report, isLoading, error } = useQuery<SpaceReport>({
    queryKey: ['space-report', spaceId, userId],
    queryFn: async () => {
      const res = await fetch(endpoint);
      if (!res.ok) throw new Error('Could not load report');
      return res.json();
    },
    retry: 1,
  });

  const { summary } = report ?? {};
  const quizAcc = summary
    ? pct(summary.total_quiz_correct, summary.total_quiz_attempts)
    : '—';
  const fcAcc = summary
    ? pct(summary.total_flashcard_known, summary.total_flashcard_reviews)
    : '—';

  const pctNum = summary?.completion_pct ?? 0;
  const barColor = pctNum >= 80 ? '#16a34a' : pctNum >= 40 ? '#d97706' : '#2563eb';

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: 12 }}>
        <Loader2 style={{ width: 24, height: 24, animation: 'spin 1s linear infinite', color: '#6b7280' }} />
        <span style={{ color: '#6b7280', fontSize: 14 }}>Loading report…</span>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: 8 }}>
        <AlertCircle style={{ width: 32, height: 32, color: '#ef4444' }} />
        <p style={{ color: '#6b7280', fontSize: 14 }}>Report could not be loaded.</p>
      </div>
    );
  }

  return (
    <>
      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, sans-serif; color: #111827; background: #fff; }
        @media print {
          .no-print { display: none !important; }
          body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
          @page { margin: 18mm 16mm; size: A4 portrait; }
        }
      `}</style>

      {/* Print button (hidden when printing) */}
      <div className="no-print" style={{
        position: 'sticky', top: 0, background: '#fff', borderBottom: '1px solid #e5e7eb',
        padding: '10px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 100,
      }}>
        <span style={{ fontSize: 13, color: '#6b7280' }}>
          Progress Report — {report.space_title}
        </span>
        <button
          onClick={() => window.print()}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '8px 16px', background: '#1447e6', color: '#fff',
            border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer',
          }}
        >
          <Download style={{ width: 14, height: 14 }} />
          Download PDF
        </button>
      </div>

      {/* Report body */}
      <div style={{ maxWidth: 780, margin: '0 auto', padding: '40px 32px 60px' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#6b7280', marginBottom: 6 }}>
              Progress Report
            </div>
            <h1 style={{ fontSize: 24, fontWeight: 700, color: '#111827', marginBottom: 4 }}>
              {report.space_title}
            </h1>
            {report.space_description && (
              <p style={{ fontSize: 13, color: '#6b7280', maxWidth: 480 }}>{report.space_description}</p>
            )}
          </div>
          <div style={{ textAlign: 'right', fontSize: 12, color: '#9ca3af', flexShrink: 0 }}>
            <div style={{ fontWeight: 500, color: '#374151', marginBottom: 2 }}>
              {report.learner.full_name || report.learner.email}
            </div>
            <div>{report.learner.email}</div>
            <div style={{ marginTop: 4 }}>Generated {fmtDate(report.generated_at ?? new Date().toISOString())}</div>
          </div>
        </div>

        {/* Divider */}
        <div style={{ borderTop: '2px solid #1447e6', marginBottom: 28 }} />

        {/* Summary stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 32 }}>
          {[
            { label: 'Completion', value: `${summary?.completion_pct ?? 0}%`, sub: `${summary?.studied_items ?? 0} of ${summary?.total_items ?? 0} items` },
            { label: 'Quiz accuracy', value: quizAcc, sub: `${summary?.total_quiz_correct ?? 0} / ${summary?.total_quiz_attempts ?? 0} correct` },
            { label: 'Flashcard score', value: fcAcc, sub: `${summary?.total_flashcard_known ?? 0} / ${summary?.total_flashcard_reviews ?? 0} known` },
            { label: 'Assessments', value: String(report.assessments?.length ?? 0), sub: 'completed' },
          ].map((s) => (
            <div key={s.label} style={{
              background: '#f9fafb', borderRadius: 10, border: '1px solid #e5e7eb', padding: '14px 16px',
            }}>
              <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                {s.label}
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#111827', lineHeight: 1 }}>{s.value}</div>
              <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>{s.sub}</div>
            </div>
          ))}
        </div>

        {/* Progress bar */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#6b7280', marginBottom: 6 }}>
            <span>Overall progress</span>
            <span style={{ fontWeight: 600, color: barColor }}>{summary?.completion_pct ?? 0}%</span>
          </div>
          <div style={{ height: 10, background: '#f3f4f6', borderRadius: 99, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${summary?.completion_pct ?? 0}%`, background: barColor, borderRadius: 99, transition: 'width 0.4s' }} />
          </div>
        </div>

        {/* Content items table */}
        <div style={{ marginBottom: 32 }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#6b7280', marginBottom: 12 }}>
            Content Items
          </h2>
          <div style={{ border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                  {['Content', 'Type', 'Status', 'Quiz', 'Flashcards'].map((h) => (
                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.items.map((item, i) => (
                  <tr key={item.content_item_id} style={{ borderBottom: i < report.items.length - 1 ? '1px solid #f3f4f6' : 'none' }}>
                    <td style={{ padding: '10px 14px', color: '#111827', fontWeight: 500, maxWidth: 220 }}>
                      {item.section_title && (
                        <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 2 }}>{item.section_title}</div>
                      )}
                      {item.title}
                    </td>
                    <td style={{ padding: '10px 14px', color: '#6b7280' }}>{contentTypeLabel(item.content_type)}</td>
                    <td style={{ padding: '10px 14px' }}>
                      {item.studied ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#16a34a', fontSize: 12, fontWeight: 500 }}>
                          <CheckCircle2 style={{ width: 14, height: 14 }} /> Studied
                        </span>
                      ) : (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#9ca3af', fontSize: 12 }}>
                          <Minus style={{ width: 14, height: 14 }} /> Not started
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '10px 14px', color: '#374151' }}>
                      {item.quiz_attempts > 0
                        ? `${item.quiz_correct}/${item.quiz_attempts} (${pct(item.quiz_correct, item.quiz_attempts)})`
                        : <span style={{ color: '#9ca3af' }}>—</span>
                      }
                    </td>
                    <td style={{ padding: '10px 14px', color: '#374151' }}>
                      {item.flashcard_reviews > 0
                        ? `${item.flashcard_known}/${item.flashcard_reviews} known`
                        : <span style={{ color: '#9ca3af' }}>—</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Assessments (if any) */}
        {(report.assessments?.length ?? 0) > 0 && (
          <div style={{ marginBottom: 32 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#6b7280', marginBottom: 12 }}>
              Assessments
            </h2>
            <div style={{ border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                    {['Assessment', 'Attempts', 'Best Score', 'Passed', 'Last attempt'].map((h) => (
                      <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.assessments?.map((a, i) => (
                    <tr key={a.assessment_id} style={{ borderBottom: i < (report.assessments?.length ?? 0) - 1 ? '1px solid #f3f4f6' : 'none' }}>
                      <td style={{ padding: '10px 14px', fontWeight: 500, color: '#111827' }}>{a.title}</td>
                      <td style={{ padding: '10px 14px', color: '#6b7280' }}>{a.attempt_count}</td>
                      <td style={{ padding: '10px 14px', color: '#374151' }}>
                        {a.best_score != null ? `${a.best_score}%` : '—'}
                      </td>
                      <td style={{ padding: '10px 14px' }}>
                        {a.passed
                          ? <span style={{ color: '#16a34a', display: 'inline-flex', alignItems: 'center', gap: 4 }}><CheckCircle2 style={{ width: 13, height: 13 }} /> Yes</span>
                          : <span style={{ color: '#9ca3af', display: 'inline-flex', alignItems: 'center', gap: 4 }}><XCircle style={{ width: 13, height: 13 }} /> No</span>
                        }
                      </td>
                      <td style={{ padding: '10px 14px', color: '#6b7280' }}>{fmtDate(a.latest_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Certificate */}
        {report.certificate && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 16,
            padding: '16px 20px', background: '#f0fdf4', border: '1px solid #86efac',
            borderRadius: 10, marginBottom: 32,
          }}>
            <Award style={{ width: 28, height: 28, color: '#16a34a', flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 600, color: '#15803d', fontSize: 14 }}>Certificate Issued</div>
              <div style={{ fontSize: 12, color: '#4ade80', marginTop: 2 }}>
                Issued to {report.certificate.learner_name || report.certificate.learner_email} on {fmtDate(report.certificate.issued_at)}
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16, display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af' }}>
          <span>axis.edzlms.com — AI-Powered Learning Platform</span>
          <span>{report.learner.email}</span>
        </div>
      </div>
    </>
  );
}
