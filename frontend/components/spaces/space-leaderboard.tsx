'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/lib/stores/auth-store';
import { Loader2, Trophy, Medal } from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface LeaderboardEntry {
  user_id: string;
  full_name: string | null;
  email: string;
  rank: number;
  score: number;
  completion_pct?: number;
  quiz_score_pct?: number;
  time_spent_minutes?: number;
}

interface LeaderboardResponse {
  entries: LeaderboardEntry[];
  sort_by: string;
  total: number;
}

type SortKey = 'completion' | 'quiz_score' | 'time_spent';

interface Props {
  spaceId: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getInitials(name: string | null, email: string): string {
  if (name) {
    return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase();
  }
  return email.charAt(0).toUpperCase();
}

function formatScore(entry: LeaderboardEntry, sortBy: SortKey): string {
  if (sortBy === 'completion') {
    return `${Math.round(entry.completion_pct ?? entry.score)}%`;
  }
  if (sortBy === 'quiz_score') {
    return `${Math.round(entry.quiz_score_pct ?? entry.score)}%`;
  }
  if (sortBy === 'time_spent') {
    const mins = Math.round(entry.time_spent_minutes ?? entry.score);
    if (mins < 60) return `${mins}m`;
    return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  }
  return String(entry.score);
}

function RankBadge({ rank }: { rank: number }) {
  if (rank === 1) {
    return (
      <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
        <Trophy className="w-3.5 h-3.5 text-amber-600" />
      </div>
    );
  }
  if (rank === 2) {
    return (
      <div className="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center flex-shrink-0">
        <Medal className="w-3.5 h-3.5 text-slate-500" />
      </div>
    );
  }
  if (rank === 3) {
    return (
      <div className="w-7 h-7 rounded-full bg-orange-100 flex items-center justify-center flex-shrink-0">
        <Medal className="w-3.5 h-3.5 text-orange-500" />
      </div>
    );
  }
  return (
    <div className="w-7 h-7 rounded-full bg-muted flex items-center justify-center flex-shrink-0">
      <span className="text-[10px] font-bold text-muted-foreground">{rank}</span>
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function SpaceLeaderboard({ spaceId }: Props) {
  const [sortBy, setSortBy] = useState<SortKey>('completion');
  const { user } = useAuthStore();

  const { data, isLoading, error } = useQuery<LeaderboardResponse>({
    queryKey: ['leaderboard', spaceId, sortBy],
    queryFn: async () => {
      const res = await fetch(`/api/reports/spaces/${spaceId}/leaderboard?sort_by=${sortBy}`);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? 'Failed to load');
      return res.json();
    },
  });

  const sortTabs: { key: SortKey; label: string }[] = [
    { key: 'completion', label: 'Completion' },
    { key: 'quiz_score', label: 'Quiz Score' },
    { key: 'time_spent', label: 'Time Spent' },
  ];

  return (
    <div className="space-y-4">
      {/* Sort tabs */}
      <div className="flex items-center gap-1 p-1 bg-muted rounded-[var(--radius)] w-fit">
        {sortTabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setSortBy(key)}
            className={cn(
              'px-4 py-1.5 text-sm font-medium rounded-[calc(var(--radius)-2px)] transition-colors',
              sortBy === key
                ? 'bg-background text-primary shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : error ? (
        <div className="enterprise-card py-8 text-center">
          <p className="text-sm text-red-500">{(error as Error).message}</p>
        </div>
      ) : !data || data.entries.length === 0 ? (
        <div className="enterprise-card flex flex-col items-center py-16 text-center">
          <div className="w-12 h-12 rounded-full bg-amber-50 flex items-center justify-center mb-3">
            <Trophy className="w-6 h-6 text-amber-500" />
          </div>
          <p className="font-semibold text-primary mb-1">Be the first to complete this space!</p>
          <p className="text-sm text-muted-foreground">
            Finish content items and quizzes to appear on the leaderboard.
          </p>
        </div>
      ) : (
        <div className="enterprise-card p-0 overflow-hidden">
          <div className="divide-y divide-border">
            {data.entries.map((entry) => {
              const isMe = user?.id === entry.user_id;
              const initials = getInitials(entry.full_name, entry.email);
              const scoreDisplay = formatScore(entry, sortBy);
              const progressValue =
                sortBy === 'completion' ? (entry.completion_pct ?? 0) :
                sortBy === 'quiz_score' ? (entry.quiz_score_pct ?? 0) :
                Math.min(100, ((entry.time_spent_minutes ?? 0) / 120) * 100); // normalize to 120 min max

              return (
                <div
                  key={entry.user_id}
                  className={cn(
                    'flex items-center gap-3 px-5 py-3 transition-colors',
                    isMe && 'bg-blue-50/70',
                  )}
                >
                  <RankBadge rank={entry.rank} />

                  {/* Avatar */}
                  <div className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0',
                    isMe ? 'bg-primary text-white' : 'bg-muted text-muted-foreground',
                  )}>
                    {initials}
                  </div>

                  {/* Name + progress bar */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className={cn('text-sm font-medium truncate', isMe ? 'text-primary' : 'text-foreground')}>
                        {entry.full_name ?? entry.email}
                        {isMe && <span className="ml-1.5 text-[10px] font-semibold uppercase tracking-wide text-primary/70">(you)</span>}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden flex-1">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.min(100, Math.max(0, progressValue))}%`,
                            backgroundColor: isMe ? '#1447e6' : '#94a3b8',
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Score */}
                  <div className="flex-shrink-0 text-right">
                    <span className={cn('text-sm font-bold', isMe ? 'text-primary' : 'text-foreground')}>
                      {scoreDisplay}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
