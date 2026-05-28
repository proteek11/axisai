'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn, formatDate, getInitials } from '@/lib/utils';
import { User, Search, Award, BookOpen, Target, Zap } from 'lucide-react';

interface LearnerProfileData {
  user_id: string;
  full_name: string | null;
  email: string;
  role: string;
  team_name: string | null;
  joined_at: string;
  last_active: string | null;
  spaces_enrolled: number;
  spaces_completed: number;
  certificates_earned: number;
  skills_earned: number;
  total_sessions: number;
  total_tokens_used: number;
  spaces: Array<{
    space_id: string;
    title: string;
    enrolled_at: string;
    completed_at: string | null;
    progress_pct: number;
  }>;
  skills: Array<{
    skill_name: string;
    level: string;
    earned_at: string;
  }>;
}

interface SearchResult {
  user_id: string;
  full_name: string | null;
  email: string;
}

function LearnerProfileReport() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  const { data: searchResults, isLoading: searching } = useQuery<SearchResult[]>({
    queryKey: ['reports', 'admin', 'learner-search', searchQuery],
    queryFn: () =>
      fetch(`/api/reports/admin/learners/search?q=${encodeURIComponent(searchQuery)}`)
        .then((r) => r.json()),
    enabled: searchQuery.trim().length >= 2,
  });

  const { data: profile, isLoading: loadingProfile } = useQuery<LearnerProfileData>({
    queryKey: ['reports', 'admin', 'learner-profile', selectedUserId],
    queryFn: () =>
      fetch(`/api/reports/admin/learner-profile/${selectedUserId}`)
        .then((r) => r.json()),
    enabled: !!selectedUserId,
  });

  return (
    <div>
      <Header
        title="Learner Profile"
        subtitle="Deep-dive into an individual learner's activity, progress and skills"
      />

      <div className="p-6 space-y-6">
        {/* Search */}
        <div className="enterprise-card space-y-3">
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Search Learner</p>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Enter name or email (min 2 characters)..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setSelectedUserId(null);
              }}
              className="w-full pl-9 pr-4 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
          {searching && <p className="text-xs text-muted-foreground">Searching...</p>}
          {searchResults && searchResults.length > 0 && !selectedUserId && (
            <ul className="border border-border rounded-lg overflow-hidden">
              {searchResults.map((r) => (
                <li key={r.user_id}>
                  <button
                    onClick={() => {
                      setSelectedUserId(r.user_id);
                      setSearchQuery(r.full_name || r.email);
                    }}
                    className="w-full text-left px-4 py-2.5 text-sm hover:bg-muted/50 transition-colors flex items-center gap-3 border-b border-border last:border-0"
                  >
                    <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-semibold text-primary flex-shrink-0">
                      {getInitials(r.full_name || r.email)}
                    </div>
                    <div>
                      <p className="font-medium">{r.full_name || '—'}</p>
                      <p className="text-xs text-muted-foreground">{r.email}</p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {searchResults && searchResults.length === 0 && searchQuery.length >= 2 && !searching && (
            <p className="text-xs text-muted-foreground">No learners found matching "{searchQuery}"</p>
          )}
        </div>

        {/* Profile */}
        {loadingProfile && (
          <div className="animate-pulse space-y-4">
            <div className="h-32 bg-muted rounded-[var(--radius)]" />
            <div className="grid grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-muted rounded-[var(--radius)]" />)}
            </div>
          </div>
        )}

        {profile && (
          <div className="space-y-6">
            {/* Identity card */}
            <div className="enterprise-card flex items-center gap-4">
              <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-lg font-bold text-primary flex-shrink-0">
                {getInitials(profile.full_name || profile.email)}
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-bold">{profile.full_name || profile.email}</h2>
                <p className="text-sm text-muted-foreground">{profile.email}</p>
                <div className="flex items-center gap-3 mt-1">
                  {profile.team_name && (
                    <span className="text-xs text-muted-foreground border border-border rounded-full px-2.5 py-0.5">{profile.team_name}</span>
                  )}
                  <span className="text-xs text-muted-foreground">Joined {formatDate(profile.joined_at)}</span>
                  {profile.last_active && (
                    <span className="text-xs text-muted-foreground">Last active {formatDate(profile.last_active)}</span>
                  )}
                </div>
              </div>
            </div>

            {/* KPI grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {[
                { label: 'Spaces Enrolled', value: profile.spaces_enrolled, icon: BookOpen, color: 'bg-purple-100 text-purple-600' },
                { label: 'Completed', value: profile.spaces_completed, icon: Award, color: 'bg-green-100 text-green-600' },
                { label: 'Certificates', value: profile.certificates_earned, icon: Award, color: 'bg-orange-100 text-orange-600' },
                { label: 'Skills Earned', value: profile.skills_earned, icon: Target, color: 'bg-pink-100 text-pink-600' },
              ].map((k) => (
                <div key={k.label} className="enterprise-card flex items-center gap-3">
                  <div className={cn('w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0', k.color)}>
                    <k.icon className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{k.label}</p>
                    <p className="text-2xl font-bold">{k.value}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Spaces table */}
            {profile.spaces && profile.spaces.length > 0 && (
              <div className="enterprise-card overflow-x-auto">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Enrolled Spaces</p>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {['Space', 'Enrolled', 'Completed', 'Progress'].map((h) => (
                        <th key={h} className="text-left py-2 px-3 text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {profile.spaces.map((s) => (
                      <tr key={s.space_id} className="border-b border-border last:border-0 hover:bg-muted/30">
                        <td className="py-3 px-3 font-medium">{s.title}</td>
                        <td className="py-3 px-3 text-muted-foreground">{formatDate(s.enrolled_at)}</td>
                        <td className="py-3 px-3 text-muted-foreground">{s.completed_at ? formatDate(s.completed_at) : '—'}</td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-2">
                            <div className="w-20 bg-muted rounded-full h-1.5 overflow-hidden">
                              <div className="h-full bg-primary rounded-full" style={{ width: `${s.progress_pct}%` }} />
                            </div>
                            <span className="text-xs text-muted-foreground">{Math.round(s.progress_pct)}%</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Skills */}
            {profile.skills && profile.skills.length > 0 && (
              <div className="enterprise-card">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold mb-4">Skills Earned</p>
                <div className="flex flex-wrap gap-2">
                  {profile.skills.map((s, i) => (
                    <div key={i} className="flex items-center gap-1.5 border border-border rounded-full px-3 py-1.5 text-xs">
                      <Target className="w-3 h-3 text-primary" />
                      <span className="font-medium">{s.skill_name}</span>
                      <span className="text-muted-foreground">·</span>
                      <span className="text-muted-foreground capitalize">{s.level}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {!selectedUserId && !searchQuery && (
          <div className="enterprise-card text-center py-16">
            <User className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-sm font-medium">Search for a learner above</p>
            <p className="text-xs text-muted-foreground mt-1">Type a name or email to get started</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function LearnerProfilePage() {
  return <LearnerProfileReport />;
}
