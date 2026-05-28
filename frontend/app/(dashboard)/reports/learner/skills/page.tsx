'use client';

import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn, formatDate } from '@/lib/utils';
import { Target, TrendingUp, Award } from 'lucide-react';

interface SkillRow {
  skill_id: string;
  skill_name: string;
  category: string | null;
  level: string;
  earned_at: string;
  space_title: string | null;
}

interface GapRow {
  skill_name: string;
  category: string | null;
  required_level: string;
  current_level: string | null;
  gap: boolean;
}

interface LearnerSkillsResponse {
  earned_skills: SkillRow[];
  skill_gaps: GapRow[];
  total_earned: number;
  total_available: number;
}

const LEVEL_COLORS: Record<string, string> = {
  beginner: 'text-blue-600 bg-blue-50 border-blue-300',
  intermediate: 'text-amber-600 bg-amber-50 border-amber-300',
  advanced: 'text-green-600 bg-green-50 border-green-300',
};

function LearnerSkillsReport() {
  const { data, isLoading, error } = useQuery<LearnerSkillsResponse>({
    queryKey: ['reports', 'learner', 'skills'],
    queryFn: () =>
      fetch('/api/reports/learner/skills').then((r) => r.json()),
  });

  const earned = data?.earned_skills ?? [];
  const gaps = data?.skill_gaps ?? [];

  // Group earned skills by category
  const byCategory: Record<string, SkillRow[]> = {};
  earned.forEach((s) => {
    const cat = s.category || 'Uncategorised';
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push(s);
  });

  // CSS radar chart: simple polygon using skills count and level
  const totalAvailable = data?.total_available || 1;
  const pct = Math.min(100, ((data?.total_earned || 0) / totalAvailable) * 100);

  return (
    <div>
      <Header
        title="My Skills"
        subtitle="Skills you have earned and gaps to close"
      />

      <div className="p-6 space-y-6">
        {isLoading && (
          <div className="animate-pulse space-y-4">
            <div className="grid grid-cols-3 gap-4">
              {[...Array(3)].map((_, i) => <div key={i} className="h-20 bg-muted rounded-[var(--radius)]" />)}
            </div>
            <div className="h-64 bg-muted rounded-[var(--radius)]" />
          </div>
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load skills data.
          </div>
        )}

        {!isLoading && !error && (
          <>
            {/* Overview KPIs */}
            <div className="grid grid-cols-3 gap-4">
              <div className="enterprise-card text-center py-4">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Skills Earned</p>
                <p className="text-3xl font-bold mt-1 text-primary">{data?.total_earned ?? 0}</p>
              </div>
              <div className="enterprise-card text-center py-4">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Available</p>
                <p className="text-3xl font-bold mt-1">{data?.total_available ?? 0}</p>
              </div>
              <div className="enterprise-card text-center py-4">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Coverage</p>
                <p className={cn('text-3xl font-bold mt-1',
                  pct >= 75 ? 'text-green-600' : pct >= 40 ? 'text-amber-600' : 'text-red-600',
                )}>
                  {Math.round(pct)}%
                </p>
              </div>
            </div>

            {/* Coverage bar visual */}
            {(data?.total_available ?? 0) > 0 && (
              <div className="enterprise-card">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Overall Skill Coverage</p>
                  <span className="text-sm font-semibold text-primary">{Math.round(pct)}%</span>
                </div>
                <div className="w-full bg-muted rounded-full h-3 overflow-hidden">
                  <div
                    className={cn('h-full rounded-full transition-all', pct >= 75 ? 'bg-green-500' : pct >= 40 ? 'bg-amber-500' : 'bg-primary')}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1.5">
                  {data?.total_earned ?? 0} of {data?.total_available ?? 0} skills earned
                </p>
              </div>
            )}

            {/* Earned Skills by Category */}
            {earned.length > 0 && (
              <div className="space-y-4">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold flex items-center gap-1.5">
                  <Award className="w-3.5 h-3.5" />
                  Skills Earned
                </p>
                {Object.entries(byCategory).map(([cat, skills]) => (
                  <div key={cat} className="enterprise-card">
                    <p className="text-xs font-semibold text-muted-foreground mb-3">{cat}</p>
                    <div className="flex flex-wrap gap-2">
                      {skills.map((s) => (
                        <div
                          key={s.skill_id}
                          className={cn('flex items-center gap-1.5 border rounded-full px-3 py-1.5 text-xs', LEVEL_COLORS[s.level] || 'text-muted-foreground bg-muted border-border')}
                          title={`Earned: ${formatDate(s.earned_at)}${s.space_title ? ` · ${s.space_title}` : ''}`}
                        >
                          <Target className="w-3 h-3" />
                          <span className="font-medium">{s.skill_name}</span>
                          <span className="opacity-70 capitalize">· {s.level}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {earned.length === 0 && (
              <div className="enterprise-card text-center py-12">
                <Target className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No skills earned yet</p>
              </div>
            )}

            {/* Skill Gaps */}
            {gaps.length > 0 && (
              <div>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-3 flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5" />
                  Skill Gaps ({gaps.filter((g) => g.gap).length})
                </p>
                <div className="enterprise-card overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        {['Skill', 'Category', 'Required', 'Your Level', 'Status'].map((h) => (
                          <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {gaps.map((g, i) => (
                        <tr key={i} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                          <td className="py-3 px-3 font-medium">{g.skill_name}</td>
                          <td className="py-3 px-3 text-muted-foreground">{g.category || '—'}</td>
                          <td className="py-3 px-3">
                            <span className={cn('text-xs px-2 py-0.5 rounded-full border capitalize', LEVEL_COLORS[g.required_level] || 'text-muted-foreground bg-muted border-border')}>
                              {g.required_level}
                            </span>
                          </td>
                          <td className="py-3 px-3">
                            {g.current_level ? (
                              <span className={cn('text-xs px-2 py-0.5 rounded-full border capitalize', LEVEL_COLORS[g.current_level] || 'text-muted-foreground bg-muted border-border')}>
                                {g.current_level}
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">Not started</span>
                            )}
                          </td>
                          <td className="py-3 px-3">
                            {g.gap ? (
                              <span className="text-xs text-red-600 border border-red-300 bg-red-50 rounded-full px-2 py-0.5">Gap</span>
                            ) : (
                              <span className="text-xs text-green-600 border border-green-400 bg-green-50 rounded-full px-2 py-0.5">Met</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function LearnerSkillsPage() {
  return <LearnerSkillsReport />;
}
