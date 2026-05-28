'use client';

/**
 * VoiceChatPanel — Phase 18: Voice AI Tutor
 *
 * Full voice conversation loop:
 *   1. Learner clicks mic → SpeechRecognition starts
 *   2. On silence/stop → transcript sent to /api/chat
 *   3. AI text response → POST /api/tts → MP3 blob → Audio.play()
 *   4. While audio plays: mic auto-disabled. After audio ends: mic re-activates.
 *
 * Uses Web Speech API (browser-native, free, Chrome/Edge/Firefox).
 * Falls back gracefully if Speech Recognition is not available.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Mic, MicOff, X, Volume2, VolumeX, Loader2,
  Radio, AudioLines,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ── Type declarations for Web Speech API ─────────────────────────────────────
declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    SpeechRecognition: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    webkitSpeechRecognition: any;
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────
interface Turn {
  role: 'user' | 'assistant';
  text: string;
}

type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

interface Props {
  contentId: string;
  onClose: () => void;
}

// ── Markdown renderer (same as content page chat) ────────────────────────────
function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  let last = 0; let match; let k = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const m = match[0];
    if (m.startsWith('**'))     parts.push(<strong key={`${keyPrefix}-b${k++}`}>{m.slice(2, -2)}</strong>);
    else if (m.startsWith('*')) parts.push(<em key={`${keyPrefix}-i${k++}`}>{m.slice(1, -1)}</em>);
    else                        parts.push(<code key={`${keyPrefix}-c${k++}`} className="bg-black/10 px-1 rounded text-[10px] font-mono">{m.slice(1, -1)}</code>);
    last = match.index + m.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = content.split('\n');
  const blocks: React.ReactNode[] = [];
  let k = 0;
  let listItems: string[] = [];
  let listType: 'ul' | 'ol' | null = null;

  const flushList = () => {
    if (!listItems.length) return;
    if (listType === 'ol') {
      blocks.push(<ol key={k++} className="list-decimal pl-4 space-y-0.5 my-1">{listItems.map((t, i) => <li key={i} className="text-xs leading-snug">{renderInline(t, `ol-${k}-${i}`)}</li>)}</ol>);
    } else {
      blocks.push(<ul key={k++} className="list-disc pl-4 space-y-0.5 my-1">{listItems.map((t, i) => <li key={i} className="text-xs leading-snug">{renderInline(t, `ul-${k}-${i}`)}</li>)}</ul>);
    }
    listItems = []; listType = null;
  };

  for (const line of lines) {
    if (/^#{1,3} /.test(line)) {
      flushList();
      const text = line.replace(/^#+\s/, '');
      blocks.push(<p key={k++} className="font-semibold text-xs mt-1.5 mb-0.5">{renderInline(text, `h${k}`)}</p>);
    } else if (/^[-*] /.test(line)) {
      if (listType !== 'ul') { flushList(); listType = 'ul'; }
      listItems.push(line.slice(2));
    } else if (/^\d+\. /.test(line)) {
      if (listType !== 'ol') { flushList(); listType = 'ol'; }
      listItems.push(line.replace(/^\d+\. /, ''));
    } else if (line.trim() === '') {
      flushList();
    } else {
      flushList();
      blocks.push(<p key={k++} className="text-xs leading-relaxed">{renderInline(line, `p${k}`)}</p>);
    }
  }
  flushList();
  return <div className="space-y-0.5">{blocks}</div>;
}

// ── Strip markdown for TTS (spoken text must be plain) ────────────────────────
function stripMarkdown(text: string): string {
  return text
    .replace(/#{1,6} /g, '')          // headings
    .replace(/\*\*([^*]+)\*\*/g, '$1') // bold
    .replace(/\*([^*]+)\*/g, '$1')     // italic
    .replace(/`([^`]+)`/g, '$1')       // inline code
    .replace(/^[-*] /gm, '')           // bullet points
    .replace(/^\d+\. /gm, '')          // numbered lists
    .replace(/\n{2,}/g, '. ')          // double newlines → pause
    .replace(/\n/g, ' ')               // single newlines → space
    .trim();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function stateLabel(state: VoiceState): string {
  switch (state) {
    case 'idle':      return 'Tap mic to speak';
    case 'listening': return 'Listening…';
    case 'thinking':  return 'AI is thinking…';
    case 'speaking':  return 'AI is speaking…';
  }
}

function stateColor(state: VoiceState): string {
  switch (state) {
    case 'idle':      return 'text-muted-foreground';
    case 'listening': return 'text-red-500';
    case 'thinking':  return 'text-blue-500';
    case 'speaking':  return 'text-green-600';
  }
}

// ── Animated waveform ─────────────────────────────────────────────────────────
function Waveform({ active }: { active: boolean }) {
  return (
    <div className="flex items-center justify-center gap-[3px] h-8">
      {[0.6, 1, 0.7, 1.2, 0.5, 0.9, 0.6, 1.1, 0.7, 0.4].map((h, i) => (
        <div
          key={i}
          className={cn(
            'w-[3px] rounded-full bg-primary transition-all',
            active ? 'animate-pulse' : '',
          )}
          style={{
            height: active ? `${h * 20}px` : '4px',
            animationDelay: `${i * 80}ms`,
            transitionDuration: '300ms',
          }}
        />
      ))}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export function VoiceChatPanel({ contentId, onClose }: Props) {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [muted, setMuted] = useState(false);
  const [supported, setSupported] = useState(true);
  const [error, setError] = useState('');

  const recognitionRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const turnsEndRef = useRef<HTMLDivElement>(null);

  // ── Check browser support ───────────────────────────────────────────────
  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      setSupported(false);
      setError('Voice input is not supported in this browser. Try Chrome or Edge.');
    }
  }, []);

  // ── Auto-scroll turns ───────────────────────────────────────────────────
  useEffect(() => {
    turnsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns]);

  // ── Cleanup on unmount ──────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      if (audioRef.current) {
        audioRef.current.pause();
        URL.revokeObjectURL(audioRef.current.src);
      }
    };
  }, []);

  // ── Synthesize and play TTS ─────────────────────────────────────────────
  const speak = useCallback(
    async (text: string) => {
      if (muted) return;
      setVoiceState('speaking');
      try {
        const r = await fetch('/api/tts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, language: 'en' }),
        });
        if (!r.ok) return;
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);

        // Stop any previous audio
        if (audioRef.current) {
          audioRef.current.pause();
          URL.revokeObjectURL(audioRef.current.src);
        }

        const audio = new Audio(url);
        audioRef.current = audio;

        audio.onended = () => {
          URL.revokeObjectURL(url);
          audioRef.current = null;
          setVoiceState('idle');
        };

        audio.onerror = () => {
          URL.revokeObjectURL(url);
          audioRef.current = null;
          setVoiceState('idle');
        };

        await audio.play();
      } catch {
        setVoiceState('idle');
      }
    },
    [muted],
  );

  // ── Send transcript to RAG chat ─────────────────────────────────────────
  const sendToChat = useCallback(
    async (text: string) => {
      if (!text.trim()) {
        setVoiceState('idle');
        return;
      }

      // Add user turn — keep transcript visible during thinking so the user
      // can see what was sent (from voice OR a starter chip)
      setTurns((prev) => [...prev, { role: 'user', text: text.trim() }]);
      setVoiceState('thinking');

      try {
        const r = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content_id: contentId, message: text.trim() }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'Chat failed');

        const reply = data.response as string;
        // Clear transcript now that the assistant is responding
        setTranscript('');
        setTurns((prev) => [...prev, { role: 'assistant', text: reply }]);

        // Speak the reply — strip markdown so TTS reads plain text
        await speak(stripMarkdown(reply));
      } catch (e: any) {
        const msg = 'Sorry, I had trouble answering. Please try again.';
        setTranscript('');
        setTurns((prev) => [...prev, { role: 'assistant', text: msg }]);
        setVoiceState('idle');
      }
    },
    [contentId, speak],
  );

  // ── Start / stop listening ──────────────────────────────────────────────
  const startListening = useCallback(async () => {
    if (!supported) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;

    // Stop any playing audio
    if (audioRef.current) {
      audioRef.current.pause();
      URL.revokeObjectURL(audioRef.current.src);
      audioRef.current = null;
    }

    // Pre-request mic permission explicitly so Chrome shows the allow dialog.
    // SpeechRecognition alone can fail silently with "not-allowed" if the
    // browser hasn't seen a getUserMedia call for this origin yet.
    if (navigator.mediaDevices?.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        // Release tracks immediately — Speech API will re-acquire
        stream.getTracks().forEach((t) => t.stop());
      } catch (permErr: any) {
        const denied =
          permErr?.name === 'NotAllowedError' ||
          permErr?.name === 'PermissionDeniedError';
        setError(
          denied
            ? 'blocked'
            : `Microphone error: ${permErr?.message ?? permErr}`,
        );
        setVoiceState('idle');
        return;
      }
    }

    const recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    recognitionRef.current = recognition;

    let finalTranscript = '';

    recognition.onstart = () => {
      setVoiceState('listening');
      setTranscript('');
      setError('');
    };

    recognition.onresult = (event: any) => {
      let interim = '';
      finalTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += t;
        } else {
          interim += t;
        }
      }
      setTranscript(finalTranscript || interim);
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      if (finalTranscript.trim()) {
        sendToChat(finalTranscript.trim());
      } else {
        setVoiceState('idle');
        setTranscript('');
      }
    };

    recognition.onerror = (event: any) => {
      recognitionRef.current = null;
      if (event.error === 'no-speech') {
        setVoiceState('idle');
        setTranscript('');
      } else if (event.error === 'not-allowed') {
        setError('blocked');
        setVoiceState('idle');
      } else if (event.error !== 'aborted') {
        setError(`Microphone error: ${event.error}`);
        setVoiceState('idle');
      }
    };

    recognition.start();
  }, [supported, sendToChat]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  const toggleMic = useCallback(() => {
    if (voiceState === 'listening') {
      stopListening();
    } else if (voiceState === 'idle') {
      startListening();
    }
    // If thinking or speaking, don't allow
  }, [voiceState, startListening, stopListening]);

  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      URL.revokeObjectURL(audioRef.current.src);
      audioRef.current = null;
    }
    setVoiceState('idle');
  }, []);

  const micActive = voiceState === 'listening';
  const busy = voiceState === 'thinking' || voiceState === 'speaking';

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="fixed bottom-6 right-6 w-[340px] bg-card border border-border rounded-[var(--radius)] shadow-xl flex flex-col z-50"
      style={{ maxHeight: '520px' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center">
            <Radio className="w-3.5 h-3.5 text-primary" />
          </div>
          <div>
            <p className="text-xs font-semibold text-foreground">Voice AI Tutor</p>
            <p className="text-[10px] text-muted-foreground">Speak naturally — AI will answer</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMuted((v) => !v)}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title={muted ? 'Unmute AI voice' : 'Mute AI voice'}
          >
            {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Conversation turns */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
        {turns.length === 0 && (
          <div className="text-center py-6 space-y-2">
            <AudioLines className="w-8 h-8 text-muted-foreground/50 mx-auto" />
            <p className="text-xs text-muted-foreground">
              Ask anything about this content — by voice
            </p>
            <div className="flex flex-wrap justify-center gap-1.5 mt-3">
              {['Summarize key points', 'Explain the main idea', 'Quiz me on this'].map((s) => (
                <button
                  key={s}
                  onClick={() => { setTranscript(s); sendToChat(s); }}
                  disabled={busy}
                  className="text-[11px] bg-muted hover:bg-muted/70 text-foreground px-2.5 py-1 rounded-full transition-colors disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => (
          <div
            key={i}
            className={cn(
              'flex',
              turn.role === 'user' ? 'justify-end' : 'justify-start',
            )}
          >
            <div
              className={cn(
                'max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed',
                turn.role === 'user'
                  ? 'bg-primary text-primary-foreground rounded-br-sm'
                  : 'bg-muted text-foreground rounded-bl-sm',
              )}
            >
              {turn.role === 'assistant'
                ? <MarkdownMessage content={turn.text} />
                : turn.text}
            </div>
          </div>
        ))}

        {/* Loading bubble */}
        {voiceState === 'thinking' && (
          <div className="flex justify-start">
            <div className="bg-muted px-3 py-2 rounded-xl rounded-bl-sm flex items-center gap-1.5">
              <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Thinking…</span>
            </div>
          </div>
        )}

        <div ref={turnsEndRef} />
      </div>

      {/* Transcript display */}
      {/* Show what was sent (voice or chip) while AI is thinking */}
      {(transcript && (voiceState === 'listening' || voiceState === 'thinking')) && (
        <div className="px-4 py-2 border-t border-border">
          <p className="text-xs text-muted-foreground italic">{transcript}</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="px-4 py-2 border-t border-border bg-red-50/50">
          {error === 'blocked' ? (
            <div className="text-xs text-red-600 space-y-1.5">
              <p className="font-semibold">🚫 Microphone access blocked.</p>
              <div className="space-y-0.5 text-red-500">
                <p className="font-medium">Fix 1 — Chrome site setting:</p>
                <p>1. Click the 🔒 lock icon in the address bar</p>
                <p>2. Set <strong>Microphone</strong> → <strong>Allow</strong></p>
                <p>3. Refresh this page</p>
              </div>
              <div className="space-y-0.5 text-red-500 pt-1 border-t border-red-200">
                <p className="font-medium">Fix 2 — macOS system setting:</p>
                <p>→ Apple menu → System Settings → Privacy &amp; Security → Microphone</p>
                <p>→ Toggle on <strong>Google Chrome</strong>, then refresh</p>
              </div>
            </div>
          ) : (
            <p className="text-xs text-red-600 font-medium leading-relaxed">{error}</p>
          )}
        </div>
      )}

      {/* Mic controls */}
      <div className="border-t border-border px-4 py-4 flex flex-col items-center gap-3 flex-shrink-0">
        {/* Status */}
        <p className={cn('text-[11px] font-medium transition-colors', stateColor(voiceState))}>
          {stateLabel(voiceState)}
        </p>

        {/* Waveform */}
        <Waveform active={micActive} />

        {/* Buttons */}
        <div className="flex items-center gap-3">
          {/* Stop audio button (only when speaking) */}
          {voiceState === 'speaking' && (
            <button
              onClick={stopAudio}
              className="w-9 h-9 rounded-full border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title="Stop audio"
            >
              <VolumeX className="w-4 h-4" />
            </button>
          )}

          {/* Main mic button */}
          <button
            onClick={toggleMic}
            disabled={!supported || busy}
            className={cn(
              'w-14 h-14 rounded-full flex items-center justify-center transition-all shadow-md',
              micActive
                ? 'bg-red-500 text-white scale-105 shadow-red-200'
                : busy
                ? 'bg-muted text-muted-foreground cursor-not-allowed'
                : 'bg-primary text-white hover:bg-primary/90 hover:scale-105',
            )}
            title={micActive ? 'Stop listening' : 'Start speaking'}
          >
            {micActive ? (
              <MicOff className="w-6 h-6" />
            ) : busy ? (
              <Loader2 className="w-6 h-6 animate-spin" />
            ) : (
              <Mic className="w-6 h-6" />
            )}
          </button>
        </div>

        {!supported && (
          <p className="text-[10px] text-muted-foreground text-center">
            Use Chrome or Edge for voice input
          </p>
        )}
      </div>
    </div>
  );
}
