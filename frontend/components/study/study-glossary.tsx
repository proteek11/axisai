'use client';

import { useState, useMemo } from 'react';
import { Search, ArrowDownAZ, ArrowUpAZ } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Term { term: string; definition: string }
interface StudyGlossaryProps { terms: Term[] }

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

export function StudyGlossary({ terms }: StudyGlossaryProps) {
  const [search,  setSearch]  = useState('');
  const [sortAsc, setSortAsc] = useState(true);
  const [letter,  setLetter]  = useState<string | null>(null);

  const filtered = useMemo(() => {
    let list = terms.filter((t) =>
      t.term.toLowerCase().includes(search.toLowerCase()) ||
      t.definition.toLowerCase().includes(search.toLowerCase()),
    );
    if (letter) {
      list = list.filter((t) => t.term.toUpperCase().startsWith(letter));
    }
    list = [...list].sort((a, b) => {
      const cmp = a.term.localeCompare(b.term);
      return sortAsc ? cmp : -cmp;
    });
    return list;
  }, [terms, search, sortAsc, letter]);

  // Which letters have content
  const activeLetters = useMemo(
    () => new Set(terms.map((t) => t.term[0]?.toUpperCase())),
    [terms],
  );

  return (
    <div className="max-w-3xl">
      {/* Search + sort row */}
      <div className="flex gap-2 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setLetter(null); }}
            placeholder="Search terms..."
            className="w-full pl-10 pr-4 py-2.5 rounded-[var(--radius)] border border-border bg-background
              text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
        </div>
        <button
          onClick={() => setSortAsc((v) => !v)}
          title={sortAsc ? 'Sort Z → A' : 'Sort A → Z'}
          className="flex items-center gap-1.5 px-3 py-2.5 border border-border rounded-[var(--radius)]
            text-sm text-muted-foreground hover:bg-muted transition-colors flex-shrink-0"
        >
          {sortAsc ? <ArrowDownAZ className="w-4 h-4" /> : <ArrowUpAZ className="w-4 h-4" />}
        </button>
      </div>

      {/* A–Z index */}
      <div className="flex flex-wrap gap-1 mb-4">
        <button
          onClick={() => setLetter(null)}
          className={cn(
            'px-2 py-0.5 rounded text-xs font-semibold transition-colors',
            letter === null
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-muted',
          )}
        >
          All
        </button>
        {ALPHABET.map((l) => (
          <button
            key={l}
            onClick={() => { setLetter(letter === l ? null : l); setSearch(''); }}
            disabled={!activeLetters.has(l)}
            className={cn(
              'px-2 py-0.5 rounded text-xs font-semibold transition-colors',
              letter === l
                ? 'bg-primary text-primary-foreground'
                : activeLetters.has(l)
                  ? 'text-muted-foreground hover:bg-muted'
                  : 'text-muted-foreground/30 cursor-not-allowed',
            )}
          >
            {l}
          </button>
        ))}
      </div>

      <p className="section-label mb-3">{filtered.length} of {terms.length} Terms</p>

      <div className="space-y-2">
        {filtered.map((term, i) => (
          <div key={i} className="enterprise-card">
            <p className="font-semibold text-sm text-primary mb-1">{term.term}</p>
            <p className="text-sm text-muted-foreground leading-relaxed">{term.definition}</p>
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="text-center text-sm text-muted-foreground py-8">No terms match your search.</p>
        )}
      </div>
    </div>
  );
}
