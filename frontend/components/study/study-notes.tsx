'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { StickyNote, Plus, Trash2, Check, X, Loader2, Pencil } from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface Note {
  id: string;
  body: string;
  created_at: string;
  updated_at: string;
}

interface StudyNotesProps {
  contentItemId: string;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function StudyNotes({ contentItemId }: StudyNotesProps) {
  const qc = useQueryClient();
  const [draft, setDraft]     = useState('');
  const [editId, setEditId]   = useState<string | null>(null);
  const [editBody, setEditBody] = useState('');

  const { data: notes = [], isLoading } = useQuery<Note[]>({
    queryKey: ['notes', contentItemId],
    queryFn: async () => {
      const res = await fetch(`/api/me/notes?content_item_id=${contentItemId}`);
      if (!res.ok) return [];
      return res.json();
    },
  });

  const createMutation = useMutation({
    mutationFn: async (body: string) => {
      const res = await fetch('/api/me/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_item_id: contentItemId, body }),
      });
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    onSuccess: () => {
      setDraft('');
      qc.invalidateQueries({ queryKey: ['notes', contentItemId] });
      toast.success('Note saved!');
    },
    onError: () => toast.error('Could not save note — please try again'),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, body }: { id: string; body: string }) => {
      const res = await fetch(`/api/me/notes/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body }),
      });
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    onSuccess: () => {
      setEditId(null);
      qc.invalidateQueries({ queryKey: ['notes', contentItemId] });
      toast.success('Note updated!');
    },
    onError: () => toast.error('Could not update note'),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await fetch(`/api/me/notes/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notes', contentItemId] });
      toast.success('Note deleted');
    },
    onError: () => toast.error('Could not delete note'),
  });

  const handleCreate = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    createMutation.mutate(trimmed);
  };

  const handleEdit = (note: Note) => {
    setEditId(note.id);
    setEditBody(note.body);
  };

  const handleSaveEdit = () => {
    if (!editId || !editBody.trim()) return;
    updateMutation.mutate({ id: editId, body: editBody.trim() });
  };

  return (
    <div className="max-w-2xl">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <StickyNote className="w-4 h-4 text-primary" />
        <p className="section-label">My Notes</p>
        <span className="text-xs text-muted-foreground ml-auto">
          {notes.length} note{notes.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Add note */}
      <div className="enterprise-card mb-4 p-3">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleCreate();
          }}
          placeholder="Add a note… (Cmd+Enter to save)"
          rows={3}
          className="w-full resize-none text-sm bg-transparent focus:outline-none text-foreground
            placeholder:text-muted-foreground leading-relaxed"
        />
        <div className="flex justify-end mt-2">
          <button
            onClick={handleCreate}
            disabled={!draft.trim() || createMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)]
              bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors"
          >
            {createMutation.isPending
              ? <Loader2 className="w-3 h-3 animate-spin" />
              : <Plus className="w-3 h-3" />}
            Add Note
          </button>
        </div>
      </div>

      {/* Notes list */}
      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
        </div>
      ) : notes.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          <StickyNote className="w-8 h-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">No notes yet. Add your first one above.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {notes.map((note) => (
            <div
              key={note.id}
              className="enterprise-card group p-3"
            >
              {editId === note.id ? (
                /* Edit mode */
                <div>
                  <textarea
                    value={editBody}
                    onChange={(e) => setEditBody(e.target.value)}
                    autoFocus
                    rows={3}
                    className="w-full resize-none text-sm bg-transparent focus:outline-none
                      text-foreground leading-relaxed"
                  />
                  <div className="flex gap-2 justify-end mt-2">
                    <button
                      onClick={() => setEditId(null)}
                      className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={handleSaveEdit}
                      disabled={updateMutation.isPending}
                      className="w-7 h-7 rounded flex items-center justify-center bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                    >
                      {updateMutation.isPending
                        ? <Loader2 className="w-3 h-3 animate-spin" />
                        : <Check className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>
              ) : (
                /* View mode */
                <div className="flex items-start gap-2">
                  <p className="flex-1 text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                    {note.body}
                  </p>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    <button
                      onClick={() => handleEdit(note)}
                      className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
                      title="Edit"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(note.id)}
                      className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-red-600 hover:bg-red-50 transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              )}
              <p className="text-[10px] text-muted-foreground mt-1.5">
                {timeAgo(note.updated_at !== note.created_at ? note.updated_at : note.created_at)}
                {note.updated_at !== note.created_at && ' · edited'}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
