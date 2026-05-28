'use client';

import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { UploadModal } from '@/components/spaces/upload-modal';
import { ShareModal } from '@/components/spaces/share-modal';
import { JobProgress } from '@/components/spaces/job-progress';
import { SpaceCertificatesSection } from '@/components/spaces/space-certificates-section';
import { LiveClassesSection } from '@/components/spaces/live-classes-section';
import CataloguePicker from '@/components/CataloguePicker';
import { ScormConfigModal } from '@/components/ScormConfigModal';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  BookOpen, Plus, ArrowRight, Globe, Lock, Settings,
  Loader2, FileText, Youtube, Video, Upload, Trash2, FileArchive,
  Eye, EyeOff, Share2, CheckCircle2, Clock, Pencil,
  AlertCircle, AlertTriangle, X, ExternalLink, Route, BarChart3, SlidersHorizontal,
  RefreshCw, Layers as LayersIcon, ChevronUp, ChevronDown, Save,
  Link2, Image as ImageIcon, Film, Brain, BookMarked, Award,
} from 'lucide-react';

interface ContentItem {
  id: string;
  title: string;
  content_type: 'pdf' | 'youtube' | 'vimeo' | 'video_upload' | 'text';
  source_url: string | null;
  status: 'queued' | 'processing' | 'done' | 'failed';
  job_id: string | null;
  has_outputs: boolean;
  created_at: string;
}

interface SpaceItem {
  id: string;
  content_item_id: string;
  position: number;
  title_override: string | null;
  is_visible: boolean;
  visible_outputs: string[];
  // Flat fields from SpaceItemSummary API response
  content_type: string | null;
  content_title: string | null;
  content_status: string | null;
  source_url: string | null;
}

interface Space {
  id: string;
  title: string;
  slug: string;
  description: string | null;
  is_published: boolean;
  is_guest_accessible: boolean;
  tags: string[];
  cover_image_url: string | null;
  items: SpaceItem[];
  share_url?: string;
  created_at: string;
  updated_at: string;
}

const CONTENT_TYPE_META: Record<string, { icon: React.ElementType; color: string; bg: string; label: string }> = {
  pdf:          { icon: FileText,    color: 'text-orange-600',  bg: 'bg-orange-50',  label: 'PDF'            },
  scorm:        { icon: FileArchive, color: 'text-violet-700', bg: 'bg-violet-50', label: 'SCORM'          },
  text:         { icon: FileText, color: 'text-gray-600',   bg: 'bg-gray-50',   label: 'Text'         },
  youtube:      { icon: Youtube,  color: 'text-red-600',    bg: 'bg-red-50',    label: 'YouTube'      },
  vimeo:        { icon: Video,    color: 'text-blue-600',   bg: 'bg-blue-50',   label: 'Vimeo'        },
  video_upload: { icon: Upload,   color: 'text-purple-600', bg: 'bg-purple-50', label: 'Local Video'  },
  assessment:   { icon: Brain,    color: 'text-indigo-600', bg: 'bg-indigo-50', label: 'Assessment'   },
};

// ── Gen Settings Modal ────────────────────────────────────────────────────────
interface GenSettingsData {
  quiz_count: number;
  flashcard_count: number;
  allow_learner_regen: boolean;
  max_quiz_count: number;
  max_flashcard_count: number;
  current_quiz_count: number;
  current_flashcard_count: number;
  quiz_regen_available: boolean;
  flashcard_regen_available: boolean;
}

const ALL_OUTPUTS = [
  { key: 'summary',     label: 'Summary'     },
  { key: 'glossary',    label: 'Glossary'    },
  { key: 'flashcards',  label: 'Flashcards'  },
  { key: 'quiz',        label: 'Quiz'        },
  { key: 'faq',         label: 'FAQ'         },
  { key: 'infographic', label: 'Infographic' },
  { key: 'chapters',    label: 'Chapters'    },
] as const;

function GenSettingsModal({
  spaceId,
  contentItemId,
  spaceItemId,
  contentTitle,
  initialVisibleOutputs,
  onClose,
}: {
  spaceId: string;
  contentItemId: string;
  spaceItemId: string;
  contentTitle: string;
  initialVisibleOutputs: string[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();

  const { data: settings, isLoading } = useQuery<GenSettingsData>({
    queryKey: ['gen-settings', spaceId, contentItemId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/content/${contentItemId}/gen-settings`);
      if (!res.ok) throw new Error('Failed to load settings');
      return res.json();
    },
  });

  // Local form state — initialised once settings load
  const [quizCount,          setQuizCount]          = useState<number | ''>(10);
  const [flashcardCount,     setFlashcardCount]     = useState<number | ''>(10);
  const [allowRegen,         setAllowRegen]         = useState(false);
  const [maxQuiz,            setMaxQuiz]            = useState<number | ''>(20);
  const [maxFlashcard,       setMaxFlashcard]       = useState<number | ''>(20);
  const [visibleOutputs,     setVisibleOutputs]     = useState<string[]>(initialVisibleOutputs);
  const [initialised,        setInitialised]        = useState(false);

  if (settings && !initialised) {
    setQuizCount(settings.quiz_count);
    setFlashcardCount(settings.flashcard_count);
    setAllowRegen(settings.allow_learner_regen);
    setMaxQuiz(settings.max_quiz_count);
    setMaxFlashcard(settings.max_flashcard_count);
    setInitialised(true);
  }

  const toggleOutput = (key: string) => {
    setVisibleOutputs((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      // Save gen settings (PATCH)
      const genRes = await fetch(
        `/api/spaces/${spaceId}/content/${contentItemId}/gen-settings`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            quiz_count:          Number(quizCount)      || 10,
            flashcard_count:     Number(flashcardCount) || 10,
            allow_learner_regen: allowRegen,
            max_quiz_count:      Number(maxQuiz)        || 20,
            max_flashcard_count: Number(maxFlashcard)   || 20,
          }),
        },
      );
      if (!genRes.ok) {
        const err = await genRes.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to save generation settings');
      }
      // Save visible_outputs (PUT space item)
      const itemRes = await fetch(
        `/api/spaces/${spaceId}/items/${spaceItemId}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ visible_outputs: visibleOutputs }),
        },
      );
      if (!itemRes.ok) {
        const err = await itemRes.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to save visible tabs');
      }
    },
    onSuccess: () => {
      toast.success('Settings saved');
      queryClient.invalidateQueries({ queryKey: ['gen-settings', spaceId, contentItemId] });
      queryClient.invalidateQueries({ queryKey: ['space', spaceId] });
      onClose();
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const NumInput = ({
    label, value, onChange, min = 1, max = 100, disabled = false,
  }: {
    label: string; value: number | ''; onChange: (v: number | '') => void;
    min?: number; max?: number; disabled?: boolean;
  }) => (
    <div className={cn('space-y-1', disabled && 'opacity-50')}>
      <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</label>
      <input
        type="number"
        min={min}
        max={max}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        className="w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background
          focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary disabled:cursor-not-allowed"
      />
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-xl mx-4 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
              <SlidersHorizontal className="w-4 h-4 text-primary" />
            </div>
            <div>
              <p className="font-semibold text-sm text-primary">Generation Settings</p>
              <p className="text-xs text-muted-foreground truncate max-w-[240px]">{contentTitle}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="px-6 py-5 space-y-6 max-h-[60vh] overflow-y-auto">

            {/* Current counts info bar */}
            {settings && (
              <div className="flex gap-3">
                <div className="flex-1 bg-muted/50 rounded-[var(--radius)] px-3 py-2.5 text-center border border-border">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Quiz Now</p>
                  <p className="text-xl font-bold text-primary">{settings.current_quiz_count}</p>
                </div>
                <div className="flex-1 bg-muted/50 rounded-[var(--radius)] px-3 py-2.5 text-center border border-border">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Flashcards Now</p>
                  <p className="text-xl font-bold text-primary">{settings.current_flashcard_count}</p>
                </div>
              </div>
            )}

            {/* Section: Initial generation */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <LayersIcon className="w-3.5 h-3.5 text-muted-foreground" />
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  Initial Generation
                </p>
              </div>
              <p className="text-xs text-muted-foreground mb-3">
                How many items to generate when this content is first processed or regenerated.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <NumInput
                  label="Quiz Questions"
                  value={quizCount}
                  onChange={setQuizCount}
                  min={1}
                  max={50}
                />
                <NumInput
                  label="Flashcards"
                  value={flashcardCount}
                  onChange={setFlashcardCount}
                  min={1}
                  max={50}
                />
              </div>
            </div>

            {/* Section: Learner regeneration */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <RefreshCw className="w-3.5 h-3.5 text-muted-foreground" />
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  Learner Regeneration
                </p>
              </div>

              {/* Toggle */}
              <button
                onClick={() => setAllowRegen((v) => !v)}
                className={cn(
                  'flex items-center justify-between w-full px-4 py-3 rounded-[var(--radius)] border transition-colors mb-3',
                  allowRegen
                    ? 'border-primary/40 bg-primary/5 text-primary'
                    : 'border-border bg-muted/30 text-muted-foreground',
                )}
              >
                <div className="flex items-center gap-2.5">
                  <div className={cn(
                    'w-9 h-5 rounded-full transition-colors flex items-center px-0.5',
                    allowRegen ? 'bg-primary' : 'bg-muted-foreground/30',
                  )}>
                    <div className={cn(
                      'w-4 h-4 rounded-full bg-white shadow transition-transform',
                      allowRegen ? 'translate-x-4' : 'translate-x-0',
                    )} />
                  </div>
                  <span className="text-sm font-medium">
                    {allowRegen ? 'Learners can generate more' : 'Disabled — learners see fixed set'}
                  </span>
                </div>
              </button>

              {/* Max counts (only visible when regen enabled) */}
              {allowRegen && (
                <div className="space-y-3">
                  <p className="text-xs text-muted-foreground">
                    Maximum items a learner can accumulate (initial + all regenerations).
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    <NumInput
                      label="Max Quiz Total"
                      value={maxQuiz}
                      onChange={setMaxQuiz}
                      min={Number(quizCount) || 1}
                      max={200}
                    />
                    <NumInput
                      label="Max Flashcard Total"
                      value={maxFlashcard}
                      onChange={setMaxFlashcard}
                      min={Number(flashcardCount) || 1}
                      max={200}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Section: Visible tabs */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Eye className="w-3.5 h-3.5 text-muted-foreground" />
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  Visible Tabs for Learners
                </p>
              </div>
              <p className="text-xs text-muted-foreground mb-3">
                Choose which AI output tabs learners can see for this content.
              </p>
              <div className="grid grid-cols-2 gap-2">
                {ALL_OUTPUTS.map(({ key, label }) => {
                  const checked = visibleOutputs.includes(key);
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => toggleOutput(key)}
                      className={cn(
                        'flex items-center gap-2 px-3 py-2 rounded-[var(--radius)] border text-sm transition-colors text-left',
                        checked
                          ? 'border-primary/50 bg-primary/5 text-primary'
                          : 'border-border text-muted-foreground hover:bg-muted',
                      )}
                    >
                      <div className={cn(
                        'w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors',
                        checked ? 'bg-primary border-primary' : 'border-muted-foreground/40',
                      )}>
                        {checked && <CheckCircle2 className="w-3 h-3 text-white" />}
                      </div>
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex gap-2 justify-end px-6 py-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm
              text-muted-foreground hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {saveMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
}
// ── Edit Space Modal (C-03) ───────────────────────────────────────────────────
function EditSpaceModal({
  spaceId, currentTitle, currentDescription, currentTags, currentCoverImageUrl, currentSlug, onClose, onSaved,
}: {
  spaceId: string; currentTitle: string; currentDescription: string;
  currentTags: string[]; currentCoverImageUrl: string | null; currentSlug: string;
  onClose: () => void; onSaved: () => void;
}) {
  const [title, setTitle]       = useState(currentTitle);
  const [desc,  setDesc]        = useState(currentDescription);
  const [slug,  setSlug]        = useState(currentSlug);
  const [tagInput, setTagInput] = useState('');
  const [tags,  setTags]        = useState<string[]>(currentTags);

  const handleTitleChange = (val: string) => {
    setTitle(val);
    if (slug === currentSlug) {
      setSlug(val.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80));
    }
  };
  const [saving, setSaving]     = useState(false);
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverPreview, setCoverPreview] = useState<string | null>(currentCoverImageUrl);
  const [uploadingCover, setUploadingCover] = useState(false);
  const coverInputRef = useRef<HTMLInputElement>(null);

  const handleCoverFile = (file: File) => {
    setCoverFile(file);
    const url = URL.createObjectURL(file);
    setCoverPreview(url);
  };

  const addTag = () => {
    const t = tagInput.trim();
    if (t && !tags.includes(t)) setTags((prev) => [...prev, t]);
    setTagInput('');
  };

  const save = async () => {
    if (!title.trim()) { toast.error('Title is required'); return; }
    setSaving(true);
    try {
      // 1. Update title / description / tags
      const res = await fetch(`/api/spaces/${spaceId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim(), description: desc.trim() || null, tags, slug: slug.trim() || undefined }),
      });
      if (!res.ok) throw new Error('Failed to save');

      // 2. Upload cover image if a new file was selected
      if (coverFile) {
        setUploadingCover(true);
        const fd = new FormData();
        fd.append('file', coverFile);
        const coverRes = await fetch(`/api/spaces/${spaceId}/cover-image`, {
          method: 'POST',
          body: fd,
        });
        if (!coverRes.ok) {
          toast.error('Space saved but cover image upload failed');
        }
        setUploadingCover(false);
      }

      toast.success('Space updated');
      onSaved();
      onClose();
    } catch { toast.error('Could not save changes'); }
    finally   { setSaving(false); setUploadingCover(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-md mx-4 shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <p className="font-semibold text-primary">Edit Space</p>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-6 py-5 space-y-4">
          {/* Cover Image */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Cover Image</label>
            <div
              className="relative w-full h-32 rounded-[var(--radius)] border-2 border-dashed border-border overflow-hidden cursor-pointer hover:border-primary/50 transition-colors group"
              onClick={() => coverInputRef.current?.click()}
            >
              {coverPreview ? (
                <>
                  <img
                    src={coverPreview.startsWith('blob:') ? coverPreview : coverPreview.startsWith('http') ? coverPreview : `/api/cover-images/${coverPreview.split('/').pop()}`}
                    alt="Cover"
                    className="w-full h-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; setCoverPreview(null); }}
                  />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <p className="text-white text-xs font-medium">Click to change</p>
                  </div>
                </>
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center gap-1 text-muted-foreground">
                  <ImageIcon className="w-6 h-6" />
                  <p className="text-xs">Click to upload cover image</p>
                  <p className="text-[10px]">JPEG, PNG, WebP · max 2 MB</p>
                </div>
              )}
            </div>
            <input
              ref={coverInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleCoverFile(f); }}
            />
            {coverFile && (
              <p className="text-[11px] text-muted-foreground">
                Selected: <span className="font-medium text-foreground">{coverFile.name}</span>
                {' · '}{(coverFile.size / 1024 / 1024).toFixed(1)} MB
              </p>
            )}
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Title *</label>
            <input value={title} onChange={(e) => handleTitleChange(e.target.value)}
              className="w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background
                focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Space Slug <span className="text-[10px] font-normal text-muted-foreground normal-case">(used in Moodle custom params)</span>
            </label>
            <div className="flex items-center gap-2">
              <input value={slug} onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 80))}
                placeholder="e.g. python-basics"
                className="flex-1 px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background font-mono
                  focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary" />
            </div>
            <p className="text-[11px] text-muted-foreground">In Moodle → External Tool → Custom parameters: <code className="bg-muted px-1 rounded">space_slug={slug || 'your-slug'}</code></p>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Description</label>
            <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={3}
              className="w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background resize-none
                focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Tags</label>
            <div className="flex gap-2">
              <input value={tagInput} onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }}
                placeholder="Add tag + Enter"
                className="flex-1 px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background
                  focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary" />
              <button onClick={addTag}
                className="px-3 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted">
                Add
              </button>
            </div>
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {tags.map((t) => (
                  <span key={t} className="flex items-center gap-1 px-2 py-0.5 bg-muted rounded-full text-xs text-muted-foreground">
                    {t}
                    <button onClick={() => setTags((p) => p.filter((x) => x !== t))}
                      className="hover:text-red-500 transition-colors">×</button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="flex gap-2 justify-end px-6 py-4 border-t border-border">
          <button onClick={onClose}
            className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted">
            Cancel
          </button>
          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 disabled:opacity-50">
            {(saving || uploadingCover) && <Loader2 className="w-4 h-4 animate-spin" />}
            {uploadingCover ? 'Uploading cover…' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
// ── Assessment publish toggle ─────────────────────────────────────────────────
function AssessmentPublishToggle({ spaceId, contentItemId }: { spaceId: string; contentItemId: string }) {
  const queryClient = useQueryClient();

  const { data: info, isLoading } = useQuery<{ assessment_id: string; is_published: boolean } | null>({
    queryKey: ['assessment-publish', contentItemId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/content/${contentItemId}/assessment-info`);
      if (!res.ok) return null;
      return res.json();
    },
    retry: false,
  });

  const toggleMutation = useMutation({
    mutationFn: async () => {
      if (!info?.assessment_id) throw new Error('No assessment ID');
      const res = await fetch(`/api/spaces/${spaceId}/assessments/${info.assessment_id}/publish`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed');
      return res.json() as Promise<{ is_published: boolean }>;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(
        ['assessment-publish', contentItemId],
        (prev: { assessment_id: string; is_published: boolean } | null) =>
          prev ? { ...prev, is_published: data.is_published } : prev
      );
      toast.success(data.is_published ? 'Assessment published — students can now take it' : 'Assessment unpublished');
    },
    onError: () => toast.error('Failed to update publish status'),
  });

  if (isLoading) return <span className="text-xs text-muted-foreground">Loading...</span>;
  if (!info) return null;

  return (
    <button
      onClick={() => toggleMutation.mutate()}
      disabled={toggleMutation.isPending}
      title={info.is_published ? 'Published — click to unpublish' : 'Unpublished — students cannot see this. Click to publish.'}
      className={cn(
        'flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border transition-colors',
        info.is_published
          ? 'border-emerald-400 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
          : 'border-amber-400 bg-amber-50 text-amber-700 hover:bg-amber-100 animate-pulse'
      )}
    >
      {toggleMutation.isPending
        ? <Loader2 className="w-3 h-3 animate-spin" />
        : info.is_published
          ? <CheckCircle2 className="w-3 h-3" />
          : <AlertTriangle className="w-3 h-3" />
      }
      {info.is_published ? 'Published' : 'Unpublished — click to publish'}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export default function SpaceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [showUpload, setShowUpload] = useState(false);
  const [showCatalogue, setShowCatalogue] = useState(false);
  const [scormConfigItem, setScormConfigItem] = useState<{ spaceItemId: string; title: string } | null>(null);
  const [showICModal, setShowICModal] = useState(false);
  const [icLibrary, setIcLibrary] = useState<Array<{content_item_id:string;title?:string;content_type:string;source_url?:string;interaction_count:number;space_id?:string;space_title?:string}>>([]);
  const [icLoading, setIcLoading] = useState(false);
  const [icSelected, setIcSelected] = useState('');
  const [icAttaching, setIcAttaching] = useState(false);
  const [icSearch, setIcSearch] = useState('');
  const [showShare, setShowShare] = useState(false);
  const [showDeleteSpaceModal, setShowDeleteSpaceModal] = useState(false);
  const [deletePreview, setDeletePreview] = useState<{
    space_id: string; space_title: string; total_items: number;
    exclusive_items: Array<{ id: string; title: string; content_type: string }>;
    shared_items: Array<{ id: string; title: string; content_type: string; other_space_titles: string[] }>;
  } | null>(null);
  const [deletePreviewLoading, setDeletePreviewLoading] = useState(false);
  const [activeJobs, setActiveJobs] = useState<Record<string, string>>({}); // contentId → jobId
  const [deleteItemId, setDeleteItemId] = useState<string | null>(null);
  const [genSettingsItem, setGenSettingsItem] = useState<{
    contentItemId: string; spaceItemId: string; title: string; visibleOutputs: string[];
  } | null>(null);
  const [showEditSpace, setShowEditSpace] = useState(false);
  const [localItems, setLocalItems] = useState<SpaceItem[]>([]);
  const [isOrderDirty, setIsOrderDirty] = useState(false);
  const [isSavingOrder, setIsSavingOrder] = useState(false);
  const [regeningItem, setRegeningItem] = useState<string | null>(null);
  const [editUrlItem, setEditUrlItem] = useState<{ contentItemId: string; currentUrl: string; title: string } | null>(null);
  const [editUrlValue, setEditUrlValue] = useState('');
  const [editTitleValue, setEditTitleValue] = useState('');
  const [isSavingUrl, setIsSavingUrl] = useState(false);

  const { data: space, isLoading } = useQuery<Space>({
    queryKey: ['space', id],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${id}`);
      if (!res.ok) throw new Error('Not found');
      return res.json();
    },
  });

  // Certificates: now handled by SpaceCertificatesSection component

  // C-04: sync local order from server data
  useEffect(() => {
    if (space?.items) {
      const sorted = [...space.items].sort((a, b) => a.position - b.position);
      setLocalItems(sorted);
      setIsOrderDirty(false);
    }
  }, [space]);

  const publishMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/spaces/${id}/publish`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    onSuccess: (data) => {
      toast.success(data.is_published ? 'Space published!' : 'Space unpublished');
      queryClient.invalidateQueries({ queryKey: ['space', id] });
    },
    onError: () => toast.error('Failed to update publish status'),
  });

  const removeItemMutation = useMutation({
    mutationFn: async (itemId: string) => {
      const res = await fetch(`/api/spaces/${id}/items/${itemId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed');
    },
    onSuccess: () => {
      toast.success('Content removed from space');
      queryClient.invalidateQueries({ queryKey: ['space', id] });
      setDeleteItemId(null);
    },
    onError: () => toast.error('Failed to remove content'),
  });

  const deleteSpaceMutation = useMutation({
    mutationFn: async (deleteContent: boolean = false) => {
      const qs = deleteContent ? '?delete_exclusive_content=true' : '';
      const res = await fetch(`/api/spaces/${id}${qs}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to delete space');
      }
    },
    onSuccess: () => {
      toast.success('Learning space deleted');
      router.push('/dashboard');
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const handleDeleteSpace = async () => {
    setShowDeleteSpaceModal(true);
    setDeletePreview(null);
    setDeletePreviewLoading(true);
    try {
      const res = await fetch(`/api/spaces/${id}/delete-preview`);
      if (res.ok) setDeletePreview(await res.json());
    } catch {/* swallow — modal still shows with fallback */}
    finally { setDeletePreviewLoading(false); }
  };

  const handleUploadSuccess = (contentId: string, jobId?: string) => {
    setShowUpload(false);
    if (jobId) {
      setActiveJobs((prev) => ({ ...prev, [contentId]: jobId }));
    }
    queryClient.invalidateQueries({ queryKey: ['space', id] });
  };

  const handleJobDone = (contentId: string) => {
    setActiveJobs((prev) => {
      const next = { ...prev };
      delete next[contentId];
      return next;
    });
    queryClient.invalidateQueries({ queryKey: ['space', id] });
    toast.success('Content processing complete!');
  };

  // C-04: move item up (-1) or down (+1) in local order
  const moveItem = (idx: number, dir: -1 | 1) => {
    setLocalItems((prev) => {
      const next = [...prev];
      const swap = idx + dir;
      if (swap < 0 || swap >= next.length) return prev;
      [next[idx], next[swap]] = [next[swap], next[idx]];
      return next;
    });
    setIsOrderDirty(true);
  };

  // C-04: persist new order
  const saveOrder = async () => {
    setIsSavingOrder(true);
    try {
      const res = await fetch(`/api/spaces/${id}/path`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: localItems.map((item, idx) => ({
            item_id:       item.id,
            position:      idx,
            section_title: null,
          })),
        }),
      });
      if (!res.ok && res.status !== 204) throw new Error('Save failed');
      setIsOrderDirty(false);
      queryClient.invalidateQueries({ queryKey: ['space', id] });
      toast.success('Order saved');
    } catch {
      toast.error('Failed to save order');
    } finally {
      setIsSavingOrder(false);
    }
  };

  // C-09: update content source URL
  const saveContentUrl = async () => {
    if (!editUrlItem) return;
    setIsSavingUrl(true);
    try {
      const res = await fetch(`/api/spaces/${id}/content/${editUrlItem.contentItemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_url: editUrlValue.trim(), title: editTitleValue.trim() || undefined }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.error ?? 'Update failed');
      }
      toast.success('URL updated — re-generate outputs to apply changes');
      setEditUrlItem(null);
      queryClient.invalidateQueries({ queryKey: ['space', id] });
    } catch (err: any) {
      toast.error(err.message ?? 'Failed to update URL');
    } finally {
      setIsSavingUrl(false);
    }
  };

  // C-01: trigger AI output regeneration for a content item
  const handleRegenerate = async (contentItemId: string) => {
    setRegeningItem(contentItemId);
    try {
      const res = await fetch(`/api/content/${contentItemId}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          output_types: ['summary', 'quiz', 'flashcards', 'glossary', 'faq', 'infographic', 'chapters'],
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.error ?? 'Regeneration failed');
      }
      toast.success('Regeneration started — outputs will refresh shortly');
      queryClient.invalidateQueries({ queryKey: ['space', id] });
    } catch (err: any) {
      toast.error(err.message ?? 'Regeneration failed');
    } finally {
      setRegeningItem(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!space) {
    return (
      <div className="page-padding flex flex-col items-center py-16">
        <AlertCircle className="w-8 h-8 text-muted-foreground mb-3" />
        <p className="text-muted-foreground">Space not found.</p>
      </div>
    );
  }

  return (
    <div>
      <Header
        title={space.title}
        subtitle={space.description ?? 'Learning space'}
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowEditSpace(true)}
              title="Edit space details"
              className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-[var(--radius)]
                text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
            >
              <Pencil className="w-4 h-4" />
              Edit
            </button>
            <button
              onClick={handleDeleteSpace}
              disabled={deleteSpaceMutation.isPending}
              title="Delete this space"
              className="flex items-center gap-1.5 px-3 py-2 bg-red-600 text-white border border-red-600
                rounded-[var(--radius)] text-sm font-medium hover:bg-red-700 hover:border-red-700
                transition-colors disabled:opacity-50"
            >
              {deleteSpaceMutation.isPending
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Trash2 className="w-4 h-4" />
              }
              Delete
            </button>
            <button
              onClick={() => publishMutation.mutate()}
              disabled={publishMutation.isPending}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-[var(--radius)] text-sm font-medium transition-colors',
                space.is_published
                  ? 'border border-green-400 text-green-600 bg-green-50 hover:bg-green-100'
                  : 'bg-primary text-primary-foreground hover:bg-primary/90'
              )}
            >
              {publishMutation.isPending
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : space.is_published
                  ? <CheckCircle2 className="w-4 h-4" />
                  : <Globe className="w-4 h-4" />
              }
              {space.is_published ? 'Published' : 'Publish'}
            </button>
          </div>
        }
      />

      <div className="page-padding">
        {/* Secondary actions chip bar */}
        <div className="flex items-center gap-2 mb-5 pb-4 border-b border-border flex-wrap">
          <Link
            href={`/learn/${id}`}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground
              border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
            title="Preview as learner"
          >
            <Eye className="w-3.5 h-3.5" />
            Preview
          </Link>
          <Link
            href={`/spaces/${id}/report`}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground
              border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            Report
          </Link>
          <Link
            href={`/spaces/${id}/path`}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground
              border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
          >
            <Route className="w-3.5 h-3.5" />
            Learning Path
          </Link>
          <button
            onClick={() => setShowShare(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground
              border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
          >
            <Share2 className="w-3.5 h-3.5" />
            Share
          </button>
        </div>

        {/* Metadata strip */}
        <div className="flex items-center gap-4 mb-6 flex-wrap">
          <span className={cn(
            'flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border',
            space.is_published
              ? 'border-green-400 text-green-600 bg-green-50'
              : 'border-border text-muted-foreground'
          )}>
            {space.is_published ? <CheckCircle2 className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
            {space.is_published ? 'Published' : 'Draft'}
          </span>
          {space.is_guest_accessible && (
            <span className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border border-blue-400 text-blue-600 bg-blue-50">
              <Globe className="w-3 h-3" />
              Guest Accessible
            </span>
          )}
          {space.tags.map((tag) => (
            <span key={tag} className="text-xs px-2.5 py-1 bg-muted rounded-full text-muted-foreground">
              {tag}
            </span>
          ))}
        </div>

        {/* Content items */}
        <div className="flex items-center justify-between mb-4">
          <p className="section-label">Content ({space.items.length})</p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setShowICModal(true);
                setIcSelected('');
                setIcLoading(true);
                fetch('/api/interactive/library', { credentials: 'include' })
                  .then(r => r.ok ? r.json() : { items: [] })
                  .then(d => setIcLibrary(d.items ?? []))
                  .catch(() => setIcLibrary([]))
                  .finally(() => setIcLoading(false));
              }}
              className="flex items-center gap-2 px-3 py-1.5 border border-border text-foreground
                rounded-[var(--radius)] text-sm font-medium hover:bg-muted transition-colors"
            >
              <Film className="w-4 h-4" />
              Add Interactive Content
            </button>
            <button
              onClick={() => setShowCatalogue(true)}
              className="flex items-center gap-2 px-3 py-1.5 border border-border text-foreground
                rounded-[var(--radius)] text-sm font-medium hover:bg-muted transition-colors"
            >
              <BookMarked className="w-4 h-4" />
              Attach from Library
            </button>
            <Link
              href={`/spaces/${id}/assessment/new`}
              className="flex items-center gap-2 px-3 py-1.5 bg-indigo-600 text-white
                rounded-[var(--radius)] text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              <Brain className="w-4 h-4" />
              Create Assessment
            </Link>
            <button
              onClick={() => setShowUpload(true)}
              className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground
                rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Add Content
            </button>
          </div>
        </div>

        {/* Active job progress cards */}
        {Object.entries(activeJobs).map(([contentId, jobId]) => (
          <div key={jobId} className="mb-3">
            <JobProgress
              jobId={jobId}
              onDone={() => handleJobDone(contentId)}
              onFailed={(err) => {
                toast.error(`Processing failed: ${err}`);
                setActiveJobs((prev) => { const n = { ...prev }; delete n[contentId]; return n; });
              }}
            />
          </div>
        ))}

        {space.items.length === 0 && Object.keys(activeJobs).length === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <div className="w-14 h-14 rounded-full bg-muted flex items-center justify-center mb-4">
              <FileText className="w-7 h-7 text-muted-foreground" />
            </div>
            <p className="font-semibold text-primary mb-2">No content yet</p>
            <p className="text-sm text-muted-foreground mb-6">
              Add PDFs, videos, or links to populate this learning space.
            </p>
            <button
              onClick={() => setShowUpload(true)}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
                rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Add First Content
            </button>
          </div>
        ) : (
          <>
          {isOrderDirty && (
            <div className="flex items-center justify-between px-4 py-2.5 mb-2 bg-amber-50 border border-amber-200 rounded-[var(--radius)]">
              <p className="text-xs text-amber-700 font-medium">Content order changed — save to apply</p>
              <button
                onClick={saveOrder}
                disabled={isSavingOrder}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {isSavingOrder ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                Save Order
              </button>
            </div>
          )}
          <div className="space-y-3">
            {localItems.map((item, itemIdx) => {
              const meta = CONTENT_TYPE_META[item.content_type ?? ''] ?? CONTENT_TYPE_META.pdf;
              const Icon = meta.icon;
              const hasActiveJob = activeJobs[item.content_item_id];

              return (
                <div key={item.id} className={cn(
                  'enterprise-card flex items-center gap-4',
                  !item.is_visible && 'opacity-60'
                )}>
                  <div className={cn('w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0', meta.bg)}>
                    <Icon className={cn('w-5 h-5', meta.color)} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-sm text-primary truncate">
                        {item.title_override || item.content_title}
                      </p>
                      <span className="text-xs text-muted-foreground capitalize flex-shrink-0">
                        {meta.label}
                      </span>
                    </div>

                    {hasActiveJob ? (
                      <JobProgress jobId={hasActiveJob} compact onDone={() => handleJobDone(item.content_item_id)} />
                    ) : (
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        <span className={cn(
                          'text-xs flex items-center gap-1',
                          item.content_status === 'ready' ? 'text-green-600' :
                          item.content_status === 'failed' ? 'text-red-600' :
                          'text-muted-foreground'
                        )}>
                          {item.content_status === 'ready' && <CheckCircle2 className="w-3 h-3" />}
                          {item.content_status === 'failed' && <AlertCircle className="w-3 h-3" />}
                          {item.content_status === 'processing' && <Loader2 className="w-3 h-3 animate-spin" />}
                          {item.content_status === 'queued' && <Clock className="w-3 h-3" />}
                          {item.content_status}
                        </span>
                        {item.content_status === 'ready' && item.content_type !== 'assessment' && (
                          <span className="text-xs text-muted-foreground">· AI outputs ready</span>
                        )}
                        {item.content_type === 'assessment' && item.content_status === 'ready' && (
                          <AssessmentPublishToggle spaceId={id} contentItemId={item.content_item_id} />
                        )}
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {/* C-04: Reorder buttons */}
                    <div className="flex flex-col gap-0.5 mr-1">
                      <button
                        onClick={() => moveItem(itemIdx, -1)}
                        disabled={itemIdx === 0}
                        className="w-5 h-5 rounded flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-muted disabled:opacity-20 transition-colors"
                        title="Move up"
                      >
                        <ChevronUp className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => moveItem(itemIdx, 1)}
                        disabled={itemIdx === localItems.length - 1}
                        className="w-5 h-5 rounded flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-muted disabled:opacity-20 transition-colors"
                        title="Move down"
                      >
                        <ChevronDown className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    {item.content_status === 'ready' && (
                      <>
                        {/* C-01: Regenerate outputs */}
                        <button
                          onClick={() => handleRegenerate(item.content_item_id)}
                          disabled={regeningItem === item.content_item_id}
                          className="w-8 h-8 rounded-[var(--radius)] flex items-center justify-center
                            text-muted-foreground hover:text-primary hover:bg-muted disabled:opacity-50 transition-colors"
                          title="Regenerate AI outputs"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${regeningItem === item.content_item_id ? 'animate-spin' : ''}`} />
                        </button>
                        {/* C-09: Edit source URL */}
                        {['youtube', 'vimeo'].includes(item.content_type ?? '') && (
                          <button
                            onClick={() => {
                              setEditUrlItem({
                                contentItemId: item.content_item_id,
                                currentUrl: item.source_url ?? '',
                                title: item.title_override || item.content_title || '',
                              });
                              setEditUrlValue(item.source_url ?? '');
                              setEditTitleValue(item.title_override || item.content_title || '');
                            }}
                            className="w-8 h-8 rounded-[var(--radius)] flex items-center justify-center
                              text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
                            title="Update source URL"
                          >
                            <Link2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {item.content_type === 'scorm' && (
                          <button
                            onClick={() => setScormConfigItem({
                              spaceItemId: item.id,
                              title: item.title_override || item.content_title || 'SCORM Package',
                            })}
                            className="w-8 h-8 rounded-[var(--radius)] flex items-center justify-center
                              text-muted-foreground hover:text-violet-600 hover:bg-violet-50 transition-colors"
                            title="SCORM settings (attempts, completion trigger)"
                          >
                            <Settings className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {item.content_type !== 'scorm' && (
                          <button
                            onClick={() => setGenSettingsItem({
                              contentItemId:  item.content_item_id,
                              spaceItemId:    item.id,
                              title:          item.title_override || item.content_title || 'Content',
                              visibleOutputs: item.visible_outputs ?? [],
                            })}
                            className="w-8 h-8 rounded-[var(--radius)] flex items-center justify-center
                              text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
                            title="Generation settings"
                          >
                            <SlidersHorizontal className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <Link
                          href={`/spaces/${id}/content/${item.content_item_id}/outputs`}
                          className="w-8 h-8 rounded-[var(--radius)] flex items-center justify-center
                            text-muted-foreground hover:text-emerald-600 hover:bg-emerald-50 transition-colors"
                          title="View AI outputs"
                        >
                          <Brain className="w-3.5 h-3.5" />
                        </Link>
                        {item.content_type === 'assessment' ? (
                          <Link
                            href={`/spaces/${id}/assessment/new?edit=${item.content_item_id}`}
                            className="w-8 h-8 rounded-[var(--radius)] flex items-center justify-center
                              text-muted-foreground hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                            title="Manage assessment"
                          >
                            <BookMarked className="w-3.5 h-3.5" />
                          </Link>
                        ) : (
                          <Link
                            href={`/learn/${id}/content/${item.content_item_id}`}
                            className="w-8 h-8 rounded-[var(--radius)] flex items-center justify-center
                              text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
                            title="Learner preview"
                          >
                            <ArrowRight className="w-4 h-4" />
                          </Link>
                        )}
                      </>
                    )}
                    <button
                      onClick={() => setDeleteItemId(item.id)}
                      className="w-8 h-8 rounded-[var(--radius)] flex items-center justify-center
                        text-muted-foreground hover:text-red-600 hover:bg-red-50 transition-colors"
                      title="Remove"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          </>
        )}
      </div>

      {showUpload && (
        <UploadModal
          spaceId={id}
          onClose={() => setShowUpload(false)}
          onSuccess={handleUploadSuccess}
        />
      )}

      {scormConfigItem && (
        <ScormConfigModal
          spaceId={id}
          spaceItemId={scormConfigItem.spaceItemId}
          packageTitle={scormConfigItem.title}
          onClose={() => setScormConfigItem(null)}
          onSaved={() => { setScormConfigItem(null); queryClient.invalidateQueries({ queryKey: ['space', id] }); }}
        />
      )}

      <CataloguePicker
        open={showCatalogue}
        onClose={() => setShowCatalogue(false)}
        spaceId={id}
        spaceName={space?.title}
        onAttached={async (item) => {
          queryClient.invalidateQueries({ queryKey: ['space', id] });
          // If SCORM, offer to configure settings — wait briefly for items to refresh
          if (item.content_type === 'scorm') {
            setTimeout(async () => {
              try {
                const res = await fetch(`/api/spaces/${id}/items`);
                if (res.ok) {
                  const items: Array<{ id: string; content_item_id: string; content_title: string; content_type: string }> = await res.json();
                  const si = items.find(i => i.content_item_id === item.id);
                  if (si) setScormConfigItem({ spaceItemId: si.id, title: si.content_title ?? item.title ?? 'SCORM Package' });
                }
              } catch { /* non-fatal */ }
            }, 800);
          }
        }}
      />

      {/* C-09: Edit URL modal */}
      {editUrlItem && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border rounded-[var(--radius)] shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <p className="font-semibold text-primary">Update Content URL</p>
              <button onClick={() => setEditUrlItem(null)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 mb-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Title</label>
                <input
                  value={editTitleValue}
                  onChange={(e) => setEditTitleValue(e.target.value)}
                  placeholder="Content title"
                  className="mt-1 w-full px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Source URL</label>
                <input
                  value={editUrlValue}
                  onChange={(e) => setEditUrlValue(e.target.value)}
                  placeholder="https://youtube.com/watch?v=..."
                  className="mt-1 w-full px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-[var(--radius)] px-3 py-2">
                After saving, click Regenerate on this item to reprocess with the new URL.
              </p>
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setEditUrlItem(null)} className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] text-muted-foreground hover:bg-muted transition-colors">Cancel</button>
              <button
                onClick={saveContentUrl}
                disabled={!editUrlValue.trim() || isSavingUrl}
                className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                {isSavingUrl && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Save URL
              </button>
            </div>
          </div>
        </div>
      )}


      {/* Add Interactive Content modal */}
      {showICModal && (() => {
        // IDs already in this space — filter them out
        const alreadyInSpace = new Set((space?.items ?? []).map(i => i.content_item_id));
        const q = icSearch.toLowerCase();
        const filtered = icLibrary.filter(item => {
          if (alreadyInSpace.has(item.content_item_id)) return false;
          if (!q) return true;
          return (item.title || item.source_url || '').toLowerCase().includes(q) ||
                 item.content_type.toLowerCase().includes(q);
        });
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
            <div className="bg-card border border-border rounded-xl w-full max-w-lg p-6 shadow-xl">
              {/* Header */}
              <div className="flex items-start justify-between mb-4">
                <div>
                  <p className="font-semibold text-foreground">Add Interactive Content</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Pick from your IC library to add to this space.
                  </p>
                </div>
                <button onClick={() => { setShowICModal(false); setIcSearch(''); setIcSelected(''); }}
                  className="text-muted-foreground hover:text-foreground ml-4">
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Search */}
              {!icLoading && icLibrary.length > 0 && (
                <input
                  type="text"
                  value={icSearch}
                  onChange={e => setIcSearch(e.target.value)}
                  placeholder="Search by title or type…"
                  className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 mb-3 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
                />
              )}

              {icLoading ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading library…
                </div>
              ) : icLibrary.length === 0 ? (
                <div className="text-center py-8 text-sm text-muted-foreground">
                  No interactive content created yet.{' '}
                  <a href="/create/interactive" className="text-primary underline">Create some first →</a>
                </div>
              ) : filtered.length === 0 ? (
                <div className="text-center py-6 text-sm text-muted-foreground">
                  {q ? 'No matches. Try a different search.' : 'All library items are already in this space.'}
                </div>
              ) : (
                <div className="space-y-2 max-h-72 overflow-y-auto mb-4 pr-1">
                  {filtered.map(item => (
                    <label
                      key={item.content_item_id}
                      className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                        icSelected === item.content_item_id
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:bg-muted/50'
                      }`}
                    >
                      <input
                        type="radio"
                        name="ic-select"
                        value={item.content_item_id}
                        checked={icSelected === item.content_item_id}
                        onChange={() => setIcSelected(item.content_item_id)}
                        className="accent-primary shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {item.title || item.source_url || 'Untitled'}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${
                            item.content_type === 'youtube' ? 'bg-red-50 text-red-600 border-red-200' :
                            item.content_type === 'vimeo'   ? 'bg-blue-50 text-blue-600 border-blue-200' :
                                                              'bg-muted text-muted-foreground border-border'
                          }`}>
                            {item.content_type}
                          </span>
                          <span className="text-[10px] text-muted-foreground">
                            {item.interaction_count} interaction{item.interaction_count !== 1 ? 's' : ''}
                          </span>
                          {item.source_url && (
                            <span className="text-[10px] text-muted-foreground truncate max-w-[180px]">
                              {item.source_url}
                            </span>
                          )}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              )}

              <div className="flex gap-2 justify-end pt-2 border-t border-border">
                <button
                  onClick={() => { setShowICModal(false); setIcSearch(''); setIcSelected(''); }}
                  className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted text-foreground transition-colors"
                >
                  Cancel
                </button>
                <button
                  disabled={!icSelected || icAttaching}
                  onClick={async () => {
                    if (!icSelected) return;
                    setIcAttaching(true);
                    try {
                      const r = await fetch(`/api/spaces/${id}/items`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({ content_item_id: icSelected }),
                      });
                      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Failed');
                      toast.success('Interactive content added to space!');
                      setShowICModal(false);
                      setIcSearch('');
                      setIcSelected('');
                      queryClient.invalidateQueries({ queryKey: ['space', id] });
                    } catch (e: any) {
                      toast.error(e.message || 'Failed to add');
                    } finally { setIcAttaching(false); }
                  }}
                  className="flex items-center gap-2 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors disabled:opacity-50 font-medium"
                >
                  {icAttaching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Film className="w-4 h-4" />}
                  {icAttaching ? 'Adding…' : 'Add to Space'}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── Certificates (SpaceCertificatesSection) ──────────────────────── */}
      <SpaceCertificatesSection
        spaceId={id}
        itemCount={space?.items?.length ?? 0}
        isCreatorOrAdmin={true}
      />

      {/* ── Live Classes (Zoom) ───────────────────────────────────────────── */}
      <LiveClassesSection spaceId={id} />
      {showShare && (
        <ShareModal
          spaceId={id}
          onClose={() => setShowShare(false)}
          isGuestAccessible={space?.is_guest_accessible ?? false}
          onGuestAccessChange={() => queryClient.invalidateQueries({ queryKey: ['space', id] })}
        />
      )}

      {/* Remove item confirm */}
      {deleteItemId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-sm mx-4 p-6 shadow-lg">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0">
                <AlertCircle className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <p className="font-semibold text-primary">Remove content?</p>
                <p className="text-sm text-muted-foreground mt-1">
                  This removes the content from this space. The underlying content item is not deleted.
                </p>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setDeleteItemId(null)}
                className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm
                  text-muted-foreground hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => removeItemMutation.mutate(deleteItemId)}
                disabled={removeItemMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white
                  rounded-[var(--radius)] text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {removeItemMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Remove
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Gen settings modal */}
      {genSettingsItem && (
        <GenSettingsModal
          spaceId={id}
          contentItemId={genSettingsItem.contentItemId}
          spaceItemId={genSettingsItem.spaceItemId}
          contentTitle={genSettingsItem.title}
          initialVisibleOutputs={genSettingsItem.visibleOutputs}
          onClose={() => setGenSettingsItem(null)}
        />
      )}

      {showEditSpace && space && (
        <EditSpaceModal
          spaceId={id}
          currentTitle={space.title}
          currentDescription={space.description ?? ''}
          currentTags={space.tags}
          currentCoverImageUrl={space.cover_image_url ?? null}
          currentSlug={space.slug ?? ''}
          onClose={() => setShowEditSpace(false)}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ['space', id] })}
        />
      )}

      {/* Smart delete space modal */}
      {showDeleteSpaceModal && space && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-md mx-4 p-6 shadow-lg">
            {/* Header */}
            <div className="flex items-start gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0">
                <AlertCircle className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <p className="font-semibold text-foreground">Delete &ldquo;{space.title}&rdquo;?</p>
                <p className="text-sm text-muted-foreground mt-0.5">This cannot be undone.</p>
              </div>
            </div>

            {/* Loading preview */}
            {deletePreviewLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-3">
                <Loader2 className="w-4 h-4 animate-spin" />
                Checking content…
              </div>
            )}

            {/* Preview loaded — empty space */}
            {!deletePreviewLoading && deletePreview && deletePreview.total_items === 0 && (
              <p className="text-sm text-muted-foreground mb-4">
                This space has no content. It will be permanently removed.
              </p>
            )}

            {/* Preview loaded — has content */}
            {!deletePreviewLoading && deletePreview && deletePreview.total_items > 0 && (
              <div className="space-y-3 mb-4">
                {/* Shared items info */}
                {deletePreview.shared_items.length > 0 && (
                  <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-sm">
                    <p className="font-medium text-blue-800 mb-1">
                      {deletePreview.shared_items.length} item{deletePreview.shared_items.length !== 1 ? 's are' : ' is'} shared with other spaces
                    </p>
                    <p className="text-blue-700 text-xs mb-2">
                      These will stay in your content library — they won&apos;t be deleted.
                    </p>
                    <ul className="space-y-1">
                      {deletePreview.shared_items.slice(0, 3).map(item => (
                        <li key={item.id} className="text-xs text-blue-700 flex items-start gap-1">
                          <span className="mt-0.5">•</span>
                          <span>
                            <span className="font-medium">{item.title}</span>
                            {item.other_space_titles.length > 0 && (
                              <span className="text-blue-500"> — also in: {item.other_space_titles.slice(0,2).join(', ')}{item.other_space_titles.length > 2 ? ` +${item.other_space_titles.length - 2} more` : ''}</span>
                            )}
                          </span>
                        </li>
                      ))}
                      {deletePreview.shared_items.length > 3 && (
                        <li className="text-xs text-blue-500">+ {deletePreview.shared_items.length - 3} more shared items</li>
                      )}
                    </ul>
                  </div>
                )}

                {/* Exclusive items — ask user */}
                {deletePreview.exclusive_items.length > 0 && (
                  <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm">
                    <p className="font-medium text-red-800 mb-1">
                      {deletePreview.exclusive_items.length} item{deletePreview.exclusive_items.length !== 1 ? 's exist' : ' exists'} only in this space
                    </p>
                    <p className="text-red-700 text-xs mb-2">
                      Choose whether to permanently delete this content too.
                    </p>
                    <ul className="space-y-1">
                      {deletePreview.exclusive_items.slice(0, 3).map(item => (
                        <li key={item.id} className="text-xs text-red-700 flex items-center gap-1">
                          <span>•</span>
                          <span className="font-medium">{item.title}</span>
                          <span className="text-red-500">({item.content_type})</span>
                        </li>
                      ))}
                      {deletePreview.exclusive_items.length > 3 && (
                        <li className="text-xs text-red-500">+ {deletePreview.exclusive_items.length - 3} more items</li>
                      )}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-col gap-2">
              {/* Exclusive items — two action buttons */}
              {!deletePreviewLoading && deletePreview && deletePreview.exclusive_items.length > 0 && (
                <>
                  <button
                    onClick={() => { setShowDeleteSpaceModal(false); deleteSpaceMutation.mutate(true); }}
                    disabled={deleteSpaceMutation.isPending}
                    className="flex items-center justify-center gap-2 w-full px-4 py-2 bg-red-600 text-white
                      rounded-[var(--radius)] text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
                  >
                    {deleteSpaceMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                    Delete Space + Content ({deletePreview.exclusive_items.length} item{deletePreview.exclusive_items.length !== 1 ? 's' : ''})
                  </button>
                  <button
                    onClick={() => { setShowDeleteSpaceModal(false); deleteSpaceMutation.mutate(false); }}
                    disabled={deleteSpaceMutation.isPending}
                    className="flex items-center justify-center gap-2 w-full px-4 py-2 border border-red-300 text-red-700
                      rounded-[var(--radius)] text-sm font-medium hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    Delete Space Only
                  </button>
                  <button
                    onClick={() => setShowDeleteSpaceModal(false)}
                    className="w-full px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Cancel
                  </button>
                </>
              )}

              {/* No exclusive items (empty space OR only shared items) */}
              {!deletePreviewLoading && deletePreview && deletePreview.exclusive_items.length === 0 && (
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setShowDeleteSpaceModal(false)}
                    className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm
                      text-muted-foreground hover:bg-muted transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => { setShowDeleteSpaceModal(false); deleteSpaceMutation.mutate(false); }}
                    disabled={deleteSpaceMutation.isPending}
                    className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white
                      rounded-[var(--radius)] text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
                  >
                    {deleteSpaceMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                    Delete Space
                  </button>
                </div>
              )}

              {/* Fallback while loading or if preview failed */}
              {(deletePreviewLoading || !deletePreview) && !deleteSpaceMutation.isPending && (
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setShowDeleteSpaceModal(false)}
                    className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm
                      text-muted-foreground hover:bg-muted transition-colors"
                  >
                    Cancel
                  </button>
                  {!deletePreviewLoading && (
                    <button
                      onClick={() => { setShowDeleteSpaceModal(false); deleteSpaceMutation.mutate(false); }}
                      className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white
                        rounded-[var(--radius)] text-sm font-medium hover:bg-red-700 transition-colors"
                    >
                      Delete Space
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
