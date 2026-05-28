'use client';

import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn, formatDate } from '@/lib/utils';
import { FileText, CheckCircle, XCircle } from 'lucide-react';

interface QuizAttemptRow {
  attempt_id: string;
  assessment_title: string;
  space_title: string;
  attempted_at: string;
  score_pct: number;
  passed: boolean;
  time_taken_minutes: number | null;
  correct_answers: number;
  total_questions: number;
}

interface QuizHistoryResponse {
  attempts: QuizAttemptRow[];
  total: number;
  avg_score: number;
  pass_rate: number;
}

function LearnerQuizHistoryReport() {
  const { data, isLoading, error } = useQuery<QuizHistoryResponse>({
    queryKey: ['reports', 'learner', 'quiz-history'],
    queryFn: () =>
      fetch('/api/reports/learner/quiz-history').then((r) => r.json()),
  });

  const rows = data?.attempts ?? [];

  return (
    <div>
      <Header
        title="Quiz History"
        subtitle="All your assessment attempts and scores"
      />

      <div className="p-6 space-y-6">
        {isLoading && (
          <div className="animate-pulse space-y-2">
            {[...Array(8)].map((_, i) => <div key={i} className="h-12 bg-muted rounded-lg" />)}
          </div>
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load quiz history.
          </div>
        )}

        {!isLoading && !error && (
          <>
            {/* Summary KPIs */}
            {rows.length > 0 && (
              <div className="grid grid-cols-3 gap-4">
                <div className="enterprise-card text-center py-4">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Total Attempts</p>
                  <p className="text-3xl font-bold mt-1">{data?.total ?? 0}</p>
                </div>
                <div className="enterprise-card text-center py-4">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Avg Score</p>
                  <p className="text-3xl font-bold mt-1 text-primary">{Math.round(data?.avg_score ?? 0)}%</p>
                </div>
                <div className="enterprise-card text-center py-4">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Pass Rate</p>
                  <p className={cn('text-3xl font-bold mt-1',
                    (data?.pass_rate ?? 0) >= 70 ? 'text-green-600' :
                    (data?.pass_rate ?? 0) >= 50 ? 'text-amber-600' : 'text-red-600',
                  )}>
                    {Math.round(data?.pass_rate ?? 0)}%
                  </p>
                </div>
              </div>
            )}

            <div className="enterprise-card overflow-x-auto">
              {rows.length === 0 ? (
                <div className="text-center py-12">
                  <FileText className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">No quiz attempts yet</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {['Assessment', 'Space', 'Date', 'Score', 'Result', 'Correct', 'Time'].map((h) => (
                        <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.attempt_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                        <td className="py-3 px-3 font-medium">{r.assessment_title}</td>
                        <td className="py-3 px-3 text-muted-foreground max-w-[130px] truncate">{r.space_title}</td>
                        <td className="py-3 px-3 text-muted-foreground whitespace-nowrap">{formatDate(r.attempted_at)}</td>
                        <td className="py-3 px-3 text-right">
                          <span className={cn('font-semibold tabular-nums',
                            r.score_pct >= 70 ? 'text-green-600' :
                            r.score_pct >= 50 ? 'text-amber-600' : 'text-red-600',
                          )}>
                            {Math.round(r.score_pct)}%
                          </span>
                        </td>
                        <td className="py-3 px-3">
                          {r.passed ? (
                            <span className="flex items-center gap-1 text-xs text-green-600">
                              <CheckCircle className="w-3.5 h-3.5" />
                              Pass
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-xs text-red-600">
                              <XCircle className="w-3.5 h-3.5" />
                              Fail
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-3 text-right text-muted-foreground tabular-nums">
                          {r.correct_answers}/{r.total_questions}
                        </td>
                        <td className="py-3 px-3 text-right text-muted-foreground">
                          {r.time_taken_minutes != null ? `${Math.round(r.time_taken_minutes)}m` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function LearnerQuizHistoryPage() {
  return <LearnerQuizHistoryReport />;
}
