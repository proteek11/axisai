'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  Library, Plus, Search, Loader2, FileText, Youtube, Globe,
  Video, Trash2, AlertCircle, CheckCircle2, Clock, Loader,
  Upload, Link2, ChevronLeft, ChevronRight, X, Filter,
  Eye, EyeOff, Zap, BookOpen, ArrowRight, Pencil, Mic,
  Layers, Presentation, Package, FileArchive, RefreshCw,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';
const PAGE_SIZE = 30;

// ── Types ─────────────────────────────────────────────────────────────────────

interface LibraryItem {
  id: string;
  title: string | null;
  content_type: string;
  experience_mode: string;
  is_public: boolean;
  status: string;
  source_url: string | null;
  language: string;
  word_count: number | null;
  chunk_count: number;
  creator_id: string | null;
  creator_name: string | null;
  space_count: number;
  created_at: string;
  updated_at: string;
}

interface LibraryResponse {
  items: LibraryItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const CONTENT_TYPES = ['pdf', 'youtube', 'vimeo', 'video_upload', 'html_page', 'text', 'interactive_pdf', 'interactive_slides', 'scorm'];

const ALL_OUTPUTS = [
  { id: 'summary',     label: 'Summary' },
  { id: 'quiz',        label: 'Quiz' },
  { id: 'flashcards',  label: 'Flashcards' },
  { id: 'glossary',    label: 'Glossary' },
  { id: 'faq',         label: 'FAQ' },
  { id: 'infographic', label: 'Infographic' },
];

const DEFAULT_OUTPUTS = ['summary', 'quiz', 'flashcards', 'glossary'];

function typeIcon(ct: string, size = 'w-4 h-4') {
  if (ct === 'youtube' || ct === 'vimeo') return <Youtube className={cn(size)} />;
  if (ct === 'video_upload') return <Video className={cn(size)} />;
  if (ct === 'html_page') return <Globe className={cn(size)} />;
  if (ct === 'interactive_pdf') return <Layers className={cn(size)} />;
  if (ct === 'interactive_slides') return <Presentation className={cn(size)} />;
  if (ct === 'scorm') return <FileArchive className={cn(size)} />;
  return <FileText className={cn(size)} />;
}

function typeColor(ct: string): string {
  if (ct === 'pdf')                return 'text-red-700 bg-red-50 border-red-200';
  if (ct === 'youtube')            return 'text-red-700 bg-red-50 border-red-200';
  if (ct === 'vimeo')              return 'text-blue-700 bg-blue-50 border-blue-200';
  if (ct === 'video_upload')       return 'text-purple-700 bg-purple-50 border-purple-200';
  if (ct === 'html_page')          return 'text-teal-700 bg-teal-50 border-teal-200';
  if (ct === 'interactive_pdf')    return 'text-indigo-700 bg-indigo-50 border-indigo-200';
  if (ct === 'interactive_slides') return 'text-orange-700 bg-orange-50 border-orange-200';
  if (ct === 'scorm') return 'text-violet-700 bg-violet-50 border-violet-200';
  return 'text-muted-foreground bg-muted border-border';
}

function statusBadge(status: string) {
  switch (status) {
    case 'ready':
      return (
        <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border border-green-300 text-green-700 bg-green-50 font-medium">
          <CheckCircle2 className="w-3 h-3" /> Ready
        </span>
      );
    case 'failed':
      return (
        <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border border-red-300 text-red-700 bg-red-50 font-medium">
          <AlertCircle className="w-3 h-3" /> Failed
        </span>
      );
    case 'processing':
      return (
        <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border border-yellow-300 text-yellow-700 bg-yellow-50 font-medium">
          <Loader className="w-3 h-3 animate-spin" /> Processing
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border border-border text-muted-foreground bg-muted font-medium">
          <Clock className="w-3 h-3" /> {status}
        </span>
      );
  }
}

function fmtDate(ts: string): string {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// ── Add Content modal ─────────────────────────────────────────────────────────

interface AddModalProps {
  onClose: () => void;
  onAdded: () => void;
}

function AddContentModal({ onClose, onAdded }: AddModalProps) {
  const [mode, setMode] = useState<'file' | 'url'>('file');
  // file tab
  const [fileInputType, setFileInputType] = useState<'document' | 'video' | 'audio' | 'interactive_pdf' | 'interactive_slides' | 'scorm'>('document');
  const [file, setFile] = useState<File | null>(null);
  // url tab
  const [url, setUrl] = useState('');
  const [urlType, setUrlType] = useState('youtube');
  // shared
  const [title, setTitle] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [experienceMode, setExperienceMode] = useState<'standard' | 'interactive'>('standard');
  const [selectedOutputs, setSelectedOutputs] = useState<string[]>(DEFAULT_OUTPUTS);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const FILE_TYPE_CONFIG = {
    document:          { label: 'Document',        icon: FileText,    accept: '.pdf,.txt,.docx',       hint: 'PDF or text file' },
    video:             { label: 'Video',            icon: Video,       accept: '.mp4,.mov,.webm,.avi,.mkv', hint: 'MP4, MOV, WEBM, AVI' },
    audio:             { label: 'Audio',            icon: Mic,         accept: '.mp3,.wav,.m4a,.aac,.ogg', hint: 'MP3, WAV, M4A' },
    interactive_pdf:   { label: 'Interactive PDF',  icon: Layers,      accept: '.pdf',                  hint: 'PDF with annotations & quiz' },
    interactive_slides:{ label: 'Slides (PPTX)',    icon: Presentation,accept: '.pptx,.ppt',            hint: 'PowerPoint — slide-by-slide' },
    scorm:             { label: 'SCORM Package',  icon: Package,     accept: '.zip',                  hint: 'SCORM 1.2 or 2004 .zip package' },
  } as const;

  // Close on Escape
  const handleClose = useCallback(() => onClose(), [onClose]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') handleClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleClose]);

  const getContentType = (): string => {
    if (mode === 'url') return urlType;
    if (fileInputType === 'video') return 'video_upload';
    if (fileInputType === 'audio') return 'audio';
    if (fileInputType === 'interactive_pdf') return 'interactive_pdf';
    if (fileInputType === 'interactive_slides') return 'interactive_slides';
    if (fileInputType === 'scorm') return 'scorm';
    return file?.name.endsWith('.pdf') ? 'pdf' : 'text';
  };

  const toggleOutput = (id: string) => {
    setSelectedOutputs((prev) =>
      prev.includes(id) ? prev.filter((o) => o !== id) : [...prev, id]
    );
  };

  const handleFileTypeChange = (ft: 'document' | 'video' | 'audio' | 'interactive_pdf' | 'interactive_slides' | 'scorm') => {
    setFileInputType(ft);
    setFile(null);
  };

  const handleSubmit = async () => {
    if (mode === 'file' && !file) { toast.error('Select a file'); return; }
    if (mode === 'url' && !url.trim()) { toast.error('Enter a URL'); return; }
    if (selectedOutputs.length === 0) { toast.error('Select at least one AI output'); return; }

    setIsUploading(true);
    try {
      if (mode === 'file') {
        const fd = new FormData();
        fd.append('file', file!);
        fd.append('content_type', getContentType());
        if (title) fd.append('title', title);
        fd.append('is_public', String(isPublic));
        fd.append('generate_outputs', JSON.stringify(selectedOutputs));
        fd.append('experience_mode', experienceMode);

        // SCORM packages go through a dedicated upload endpoint
        const uploadUrl = fileInputType === 'scorm' ? '/api/library/scorm' : '/api/library/upload';
        const res = await fetch(uploadUrl, { method: 'POST', body: fd });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || err.detail || 'Upload failed');
        }
      } else {
        const res = await fetch('/api/library/upload-url', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_url: url.trim(),
            content_type: getContentType(),
            title: title || url.trim(),
            is_public: isPublic,
            generate_outputs: selectedOutputs,
            experience_mode: experienceMode,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || err.detail || 'Failed to add URL');
        }
      }

      toast.success('Content added — processing will begin shortly');
      onAdded();
      onClose();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-md shadow-lg max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <Library className="w-4 h-4 text-primary" />
            </div>
            <p className="font-semibold text-sm text-primary">Add to Library</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4 overflow-y-auto">
          {/* Mode tabs */}
          <div className="flex gap-1 p-1 bg-muted rounded-[var(--radius)]">
            {[
              { id: 'file', label: 'Upload File', icon: Upload },
              { id: 'url', label: 'Add URL', icon: Link2 },
            ].map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setMode(id as 'file' | 'url')}
                className={cn(
                  'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-[calc(var(--radius)-2px)] text-xs font-medium transition-colors',
                  mode === id
                    ? 'bg-background text-primary shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            ))}
          </div>

          {/* Title */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Title <span className="text-muted-foreground/60">(optional)</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Auto-detected if left blank"
              className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background
                text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>

          {mode === 'file' ? (
            <div className="space-y-3">
              {/* File type selector */}
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">Content Type</label>
                <div className="grid grid-cols-3 gap-2">
                  {(Object.keys(FILE_TYPE_CONFIG) as Array<keyof typeof FILE_TYPE_CONFIG>).map((ft) => {
                    const cfg = FILE_TYPE_CONFIG[ft];
                    const Icon = cfg.icon;
                    return (
                      <button
                        key={ft}
                        onClick={() => handleFileTypeChange(ft)}
                        className={cn(
                          'flex flex-col items-center gap-1 py-2.5 px-2 rounded-[var(--radius)] border text-xs font-medium transition-colors',
                          fileInputType === ft
                            ? 'border-primary bg-primary/5 text-primary'
                            : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground'
                        )}
                      >
                        <Icon className="w-4 h-4" />
                        {cfg.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Drop zone */}
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">File</label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className={cn(
                    'border-2 border-dashed rounded-[var(--radius)] p-6 text-center cursor-pointer transition-colors',
                    file
                      ? 'border-primary/40 bg-primary/5'
                      : 'border-border hover:border-primary/40 hover:bg-muted/50'
                  )}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={FILE_TYPE_CONFIG[fileInputType].accept}
                    className="hidden"
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  />
                  {file ? (
                    <div className="flex items-center justify-center gap-2">
                      <FileText className="w-4 h-4 text-primary" />
                      <span className="text-sm font-medium text-primary">{file.name}</span>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <Upload className="w-6 h-6 text-muted-foreground mx-auto" />
                      <p className="text-sm text-muted-foreground">
                        Click to select — {FILE_TYPE_CONFIG[fileInputType].hint}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">Content Type</label>
                <select
                  value={urlType}
                  onChange={(e) => setUrlType(e.target.value)}
                  className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background
                    text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                >
                  <option value="youtube">YouTube</option>
                  <option value="vimeo">Vimeo</option>
                  <option value="pdf">PDF URL</option>
                  <option value="html_page">Web Page</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">URL</label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://..."
                  className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background
                    text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
              </div>
            </div>
          )}

          {/* Experience Mode */}
          {(mode === 'file' && (fileInputType === 'document' || fileInputType === 'interactive_pdf')) && (
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">Experience Mode</label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { value: 'standard', label: 'Standard', desc: 'Tabs: Summary, Quiz, Flashcards…' },
                  { value: 'interactive', label: 'Interactive', desc: 'Quiz-first engagement flow' },
                ].map(({ value, label, desc }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setExperienceMode(value as 'standard' | 'interactive')}
                    className={cn(
                      'text-left p-3 rounded-[var(--radius)] border transition-colors',
                      experienceMode === value
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted'
                    )}
                  >
                    <p className={cn('text-xs font-semibold', experienceMode === value ? 'text-primary' : 'text-foreground')}>{label}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">{desc}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* AI Outputs */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-2">
              Generate AI Outputs
              {(fileInputType === 'interactive_pdf' || fileInputType === 'interactive_slides') && (
                <span className="ml-2 text-[10px] text-primary/70 font-normal">(quiz runs per slide/page)</span>
              )}
            </label>
            <div className="grid grid-cols-3 gap-2">
              {ALL_OUTPUTS.map(({ id, label }) => {
                const checked = selectedOutputs.includes(id);
                return (
                  <button
                    key={id}
                    onClick={() => toggleOutput(id)}
                    className={cn(
                      'flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--radius)] border text-xs font-medium transition-colors text-left',
                      checked
                        ? 'border-primary bg-primary/5 text-primary'
                        : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground'
                    )}
                  >
                    <span className={cn(
                      'w-3.5 h-3.5 rounded flex-shrink-0 border flex items-center justify-center',
                      checked ? 'bg-primary border-primary' : 'border-muted-foreground/40'
                    )}>
                      {checked && (
                        <svg className="w-2 h-2 text-white" viewBox="0 0 12 12" fill="none">
                          <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    {label}
                  </button>
                );
              })}
            </div>
            {selectedOutputs.length === 0 && (
              <p className="text-[11px] text-amber-600 mt-1.5">Select at least one output</p>
            )}
          </div>

          {/* Visibility toggle */}
          <div className="flex items-center justify-between p-3 rounded-[var(--radius)] bg-muted">
            <div>
              <p className="text-xs font-medium text-primary">Share with all creators</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {isPublic ? 'Visible to all creators in your organisation' : 'Only visible to you'}
              </p>
            </div>
            <button
              onClick={() => setIsPublic((v) => !v)}
              className={cn(
                'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
                isPublic ? 'bg-primary' : 'bg-muted-foreground/30'
              )}
            >
              <span
                className={cn(
                  'inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform',
                  isPublic ? 'translate-x-4' : 'translate-x-0.5'
                )}
              />
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-2 justify-end p-5 border-t border-border flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isUploading || selectedOutputs.length === 0}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            {isUploading ? 'Adding...' : 'Add Content'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Edit modal ────────────────────────────────────────────────────────────────

interface EditModalProps {
  item: LibraryItem;
  onClose: () => void;
  onUpdated: () => void;
}

// Determine which content tabs should be available for a given content type
const URL_TYPES = new Set(['youtube', 'vimeo', 'html_page', 'page', 'text']);
const FILE_TYPES = new Set(['pdf', 'video_upload', 'audio', 'interactive_pdf', 'interactive_slides']);

function EditModal({ item, onClose, onUpdated }: EditModalProps) {
  // Determine available tabs based on content type
  const isScorm = item.content_type === 'scorm';
  const isUrlType = URL_TYPES.has(item.content_type);
  const isFileType = FILE_TYPES.has(item.content_type);
  const hasReplaceTab = isScorm || isUrlType || isFileType;

  const [activeTab, setActiveTab] = useState<'details' | 'replace'>('details');

  // Details tab state
  const [title, setTitle] = useState(item.title ?? '');
  const [isPublic, setIsPublic] = useState(item.is_public);
  const [experienceMode, setExperienceMode] = useState(item.experience_mode ?? 'standard');
  const [isSaving, setIsSaving] = useState(false);

  // Replace tab state — file
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const replaceFileRef = useRef<HTMLInputElement>(null);
  const [isReplacing, setIsReplacing] = useState(false);
  const [replaceProgress, setReplaceProgress] = useState<string | null>(null);

  // Replace tab state — URL
  const [newUrl, setNewUrl] = useState(item.source_url ?? '');

  const handleSaveDetails = async () => {
    setIsSaving(true);
    try {
      const res = await fetch(`/api/library/${item.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title.trim() || null,
          is_public: isPublic,
          experience_mode: experienceMode,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || 'Update failed');
      }
      toast.success('Content updated');
      onUpdated();
      onClose();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleReplaceFile = async () => {
    if (!replaceFile) { toast.error('Select a file'); return; }
    setIsReplacing(true);
    setReplaceProgress('Uploading file…');
    try {
      const fd = new FormData();
      fd.append('file', replaceFile);
      const endpoint = isScorm ? `/api/library/${item.id}/replace-scorm` : `/api/library/${item.id}/replace-file`;
      const res = await fetch(endpoint, { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || 'Replace failed');
      }
      const data = await res.json();
      setReplaceProgress(isScorm ? 'SCORM package replaced ✓' : 'File replaced — re-processing queued ✓');
      toast.success(isScorm ? 'SCORM package replaced successfully' : 'File replaced — re-processing started');
      setTimeout(() => { onUpdated(); onClose(); }, 1200);
    } catch (err: any) {
      toast.error(err.message);
      setReplaceProgress(null);
    } finally {
      setIsReplacing(false);
    }
  };

  const handleChangeUrl = async () => {
    if (!newUrl.trim()) { toast.error('Enter a URL'); return; }
    setIsReplacing(true);
    setReplaceProgress('Updating URL and queuing re-ingestion…');
    try {
      const res = await fetch(`/api/library/${item.id}/change-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_url: newUrl.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || 'URL change failed');
      }
      setReplaceProgress('URL updated — re-ingestion queued ✓');
      toast.success('URL updated — re-ingestion started');
      setTimeout(() => { onUpdated(); onClose(); }, 1200);
    } catch (err: any) {
      toast.error(err.message);
      setReplaceProgress(null);
    } finally {
      setIsReplacing(false);
    }
  };

  const replaceAccept = isScorm ? '.zip' : isFileType
    ? (item.content_type === 'video_upload' ? '.mp4,.mov,.webm,.avi,.mkv'
      : item.content_type === 'audio' ? '.mp3,.wav,.m4a,.aac,.ogg'
      : '.pdf')
    : undefined;

  const replaceHint = isScorm ? 'SCORM 1.2 or 2004 .zip package'
    : item.content_type === 'video_upload' ? 'MP4, MOV, WEBM'
    : item.content_type === 'audio' ? 'MP3, WAV, M4A'
    : 'PDF file';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-md shadow-lg max-h-[90vh] flex flex-col">
        {/* Modal header */}
        <div className="flex items-center justify-between p-5 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <Pencil className="w-4 h-4 text-primary" />
            </div>
            <div>
              <p className="font-semibold text-sm text-primary">Edit Content</p>
              <p className="text-[11px] text-muted-foreground truncate max-w-[240px]">
                {item.title || 'Untitled'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        {hasReplaceTab && (
          <div className="flex gap-1 p-3 border-b border-border flex-shrink-0">
            <button
              onClick={() => setActiveTab('details')}
              className={cn(
                'flex-1 py-1.5 text-xs font-medium rounded-[calc(var(--radius)-2px)] transition-colors',
                activeTab === 'details' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              )}
            >
              Details
            </button>
            <button
              onClick={() => setActiveTab('replace')}
              className={cn(
                'flex-1 py-1.5 text-xs font-medium rounded-[calc(var(--radius)-2px)] transition-colors flex items-center justify-center gap-1',
                activeTab === 'replace' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              )}
            >
              <RefreshCw className="w-3 h-3" />
              {isUrlType ? 'Change URL' : isScorm ? 'Replace Package' : 'Replace File'}
            </button>
          </div>
        )}

        <div className="p-5 space-y-4 overflow-y-auto flex-1">
          {activeTab === 'details' ? (
            <>
              {/* Title */}
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">Title</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Content title"
                  className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background
                    text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
              </div>

              {/* Experience mode — only for file types */}
              {(isFileType || isScorm) && (
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">Experience Mode</label>
                  <select
                    value={experienceMode}
                    onChange={(e) => setExperienceMode(e.target.value)}
                    className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background
                      text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                  >
                    <option value="standard">Standard</option>
                    <option value="interactive">Interactive</option>
                  </select>
                </div>
              )}

              {/* Visibility toggle */}
              <div className="flex items-center justify-between p-3 rounded-[var(--radius)] bg-muted">
                <div>
                  <p className="text-xs font-medium text-primary">Share with all creators</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {isPublic ? 'Visible to all creators' : 'Only visible to you'}
                  </p>
                </div>
                <button
                  onClick={() => setIsPublic((v) => !v)}
                  className={cn(
                    'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
                    isPublic ? 'bg-primary' : 'bg-muted-foreground/30'
                  )}
                >
                  <span
                    className={cn(
                      'inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform',
                      isPublic ? 'translate-x-4' : 'translate-x-0.5'
                    )}
                  />
                </button>
              </div>
            </>
          ) : (
            /* Replace tab */
            <>
              {isUrlType ? (
                <div className="space-y-3">
                  <div className="p-3 rounded-[var(--radius)] bg-amber-50 border border-amber-200">
                    <p className="text-xs text-amber-800 font-medium">Re-ingestion warning</p>
                    <p className="text-xs text-amber-700 mt-0.5">
                      Changing the URL will delete all existing AI outputs and re-run the full ingestion pipeline. This may take a few minutes.
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">New URL</label>
                    <input
                      type="url"
                      value={newUrl}
                      onChange={(e) => setNewUrl(e.target.value)}
                      placeholder="https://..."
                      className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background
                        text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Current: {item.source_url || '—'}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {!isScorm && (
                    <div className="p-3 rounded-[var(--radius)] bg-amber-50 border border-amber-200">
                      <p className="text-xs text-amber-800 font-medium">Re-ingestion warning</p>
                      <p className="text-xs text-amber-700 mt-0.5">
                        Replacing the file will delete all existing AI outputs and re-run the full ingestion pipeline.
                      </p>
                    </div>
                  )}
                  {isScorm && (
                    <div className="p-3 rounded-[var(--radius)] bg-blue-50 border border-blue-200">
                      <p className="text-xs text-blue-800 font-medium">Learner history is preserved</p>
                      <p className="text-xs text-blue-700 mt-0.5">
                        Replacing the package updates the SCORM content while keeping all learner session history and scores intact.
                      </p>
                    </div>
                  )}
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                      {isScorm ? 'New SCORM Package (.zip)' : 'New File'}
                    </label>
                    <div
                      onClick={() => replaceFileRef.current?.click()}
                      className={cn(
                        'border-2 border-dashed rounded-[var(--radius)] p-5 text-center cursor-pointer transition-colors',
                        replaceFile
                          ? 'border-primary/40 bg-primary/5'
                          : 'border-border hover:border-primary/40 hover:bg-muted/50'
                      )}
                    >
                      <input
                        ref={replaceFileRef}
                        type="file"
                        accept={replaceAccept}
                        className="hidden"
                        onChange={(e) => setReplaceFile(e.target.files?.[0] ?? null)}
                      />
                      {replaceFile ? (
                        <div className="flex items-center justify-center gap-2">
                          <FileText className="w-4 h-4 text-primary" />
                          <span className="text-sm font-medium text-primary">{replaceFile.name}</span>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <Upload className="w-5 h-5 text-muted-foreground mx-auto" />
                          <p className="text-sm text-muted-foreground">Click to select — {replaceHint}</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {replaceProgress && (
                <div className="flex items-center gap-2 p-3 rounded-[var(--radius)] bg-primary/5 border border-primary/20">
                  {isReplacing
                    ? <Loader2 className="w-4 h-4 text-primary animate-spin flex-shrink-0" />
                    : <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0" />
                  }
                  <p className="text-xs text-primary">{replaceProgress}</p>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-2 justify-end p-5 border-t border-border flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          {activeTab === 'details' ? (
            <button
              onClick={handleSaveDetails}
              disabled={isSaving}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
                rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
              Save Changes
            </button>
          ) : (
            <button
              onClick={isUrlType ? handleChangeUrl : handleReplaceFile}
              disabled={isReplacing || (!isUrlType && !replaceFile) || (isUrlType && !newUrl.trim())}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
                rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {isReplacing
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Processing…</>
                : <><RefreshCw className="w-4 h-4" /> {isUrlType ? 'Update URL' : isScorm ? 'Replace Package' : 'Replace File'}</>
              }
            </button>
          )}
        </div>
      </div>
    </div>
  );
}


// ── Delete confirm modal ───────────────────────────────────────────────────────

interface DeleteModalProps {
  item: LibraryItem;
  onClose: () => void;
  onDeleted: () => void;
}

function DeleteModal({ item, onClose, onDeleted }: DeleteModalProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [blockMsg, setBlockMsg] = useState<string | null>(null);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      const res = await fetch(`/api/library/${item.id}`, { method: 'DELETE' });
      if (res.status === 204) {
        toast.success('Content deleted');
        onDeleted();
        onClose();
        return;
      }
      const err = await res.json().catch(() => ({}));
      if (res.status === 409 && err.error === 'content_attached_to_spaces') {
        const names = (err.spaces as string[]).join(', ');
        setBlockMsg(`This content is attached to: ${names}. Detach it from all spaces first.`);
      } else {
        throw new Error(err.detail || err.error || 'Delete failed');
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-sm shadow-lg p-6">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-9 h-9 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0">
            <AlertCircle className="w-5 h-5 text-red-600" />
          </div>
          <div>
            <p className="font-semibold text-primary text-sm">Delete "{item.title || 'Untitled'}"?</p>
            {blockMsg ? (
              <p className="text-sm text-red-600 mt-2">{blockMsg}</p>
            ) : (
              <p className="text-sm text-muted-foreground mt-1">
                This will permanently remove the content from your library. This cannot be undone.
              </p>
            )}
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors"
          >
            {blockMsg ? 'Close' : 'Cancel'}
          </button>
          {!blockMsg && (
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white
                rounded-[var(--radius)] text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
            >
              {isDeleting && <Loader2 className="w-4 h-4 animate-spin" />}
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function LibraryPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterVisibility, setFilterVisibility] = useState('');
  const [filterMode, setFilterMode] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<LibraryItem | null>(null);
  const [editTarget, setEditTarget] = useState<LibraryItem | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout>>();

  const queryKey = ['library', page, debouncedSearch, filterType, filterVisibility, filterMode];

  const { data, isLoading } = useQuery<LibraryResponse>({
    queryKey,
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (debouncedSearch) params.set('search', debouncedSearch);
      if (filterType) params.set('content_type', filterType);
      if (filterVisibility) params.set('visibility', filterVisibility);
      if (filterMode) params.set('experience_mode', filterMode);
      const res = await fetch(`/api/library?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to load library');
      return res.json();
    },
    placeholderData: (prev) => prev,
  });

  const handleSearch = (val: string) => {
    setSearch(val);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setDebouncedSearch(val);
      setPage(1);
    }, 350);
  };

  const handleFilterChange = () => setPage(1);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = data?.pages ?? 1;

  const activeFilters = [filterType, filterVisibility, filterMode].filter(Boolean).length;

  return (
    <div>
      <Header
        title="Content Library"
        subtitle="Your reusable content catalogue"
        action={
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
              rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Content
          </button>
        }
      />

      <div className="page-padding">
        {/* Search + filter bar */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder="Search library..."
              className="w-full pl-10 pr-4 py-2.5 rounded-[var(--radius)] border border-border bg-background
                text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <button
            onClick={() => setShowFilters((v) => !v)}
            className={cn(
              'flex items-center gap-2 px-3 py-2.5 rounded-[var(--radius)] border text-sm transition-colors',
              activeFilters > 0
                ? 'border-primary bg-primary/5 text-primary'
                : 'border-border text-muted-foreground hover:bg-muted'
            )}
          >
            <Filter className="w-4 h-4" />
            Filters
            {activeFilters > 0 && (
              <span className="w-4 h-4 rounded-full bg-primary text-primary-foreground text-[10px] flex items-center justify-center font-bold">
                {activeFilters}
              </span>
            )}
          </button>
        </div>

        {/* Filter row */}
        {showFilters && (
          <div className="flex flex-wrap gap-3 mb-4 p-4 bg-muted/50 rounded-[var(--radius)] border border-border">
            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Type</label>
              <select
                value={filterType}
                onChange={(e) => { setFilterType(e.target.value); handleFilterChange(); }}
                className="px-2.5 py-1.5 rounded-[var(--radius)] border border-border bg-background text-xs
                  focus:outline-none focus:ring-2 focus:ring-primary/30"
              >
                <option value="">All types</option>
                {CONTENT_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Visibility</label>
              <select
                value={filterVisibility}
                onChange={(e) => { setFilterVisibility(e.target.value); handleFilterChange(); }}
                className="px-2.5 py-1.5 rounded-[var(--radius)] border border-border bg-background text-xs
                  focus:outline-none focus:ring-2 focus:ring-primary/30"
              >
                <option value="">All</option>
                <option value="own">My content</option>
                <option value="public">Public</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Mode</label>
              <select
                value={filterMode}
                onChange={(e) => { setFilterMode(e.target.value); handleFilterChange(); }}
                className="px-2.5 py-1.5 rounded-[var(--radius)] border border-border bg-background text-xs
                  focus:outline-none focus:ring-2 focus:ring-primary/30"
              >
                <option value="">All modes</option>
                <option value="standard">Standard</option>
                <option value="interactive">Interactive</option>
              </select>
            </div>
            {activeFilters > 0 && (
              <div className="flex items-end">
                <button
                  onClick={() => {
                    setFilterType('');
                    setFilterVisibility('');
                    setFilterMode('');
                    setPage(1);
                  }}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
                >
                  <X className="w-3 h-3" /> Clear filters
                </button>
              </div>
            )}
          </div>
        )}

        {/* Stats row */}
        {total > 0 && (
          <p className="text-xs text-muted-foreground mb-4">
            {total} item{total !== 1 ? 's' : ''} in your library
          </p>
        )}

        {/* Content grid */}
        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
              <Library className="w-7 h-7 text-primary" />
            </div>
            <p className="font-semibold text-primary mb-1">
              {debouncedSearch || activeFilters ? 'No items match your filters' : 'Your library is empty'}
            </p>
            <p className="text-sm text-muted-foreground mb-4">
              {debouncedSearch || activeFilters
                ? 'Try adjusting your search or filters'
                : 'Add PDFs, videos, and web pages to reuse across all your spaces'}
            </p>
            {!debouncedSearch && !activeFilters && (
              <button
                onClick={() => setShowAddModal(true)}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground
                  rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Your First Content
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {items.map((item) => (
                <LibraryCard
                  key={item.id}
                  item={item}
                  onDelete={() => setDeleteTarget(item)}
                  onEdit={() => setEditTarget(item)}
                  onUpdated={() => queryClient.invalidateQueries({ queryKey: ['library'] })}
                />
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-6 pt-4 border-t border-border">
                <p className="text-sm text-muted-foreground">
                  Page {page} of {totalPages} · {total} items
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="p-1.5 border border-border rounded-[var(--radius)] hover:bg-muted disabled:opacity-40 transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <span className="text-sm text-muted-foreground px-1">{page} / {totalPages}</span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="p-1.5 border border-border rounded-[var(--radius)] hover:bg-muted disabled:opacity-40 transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Modals */}
      {showAddModal && (
        <AddContentModal
          onClose={() => setShowAddModal(false)}
          onAdded={() => queryClient.invalidateQueries({ queryKey: ['library'] })}
        />
      )}
      {deleteTarget && (
        <DeleteModal
          item={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => queryClient.invalidateQueries({ queryKey: ['library'] })}
        />
      )}
      {editTarget && (
        <EditModal
          item={editTarget}
          onClose={() => setEditTarget(null)}
          onUpdated={() => queryClient.invalidateQueries({ queryKey: ['library'] })}
        />
      )}
    </div>
  );
}

// ── Library Card ──────────────────────────────────────────────────────────────

interface LibraryCardProps {
  item: LibraryItem;
  onDelete: () => void;
  onEdit: () => void;
  onUpdated: () => void;
}

function LibraryCard({ item, onDelete, onEdit, onUpdated }: LibraryCardProps) {
  const [isTogglingVisibility, setIsTogglingVisibility] = useState(false);

  const toggleVisibility = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsTogglingVisibility(true);
    try {
      const res = await fetch(`/api/library/${item.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_public: !item.is_public }),
      });
      if (!res.ok) throw new Error('Update failed');
      toast.success(item.is_public ? 'Set to private' : 'Shared with all creators');
      onUpdated();
    } catch {
      toast.error('Failed to update visibility');
    } finally {
      setIsTogglingVisibility(false);
    }
  };

  return (
    <div className="enterprise-card hover:bg-muted/30 transition-colors group p-4 flex flex-col">
      {/* Top row */}
      <div className="flex items-start justify-between gap-2 mb-3">
        {/* Type icon */}
        <div className={cn(
          'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 border',
          typeColor(item.content_type)
        )}>
          {typeIcon(item.content_type)}
        </div>

        {/* Status + mode badges */}
        <div className="flex flex-wrap items-center gap-1.5 justify-end">
          {statusBadge(item.status)}
          {item.experience_mode === 'interactive' && (
            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border border-purple-300 text-purple-700 bg-purple-50 font-medium">
              <Zap className="w-3 h-3" /> Interactive
            </span>
          )}
        </div>
      </div>

      {/* Title */}
      <p className="font-semibold text-sm text-primary leading-snug mb-1 line-clamp-2">
        {item.title || 'Untitled'}
      </p>

      {/* Type label + creator */}
      <div className="flex items-center gap-2 mb-3">
        <span className={cn(
          'text-[11px] px-2 py-0.5 rounded-full border font-medium',
          typeColor(item.content_type)
        )}>
          {item.content_type}
        </span>
        {item.creator_name && (
          <span className="text-[11px] text-muted-foreground truncate">by {item.creator_name}</span>
        )}
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-3 text-[11px] text-muted-foreground mb-3">
        {item.space_count > 0 && (
          <span className="flex items-center gap-1">
            <BookOpen className="w-3 h-3" />
            {item.space_count} space{item.space_count !== 1 ? 's' : ''}
          </span>
        )}
        {item.word_count != null && (
          <span>{item.word_count.toLocaleString()} words</span>
        )}
        <span className="ml-auto">{fmtDate(item.created_at)}</span>
      </div>

      {/* Visibility row */}
      <div className="flex items-center gap-1.5 text-[11px] mb-3">
        {item.is_public ? (
          <span className="flex items-center gap-1 text-teal-600">
            <Eye className="w-3 h-3" /> Shared with creators
          </span>
        ) : (
          <span className="flex items-center gap-1 text-muted-foreground">
            <EyeOff className="w-3 h-3" /> Private
          </span>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />
      <div className="border-t border-border mb-2.5" />

      {/* Actions */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {/* Edit */}
          <button
            onClick={(e) => { e.preventDefault(); onEdit(); }}
            title="Edit content"
            className="p-1.5 rounded-lg border border-border text-muted-foreground
              hover:text-primary hover:bg-muted transition-colors"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>

          {/* Toggle visibility */}
          <button
            onClick={toggleVisibility}
            disabled={isTogglingVisibility}
            title={item.is_public ? 'Make private' : 'Share with creators'}
            className="p-1.5 rounded-lg border border-border text-muted-foreground
              hover:text-primary hover:bg-muted transition-colors disabled:opacity-50"
          >
            {isTogglingVisibility
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : item.is_public
                ? <EyeOff className="w-3.5 h-3.5" />
                : <Eye className="w-3.5 h-3.5" />
            }
          </button>

          {/* Delete — hover only */}
          <button
            onClick={(e) => { e.preventDefault(); onDelete(); }}
            title="Delete content"
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg
              text-muted-foreground hover:text-red-600 hover:bg-red-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Open detail */}
        <Link
          href={`/library/${item.id}`}
          className="flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
        >
          Open <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
}
