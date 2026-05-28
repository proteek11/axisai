'use client';

/**
 * GlobalChat — floating AI assistant (general / KB mode).
 *
 * This is for GENERAL questions about the platform, how things work,
 * or anything in the knowledge base. For questions about a specific
 * course item, use the chat panel on that content page.
 *
 * POST /api/chat with content_id = null → KB / support pipeline.
 */

import { useState, useRef, useEffect, FormEvent } from 'react';
import { cn } from '@/lib/utils';
import { MessageSquare, X, Send, Loader2, Bot, User, Sparkles } from 'lucide-react';

interface Msg {
  role: 'user' | 'assistant';
  text: string;
  suggestions?: string[];
}

const STARTERS = [
  'What can I learn on this platform?',
  'How do I start a learning space?',
  'How does the quiz tracking work?',
  'What AI features are available?',
];

export function GlobalChat() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [unread, setUnread] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [msgs, loading]);

  useEffect(() => {
    if (open) {
      setUnread(0);
      // small delay so the panel animation completes before focusing
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [open]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setInput('');
    setMsgs((prev) => [...prev, { role: 'user', text: trimmed }]);
    setLoading(true);
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ message: trimmed, content_id: null }),
      });
      const data = await res.json();
      const answer = res.ok
        ? (data.response ?? 'No response received.')
        : (data.error ?? 'Something went wrong. Please try again.');
      setMsgs((prev) => [
        ...prev,
        { role: 'assistant', text: answer, suggestions: data.suggestions ?? [] },
      ]);
      if (!open) setUnread((n) => n + 1);
    } catch {
      setMsgs((prev) => [
        ...prev,
        { role: 'assistant', text: 'Connection error. Please check your network and try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => { e.preventDefault(); send(input); };
  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); }
  };

  return (
    <>
      {/* ── Floating trigger button ─────────────────────────────── */}
      <button
        onClick={() => setOpen((v) => !v)}
        title={open ? 'Close AI assistant' : 'Ask Axis AI'}
        className={cn(
          'fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full shadow-xl',
          'bg-primary text-primary-foreground flex items-center justify-center',
          'hover:bg-primary/90 active:scale-95 transition-all duration-200',
        )}
      >
        {open ? <X className="w-6 h-6" /> : <MessageSquare className="w-6 h-6" />}
        {!open && unread > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
            {unread}
          </span>
        )}
      </button>

      {/* ── Chat panel ──────────────────────────────────────────── */}
      {open && (
        <div
          className={cn(
            'fixed bottom-24 right-6 z-50',
            'w-[380px] max-w-[calc(100vw-2rem)]',
            'bg-background border border-border rounded-[var(--radius)] shadow-2xl',
            'flex flex-col',
          )}
          style={{ height: 'min(540px, calc(100vh - 140px))' }}
        >
          {/* Header — fixed */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-primary/5 rounded-t-[var(--radius)] flex-shrink-0">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
                <Bot className="w-4 h-4 text-primary-foreground" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">Axis AI Assistant</p>
                <p className="text-[10px] text-muted-foreground flex items-center gap-1">
                  <Sparkles className="w-2.5 h-2.5" />
                  General &amp; knowledge base mode
                </p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground p-1 transition-colors rounded-[var(--radius)] hover:bg-muted">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Note: content-page chat */}
          <div className="px-4 py-2 bg-amber-50 border-b border-amber-200 flex-shrink-0">
            <p className="text-[10px] text-amber-700">
              💡 <strong>General assistant</strong> — for questions about a specific course item, open that content page and use the chat there.
            </p>
          </div>

          {/* Messages — scrollable, grows to fill space */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
            {/* Welcome + starters when no messages */}
            {msgs.length === 0 && (
              <div className="space-y-4">
                <div className="flex items-start gap-2">
                  <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Bot className="w-3.5 h-3.5 text-primary-foreground" />
                  </div>
                  <div className="bg-muted rounded-[var(--radius)] rounded-tl-none px-3 py-2 text-sm text-foreground max-w-[90%]">
                    Hi! I&apos;m your Axis AI assistant. Type a question below, or tap one of these to get started:
                  </div>
                </div>
                <div className="space-y-2 pl-8">
                  {STARTERS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="block w-full text-left text-xs px-3 py-2 rounded-[var(--radius)] border border-border hover:bg-primary/5 hover:border-primary/30 transition-colors text-foreground"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Conversation messages */}
            {msgs.map((msg, i) => (
              <div key={i} className={cn('flex items-start gap-2', msg.role === 'user' && 'flex-row-reverse')}>
                <div className={cn(
                  'w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5',
                  msg.role === 'assistant' ? 'bg-primary' : 'bg-muted',
                )}>
                  {msg.role === 'assistant'
                    ? <Bot className="w-3.5 h-3.5 text-primary-foreground" />
                    : <User className="w-3.5 h-3.5 text-muted-foreground" />}
                </div>
                <div className="max-w-[85%] space-y-2">
                  <div className={cn(
                    'px-3 py-2 rounded-[var(--radius)] text-sm leading-relaxed whitespace-pre-wrap',
                    msg.role === 'assistant'
                      ? 'bg-muted text-foreground rounded-tl-none'
                      : 'bg-primary text-primary-foreground rounded-tr-none',
                  )}>
                    {msg.text}
                  </div>
                  {msg.role === 'assistant' && msg.suggestions && msg.suggestions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {msg.suggestions.slice(0, 3).map((s, si) => (
                        <button
                          key={si}
                          onClick={() => send(s)}
                          className="text-[10px] px-2 py-1 rounded-full border border-primary/30 text-primary hover:bg-primary/10 transition-colors"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {loading && (
              <div className="flex items-start gap-2">
                <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Bot className="w-3.5 h-3.5 text-primary-foreground" />
                </div>
                <div className="bg-muted rounded-[var(--radius)] rounded-tl-none px-3 py-2.5">
                  <div className="flex gap-1">
                    <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input area — always visible at bottom, never clipped */}
          <div className="border-t border-border p-3 bg-background rounded-b-[var(--radius)] flex-shrink-0">
            <p className="text-[10px] font-medium text-muted-foreground mb-2">Type your question:</p>
            <form onSubmit={handleSubmit} className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => { setInput(e.target.value); /* auto-resize */ e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 100) + 'px'; }}
                onKeyDown={handleKey}
                placeholder="e.g. How do I create a learning space?"
                disabled={loading}
                className={cn(
                  'flex-1 resize-none rounded-[var(--radius)] border-2 border-border',
                  'bg-background px-3 py-2 text-sm text-foreground',
                  'placeholder:text-muted-foreground/60',
                  'focus:outline-none focus:border-primary',
                  'disabled:opacity-50 transition-colors',
                  'overflow-hidden',
                )}
                style={{ minHeight: '44px', maxHeight: '100px' }}
                rows={1}
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className={cn(
                  'flex-shrink-0 w-10 h-10 flex items-center justify-center',
                  'rounded-[var(--radius)] bg-primary text-primary-foreground',
                  'hover:bg-primary/90 active:scale-95 transition-all',
                  'disabled:opacity-40 disabled:cursor-not-allowed',
                )}
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </button>
            </form>
            <p className="text-[10px] text-muted-foreground mt-1.5">
              Press <kbd className="px-1 py-0.5 bg-muted rounded text-[9px] font-mono">Enter</kbd> to send &nbsp;·&nbsp; <kbd className="px-1 py-0.5 bg-muted rounded text-[9px] font-mono">Shift+Enter</kbd> for new line
            </p>
          </div>
        </div>
      )}
    </>
  );
}
