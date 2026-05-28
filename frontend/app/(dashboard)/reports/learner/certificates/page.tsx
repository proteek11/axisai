'use client';

import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { formatDate } from '@/lib/utils';
import { Award, Download, ExternalLink } from 'lucide-react';

interface CertRow {
  cert_id: string;
  space_title: string;
  issued_at: string;
  method: string;
  download_url: string | null;
}

interface LearnerCertsResponse {
  certificates: CertRow[];
  total: number;
}

function LearnerCertificatesReport() {
  const { data, isLoading, error } = useQuery<LearnerCertsResponse>({
    queryKey: ['reports', 'learner', 'certificates'],
    queryFn: () =>
      fetch('/api/reports/learner/certificates').then((r) => r.json()),
  });

  const rows = data?.certificates ?? [];

  function handleDownload(cert: CertRow) {
    if (cert.download_url) {
      window.open(cert.download_url, '_blank');
    }
  }

  return (
    <div>
      <Header
        title="My Certificates"
        subtitle="All certificates you have earned"
      />

      <div className="p-6">
        {isLoading && (
          <div className="animate-pulse grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...Array(3)].map((_, i) => <div key={i} className="h-36 bg-muted rounded-[var(--radius)]" />)}
          </div>
        )}

        {error && (
          <div className="enterprise-card text-center py-12 text-muted-foreground">
            Failed to load certificates.
          </div>
        )}

        {!isLoading && !error && rows.length === 0 && (
          <div className="enterprise-card text-center py-16">
            <Award className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-sm font-medium">No certificates yet</p>
            <p className="text-xs text-muted-foreground mt-1">Complete a space to earn your first certificate</p>
          </div>
        )}

        {rows.length > 0 && (
          <>
            <p className="text-xs text-muted-foreground mb-4">
              {rows.length} certificate{rows.length !== 1 ? 's' : ''} earned
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {rows.map((cert) => (
                <div key={cert.cert_id} className="enterprise-card flex flex-col gap-3">
                  {/* Certificate visual */}
                  <div className="w-full h-20 rounded-lg bg-gradient-to-br from-primary/10 to-primary/5 border border-primary/20 flex items-center justify-center">
                    <Award className="w-8 h-8 text-primary opacity-60" />
                  </div>

                  <div>
                    <p className="font-semibold text-sm">{cert.space_title}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Issued {formatDate(cert.issued_at)}
                    </p>
                    <span className="inline-flex mt-1.5 text-xs px-2 py-0.5 rounded-full border text-green-600 border-green-400 bg-green-50 capitalize">
                      {cert.method || 'auto'}
                    </span>
                  </div>

                  {cert.download_url && (
                    <button
                      onClick={() => handleDownload(cert)}
                      className="flex items-center justify-center gap-1.5 text-xs text-primary border border-primary/30 rounded-lg px-3 py-1.5 hover:bg-primary/5 transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download Certificate
                    </button>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function LearnerCertificatesPage() {
  return <LearnerCertificatesReport />;
}
