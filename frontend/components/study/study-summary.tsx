'use client';

import { useState, useRef } from 'react';
import { Volume2, Loader2, StopCircle, AlertCircle } from 'lucide-react';

interface StudySummaryProps { summary: string }

export function StudySummary({ summary }: StudySummaryProps) {
  const [audioState, setAudioState] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const audioRef = useRef<HTMLAudioElement | null>(null);

  async function handleListen() {
    // Stop if already playing
    if (audioState === 'playing') {
      audioRef.current?.pause();
      setAudioState('idle');
      return;
    }

    setAudioState('loading');
    setErrorMsg('');

    try {
      // TTS max is 5000 chars — truncate at sentence boundary
      const text = summary.length > 4500
        ? summary.slice(0, 4500).replace(/[^.!?]*$/, '').trim() || summary.slice(0, 4500)
        : summary;

      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, language: 'en' }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `TTS failed (${res.status})`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);

      // Clean up previous audio
      if (audioRef.current) {
        audioRef.current.pause();
        URL.revokeObjectURL(audioRef.current.src);
      }

      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => setAudioState('idle');
      audio.onerror = () => { setAudioState('error'); setErrorMsg('Playback failed'); };

      await audio.play();
      setAudioState('playing');
    } catch (e: any) {
      setAudioState('error');
      setErrorMsg(e.message || 'Failed to generate audio');
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="enterprise-card">
        {/* Header row */}
        <div className="flex items-center justify-between mb-4">
          <p className="section-label">Summary</p>

          <div className="flex items-center gap-2">
            {audioState === 'error' && (
              <span className="flex items-center gap-1 text-[10px] text-red-600">
                <AlertCircle className="w-3 h-3" />
                {errorMsg}
              </span>
            )}
            <button
              onClick={handleListen}
              disabled={audioState === 'loading' || !summary}
              title={audioState === 'playing' ? 'Stop audio' : 'Listen to summary'}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] border transition-colors ${
                audioState === 'playing'
                  ? 'bg-primary text-white border-primary hover:bg-primary/90'
                  : 'bg-background text-muted-foreground border-border hover:text-foreground hover:border-primary/50'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {audioState === 'loading' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : audioState === 'playing' ? (
                <StopCircle className="w-3.5 h-3.5" />
              ) : (
                <Volume2 className="w-3.5 h-3.5" />
              )}
              {audioState === 'loading' ? 'Generating…' : audioState === 'playing' ? 'Stop' : 'Listen'}
            </button>
          </div>
        </div>

        <div className="prose prose-sm max-w-none text-foreground leading-relaxed whitespace-pre-wrap text-sm">
          {summary}
        </div>
      </div>
    </div>
  );
}
