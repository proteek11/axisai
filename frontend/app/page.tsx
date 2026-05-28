import Link from 'next/link';
import { LandingNavClient } from '@/components/landing/landing-nav-client';

export const metadata = {
  title: 'Axis AI — Intelligent Learning, for Every Platform',
  description:
    'Axis AI transforms any learning content into summaries, quizzes, flashcards, and RAG-powered chat — standalone or integrated with your LMS.',
};

export default function LandingPage() {
  return (
    <>
      <style>{`
        .lp *, .lp *::before, .lp *::after { box-sizing: border-box; }
        .lp {
          --lp-blue: #1447e6;
          --lp-blue-light: #eff4ff;
          --lp-blue-border: #c7d9ff;
          --lp-bg: #ffffff;
          --lp-bg-muted: #f8f6f8;
          --lp-text: #0c090c;
          --lp-text-muted: #79697b;
          --lp-border: #e7e4e7;
          --lp-radius: 14px;
          --lp-radius-sm: 8px;
          font-family: 'Instrument Sans', system-ui, sans-serif;
          background: var(--lp-bg);
          color: var(--lp-text);
          font-size: 15px;
          line-height: 1.6;
          -webkit-font-smoothing: antialiased;
        }
        .lp a { color: inherit; text-decoration: none; }
        .lp button { font-family: inherit; cursor: pointer; border: none; outline: none; }

        /* NAV */
        .lp-nav {
          position: sticky; top: 0; z-index: 100;
          background: rgba(255,255,255,0.92);
          backdrop-filter: blur(12px);
          border-bottom: 1px solid var(--lp-border);
        }
        .lp-nav-inner {
          display: flex; align-items: center; justify-content: space-between;
          padding: 14px 40px; max-width: 1120px; margin: 0 auto;
        }
        .lp-logo { display: flex; align-items: center; gap: 9px; font-size: 16px; font-weight: 600; color: var(--lp-text); }
        .lp-logo-mark { width: 30px; height: 30px; background: var(--lp-blue); border-radius: 8px; display: flex; align-items: center; justify-content: center; }
        .lp-nav-links { display: flex; align-items: center; gap: 28px; }
        .lp-nav-links a { font-size: 14px; color: var(--lp-text-muted); transition: color 0.15s; }
        .lp-nav-links a:hover { color: var(--lp-text); }
        .lp-nav-actions { display: flex; align-items: center; gap: 10px; }
        .lp-btn-ghost-sm {
          font-size: 14px; color: var(--lp-text); background: transparent;
          border: 1px solid var(--lp-border); border-radius: var(--lp-radius-sm);
          padding: 8px 16px; transition: border-color 0.15s;
        }
        .lp-btn-ghost-sm:hover { border-color: var(--lp-text-muted); }
        .lp-btn-primary-sm {
          font-size: 14px; font-weight: 500; color: #fff; background: var(--lp-blue);
          border-radius: var(--lp-radius-sm); padding: 8px 18px; transition: opacity 0.15s;
        }
        .lp-btn-primary-sm:hover { opacity: 0.88; }

        /* HERO */
        .lp-hero {
          padding: 80px 40px 70px; max-width: 1120px; margin: 0 auto;
          display: grid; grid-template-columns: 1fr 1fr; gap: 60px; align-items: center;
        }
        .lp-hero h1 { font-size: 42px; font-weight: 500; line-height: 1.18; margin-bottom: 20px; }
        .lp-hero h1 em { font-style: normal; color: var(--lp-blue); }
        .lp-hero > div > p { font-size: 16px; color: var(--lp-text-muted); line-height: 1.75; margin-bottom: 32px; max-width: 460px; }
        .lp-tag {
          display: inline-flex; align-items: center; gap: 6px;
          font-size: 12px; font-weight: 500; color: var(--lp-blue);
          background: var(--lp-blue-light); border: 1px solid var(--lp-blue-border);
          border-radius: 20px; padding: 5px 14px; margin-bottom: 22px;
        }
        .lp-tag-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--lp-blue); display: inline-block; }
        .lp-hero-btns { display: flex; gap: 12px; flex-wrap: wrap; }
        .lp-btn-primary {
          display: inline-flex; align-items: center; gap: 8px;
          font-size: 15px; font-weight: 500; color: #fff; background: var(--lp-blue);
          border-radius: var(--lp-radius-sm); padding: 12px 24px; transition: opacity 0.15s;
        }
        .lp-btn-primary:hover { opacity: 0.88; }
        .lp-btn-ghost {
          display: inline-flex; align-items: center; gap: 8px;
          font-size: 15px; color: var(--lp-text); background: transparent;
          border: 1px solid var(--lp-border); border-radius: var(--lp-radius-sm);
          padding: 12px 24px; transition: border-color 0.15s;
        }
        .lp-btn-ghost:hover { border-color: var(--lp-text-muted); }

        /* HERO VISUAL */
        .lp-visual {
          background: var(--lp-bg-muted); border-radius: var(--lp-radius);
          border: 1px solid var(--lp-border); padding: 22px;
          display: flex; flex-direction: column; gap: 10px;
        }
        .lp-chat-row { display: flex; gap: 10px; align-items: flex-start; }
        .lp-chat-avatar {
          width: 28px; height: 28px; border-radius: 50%; background: var(--lp-blue);
          flex-shrink: 0; display: flex; align-items: center; justify-content: center;
        }
        .lp-bubble {
          background: var(--lp-bg); border: 1px solid var(--lp-border); border-radius: 10px;
          padding: 10px 14px; font-size: 13px; color: var(--lp-text-muted); line-height: 1.55; flex: 1;
        }
        .lp-bubble-ai { background: var(--lp-blue-light); border-color: var(--lp-blue-border); color: #193cb8; }
        .lp-chat-status { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--lp-text-muted); }
        .lp-dot-green { width: 6px; height: 6px; border-radius: 50%; background: #22c55e; display: inline-block; flex-shrink: 0; }
        .lp-chip-row { display: flex; gap: 6px; flex-wrap: wrap; padding-top: 2px; }
        .lp-chip {
          background: var(--lp-bg); border: 1px solid var(--lp-border); border-radius: 6px;
          padding: 4px 10px; font-size: 11px; color: var(--lp-text-muted);
          display: flex; align-items: center; gap: 5px;
        }

        /* TRUST BAR */
        .lp-trust { background: var(--lp-bg-muted); border-top: 1px solid var(--lp-border); border-bottom: 1px solid var(--lp-border); padding: 22px 40px; }
        .lp-trust-inner { max-width: 1120px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
        .lp-trust-label { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--lp-text-muted); opacity: 0.55; white-space: nowrap; }
        .lp-trust-div { width: 1px; height: 30px; background: var(--lp-border); }
        .lp-trust-stat { text-align: center; }
        .lp-trust-num { font-size: 18px; font-weight: 500; color: var(--lp-text-muted); opacity: 0.6; line-height: 1; margin-bottom: 3px; }
        .lp-trust-desc { font-size: 10px; color: var(--lp-text-muted); opacity: 0.45; letter-spacing: 0.03em; }

        /* SECTION COMMON */
        .lp-section { padding: 80px 40px; max-width: 1120px; margin: 0 auto; }
        .lp-section-bg { background: var(--lp-bg-muted); border-top: 1px solid var(--lp-border); border-bottom: 1px solid var(--lp-border); }
        .lp-label { font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--lp-blue); margin-bottom: 10px; }
        .lp-title { font-size: 28px; font-weight: 500; line-height: 1.25; margin-bottom: 12px; }
        .lp-sub { font-size: 15px; color: var(--lp-text-muted); line-height: 1.7; max-width: 560px; margin-bottom: 40px; }

        /* HOW IT WORKS */
        .lp-how-grid {
          display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; position: relative;
        }
        .lp-how-grid::before {
          content: ''; position: absolute; top: 22px;
          left: calc(12.5% + 18px); right: calc(12.5% + 18px);
          height: 0; border-top: 1.5px dashed var(--lp-blue-border);
        }
        .lp-how-step { padding: 0 20px 0 0; }
        .lp-how-icon {
          width: 44px; height: 44px; border-radius: 50%;
          background: var(--lp-blue-light); border: 2px solid var(--lp-blue);
          display: flex; align-items: center; justify-content: center;
          margin-bottom: 18px; position: relative; z-index: 1;
        }
        .lp-how-step h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
        .lp-how-step p { font-size: 13px; color: var(--lp-text-muted); line-height: 1.65; }

        /* FEATURES */
        .lp-feat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
        .lp-feat-card {
          background: var(--lp-bg); border: 1px solid var(--lp-border);
          border-radius: var(--lp-radius); padding: 24px; transition: border-color 0.2s;
        }
        .lp-feat-card:hover { border-color: var(--lp-blue-border); }
        .lp-feat-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; }
        .lp-feat-card h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
        .lp-feat-card p { font-size: 13px; color: var(--lp-text-muted); line-height: 1.65; }
        .lp-feat-coming {
          grid-column: 1 / -1;
          background: linear-gradient(135deg, #0d1a4a 0%, #1a2f7a 60%, #0d1a4a 100%);
          border-color: #2a4acc;
          display: flex; flex-direction: row; align-items: center; gap: 32px;
        }
        .lp-feat-coming:hover { border-color: #4060ee; }
        .lp-feat-coming h4 { color: #fff; font-size: 17px; }
        .lp-feat-coming p { color: rgba(255,255,255,0.6); font-size: 14px; line-height: 1.7; }
        .lp-coming-badge {
          display: inline-flex; align-items: center; gap: 6px;
          background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
          border-radius: 20px; padding: 4px 12px; font-size: 10px; font-weight: 700;
          color: rgba(255,255,255,0.8); letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 14px;
        }
        .lp-coming-icon {
          width: 96px; height: 96px; background: rgba(255,255,255,0.06);
          border: 1px solid rgba(255,255,255,0.12); border-radius: var(--lp-radius);
          display: flex; align-items: center; justify-content: center; flex-shrink: 0;
        }

        /* INDUSTRIES */
        .lp-ind-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
        .lp-ind-card {
          background: var(--lp-bg); border: 1px solid var(--lp-border); border-radius: var(--lp-radius);
          padding: 22px 20px; display: flex; align-items: flex-start; gap: 16px;
          transition: border-color 0.2s, transform 0.15s;
        }
        .lp-ind-card:hover { border-color: var(--lp-blue-border); transform: translateY(-2px); }
        .lp-ind-icon { width: 46px; height: 46px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .lp-ind-card h4 { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
        .lp-ind-card p { font-size: 12px; color: var(--lp-text-muted); line-height: 1.55; }

        /* LMS STEPS */
        .lp-lms-steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
        .lp-lms-step { background: var(--lp-bg); border: 1px solid var(--lp-border); border-radius: var(--lp-radius); padding: 22px; }
        .lp-lms-badge {
          display: inline-flex; align-items: center; justify-content: center;
          width: 28px; height: 28px; background: var(--lp-blue); border-radius: 7px;
          font-size: 12px; font-weight: 600; color: #fff; margin-bottom: 14px;
        }
        .lp-lms-step h4 { font-size: 13px; font-weight: 600; margin-bottom: 7px; }
        .lp-lms-step p { font-size: 12px; color: var(--lp-text-muted); line-height: 1.65; }

        /* CTA */
        .lp-cta-wrap { padding: 40px; max-width: 1120px; margin: 0 auto 20px; }
        .lp-cta-box { background: var(--lp-blue); border-radius: var(--lp-radius); padding: 60px; text-align: center; }
        .lp-cta-box h2 { font-size: 30px; font-weight: 500; color: #fff; margin-bottom: 12px; }
        .lp-cta-box p { font-size: 16px; color: rgba(255,255,255,0.72); margin-bottom: 32px; }
        .lp-cta-btns { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
        .lp-btn-white {
          display: inline-flex; align-items: center; gap: 8px;
          font-size: 15px; font-weight: 500; color: var(--lp-blue); background: #fff;
          border-radius: var(--lp-radius-sm); padding: 13px 28px; transition: opacity 0.15s;
        }
        .lp-btn-white:hover { opacity: 0.92; }
        .lp-btn-outline {
          display: inline-flex; align-items: center; gap: 8px;
          font-size: 15px; color: #fff; background: transparent;
          border: 1px solid rgba(255,255,255,0.38); border-radius: var(--lp-radius-sm);
          padding: 13px 28px; transition: border-color 0.15s; cursor: pointer;
        }
        .lp-btn-outline:hover { border-color: rgba(255,255,255,0.65); }

        /* FOOTER */
        .lp-footer { background: #0a0709; padding: 60px 40px 36px; }
        .lp-footer-inner { max-width: 1120px; margin: 0 auto; }
        .lp-footer-top {
          display: grid; grid-template-columns: 2.2fr 1fr 1fr 1fr; gap: 40px;
          padding-bottom: 48px; border-bottom: 1px solid rgba(255,255,255,0.07);
        }
        .lp-footer-logo { display: flex; align-items: center; gap: 9px; font-size: 16px; font-weight: 600; color: #fff; margin-bottom: 14px; }
        .lp-footer-desc { font-size: 13px; color: rgba(255,255,255,0.4); line-height: 1.75; max-width: 280px; margin-bottom: 22px; }
        .lp-footer-contact { display: flex; align-items: center; gap: 8px; font-size: 13px; color: rgba(255,255,255,0.48); margin-bottom: 8px; }
        .lp-footer-col h5 { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(255,255,255,0.28); margin-bottom: 16px; }
        .lp-footer-col a { display: block; font-size: 13px; color: rgba(255,255,255,0.48); margin-bottom: 10px; transition: color 0.15s; }
        .lp-footer-col a:hover { color: rgba(255,255,255,0.85); }
        .lp-footer-bottom { padding-top: 28px; display: flex; align-items: center; justify-content: space-between; }
        .lp-footer-bottom p { font-size: 12px; color: rgba(255,255,255,0.2); }

        /* RESPONSIVE */
        @media (max-width: 960px) {
          .lp-hero { grid-template-columns: 1fr; gap: 40px; padding: 50px 24px 40px; }
          .lp-hero h1 { font-size: 30px; }
          .lp-how-grid { grid-template-columns: 1fr 1fr; }
          .lp-how-grid::before { display: none; }
          .lp-lms-steps { grid-template-columns: 1fr 1fr; }
          .lp-feat-grid { grid-template-columns: 1fr 1fr; }
          .lp-ind-grid { grid-template-columns: 1fr 1fr; }
          .lp-section { padding: 60px 24px; }
          .lp-lms-steps, .lp-ind-grid { padding: 0 24px; }
          .lp-footer-top { grid-template-columns: 1fr 1fr; }
          .lp-nav-links { display: none; }
          .lp-trust-inner { gap: 20px; flex-wrap: wrap; justify-content: center; }
        }
        @media (max-width: 600px) {
          .lp-how-grid, .lp-lms-steps, .lp-feat-grid, .lp-ind-grid { grid-template-columns: 1fr; }
          .lp-feat-coming { flex-direction: column; }
          .lp-coming-icon { display: none; }
          .lp-hero-btns { flex-direction: column; }
          .lp-cta-box { padding: 40px 24px; }
          .lp-footer-top { grid-template-columns: 1fr; }
          .lp-trust-div { display: none; }
        }
      `}</style>

      <div className="lp">
        {/* NAV */}
        <nav className="lp-nav">
          <div className="lp-nav-inner">
            <div className="lp-logo">
              <div className="lp-logo-mark">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8.5L6.5 12L13 4.5" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </div>
              Axis AI
            </div>
            <div className="lp-nav-links">
              <a href="#how-it-works">How it works</a>
              <a href="#features">Features</a>
              <a href="#industries">Industries</a>
              <a href="#lms-integration">LMS Integration</a>
            </div>
            <div className="lp-nav-actions">
              <LandingNavClient />
            </div>
          </div>
        </nav>

        {/* HERO */}
        <div className="lp-hero">
          <div>
            <div className="lp-tag"><span className="lp-tag-dot" /> Intelligent learning, for any platform</div>
            <h1>Turn any content into <em>powerful learning</em> experiences</h1>
            <p>Axis AI transforms PDFs, videos, web pages, and SCORM content into summaries, quizzes, flashcards, mind maps, and an AI study assistant &mdash; standalone or connected to your LMS.</p>
            <div className="lp-hero-btns">
              <Link href="/login"><button className="lp-btn-primary">Start free &rarr;</button></Link>
              <a href="#how-it-works"><button className="lp-btn-ghost">
                <svg width="15" height="15" viewBox="0 0 15 15" fill="none"><circle cx="7.5" cy="7.5" r="6.5" stroke="currentColor" strokeWidth="1.3"/><path d="M6 5l3 2.5-3 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                See how it works
              </button></a>
            </div>
          </div>
          <div className="lp-visual">
            <div className="lp-chat-status">
              <span className="lp-dot-green" />
              Processing: <strong style={{color:'#0c090c', fontSize:'12px', marginLeft:'2px'}}>Advanced SQL Indexing.pdf</strong>
            </div>
            <div className="lp-bubble lp-bubble-ai" style={{fontSize:'12px'}}>
              &#10003; Summary &nbsp;&middot;&nbsp; 14 quiz questions &nbsp;&middot;&nbsp; 28 flashcards &nbsp;&middot;&nbsp; Glossary ready
            </div>
            <div className="lp-chat-row">
              <div className="lp-bubble">&#128172; &nbsp;&ldquo;What&apos;s the difference between clustered and non-clustered indexes?&rdquo;</div>
            </div>
            <div className="lp-chat-row">
              <div className="lp-chat-avatar">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 6.5l3.5 3.5L11 3" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </div>
              <div className="lp-bubble lp-bubble-ai">
                A clustered index determines the physical order of rows &mdash; each table can only have one. A non-clustered index stores a separate lookup with pointers back to the rows&hellip;
                <span style={{display:'block', marginTop:'6px', fontSize:'11px', opacity:0.65}}>&#128206; Source: pg. 12 &mdash; SQL Indexing.pdf</span>
              </div>
            </div>
            <div className="lp-chip-row">
              <span className="lp-chip">&#9679; Instant answers</span>
              <span className="lp-chip">&#8599; Source-cited</span>
              <span className="lp-chip">&#9679; Multilingual</span>
              <span className="lp-chip">&#9632; Any format</span>
            </div>
          </div>
        </div>

        {/* TRUST BAR */}
        <div className="lp-trust">
          <div className="lp-trust-inner">
            <span className="lp-trust-label">Trusted by learning teams at</span>
            <div className="lp-trust-div" />
            <div className="lp-trust-stat"><div className="lp-trust-num">50K+</div><div className="lp-trust-desc">Students served</div></div>
            <div className="lp-trust-div" />
            <div className="lp-trust-stat"><div className="lp-trust-num">99.7%</div><div className="lp-trust-desc">Uptime SLA</div></div>
            <div className="lp-trust-div" />
            <div className="lp-trust-stat"><div className="lp-trust-num">10+</div><div className="lp-trust-desc">Content formats</div></div>
            <div className="lp-trust-div" />
            <div className="lp-trust-stat"><div className="lp-trust-num">&lt;2s</div><div className="lp-trust-desc">Chat response</div></div>
            <div className="lp-trust-div" />
            <div className="lp-trust-stat"><div className="lp-trust-num">400+</div><div className="lp-trust-desc">TTS voices</div></div>
          </div>
        </div>

        {/* HOW IT WORKS */}
        <section id="how-it-works">
          <div className="lp-section">
            <div className="lp-label">How Axis AI works</div>
            <div className="lp-title">Learning intelligence in four steps</div>
            <div className="lp-sub">Log in, upload your content, and let Axis AI do the rest. No LMS required &mdash; get started in minutes.</div>
            <div className="lp-how-grid">
              {[
                { icon: <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="3" width="11" height="14" rx="2" stroke="#1447e6" strokeWidth="1.5"/><path d="M14 7.5l3.5 2.5-3.5 2.5" stroke="#1447e6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M17.5 10H9" stroke="#1447e6" strokeWidth="1.5" strokeLinecap="round"/></svg>, title: 'Create an account', body: 'Sign up in seconds. Get a personal workspace where all your content, AI outputs, and learner activity live together.' },
                { icon: <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 14V4M10 4L7 7M10 4l3 3" stroke="#1447e6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M3 15v2a1 1 0 001 1h12a1 1 0 001-1v-2" stroke="#1447e6" strokeWidth="1.5" strokeLinecap="round"/></svg>, title: 'Upload your content', body: 'Drop in PDFs, paste a YouTube or Vimeo URL, upload SCORM packages, or a web page &mdash; Axis AI handles all formats.' },
                { icon: <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 2l1.5 4.5L16 8l-4.5 1.5L10 14l-1.5-4.5L4 8l4.5-1.5L10 2z" stroke="#1447e6" strokeWidth="1.4" strokeLinejoin="round"/></svg>, title: 'AI generates outputs', body: 'Summaries, quizzes, flashcards, glossaries, mind maps, FAQs, and chapter breakdowns ready in under a minute.' },
                { icon: <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="15" cy="5" r="2" stroke="#1447e6" strokeWidth="1.4"/><circle cx="15" cy="15" r="2" stroke="#1447e6" strokeWidth="1.4"/><circle cx="5" cy="10" r="2" stroke="#1447e6" strokeWidth="1.4"/><path d="M7 9l6-3M7 11l6 3" stroke="#1447e6" strokeWidth="1.3" strokeLinecap="round"/></svg>, title: 'Share with learners', body: 'Invite learners to your space. They get an AI study assistant with source-cited answers drawn from your content.' },
              ].map((step) => (
                <div key={step.title} className="lp-how-step">
                  <div className="lp-how-icon">{step.icon}</div>
                  <h4>{step.title}</h4>
                  <p dangerouslySetInnerHTML={{__html: step.body}} />
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FEATURES */}
        <section id="features" className="lp-section-bg">
          <div className="lp-section" style={{background:'transparent'}}>
            <div className="lp-label">What you can do</div>
            <div className="lp-title">Everything a learner needs</div>
            <div className="lp-sub">Ten AI output types, RAG chat, multilingual support &mdash; generated automatically from your existing content.</div>
            <div className="lp-feat-grid">
              {[
                { bg:'#eff4ff', icon:<svg width="22" height="22" viewBox="0 0 22 22" fill="none"><rect x="3" y="3" width="16" height="16" rx="2.5" stroke="#1447e6" strokeWidth="1.5"/><path d="M7 8h8M7 11h8M7 14h5" stroke="#1447e6" strokeWidth="1.4" strokeLinecap="round"/></svg>, title:'Smart summaries', body:'Auto-generated concise summaries from any content — PDFs, videos, web pages, SCORM. Instant, readable, accurate.' },
                { bg:'#f0fdf4', icon:<svg width="22" height="22" viewBox="0 0 22 22" fill="none"><rect x="3" y="3" width="16" height="16" rx="2.5" stroke="#16a34a" strokeWidth="1.5"/><path d="M7 11l3 3 5-5" stroke="#16a34a" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>, title:'Quiz generator', body:'MCQ, true/false, and short-answer questions with answer explanations — ready to embed or export in seconds.' },
                { bg:'#fff7ed', icon:<svg width="22" height="22" viewBox="0 0 22 22" fill="none"><rect x="4.5" y="6.5" width="13" height="9" rx="2" stroke="#ea580c" strokeWidth="1.5"/><rect x="2.5" y="4.5" width="13" height="9" rx="2" stroke="#ea580c" strokeWidth="1.3" strokeDasharray="3 2.5"/></svg>, title:'Flashcard decks', body:'Spaced-repetition ready flashcard sets extracted automatically. Perfect for exam prep and long-term retention.' },
                { bg:'#fdf4ff', icon:<svg width="22" height="22" viewBox="0 0 22 22" fill="none"><path d="M4 5.5a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2h-4l-4 3.5v-3.5H6a2 2 0 01-2-2V5.5z" stroke="#9333ea" strokeWidth="1.5" strokeLinejoin="round"/><path d="M8 9h6M8 12h4" stroke="#9333ea" strokeWidth="1.4" strokeLinecap="round"/></svg>, title:'RAG-powered chat', body:"Learners ask questions in natural language and get source-cited answers pulled directly from your course content." },
                { bg:'#fef2f2', icon:<svg width="22" height="22" viewBox="0 0 22 22" fill="none"><circle cx="11" cy="11" r="3" stroke="#dc2626" strokeWidth="1.5"/><circle cx="11" cy="4" r="1.5" stroke="#dc2626" strokeWidth="1.3"/><circle cx="18" cy="11" r="1.5" stroke="#dc2626" strokeWidth="1.3"/><circle cx="4" cy="11" r="1.5" stroke="#dc2626" strokeWidth="1.3"/><circle cx="11" cy="18" r="1.5" stroke="#dc2626" strokeWidth="1.3"/><path d="M11 8V5.5M15 11h2.5M11 14v2.5M6.5 11H8.5" stroke="#dc2626" strokeWidth="1.2" strokeLinecap="round"/></svg>, title:'Mind maps & glossary', body:'Visual mind maps, key term glossaries, FAQs, and Bloom\'s taxonomy-aligned objectives — all auto-generated.' },
                { bg:'#ecfdf5', icon:<svg width="22" height="22" viewBox="0 0 22 22" fill="none"><path d="M4 6h14M4 10h10M4 14h12M4 18h8" stroke="#059669" strokeWidth="1.5" strokeLinecap="round"/><circle cx="17" cy="16" r="3.5" stroke="#059669" strokeWidth="1.4"/><path d="M15.5 16l1 1 2-2" stroke="#059669" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>, title:'Objectives & Bloom\'s', body:"Auto-generated learning objectives, chapter outlines, and Bloom's taxonomy-mapped outcomes for every piece of content." },
              ].map((card) => (
                <div key={card.title} className="lp-feat-card">
                  <div className="lp-feat-icon" style={{background:card.bg}}>{card.icon}</div>
                  <h4>{card.title}</h4>
                  <p>{card.body}</p>
                </div>
              ))}

              {/* Coming soon — video — full width */}
              <div className="lp-feat-card lp-feat-coming">
                <div style={{flex:1}}>
                  <div className="lp-coming-badge">
                    <svg width="9" height="9" viewBox="0 0 9 9" fill="rgba(255,255,255,0.75)"><path d="M4.5 1l.9 2.7H8L5.8 5.4l.9 2.6-2.2-1.6-2.2 1.6.9-2.6L1 3.7h2.6L4.5 1z"/></svg>
                    Coming soon
                  </div>
                  <h4>Automatic video creation</h4>
                  <p>Transform any course material into a fully narrated video &mdash; slides, TTS voiceover in 400+ languages, and chapter markers. Upload a PDF or paste a topic and Axis AI builds the entire video end-to-end.</p>
                </div>
                <div className="lp-coming-icon">
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <rect x="4" y="9" width="28" height="20" rx="3.5" stroke="rgba(255,255,255,0.45)" strokeWidth="1.8"/>
                    <path d="M32 16.5l9-5v15l-9-5v-5z" stroke="rgba(255,255,255,0.45)" strokeWidth="1.8" strokeLinejoin="round"/>
                    <path d="M4 33h28M10 38h16" stroke="rgba(255,255,255,0.25)" strokeWidth="1.8" strokeLinecap="round"/>
                    <path d="M16 15.5l7 3.5-7 3.5v-7z" fill="rgba(255,255,255,0.4)"/>
                    <circle cx="38" cy="38" r="7" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.2)" strokeWidth="1.3"/>
                    <path d="M36 38l2 1.5-2 1.5V38z" fill="rgba(255,255,255,0.5)"/>
                  </svg>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* INDUSTRIES */}
        <section id="industries">
          <div className="lp-section">
            <div className="lp-label">Industries we serve</div>
            <div className="lp-title">Built for every learning context</div>
            <div className="lp-sub">From corporate compliance to higher education &mdash; Axis AI adapts to your sector&apos;s specific learning needs.</div>
            <div className="lp-ind-grid">
              {[
                { bg:'#eff4ff', icon:<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M3 18.5l9-9 9 9" stroke="#1447e6" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/><path d="M12 9.5V3.5" stroke="#1447e6" strokeWidth="1.6" strokeLinecap="round"/><rect x="6" y="14" width="12" height="7" rx="1" stroke="#1447e6" strokeWidth="1.4"/><rect x="9" y="14" width="6" height="7" stroke="#1447e6" strokeWidth="1.2"/></svg>, title:'Higher Education', body:'Universities and colleges delivering AI-powered study tools to thousands of enrolled students.' },
                { bg:'#fff7ed', icon:<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><rect x="2" y="8" width="20" height="13" rx="2" stroke="#ea580c" strokeWidth="1.5"/><path d="M8 8V6a2 2 0 014 0v2" stroke="#ea580c" strokeWidth="1.5" strokeLinecap="round"/><circle cx="12" cy="14.5" r="1.8" stroke="#ea580c" strokeWidth="1.3"/><path d="M12 16.3v2" stroke="#ea580c" strokeWidth="1.3" strokeLinecap="round"/></svg>, title:'Corporate Training', body:'L&D teams turning policy docs, SOPs, and training decks into interactive learning modules.' },
                { bg:'#f0fdf4', icon:<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><rect x="3" y="10" width="18" height="11" rx="2" stroke="#16a34a" strokeWidth="1.5"/><path d="M3 10l9-7 9 7" stroke="#16a34a" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M9 21v-5h6v5" stroke="#16a34a" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>, title:'BFSI', body:'Banks, financial services, and fintech firms upskilling teams on products, regulations, and compliance.' },
                { bg:'#fdf4ff', icon:<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><rect x="4" y="4" width="16" height="16" rx="3" stroke="#9333ea" strokeWidth="1.5"/><path d="M12 8v8M8 12h8" stroke="#9333ea" strokeWidth="1.8" strokeLinecap="round"/></svg>, title:'Healthcare', body:'Hospitals and clinical organisations digitising training manuals, drug protocols, and CPD programmes.' },
                { bg:'#fef2f2', icon:<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 3l9 4V13c0 4.5-4 7.5-9 8-5-.5-9-3.5-9-8V7l9-4z" stroke="#dc2626" strokeWidth="1.5" strokeLinejoin="round"/><path d="M9 12l2.5 2.5 4-4" stroke="#dc2626" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>, title:'Insurance', body:'Insurers and brokers building AI-assisted onboarding, product knowledge bases, and claims training.' },
                { bg:'#e0f2fe', icon:<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><rect x="3" y="5" width="18" height="14" rx="2" stroke="#0891b2" strokeWidth="1.5"/><path d="M7 20h10M12 19v1" stroke="#0891b2" strokeWidth="1.4" strokeLinecap="round"/><path d="M7.5 11l3 2-3 2" stroke="#0891b2" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/><path d="M13.5 15h4" stroke="#0891b2" strokeWidth="1.4" strokeLinecap="round"/></svg>, title:'EdTech SaaS', body:'Embed Axis AI as a white-label intelligence layer inside your own learning product — full API access included.' },
              ].map((card) => (
                <div key={card.title} className="lp-ind-card">
                  <div className="lp-ind-icon" style={{background:card.bg}}>{card.icon}</div>
                  <div>
                    <h4>{card.title}</h4>
                    <p>{card.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* LMS INTEGRATION */}
        <section id="lms-integration" className="lp-section-bg">
          <div className="lp-section" style={{background:'transparent'}}>
            <div className="lp-label">Integration with LMS</div>
            <div className="lp-title">Already running Moodle? Plug straight in.</div>
            <div className="lp-sub">The Axis AI Moodle plugin connects to your existing instance in minutes &mdash; no data migration, no disruption to enrolled learners.</div>
            <div className="lp-lms-steps">
              {[
                { n:'1', title:'Install the plugin', body:'Download the Axis AI local plugin from the Moodle marketplace. One API key, zero config. Works with Moodle 4.x and above.' },
                { n:'2', title:'Ingest your courses', body:'Point Axis AI at any course module — PDFs, YouTube, SCORM, Vimeo, or Moodle page HTML. Processed automatically in the background.' },
                { n:'3', title:'AI outputs appear instantly', body:'Summaries, quizzes, flashcards, and mind maps surface inside your existing Moodle course view — no new interface to learn.' },
                { n:'4', title:'Students learn smarter', body:'Every enrolled student gets an AI study assistant that answers questions with citations drawn from your actual course material.' },
              ].map((step) => (
                <div key={step.n} className="lp-lms-step">
                  <div className="lp-lms-badge">{step.n}</div>
                  <h4>{step.title}</h4>
                  <p>{step.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <div className="lp-cta-wrap">
          <div className="lp-cta-box">
            <h2>Ready to transform how your learners study?</h2>
            <p>Join thousands of educators and L&amp;D teams using Axis AI to deliver smarter learning experiences.</p>
            <div className="lp-cta-btns">
              <Link href="/login"><button className="lp-btn-white">Start free trial &rarr;</button></Link>
              <button className="lp-btn-outline">Book a demo</button>
            </div>
          </div>
        </div>

        {/* FOOTER */}
        <footer className="lp-footer">
          <div className="lp-footer-inner">
            <div className="lp-footer-top">
              <div>
                <div className="lp-footer-logo">
                  <div className="lp-logo-mark">
                    <svg width="15" height="15" viewBox="0 0 15 15" fill="none"><path d="M2.5 8L6 11.5L12.5 4" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </div>
                  Axis AI
                </div>
                <p className="lp-footer-desc">AI-powered learning intelligence for any platform. Summaries, quizzes, flashcards, and RAG chat &mdash; from your existing content.</p>
                <div className="lp-footer-contact">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1" y="3" width="12" height="8" rx="1.5" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2"/><path d="M1 4.5l6 3.5 6-3.5" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2" strokeLinecap="round"/></svg>
                  support@edzlms.com
                </div>
                <div className="lp-footer-contact">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 2.5h2.5l1 3-1.5 1a8.5 8.5 0 003.5 3.5l1-1.5 3 1V12a1 1 0 01-1 1C5 13 1 9 1 3.5a1 1 0 011-1z" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2" strokeLinejoin="round"/></svg>
                  +91 98765 43210
                </div>
              </div>
              <div className="lp-footer-col">
                <h5>Product</h5>
                <a href="#features">Features</a>
                <a href="#how-it-works">How it works</a>
                <a href="#">Pricing</a>
                <a href="#">Changelog</a>
                <a href="#">API docs</a>
              </div>
              <div className="lp-footer-col">
                <h5>Use cases</h5>
                <a href="#">Higher Ed</a>
                <a href="#">Corporate L&amp;D</a>
                <a href="#">BFSI</a>
                <a href="#">Healthcare</a>
                <a href="#">Insurance</a>
                <a href="#">EdTech SaaS</a>
              </div>
              <div className="lp-footer-col">
                <h5>Company</h5>
                <a href="#">About EDZLMS</a>
                <a href="#">Privacy policy</a>
                <a href="#">Terms of service</a>
                <a href="#">Contact us</a>
                <Link href="/login">Log in</Link>
              </div>
            </div>
            <div className="lp-footer-bottom">
              <p>&copy; 2026 EDZLMS &middot; Axis AI. All rights reserved.</p>
              <p>Powered by OpenAI &amp; Anthropic</p>
            </div>
          </div>
        </footer>
      </div>
    </>
  );
}
