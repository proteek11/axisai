'use client';

import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn, getInitials } from '@/lib/utils';
import { Star, RefreshCw, Download, Trophy } from 'lucide-react';

interface LeaderboardRow {
  rank: number;
  user_id: string;
  full_name: string | null;
  email: string;
  team_name: string | null;
  skills_count: number;
  advanced_skills: number;
  intermediate_skills: number;
  beginner_skills: number;
  spaces_completed: number;
}

interface LeaderboardResponse {
  learners: LeaderboardRow[];
  total: number;
}

const RANK_STYLES: Record<number, string> = {
  1: 'text-yellow-500 font-bold text-base',
  2: 'text-gray-400 font-bold text-base',
  3: 'text-amber-600 font-bold text-base',
};

function SkillsLeaderboardReport() {
  const { data, isLoading, error, refetch } = useQuery<LeaderboardResponse>({
    queryKey: ['reports', 'admin', 'skills-leaderboard'],
    queryFn: () =>
      fetch('/api/reports/admin/skills-leaderboard').then((r) => r.json()),
  });

  async function handleExport() {
    const res = await fetch('/api/reports/export/csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'skills_leaderboard' }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'skills-leaderboard.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const rows = data?.learners ?? [];

  return (
    <div>
      <Header
        title="Skills Leaderboard"
        subtitle="Top learners ranked by total skills earned"
        action={
          <div className="flex items-center gap-2">
            <button onClick={() => refetch()} className="p-1.5 border border-border rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors">
              <RefreshCw className="w-4 h-4" />
            </button>
            <button onClick={handleExport} className="flex items-center gap-1.5 text-sm bg-primary text-primary-foreground rounded-lg px-3 py-1.5 hover:bg-primary/90 transition-colors">
              <Download className="w-3.5 h-3.5" />
              Export CSV
            </button>
          </div>
        }
      />

      <div className="p-6">
        {isLoading && (
          <div className="animate-pulse space-y-2">
            {[...Array(10)].map((_, i) => <div key={i} className="h-14 bg-muted rounded-lg" />)}
          </div>
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load leaderboard data.
          </div>
        )}

        {!isLoading && !error && (
          <div className="enterprise-card overflow-x-auto">
            {rows.length === 0 ? (
              <div className="text-center py-12">
                <Trophy className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No skills data yet</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Rank', 'Learner', 'Team', 'Total Skills', 'Advanced', 'Intermediate', 'Beginner', 'Spaces Done'].map((h) => (
                      <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.user_id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-3">
                        <span className={cn('tabular-nums', RANK_STYLES[r.rank] || 'text-muted-foreground text-sm')}>
                          {r.rank <= 3 ? ['🥇', '🥈', '🥉'][r.rank - 1] : `#${r.rank}`}
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-semibold text-primary flex-shrink-0">
                            {getInitials(r.full_name || r.email)}
                          </div>
                          <div>
                            <p className="font-medium">{r.full_name || '—'}</p>
                            <p className="text-xs text-muted-foreground">{r.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-muted-foreground">{r.team_name || '—'}</td>
                      <td className="py-3 px-3 text-right font-bold tabular-nums text-primary">{r.skills_count}</td>
                      <td className="py-3 px-3 text-right tabular-nums text-green-600">{r.advanced_skills}</td>
                      <td className="py-3 px-3 text-right tabular-nums text-amber-600">{r.intermediate_skills}</td>
                      <td className="py-3 px-3 text-right tabular-nums text-muted-foreground">{r.beginner_skills}</td>
                      <td className="py-3 px-3 text-right tabular-nums">{r.spaces_completed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function SkillsLeaderboardPage() {
  return <SkillsLeaderboardReport />;
}
