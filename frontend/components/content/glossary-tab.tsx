'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  Plus, Trash2, Save, RotateCcw, Loader2, GripVertical, Search, X
} from 'lucide-react';

interface Term { term: string; definition: string }
interface GlossaryTabProps { contentId: string; terms: Term[] }

export function GlossaryTab({ contentId, terms: initialTerms }: GlossaryTabProps) {
  const queryClient = useQueryClient();
  const [terms, setTerms] = useState<Term[]>(initialTerms);
  const [search, setSearch] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<Term>({ term: '', definition: '' });
  const [newTerm, setNewTerm] = useState<Term>({ term: '', definition: '' });
  const [showAdd, setShowAdd] = useState(false);

  const saveMutation = useMutation({
    mutationFn: async (data: Term[]) => {
      const res = await fetch(`/api/content/${contentId}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_type: 'glossary', content: data, action: 'update' }),
      });
      if (!res.ok) throw new Error('Failed');
    },
    onSuccess: () => {
      toast.success('Glossary saved');
      queryClient.invalidateQueries({ queryKey: ['content', contentId, 'outputs'] });
      setIsDirty(false);
    },
    onError: () => toast.error('Failed to save'),
  });

  const filtered = terms.filter((t) =>
    t.term.toLowerCase().includes(search.toLowerCase()) ||
    t.definition.toLowerCase().includes(search.toLowerCase())
  );

  const updateTerm = (idx: number, updated: Term) => {
    setTerms((prev) => prev.map((t, i) => (i === idx ? updated : t)));
    setIsDirty(true);
    setEditIdx(null);
  };

  const deleteTerm = (idx: number) => {
    setTerms((prev) => prev.filter((_, i) => i !== idx));
    setIsDirty(true);
  };

  const addTerm = () => {
    if (!newTerm.term.trim() || !newTerm.definition.trim()) {
      toast.error('Both term and definition are required');
      return;
    }
    setTerms((prev) => [...prev, newTerm]);
    setNewTerm({ term: '', definition: '' });
    setShowAdd(false);
    setIsDirty(true);
  };

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-4">
        <p className="section-label">{terms.length} Terms</p>
        <div className="flex items-center gap-2">
          {isDirty && (
            <button
              onClick={() => saveMutation.mutate(terms)}
              disabled={saveMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground
                rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {saveMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              Save Changes
            </button>
          )}
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[var(--radius)]
              text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
          >
            <Plus className="w-3 h-3" />
            Add Term
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search terms..."
          className="w-full pl-10 pr-4 py-2 rounded-[var(--radius)] border border-border bg-background
            text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
        />
      </div>

      {/* Add new term form */}
      {showAdd && (
        <div className="enterprise-card mb-4 border-primary/30">
          <p className="section-label mb-3">New Term</p>
          <div className="space-y-2">
            <input
              value={newTerm.term}
              onChange={(e) => setNewTerm((t) => ({ ...t, term: e.target.value }))}
              placeholder="Term..."
              className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm
                focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            <textarea
              value={newTerm.definition}
              onChange={(e) => setNewTerm((t) => ({ ...t, definition: e.target.value }))}
              rows={3}
              placeholder="Definition..."
              className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm
                focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
            />
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => setShowAdd(false)} className="px-3 py-1.5 border border-border rounded-[var(--radius)] text-xs text-muted-foreground hover:bg-muted">Cancel</button>
            <button onClick={addTerm} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90">Add</button>
          </div>
        </div>
      )}

      {/* Terms list */}
      <div className="space-y-2">
        {filtered.map((term, idx) => {
          const realIdx = terms.indexOf(term);
          const isEditing = editIdx === realIdx;
          return (
            <div key={realIdx} className="enterprise-card">
              {isEditing ? (
                <div className="space-y-2">
                  <input
                    value={editDraft.term}
                    onChange={(e) => setEditDraft((d) => ({ ...d, term: e.target.value }))}
                    className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm
                      focus:outline-none focus:ring-2 focus:ring-primary/30 font-semibold"
                  />
                  <textarea
                    value={editDraft.definition}
                    onChange={(e) => setEditDraft((d) => ({ ...d, definition: e.target.value }))}
                    rows={3}
                    className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm
                      focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                  />
                  <div className="flex gap-2">
                    <button onClick={() => setEditIdx(null)} className="px-3 py-1.5 border border-border rounded-[var(--radius)] text-xs text-muted-foreground hover:bg-muted">Cancel</button>
                    <button onClick={() => updateTerm(realIdx, editDraft)} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90">Save</button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm text-primary mb-1">{term.term}</p>
                    <p className="text-sm text-muted-foreground leading-relaxed">{term.definition}</p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => { setEditIdx(realIdx); setEditDraft(term); }}
                      className="w-7 h-7 rounded-[var(--radius)] flex items-center justify-center
                        text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
                    >
                      <Save className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => deleteTerm(realIdx)}
                      className="w-7 h-7 rounded-[var(--radius)] flex items-center justify-center
                        text-muted-foreground hover:text-red-600 hover:bg-red-50 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {filtered.length === 0 && (
          <p className="text-center text-sm text-muted-foreground py-8">No terms match your search.</p>
        )}
      </div>
    </div>
  );
}
