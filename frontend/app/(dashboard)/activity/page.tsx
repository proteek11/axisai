'use client';

/**
 * Activity Timeline — /activity
 * Learners: chat sessions · Creators/Admins: content uploads.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  MessageSquare, BookOpen, Clock, Loader2,
  Zap, ChevronRight, Calendar, Upload, CheckCircle2, AlertCircle, RefreshCw,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────────

interface ActivityEvent {
  type: 'chat' | 'upload';
  // chat fields
  session_id?: string;
  content_item_id?: string | null;
  content_title?: string | null;
  session_title?: string | null;
  message_count?: number;
  total_tokens?: number;
  // upload fields
  content_type?: string;
  content_status?: string;
  space_id?: string;
  space_title?: string;
  ts: string;
  date: string;
}

interface DayGroup {
  date: string;
  events: ActivityEvent[];
}

interface ActivityResponse {
  days: number;
  role: string;
  total_events: number;
  timeline: DayGroup[];
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00');
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  if (date.getTime() === today.getTime())     return 'Today';
  if (date.getTime() === yesterday.getTime()) return 'Yesterday';

  return date.toLocaleDateString('en-US', {
    weekday: 'long', month: 'short', day: 'numeric',
  });
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', hour12: true,
  });
}

// ── Event card ─────────────────────────────────────────────────────────────────

const STATUS_ICONS: Record<string, { icon: React.ElementType; color: string; label: string }> = {
  ready:      { icon: CheckCircle2, color: 'text-emerald-500', label: 'Ready' },
  processing: { icon: RefreshCw,    color: 'text-blue-500 animate-spin', label: 'Processing' },
  failed:     { icon: AlertCircle,  color: 'text-red-500',    label: 'Failed' },
  queued:     { icon: Clock,        color: 'text-amber-500',  label: 'Queued' },
};

function EventCard({ event }: { event: ActivityEvent }) {
  if (event.type === 'upload') {
    const statusInfo = STATUS_ICONS[event.content_status ?? ''] ?? STATUS_ICONS.queued;
    const StatusIcon = statusInfo.icon;
    return (
      <div className="flex items-start gap-3 py-3 px-4 rounded-[var(--radius)] hover:bg-muted/40
        transition-colors group border border-transparent hover:border-border">
        <div className="w-8 h-8 rounded-full bg-orange-50 flex items-center justify-center flex-shrink-0 mt-0.5">
          <Upload className="w-4 h-4 text-orange-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground truncate">
            {event.content_title ?? 'Untitled content'}
          </p>
          <div className="flex items-center gap-3 mt-0.5 flex-wrap">
            <span className="text-xs text-muted-foreground">{event.space_title}</span>
            <span className={`text-xs flex items-center gap-1 ${statusInfo.color}`}>
              <StatusIcon className="w-3 h-3" />
              {statusInfo.label}
            </span>
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatTime(event.ts)}
            </span>
          </div>
        </div>
        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <ChevronRight className="w-4 h-4 text-muted-foreground" />
        </div>
      </div>
    );
  }

  const title = event.session_title || event.content_title || 'Study session';
  return (
    <div className="flex items-start gap-3 py-3 px-4 rounded-[var(--radius)] hover:bg-muted/40
      transition-colors group border border-transparent hover:border-border">
      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
        <MessageSquare className="w-4 h-4 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{title}</p>
        <div className="flex items-center gap-3 mt-0.5 flex-wrap">
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <MessageSquare className="w-3 h-3" />
            {event.message_count ?? 0} message{(event.message_count ?? 0) !== 1 ? 's' : ''}
          </span>
          {(event.total_tokens ?? 0) > 0 && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Zap className="w-3 h-3" />
              {(event.total_tokens ?? 0).toLocaleString()} tokens
            </span>
          )}
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatTime(event.ts)}
          </span>
        </div>
      </div>
      {event.content_item_id && (
        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <ChevronRight className="w-4 h-4 text-muted-foreground" />
        </div>
      )}
    </div>
  );
}

// ── Day group ──────────────────────────────────────────────────────────────────

function DayGroup({ group }: { group: DayGroup }) {
  return (
    <div className="mb-6">
      {/* Day header */}
      <div className="flex items-center gap-2 mb-2 sticky top-0 bg-background/80 backdrop-blur-sm py-1 z-10">
        <Calendar className="w-3.5 h-3.5 text-primary flex-shrink-0" />
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {formatDate(group.date)}
        </h2>
        <div className="flex-1 h-px bg-border" />
        <span className="text-xs text-muted-foreground">
          {group.events.length} event{group.events.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Events */}
      <div className="enterprise-card p-1">
        {group.events.map((ev, i) => (
          <div key={ev.session_id}>
            <EventCard event={ev} />
            {i < group.events.length - 1 && (
              <div className="ml-4 mr-4 border-b border-border/50" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

const DAY_OPTIONS = [7, 15, 30];

export default function ActivityPage() {
  const [days, setDays] = useState(15);

  const { data, isLoading } = useQuery<ActivityResponse>({
    queryKey: ['me', 'activity', days],
    queryFn: async () => {
      const res = await fetch(`/api/me/activity?days=${days}`);
      if (!res.ok) throw new Error('Failed to load activity');
      return res.json();
    },
  });

  const isCreatorView = data?.role === 'creator' || data?.role === 'admin';
  const totalMessages = data?.timeline.reduce(
    (acc, day) => acc + day.events.reduce((s, ev) => s + (ev.message_count ?? 0), 0),
    0
  ) ?? 0;
  const totalSessions = data?.total_events ?? 0;
  const readyUploads = data?.timeline.reduce(
    (acc, day) => acc + day.events.filter((ev) => ev.type === 'upload' && ev.content_status === 'ready').length,
    0
  ) ?? 0;

  return (
    <div>
      <Header
        title="My Activity"
        subtitle={data?.role && (data.role === 'creator' || data.role === 'admin') ? 'Your recent content uploads' : 'Your recent study sessions'}
        action={
          <div className="flex items-center gap-1 border border-border rounded-[var(--radius)] p-0.5">
            {DAY_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={cn(
                  'px-3 py-1.5 rounded text-xs font-medium transition-colors',
                  days === d
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                )}
              >
                {d}d
              </button>
            ))}
          </div>
        }
      />

      <div className="page-padding max-w-2xl">

        {/* Summary stats */}
        {!isLoading && data && (
          <div className="grid grid-cols-2 gap-3 mb-6">
            <div className="enterprise-card flex items-center gap-3">
              <div className={cn("w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0", isCreatorView ? "bg-orange-50" : "bg-primary/10")}>
                {isCreatorView ? <Upload className="w-4 h-4 text-orange-500" /> : <BookOpen className="w-4 h-4 text-primary" />}
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{totalSessions}</p>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">
                  {isCreatorView ? `Upload${totalSessions !== 1 ? 's' : ''}` : `Session${totalSessions !== 1 ? 's' : ''}`}
                </p>
              </div>
            </div>
            <div className="enterprise-card flex items-center gap-3">
              <div className={cn("w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0", isCreatorView ? "bg-emerald-50" : "bg-blue-50")}>
                {isCreatorView ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <MessageSquare className="w-4 h-4 text-blue-600" />}
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{isCreatorView ? readyUploads : totalMessages}</p>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">
                  {isCreatorView ? 'Ready' : `AI Message${totalMessages !== 1 ? 's' : ''}`}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Timeline */}
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : !data || data.timeline.length === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <Clock className="w-10 h-10 text-muted-foreground/30 mb-3" />
            <p className="text-sm font-medium text-foreground mb-1">No activity yet</p>
            <p className="text-xs text-muted-foreground mb-4">
              {isCreatorView
                ? 'Upload content to your spaces and your uploads will appear here.'
                : 'Start studying content in your spaces and your activity will appear here.'}
            </p>
            <Link
              href="/learn"
              className="text-xs text-primary font-medium hover:underline flex items-center gap-1"
            >
              Browse my library <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        ) : (
          <div>
            {data.timeline.map((group) => (
              <DayGroup key={group.date} group={group} />
            ))}
          </div>
        )}

      </div>
    </div>
  );
}
