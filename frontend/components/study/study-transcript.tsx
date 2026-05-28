'use client';

import { useState, useMemo } from 'react';
import { Search, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Segment {
  start_sec: number;
  end_sec: number;
  text: string;
}

interface StudyTranscriptProps {
  segments: Segment[];
  fullText?: string;
  language?: string;
  onSeek?: (sec: number) => void;
}

/** Format seconds as M:SS or H:MM:SS */
function fmtSec(sec: number): string {
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
  return `${m}:${String(ss).padStart(2, '0')}`;
}

export function StudyTranscript({ segments, fullText, language, onSeek }: StudyTranscriptProps) {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return segments;
    const q = search.toLowerCase();
    return segments.filter((s) => s.text.toLowerCase().includes(q));
  }, [segments, search]);

  if (segments.length === 0) {
    return (
      <p className="text-center text-sm text-muted-foreground py-12">
        No transcript available for this content.
      </p>
    );
  }

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <p className="section-label">Transcript</p>
          {language && language !== 'en' && (
            <span className="text-xs px-2 py-0.5 bg-muted rounded-full text-muted-foreground uppercase">
              {language}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">{segments.length} segments</p>
      </div>

      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search transcript..."
          className="w-full pl-10 pr-4 py-2.5 rounded-[var(--radius)] border border-border bg-background
            text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
        />
      </div>

      {search && (
        <p className="section-label mb-3">{filtered.length} of {segments.length} segments</p>
      )}

      {/* Segment list */}
      <div className="space-y-1">
        {filtered.map((seg, i) => (
          <button
            key={i}
            onClick={() => onSeek?.(seg.start_sec)}
            disabled={!onSeek}
            className={cn(
              'w-full text-left flex items-start gap-3 px-4 py-2.5 rounded-[var(--radius)] transition-colors group',
              onSeek
                ? 'hover:bg-primary/5 cursor-pointer'
                : 'cursor-default',
            )}
          >
            {/* Timestamp pill */}
            <span className={cn(
              'flex items-center gap-1 text-xs font-mono font-medium px-2 py-0.5 rounded-full flex-shrink-0 mt-0.5 transition-colors',
              onSeek
                ? 'bg-muted text-muted-foreground group-hover:bg-primary group-hover:text-primary-foreground'
                : 'bg-muted text-muted-foreground',
            )}>
              <Clock className="w-3 h-3" />
              {fmtSec(seg.start_sec)}
            </span>
            {/* Text */}
            <span className="text-sm text-foreground leading-relaxed">
              {search ? highlightMatch(seg.text, search) : seg.text}
            </span>
          </button>
        ))}

        {filtered.length === 0 && (
          <p className="text-center text-sm text-muted-foreground py-8">
            No segments match your search.
          </p>
        )}
      </div>
    </div>
  );
}

/** Highlight matching text in a segment */
function highlightMatch(text: string, query: string): React.ReactNode {
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-yellow-200 text-foreground rounded px-0.5">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}
