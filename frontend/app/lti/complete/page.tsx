'use client';

/**
 * /lti/complete
 * Receives ?ott=<one-time-token>&to=<redirect-path> from the LTI backend.
 * Exchanges the OTT for axis JWT cookies, then redirects the learner to their space.
 *
 * useSearchParams() must be inside a <Suspense> boundary in Next.js 14 App Router.
 */
import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Zap, Loader2, AlertCircle } from 'lucide-react';

function SpinnerUI() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#f8f6f8]">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 rounded-full bg-[#dbeafe] flex items-center justify-center">
          <Zap className="w-6 h-6 text-[#1447e6]" />
        </div>
        <div className="flex items-center gap-2 text-[#79697b] text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Signing you in from your LMS…</span>
        </div>
      </div>
    </div>
  );
}

function LTICompleteInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ott = searchParams.get('ott');
    const to  = searchParams.get('to') || '/learn';

    // Validate redirect target to prevent open-redirect
    const safeRedirects = ['/learn', '/dashboard', '/courses', '/'];
    const safeTo = safeRedirects.some(p => to.startsWith(p)) ? to : '/learn';

    if (!ott) {
      setError('Missing launch token. Please try again from your LMS.');
      return;
    }

    (async () => {
      try {
        const res = await fetch('/api/auth/lti-exchange', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ott }),
        });

        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          setError(data.detail || 'Launch failed. The session link may have expired — please retry from your LMS.');
          return;
        }

        // Cookies are set by the server route — redirect now
        router.replace(safeTo);
      } catch {
        setError('Network error. Please check your connection and retry.');
      }
    })();
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f8f6f8]">
        <div className="bg-white border border-[#e7e4e7] rounded-2xl p-8 max-w-sm w-full text-center shadow-sm">
          <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
            <AlertCircle className="w-6 h-6 text-red-500" />
          </div>
          <h1 className="text-base font-bold text-[#0c090c] mb-2">Launch failed</h1>
          <p className="text-sm text-[#79697b] mb-6">{error}</p>
          <a
            href="/login"
            className="inline-block px-4 py-2 bg-[#1447e6] text-white text-sm font-semibold rounded-xl hover:bg-[#0f3bcc] transition-colors"
          >
            Sign in manually
          </a>
        </div>
      </div>
    );
  }

  return <SpinnerUI />;
}

export default function LTICompletePage() {
  return (
    <Suspense fallback={<SpinnerUI />}>
      <LTICompleteInner />
    </Suspense>
  );
}
