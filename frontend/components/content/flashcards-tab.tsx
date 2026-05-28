'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Plus, Trash2, Save, Loader2, RotateCcw, Pencil, X } from 'lucide-react';

interface Card { front: string; back: string }
interface FlashcardsTabProps { contentId: string; cards: Card[] }

function FlashCard({ card, onEdit, onDelete }: { card: Card; onEdit: () => void; onDelete: () => void }) {
  const [flipped, setFlipped] = useState(false);

  return (
    <div className="relative group">
      {/* Card flip container */}
      <div
        className="relative h-48 cursor-pointer"
        style={{ perspective: '1000px' }}
        onClick={() => setFlipped((f) => !f)}
      >
        <div
          className="absolute inset-0 transition-transform duration-500"
          style={{
            transformStyle: 'preserve-3d',
            transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
          }}
        >
          {/* Front */}
          <div
            className="absolute inset-0 rounded-[var(--radius)] border border-border bg-card
              flex flex-col items-center justify-center p-5 text-center"
            style={{ backfaceVisibility: 'hidden' }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">FRONT</p>
            <p className="font-semibold text-primary text-sm leading-relaxed">{card.front}</p>
            <p className="text-xs text-muted-foreground mt-3">Click to reveal answer</p>
          </div>
          {/* Back */}
          <div
            className="absolute inset-0 rounded-[var(--radius)] border border-primary/30 bg-primary/5
              flex flex-col items-center justify-center p-5 text-center"
            style={{ backfaceVisibility: 'hidden', transform: 'rotateY(180deg)' }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-primary/60 mb-3">ANSWER</p>
            <p className="text-sm text-foreground leading-relaxed">{card.back}</p>
          </div>
        </div>
      </div>

      {/* Edit/delete buttons */}
      <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={(e) => { e.stopPropagation(); onEdit(); }}
          className="w-7 h-7 rounded-[var(--radius)] bg-background border border-border flex items-center justify-center
            text-muted-foreground hover:text-primary transition-colors shadow-sm"
        >
          <Pencil className="w-3 h-3" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="w-7 h-7 rounded-[var(--radius)] bg-background border border-border flex items-center justify-center
            text-muted-foreground hover:text-red-600 transition-colors shadow-sm"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>

      {/* Flip indicator */}
      <div className="flex justify-center mt-2">
        <div className="flex gap-1">
          <span className={cn('w-1.5 h-1.5 rounded-full transition-colors', !flipped ? 'bg-primary' : 'bg-border')} />
          <span className={cn('w-1.5 h-1.5 rounded-full transition-colors', flipped ? 'bg-primary' : 'bg-border')} />
        </div>
      </div>
    </div>
  );
}

export function FlashcardsTab({ contentId, cards: initialCards }: FlashcardsTabProps) {
  const queryClient = useQueryClient();
  const [cards, setCards] = useState<Card[]>(initialCards);
  const [isDirty, setIsDirty] = useState(false);
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<Card>({ front: '', back: '' });
  const [showAdd, setShowAdd] = useState(false);
  const [newCard, setNewCard] = useState<Card>({ front: '', back: '' });

  const saveMutation = useMutation({
    mutationFn: async (data: Card[]) => {
      const res = await fetch(`/api/content/${contentId}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_type: 'flashcards', content: data, action: 'update' }),
      });
      if (!res.ok) throw new Error('Failed');
    },
    onSuccess: () => {
      toast.success('Flashcards saved');
      queryClient.invalidateQueries({ queryKey: ['content', contentId, 'outputs'] });
      setIsDirty(false);
    },
    onError: () => toast.error('Failed to save'),
  });

  const deleteCard = (idx: number) => {
    setCards((prev) => prev.filter((_, i) => i !== idx));
    setIsDirty(true);
  };

  const updateCard = (idx: number, updated: Card) => {
    setCards((prev) => prev.map((c, i) => (i === idx ? updated : c)));
    setIsDirty(true);
    setEditIdx(null);
  };

  const addCard = () => {
    if (!newCard.front.trim() || !newCard.back.trim()) {
      toast.error('Both front and back are required');
      return;
    }
    setCards((prev) => [...prev, newCard]);
    setNewCard({ front: '', back: '' });
    setShowAdd(false);
    setIsDirty(true);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="section-label">{cards.length} Flashcards · click any card to flip</p>
        <div className="flex items-center gap-2">
          {isDirty && (
            <button
              onClick={() => saveMutation.mutate(cards)}
              disabled={saveMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground
                rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {saveMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              Save
            </button>
          )}
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[var(--radius)]
              text-xs font-medium text-muted-foreground hover:bg-muted"
          >
            <Plus className="w-3 h-3" />
            Add Card
          </button>
        </div>
      </div>

      {/* Inline edit */}
      {editIdx !== null && (
        <div className="enterprise-card mb-4 border-primary/30">
          <p className="section-label mb-3">Edit Card</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Front</label>
              <textarea value={editDraft.front} onChange={(e) => setEditDraft((d) => ({ ...d, front: e.target.value }))} rows={4}
                className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Back</label>
              <textarea value={editDraft.back} onChange={(e) => setEditDraft((d) => ({ ...d, back: e.target.value }))} rows={4}
                className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none" />
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => setEditIdx(null)} className="px-3 py-1.5 border border-border rounded-[var(--radius)] text-xs text-muted-foreground hover:bg-muted">Cancel</button>
            <button onClick={() => updateCard(editIdx, editDraft)} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90">Save</button>
          </div>
        </div>
      )}

      {/* Add card form */}
      {showAdd && (
        <div className="enterprise-card mb-4 border-primary/30">
          <p className="section-label mb-3">New Card</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Front</label>
              <textarea value={newCard.front} onChange={(e) => setNewCard((c) => ({ ...c, front: e.target.value }))} rows={4}
                className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Back</label>
              <textarea value={newCard.back} onChange={(e) => setNewCard((c) => ({ ...c, back: e.target.value }))} rows={4}
                className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none" />
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => setShowAdd(false)} className="px-3 py-1.5 border border-border rounded-[var(--radius)] text-xs text-muted-foreground hover:bg-muted">Cancel</button>
            <button onClick={addCard} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-[var(--radius)] text-xs font-medium hover:bg-primary/90">Add</button>
          </div>
        </div>
      )}

      {/* Cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {cards.map((card, idx) => (
          <FlashCard
            key={idx}
            card={card}
            onEdit={() => { setEditIdx(idx); setEditDraft(card); }}
            onDelete={() => deleteCard(idx)}
          />
        ))}
      </div>
      {cards.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-sm">No flashcards yet. Add your first card above.</p>
        </div>
      )}
    </div>
  );
}
