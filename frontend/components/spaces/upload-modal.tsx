'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  X, FileText, Youtube, Video, Link as LinkIcon, Globe,
  Upload, Loader2, CheckCircle2, AlertCircle, ChevronDown
} from 'lucide-react';

type ContentType = 'pdf' | 'youtube' | 'vimeo' | 'video_upload' | 'text' | 'page';

interface UploadModalProps {
  spaceId: string;
  onClose: () => void;
  onSuccess: (contentId: string, jobId?: string) => void;
}

const CONTENT_TYPES: Array<{ type: ContentType; label: string; icon: React.ElementType; color: string; bg: string; desc: string }> = [
  { type: 'pdf',          label: 'PDF / Text',    icon: FileText,  color: 'text-orange-600', bg: 'bg-orange-50', desc: 'Upload a PDF or plain text file' },
  { type: 'youtube',      label: 'YouTube',        icon: Youtube,   color: 'text-red-600',    bg: 'bg-red-50',    desc: 'Process a YouTube video' },
  { type: 'vimeo',        label: 'Vimeo',          icon: Video,     color: 'text-blue-600',   bg: 'bg-blue-50',   desc: 'Process a Vimeo video' },
  { type: 'video_upload', label: 'Local Video',    icon: Upload,    color: 'text-purple-600', bg: 'bg-purple-50', desc: 'Upload an MP4/MOV video file' },
  { type: 'page',         label: 'Web URL',        icon: Globe,     color: 'text-teal-600',   bg: 'bg-teal-50',   desc: 'Extract content from any web page' },
];

const AI_OUTPUTS = [
  { key: 'summary',     label: 'Summary'     },
  { key: 'quiz',        label: 'Quiz'        },
  { key: 'flashcards',  label: 'Flashcards'  },
  { key: 'glossary',    label: 'Glossary'    },
  { key: 'faq',         label: 'FAQ'         },
  { key: 'infographic', label: 'Infographic' },
];

const DEFAULT_OUTPUTS = ['summary', 'quiz', 'flashcards', 'glossary', 'faq'];

export function UploadModal({ spaceId, onClose, onSuccess }: UploadModalProps) {
  const [contentType, setContentType] = useState<ContentType>('pdf');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [selectedOutputs, setSelectedOutputs] = useState<string[]>(DEFAULT_OUTPUTS);
  const [experienceMode, setExperienceMode] = useState<'standard' | 'interactive'>('standard');
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const toggleOutput = (key: string) => {
    setSelectedOutputs((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  // Allowed MIME types and extensions per content type
  const ALLOWED: Record<string, { mimes: string[]; exts: string[] }> = {
    pdf:          { mimes: ['application/pdf', 'text/plain'], exts: ['.pdf', '.txt'] },
    video_upload: {
      mimes: ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska'],
      exts: ['.mp4', '.mov', '.avi', '.mkv'],
    },
  };

  const [uploadLimitMb, setUploadLimitMb] = useState<number>(100);

  // Fetch the admin-set upload limit on mount
  useEffect(() => {
    fetch('/api/admin/upload-limit')
      .then((r) => r.json())
      .then((d) => { if (d.max_upload_size_mb) setUploadLimitMb(d.max_upload_size_mb); })
      .catch(() => {/* use default */});
  }, []);

  const validateFile = (f: File): string | null => {
    const rules = ALLOWED[contentType];
    if (!rules) return null; // no file needed for this type
    const ext = '.' + (f.name.split('.').pop() ?? '').toLowerCase();
    if (!rules.exts.includes(ext) && !rules.mimes.includes(f.type)) {
      return `Invalid file type. Allowed: ${rules.exts.join(', ')}`;
    }
    const maxMb = uploadLimitMb;
    if (f.size > maxMb * 1024 * 1024) {
      return `File too large. Maximum allowed is ${maxMb} MB (set by your admin).`;
    }
    return null;
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) {
      const err = validateFile(dropped);
      if (err) { setFileError(err); return; }
      setFileError(null);
      setFile(dropped);
    }
  }, [contentType, uploadLimitMb]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      const err = validateFile(f);
      if (err) { setFileError(err); return; }
      setFileError(null);
      setFile(f);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      let response: any;

      if (contentType === 'pdf' || contentType === 'video_upload') {
        if (!file) { toast.error('Please select a file'); setIsSubmitting(false); return; }

        // Auto-detect .txt uploads — backend also detects, but be explicit
        const fileExt = (file.name.split('.').pop() ?? '').toLowerCase();
        const resolvedContentType =
          contentType === 'pdf' && fileExt === 'txt' ? 'text'
          : contentType === 'pdf' ? 'pdf'
          : 'video_upload';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('content_type', resolvedContentType);
        if (title) formData.append('title', title);
        formData.append('generate_outputs', JSON.stringify(selectedOutputs));
        formData.append('experience_mode', experienceMode);

        const res = await fetch(`/api/spaces/${spaceId}/upload`, { method: 'POST', body: formData });
        if (!res.ok) {
          // Safely parse error — Nginx 413 returns HTML, not JSON
          const ct = res.headers.get('content-type') ?? '';
          if (ct.includes('application/json')) {
            const d = await res.json();
            throw new Error(d.error || `Upload failed (${res.status})`);
          } else if (res.status === 413) {
            throw new Error('File too large — the server rejected the upload. Please contact your admin to increase the upload size limit.');
          } else {
            throw new Error(`Upload failed (HTTP ${res.status}). Check your connection and try again.`);
          }
        }
        response = await res.json();
      } else {
        // URL-based (youtube, vimeo, vimeo showcase)
        if (!url.trim()) { toast.error('Please enter a URL'); setIsSubmitting(false); return; }

        // Vimeo showcase URLs (vimeo.com/showcase/...) share the 'vimeo' content_type —
        // the backend detects the showcase pattern and routes to yt-dlp automatically.
        // 'page' is the frontend label; backend expects 'html_page' for web URL content.
        const resolvedUrlContentType = contentType === 'page' ? 'html_page' : contentType;

        const res = await fetch('/api/content/ingest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content_type: resolvedUrlContentType,
            source_url: url.trim(),
            title: title || undefined,
            generate_outputs: selectedOutputs,
            experience_mode: experienceMode,
            space_id: spaceId,
          }),
        });
        if (!res.ok) { const d = await res.json(); throw new Error(d.error || 'Ingest failed'); }
        response = await res.json();
      }

      toast.success('Content submitted — processing started');
      onSuccess(response.content_item_id, response.job_id);
    } catch (err: any) {
      toast.error(err.message || 'Failed to submit content');
    } finally {
      setIsSubmitting(false);
    }
  };

  const needsFile = contentType === 'pdf' || contentType === 'video_upload';
  const needsUrl  = contentType === 'youtube' || contentType === 'vimeo' || contentType === 'page';
  const acceptAttr = contentType === 'pdf' ? '.pdf,.txt' : '.mp4,.mov,.avi,.mkv';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-xl max-h-[90vh] overflow-y-auto shadow-lg">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-card">
          <div>
            <h2 className="font-semibold text-primary">Add Content</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Upload or link content to this learning space</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* Content type selector */}
          <div>
            <label className="section-label block mb-2">Content Type</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {CONTENT_TYPES.map((ct) => {
                const Icon = ct.icon;
                return (
                  <button
                    key={ct.type}
                    type="button"
                    onClick={() => { setContentType(ct.type); setFile(null); setUrl(''); }}
                    className={cn(
                      'flex flex-col items-center gap-2 p-3 rounded-[var(--radius)] border text-center transition-colors',
                      contentType === ct.type
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted'
                    )}
                  >
                    <div className={cn('w-8 h-8 rounded-full flex items-center justify-center', ct.bg)}>
                      <Icon className={cn('w-4 h-4', ct.color)} />
                    </div>
                    <span className={cn(
                      'text-xs font-medium',
                      contentType === ct.type ? 'text-primary' : 'text-muted-foreground'
                    )}>
                      {ct.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* File drop zone or URL input */}
          {needsFile ? (
            <div>
              <label className="section-label block mb-2">File</label>
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileRef.current?.click()}
                className={cn(
                  'border-2 border-dashed rounded-[var(--radius)] p-8 text-center cursor-pointer transition-colors',
                  isDragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50 hover:bg-muted/30',
                  file ? 'bg-green-50 border-green-400' : ''
                )}
              >
                <input
                  ref={fileRef}
                  type="file"
                  accept={acceptAttr}
                  onChange={handleFileChange}
                  className="hidden"
                />
                {file ? (
                  <div className="flex flex-col items-center gap-2">
                    <CheckCircle2 className="w-8 h-8 text-green-600" />
                    <p className="font-medium text-sm text-green-700">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(file.size / (1024 * 1024)).toFixed(2)} MB
                    </p>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); setFile(null); setFileError(null); }}
                      className="text-xs text-muted-foreground underline hover:text-foreground"
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <Upload className="w-8 h-8" />
                    <p className="text-sm font-medium">Drop file here or click to browse</p>
                    <p className="text-xs">{contentType === 'pdf' ? 'PDF or TXT' : 'MP4, MOV, AVI, MKV'} · Max {uploadLimitMb} MB</p>
                  </div>
                )}
              </div>
              {fileError && (
                <p className="mt-2 text-xs text-red-600">{fileError}</p>
              )}
            </div>
          ) : (
            <div>
              <label className="section-label block mb-2">
                {contentType === 'youtube' ? 'YouTube URL' : contentType === 'vimeo' ? 'Vimeo URL' : 'Web Page URL'}
              </label>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder={contentType === 'youtube'
                  ? 'https://www.youtube.com/watch?v=...'
                  : contentType === 'vimeo'
                    ? 'https://vimeo.com/VIDEO_ID  or  vimeo.com/showcase/...'
                    : 'https://example.com/article-url'
                }
                className="w-full px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background
                  text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>
          )}

          {/* Title override */}
          <div>
            <label className="section-label block mb-1.5">
              Title <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Custom title for this content..."
              className="w-full px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background
                text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>

          {/* Experience Mode — only meaningful for document content */}
          {(contentType === 'pdf') && (
            <div>
              <label className="section-label block mb-1.5">Experience Mode</label>
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
            <label className="section-label block mb-2">Generate AI Outputs</label>
            <div className="flex flex-wrap gap-2">
              {AI_OUTPUTS.map((o) => (
                <button
                  key={o.key}
                  type="button"
                  onClick={() => toggleOutput(o.key)}
                  className={cn(
                    'text-xs px-3 py-1.5 rounded-full border font-medium transition-colors',
                    selectedOutputs.includes(o.key)
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border text-muted-foreground hover:bg-muted'
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
            {selectedOutputs.length === 0 && (
              <p className="text-xs text-orange-600 mt-2 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" />
                Select at least one AI output type
              </p>
            )}
          </div>

          {/* Submit */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm
                font-medium text-muted-foreground hover:bg-muted transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || selectedOutputs.length === 0}
              className="flex items-center gap-2 px-5 py-2 bg-primary text-primary-foreground
                rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  Upload & Process
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
