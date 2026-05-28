'use client';

import { useState } from 'react';
import { ExternalLink, Download, Loader2 } from 'lucide-react';

interface StudyInfographicProps { html: string }

type Html2CanvasFn = (el: HTMLElement, opts?: object) => Promise<HTMLCanvasElement>;

declare global {
  interface Window {
    html2canvas?: Html2CanvasFn;
  }
}

async function loadHtml2Canvas(): Promise<Html2CanvasFn | undefined> {
  if (window.html2canvas) return window.html2canvas;
  return new Promise<Html2CanvasFn | undefined>((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
    s.onload = () => resolve(window.html2canvas);
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

export function StudyInfographic({ html }: StudyInfographicProps) {
  const [downloading, setDownloading] = useState(false);

  const openFull = () => {
    const win = window.open('', '_blank');
    if (win) { win.document.write(html); win.document.close(); }
  };

  const downloadPNG = async () => {
    setDownloading(true);
    try {
      const h2c = await loadHtml2Canvas();
      if (!h2c) throw new Error('unavailable');
      const container = document.createElement('div');
      container.innerHTML = html;
      container.style.cssText = 'position:fixed;left:-9999px;top:0;width:1100px;background:#fff;';
      document.body.appendChild(container);
      await new Promise((r) => setTimeout(r, 150));
      const canvas = await h2c(container, { useCORS: true, scale: 2, width: 1100, backgroundColor: '#ffffff' });
      document.body.removeChild(container);
      const link = document.createElement('a');
      link.download = 'infographic.png';
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch {
      openFull();
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="section-label">Infographic</p>
        <div className="flex gap-2">
          <button
            onClick={downloadPNG}
            disabled={downloading}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[var(--radius)]
              text-xs font-medium text-muted-foreground hover:bg-muted transition-colors disabled:opacity-50"
          >
            {downloading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
            {downloading ? 'Saving…' : 'Download PNG'}
          </button>
          <button
            onClick={openFull}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-[var(--radius)]
              text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            Full Screen
          </button>
        </div>
      </div>
      <div className="border border-border rounded-[var(--radius)] overflow-hidden bg-white">
        <iframe
          srcDoc={html}
          className="w-full"
          style={{ height: '700px', border: 'none' }}
          title="Infographic"
          sandbox="allow-scripts allow-same-origin"
        />
      </div>
    </div>
  );
}
