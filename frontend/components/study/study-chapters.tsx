'use client';

import { PlayCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Chapter {
  title: string;
  start_sec: number;
  end_sec: number;
  summary: string;
}

interface StudyChaptersProps {
  chapters: Chapter[];
  totalDurationSec?: number;
  /** YouTube video ID — used to build thumbnail URLs */
  youtubeVideoId?: string;
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

/** YouTube thumbnail at a specific second (uses mqdefault as fallback) */
function ytThumb(videoId: string, sec: number): string {
  // YouTube maxres thumbnail — can't seek to a specific second, use default
  return `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`;
}

export function StudyChapters({ chapters, totalDurationSec, youtubeVideoId, onSeek }: StudyChaptersProps) {
  if (chapters.length === 0) {
    return (
      <p className="text-center text-sm text-muted-foreground py-12">
        No chapters available for this content.
      </p>
    );
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-4">
        <p className="section-label">Chapters</p>
        <p className="text-xs text-muted-foreground">
          {chapters.length} chapter{chapters.length !== 1 ? 's' : ''}
          {totalDurationSec ? ` · ${fmtSec(totalDurationSec)} total` : ''}
        </p>
      </div>

      <div className="space-y-3">
        {chapters.map((ch, i) => (
          <button
            key={i}
            onClick={() => onSeek?.(ch.start_sec)}
            disabled={!onSeek}
            className={cn(
              'w-full text-left enterprise-card flex items-start gap-4 p-0 overflow-hidden transition-colors group',
              onSeek ? 'hover:bg-muted/50 cursor-pointer' : 'cursor-default',
            )}
          >
            {/* Thumbnail (YouTube only) */}
            {youtubeVideoId ? (
              <div className="relative flex-shrink-0 w-32 h-20 bg-muted overflow-hidden rounded-l-[var(--radius)]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={ytThumb(youtubeVideoId, ch.start_sec)}
                  alt={ch.title}
                  className="w-full h-full object-cover"
                />
                {/* Timestamp overlay */}
                <span className="absolute bottom-1 right-1 text-[10px] font-mono font-bold
                  bg-black/80 text-white px-1 py-0.5 rounded">
                  {fmtSec(ch.start_sec)}
                </span>
                {onSeek && (
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors
                    flex items-center justify-center">
                    <PlayCircle className="w-8 h-8 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                )}
              </div>
            ) : (
              /* Non-YouTube: show chapter number + timestamp */
              <div className="flex-shrink-0 w-16 flex flex-col items-center justify-center bg-muted
                self-stretch rounded-l-[var(--radius)] gap-1 p-3">
                <span className="text-xs font-bold text-primary">{i + 1}</span>
                <span className="text-[10px] font-mono text-muted-foreground">{fmtSec(ch.start_sec)}</span>
              </div>
            )}

            {/* Chapter info */}
            <div className="flex-1 py-3 pr-4">
              <div className="flex items-start justify-between gap-2 mb-1">
                <p className="text-sm font-semibold text-primary leading-snug">{ch.title}</p>
                {!youtubeVideoId && onSeek && (
                  <PlayCircle className="w-4 h-4 text-primary flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity mt-0.5" />
                )}
              </div>
              {ch.summary && (
                <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">{ch.summary}</p>
              )}
              {ch.end_sec > ch.start_sec && (
                <p className="text-[10px] text-muted-foreground mt-1.5 font-mono">
                  {fmtSec(ch.start_sec)} – {fmtSec(ch.end_sec)}
                </p>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
