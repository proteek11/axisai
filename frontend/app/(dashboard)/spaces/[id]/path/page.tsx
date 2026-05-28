'use client';

/**
 * Learning Path Builder — /spaces/[id]/path
 *
 * Drag-and-drop interface for creators/admins to:
 *   • Reorder content items
 *   • Group them into labelled sections (section_title)
 *   • Save the layout back to the server via PUT /api/spaces/[id]/path
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { ChevronDown, ChevronUp, FileText, FileArchive, GripVertical,
  Layers, Loader2, Pencil, Plus, Save, Trash2, Youtube, Video, Upload, X,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────────

interface PathItem {
  id: string;           // SpaceItem.id
  content_item_id: string;
  position: number;
  section_title: string | null;
  title_override: string | null;
  content_type: string | null;
  content_title: string | null;
  content_status: string | null;
}

interface SpaceData {
  id: string;
  title: string;
  creator_id: string;
  items: PathItem[];
}

// ── Content type icon map ──────────────────────────────────────────────────────

const ICON_MAP: Record<string, React.ElementType> = {
  pdf: FileText, text: FileText, scorm: FileArchive,
  youtube: Youtube, vimeo: Video, video_upload: Upload,
};
const ICON_COLOR: Record<string, string> = {
  pdf: 'text-orange-600 bg-orange-50',
  text: 'text-gray-600 bg-gray-50',
  youtube: 'text-red-600 bg-red-50',
  vimeo: 'text-blue-600 bg-blue-50',
  video_upload: 'text-purple-600 bg-purple-50',
};

function ContentIcon({ type }: { type: string | null }) {
  const Icon = ICON_MAP[type ?? ''] ?? FileText;
  const cls  = ICON_COLOR[type ?? ''] ?? 'text-muted-foreground bg-muted';
  return (
    <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0', cls)}>
      <Icon className="w-4 h-4" />
    </div>
  );
}

// ── Section header row with editable label ─────────────────────────────────────

function SectionHeader({
  label,
  onLabelChange,
  onRemove,
}: {
  label: string;
  onLabelChange: (v: string) => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft]     = useState(label);
  const inputRef              = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commit = () => {
    const val = draft.trim();
    if (val) onLabelChange(val);
    else setDraft(label); // revert if blank
    setEditing(false);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-muted/60 border border-border
      rounded-[var(--radius)] mb-1 group">
      <Layers className="w-3.5 h-3.5 text-primary flex-shrink-0" />
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { setDraft(label); setEditing(false); } }}
          className="flex-1 bg-transparent text-xs font-semibold uppercase tracking-wide
            text-foreground border-b border-primary outline-none"
        />
      ) : (
        <span
          className="flex-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground
            cursor-pointer hover:text-foreground transition-colors"
          onClick={() => setEditing(true)}
        >
          {label}
        </span>
      )}
      <button
        onClick={() => setEditing(true)}
        className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
        title="Rename section"
      >
        <Pencil className="w-3 h-3" />
      </button>
      <button
        onClick={onRemove}
        className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-red-500"
        title="Remove section label (items stay)"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

// ── Single draggable item row ──────────────────────────────────────────────────

function DraggableItem({
  item,
  index,
  total,
  onMoveUp,
  onMoveDown,
  onAddSectionAbove,
}: {
  item: PathItem;
  index: number;
  total: number;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onAddSectionAbove: () => void;
}) {
  const displayTitle = item.title_override || item.content_title || 'Untitled';
  const isReady      = item.content_status === 'ready';

  return (
    <div
      className="flex items-center gap-3 px-3 py-3 bg-card border border-border
        rounded-[var(--radius)] mb-2 group hover:border-primary/30 hover:shadow-sm transition-all"
      draggable={false} /* We use button-based reorder for reliability */
    >
      {/* Drag handle (visual only) */}
      <GripVertical className="w-4 h-4 text-border group-hover:text-muted-foreground flex-shrink-0 transition-colors" />

      <ContentIcon type={item.content_type} />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{displayTitle}</p>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-xs text-muted-foreground capitalize">{item.content_type ?? 'Unknown'}</span>
          {!isReady && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 border border-amber-200">
              {item.content_status}
            </span>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onAddSectionAbove}
          title="Add section above"
          className="p-1.5 rounded text-muted-foreground hover:text-primary hover:bg-primary/5 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onMoveUp}
          disabled={index === 0}
          title="Move up"
          className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted
            disabled:opacity-30 transition-colors"
        >
          <ChevronUp className="w-4 h-4" />
        </button>
        <button
          onClick={onMoveDown}
          disabled={index === total - 1}
          title="Move down"
          className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted
            disabled:opacity-30 transition-colors"
        >
          <ChevronDown className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function LearningPathPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: space, isLoading } = useQuery<SpaceData>({
    queryKey: ['space', id],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${id}`);
      if (!res.ok) throw new Error('Failed to load space');
      return res.json();
    },
  });

  // Local ordered list of items — this is what gets saved
  const [items, setItems] = useState<PathItem[]>([]);
  const [isDirty, setIsDirty] = useState(false);

  // Initialise from server data
  useEffect(() => {
    if (space?.items) {
      const sorted = [...space.items].sort((a, b) => a.position - b.position);
      setItems(sorted);
      setIsDirty(false);
    }
  }, [space]);

  // ── Mutations ──────────────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        items: items.map((item, idx) => ({
          item_id: item.id,
          position: idx,
          section_title: item.section_title || null,
        })),
      };
      const res = await fetch(`/api/spaces/${id}/path`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok && res.status !== 204) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error ?? 'Save failed');
      }
    },
    onSuccess: () => {
      setIsDirty(false);
      queryClient.invalidateQueries({ queryKey: ['space', id] });
      toast.success('Learning path saved');
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── Item manipulation helpers ──────────────────────────────────────────────

  const mutateItems = useCallback((fn: (prev: PathItem[]) => PathItem[]) => {
    setItems((prev) => fn(prev));
    setIsDirty(true);
  }, []);

  const moveUp = (idx: number) => {
    if (idx === 0) return;
    mutateItems((prev) => {
      const next = [...prev];
      [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      return next;
    });
  };

  const moveDown = (idx: number) => {
    mutateItems((prev) => {
      if (idx >= prev.length - 1) return prev;
      const next = [...prev];
      [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
      return next;
    });
  };

  const addSectionAbove = (idx: number) => {
    mutateItems((prev) => {
      const next = [...prev];
      // If this item already has a section label, just focus the edit
      if (!next[idx].section_title) {
        next[idx] = { ...next[idx], section_title: 'Section' };
      }
      return next;
    });
  };

  const updateSectionLabel = (idx: number, label: string) => {
    mutateItems((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], section_title: label };
      return next;
    });
  };

  const removeSection = (idx: number) => {
    mutateItems((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], section_title: null };
      return next;
    });
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div>
        <Header title="Learning Path" subtitle="Arrange content into a structured sequence" />
        <div className="page-padding flex justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (!space) {
    return (
      <div>
        <Header title="Learning Path" />
        <div className="page-padding">
          <p className="text-muted-foreground">Space not found.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Header
        title="Learning Path"
        subtitle={`${space.title} · ${items.length} item${items.length !== 1 ? 's' : ''}`}
        backHref={`/spaces/${id}`}
        backLabel="Back to Space"
        action={
          <button
            onClick={() => saveMutation.mutate()}
            disabled={!isDirty || saveMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saveMutation.isPending
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</>
              : <><Save className="w-4 h-4" /> Save Path</>
            }
          </button>
        }
      />

      <div className="page-padding max-w-2xl">

        {/* Info banner */}
        <div className="enterprise-card bg-primary/5 border-primary/20 mb-6 flex items-start gap-3">
          <Layers className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-foreground mb-0.5">Build your learning sequence</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Use the <strong>↑ ↓</strong> arrows to reorder items, and the <strong>+</strong> button to add a section label above any item. Learners will see content in this exact order, grouped by your sections.
            </p>
          </div>
        </div>

        {items.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <Layers className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No content yet. Add content to this space first.</p>
            <button
              onClick={() => router.push(`/spaces/${id}`)}
              className="mt-4 text-xs text-primary hover:underline"
            >
              Go to space →
            </button>
          </div>
        ) : (
          <div>
            {items.map((item, idx) => (
              <div key={item.id}>
                {/* Section header (shown above item if item has a section_title) */}
                {item.section_title && (
                  <SectionHeader
                    label={item.section_title}
                    onLabelChange={(v) => updateSectionLabel(idx, v)}
                    onRemove={() => removeSection(idx)}
                  />
                )}

                <DraggableItem
                  item={item}
                  index={idx}
                  total={items.length}
                  onMoveUp={() => moveUp(idx)}
                  onMoveDown={() => moveDown(idx)}
                  onAddSectionAbove={() => addSectionAbove(idx)}
                />
              </div>
            ))}

            {/* Dirty-state footer */}
            {isDirty && (
              <div className="flex items-center justify-between pt-4 border-t border-border mt-4">
                <p className="text-xs text-amber-600 font-medium">Unsaved changes</p>
                <button
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
                    rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors
                    disabled:opacity-50"
                >
                  {saveMutation.isPending
                    ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</>
                    : <><Save className="w-4 h-4" /> Save Path</>
                  }
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
