'use client';

import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import { Target, RefreshCw, Download } from 'lucide-react';

interface SkillGapCell {
  pct: number;
  learners_with_skill: number;
  total_learners: number;
}

interface SkillGapResponse {
  teams: string[];
  skills: string[];
  data: Record<string, Record<string, SkillGapCell>>;
}

function cellColor(pct: number) {
  if (pct >= 75) return 'bg-green-100 text-green-800';
  if (pct >= 40) return 'bg-amber-100 text-amber-800';
  return 'bg-red-100 text-red-800';
}

function SkillGapReport() {
  const { data, isLoading, error, refetch } = useQuery<SkillGapResponse>({
    queryKey: ['reports', 'admin', 'skill-gap'],
    queryFn: () =>
      fetch('/api/reports/admin/skill-gap').then((r) => r.json()),
  });

  async function handleExport() {
    const res = await fetch('/api/reports/export/csv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: 'skill_gap' }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'skill-gap.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <Header
        title="Skill Gap Analysis"
        subtitle="Team × skill heatmap showing percentage of learners with each skill"
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
        {/* Legend */}
        <div className="flex items-center gap-4 mb-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="w-4 h-4 rounded bg-green-100 border border-green-300 inline-block" /> ≥75% Strong</span>
          <span className="flex items-center gap-1.5"><span className="w-4 h-4 rounded bg-amber-100 border border-amber-300 inline-block" /> 40–74% Developing</span>
          <span className="flex items-center gap-1.5"><span className="w-4 h-4 rounded bg-red-100 border border-red-300 inline-block" /> &lt;40% Gap</span>
        </div>

        {isLoading && (
          <div className="animate-pulse h-64 bg-muted rounded-[var(--radius)]" />
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load skill gap data.
          </div>
        )}

        {data && (!data.teams || data.teams.length === 0) && (
          <div className="enterprise-card text-center py-12">
            <Target className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">No skill gap data yet. Skills and teams need to be configured first.</p>
          </div>
        )}

        {data && data.teams && data.teams.length > 0 && (
          <div className="enterprise-card overflow-x-auto">
            <table className="text-xs border-collapse">
              <thead>
                <tr>
                  <th className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold sticky left-0 bg-card min-w-[140px]">
                    Team / Skill
                  </th>
                  {data.skills.map((skill) => (
                    <th key={skill} className="py-2 px-2 text-[10px] text-muted-foreground font-semibold whitespace-nowrap text-center max-w-[80px]">
                      <div className="truncate max-w-[80px]" title={skill}>{skill}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.teams.map((team) => (
                  <tr key={team} className="border-t border-border">
                    <td className="py-2 px-3 font-medium sticky left-0 bg-card whitespace-nowrap">{team}</td>
                    {data.skills.map((skill) => {
                      const cell = data.data[team]?.[skill];
                      const pct = cell?.pct ?? 0;
                      return (
                        <td key={skill} className="py-1 px-1 text-center">
                          <div
                            className={cn('rounded px-1.5 py-1 text-[10px] font-semibold tabular-nums cursor-default', cellColor(pct))}
                            title={cell ? `${cell.learners_with_skill}/${cell.total_learners} learners` : 'No data'}
                          >
                            {pct > 0 ? `${Math.round(pct)}%` : '—'}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SkillGapPage() {
  return <SkillGapReport />;
}
