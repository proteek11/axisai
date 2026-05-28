'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { Award, Download, Loader2, FileX2, Calendar, BookOpen } from 'lucide-react';
import { cn } from '@/lib/utils';

interface IssuedCertificate {
  certificate_id: string;
  space_id: string;
  space_title: string;
  issued_at: string;
  download_url: string;
  cert_title?: string;
}

export default function MyCertificatesPage() {
  const [downloading, setDownloading] = useState<string | null>(null);

  const { data: certs = [], isLoading, isError } = useQuery<IssuedCertificate[]>({
    queryKey: ['my-certificates'],
    queryFn: async () => {
      const res = await fetch('/api/my/certificates');
      if (!res.ok) throw new Error('Failed to load certificates');
      return res.json();
    },
  });

  const handleDownload = async (cert: IssuedCertificate) => {
    setDownloading(cert.certificate_id);
    try {
      // The download_url from backend is a relative path like /api/v1/spaces/{id}/certificate
      // We proxy it through Next.js
      const spaceId = cert.space_id;
      const res = await fetch(`/api/spaces/${spaceId}/certificate`);
      if (!res.ok) throw new Error('Download failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${cert.space_title.replace(/[^a-z0-9]/gi, '_')}_certificate.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Certificate download failed', e);
    } finally {
      setDownloading(null);
    }
  };

  const formatDate = (iso: string) => {
    return new Date(iso).toLocaleDateString('en-US', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  };

  return (
    <div className="flex flex-col min-h-screen">
      <Header
        title="My Certificates"
        subtitle="Download your earned certificates"
      />

      <div className="flex-1 p-6 max-w-5xl mx-auto w-full">
        {isLoading && (
          <div className="flex items-center justify-center py-24 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" />
            <span>Loading your certificates…</span>
          </div>
        )}

        {isError && (
          <div className="flex flex-col items-center justify-center py-24 text-muted-foreground gap-3">
            <FileX2 className="w-10 h-10 text-destructive/60" />
            <p className="text-sm">Could not load certificates. Please try again.</p>
          </div>
        )}

        {!isLoading && !isError && certs.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
              <Award className="w-8 h-8 text-primary/60" />
            </div>
            <div>
              <p className="font-semibold text-foreground">No certificates yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Complete a learning space to earn your first certificate.
              </p>
            </div>
          </div>
        )}

        {!isLoading && certs.length > 0 && (
          <>
            {/* Summary bar */}
            <div className="mb-6 flex items-center gap-2 text-sm text-muted-foreground">
              <Award className="w-4 h-4 text-primary" />
              <span>
                You have earned{' '}
                <span className="font-semibold text-foreground">{certs.length}</span>{' '}
                {certs.length === 1 ? 'certificate' : 'certificates'}
              </span>
            </div>

            {/* Certificate cards grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {certs.map((cert) => (
                <div
                  key={cert.certificate_id}
                  className="group border border-border rounded-[var(--radius)] bg-card p-5 flex flex-col gap-3 hover:border-primary/30 transition-colors"
                >
                  {/* Icon strip */}
                  <div className="flex items-start justify-between">
                    <div className="w-10 h-10 rounded-full bg-amber-500/10 flex items-center justify-center flex-shrink-0">
                      <Award className="w-5 h-5 text-amber-500" />
                    </div>
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-green-600 bg-green-50 px-2 py-0.5 rounded-full border border-green-200">
                      Earned
                    </span>
                  </div>

                  {/* Space title */}
                  <div className="flex-1">
                    <p className="font-semibold text-sm text-foreground line-clamp-2 leading-tight">
                      {cert.cert_title || cert.space_title}
                    </p>
                    {cert.cert_title && (
                      <p className="flex items-center gap-1 text-[11px] text-muted-foreground mt-1">
                        <BookOpen className="w-3 h-3 flex-shrink-0" />
                        {cert.space_title}
                      </p>
                    )}
                  </div>

                  {/* Issued date */}
                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <Calendar className="w-3 h-3 flex-shrink-0" />
                    <span>Issued {formatDate(cert.issued_at)}</span>
                  </div>

                  {/* Download button */}
                  <button
                    onClick={() => handleDownload(cert)}
                    disabled={downloading === cert.certificate_id}
                    className={cn(
                      'w-full flex items-center justify-center gap-2 px-3 py-2 rounded-[var(--radius)]',
                      'text-xs font-medium border border-border transition-colors',
                      'hover:bg-primary hover:text-primary-foreground hover:border-primary',
                      downloading === cert.certificate_id && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    {downloading === cert.certificate_id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Download className="w-3.5 h-3.5" />
                    )}
                    {downloading === cert.certificate_id ? 'Downloading…' : 'Download PDF'}
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
