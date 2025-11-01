import { Book, Keyboard, Zap, Shield, HelpCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import '../styles/Help.css';

const Help = () => {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const suggestionsRef = useRef(null);

  const sections = useMemo(() => [
    {
      key: 'getting-started',
      icon: <HelpCircle size={20} />,
      title: 'Getting Started',
      summary: 'Overview of how to use the platform and begin conversations with MAYA.',
      items: [
        'Create a new chat using the "New Chat" button',
        'Type your question or use voice input',
        'Attach files and images to provide context',
        'Use the sidebar to access saved conversations',
      ],
    },
    {
      key: 'account-profile',
      icon: <Keyboard size={20} />,
      title: 'Account & Profile',
      summary: 'Login, registration, password recovery, and profile management.',
      items: [
        'How to register and verify your account',
        'Reset your password from the login screen',
        'Update profile details and avatar',
        'Manage connected apps and API keys',
      ],
    },
    {
      key: 'features-dashboard',
      icon: <Zap size={20} />,
      title: 'Features & Dashboard',
      summary: 'Guides on different modules, tools, and dashboard workflows.',
      items: [
        'Understanding the Dashboard layout and widgets',
        'Using Tasks, Memory, and Suggestions features',
        'Exporting or saving conversation transcripts',
        'Keyboard shortcuts and productivity tips',
      ],
    },
    {
      key: 'troubleshooting',
      icon: <Shield size={20} />,
      title: 'Troubleshooting',
      summary: 'Common errors and step-by-step fixes for connectivity or UI issues.',
      items: [
        'If messages fail to send, check network and retry',
        'Clear local cache or refresh to recover from UI glitches',
        'Check server status or contact support for prolonged outages',
      ],
    },
    {
      key: 'tips',
      icon: <Book size={20} />,
      title: 'Tips & Best Practices',
      summary: 'Short tips for better results and privacy-aware usage.',
      items: [
        'Be specific with prompts to get better responses',
        'Use the edit feature to refine inputs',
        'Manage memory settings to control what is retained',
      ],
    },
  ], []);

  const faqs = [
    { q: 'How do I reset my password?', a: 'Go to the sign-in page and click "Forgot password". You will get a reset link via email.' },
    { q: 'How do I export a conversation?', a: 'Open the conversation, click the options menu, and choose Export to download a transcript.' },
    { q: 'Why am I not receiving notifications?', a: 'Check your browser notification permissions and your account notification settings.' },
  ];

  // track opened collapsible panels
  const [openPanels, setOpenPanels] = useState(() => ({ 'getting-started': true }));
  const togglePanel = (key) => setOpenPanels((s) => ({ ...s, [key]: !s[key] }));

  // FAQ open state
  const [openFaq, setOpenFaq] = useState({});
  const toggleFaq = (i) => setOpenFaq((s) => ({ ...s, [i]: !s[i] }));

  // Contact form state + feedback
  const [contact, setContact] = useState({ name: '', email: '', message: '' });
  const [submitted, setSubmitted] = useState(false);
  const [feedback, setFeedback] = useState(null); // 'yes' | 'no'

  const handleContactSubmit = (e) => {
    e.preventDefault();
    // Simple local handling — replace with API call if backend available
    console.log('Contact submission', contact);
    setSubmitted(true);
    setTimeout(() => setSubmitted(false), 4000);
  };

  const handleFeedback = (val) => {
    setFeedback(val);
    // optionally send feedback to backend
  };

  // Build a flat list of searchable topics from section titles and items
  const topics = useMemo(() => {
    const t = [];
    sections.forEach((s) => {
      t.push(s.title);
      s.items.forEach((it) => t.push(it));
    });
    return Array.from(new Set(t));
  }, [sections]);

  const filtered = useMemo(() => {
    if (!query) return [];
    const q = query.toLowerCase();
    return topics.filter((t) => t.toLowerCase().includes(q)).slice(0, 6);
  }, [query, topics]);

  useEffect(() => {
    const onDocClick = (e) => {
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, []);

  const handleSelectSuggestion = (text) => {
    setQuery(text);
    setShowSuggestions(false);
    // try to scroll to matching section if exists
    const slug = text.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    const el = document.getElementById(`help-${slug}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="help-page">
      <button className="profile-back-btn" aria-label="Go back" onClick={() => navigate(-1)}>
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="m12 19-7-7 7-7"></path>
          <path d="M19 12H5"></path>
        </svg>
        <span className="profile-back-text">Back</span>
      </button>
      <header className="help-header">
        <div className="help-header-inner">
          <h1>Help Center</h1>
          <p className="help-subtitle">Find quick answers, guides, and assistance anytime.</p>

          <div className="help-search" ref={suggestionsRef}>
            <input
              aria-label="Search help"
              className="help-search-input"
              placeholder="Search your question or topic..."
              value={query}
              onFocus={() => setShowSuggestions(true)}
              onChange={(e) => { setQuery(e.target.value); setShowSuggestions(true); }}
            />
            {showSuggestions && (filtered.length > 0 || query) && (
              <ul className="help-suggestions" role="listbox">
                {filtered.length === 0 && (
                  <li className="no-suggestion">No suggestions. Press Enter to search.</li>
                )}
                {filtered.map((s, i) => (
                  <li key={i} role="option" aria-selected={false} tabIndex={0} onClick={() => handleSelectSuggestion(s)} onKeyDown={(e)=>{ if(e.key==='Enter') handleSelectSuggestion(s); }}>
                    {s}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </header>

      <main className="help-content">
        {sections.map((section) => (
          <div key={section.key} className="panel">
            <div className="panel-header" onClick={() => togglePanel(section.key)}>
              <div className="help-icon">{section.icon}</div>
              <div style={{ flex: 1 }}>
                <div className="panel-title">{section.title}</div>
                <div className="panel-sub">{section.summary}</div>
              </div>
              <div aria-hidden style={{ opacity: 0.6 }}>{openPanels[section.key] ? '−' : '+'}</div>
            </div>
            {openPanels[section.key] && (
              <div className="panel-body">
                <ul className="panel-list">
                  {section.items.map((it, i) => <li key={i}>{it}</li>)}
                </ul>
              </div>
            )}
          </div>
        ))}

        <div className="panel" style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: 0 }}>Frequently Asked Questions</h3>
              <p className="panel-sub" style={{ margin: '6px 0 0' }}>Common questions and quick answers.</p>
            </div>
          </div>

          <div className="faq">
            {faqs.map((f, i) => (
              <div key={i} className="faq-item">
                <div className="faq-q" onClick={() => toggleFaq(i)}>
                  <div>{f.q}</div>
                  <div style={{ opacity: 0.6 }}>{openFaq[i] ? '−' : '+'}</div>
                </div>
                {openFaq[i] && <div className="faq-a">{f.a}</div>}
              </div>
            ))}
          </div>
        </div>

        <div className="panel" style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: 0 }}>Still need help? We’re here for you.</h3>
              <p className="panel-sub">Choose an option below to contact support or leave feedback.</p>
            </div>
          </div>

          <div className="contact-panel" style={{ marginTop: 12 }}>
            <form className="contact-form" onSubmit={handleContactSubmit}>
              <input className="contact-input" placeholder="Your name" value={contact.name} onChange={(e) => setContact({ ...contact, name: e.target.value })} />
              <div style={{ height: 8 }} />
              <input className="contact-input" placeholder="Your email" value={contact.email} onChange={(e) => setContact({ ...contact, email: e.target.value })} />
              <div style={{ height: 8 }} />
              <textarea className="contact-textarea" placeholder="How can we help?" value={contact.message} onChange={(e) => setContact({ ...contact, message: e.target.value })} />
              <div className="contact-actions">
                <button type="submit" className="contact-btn">Send message</button>
                <button type="button" className="docs-btn" onClick={() => window.open('mailto:support@example.com')}>Email Support</button>
                <button type="button" className="docs-btn" onClick={() => navigate('/chat?new=true')}>Start Chat</button>
              </div>
              {submitted && <div className="thanks-msg">Thanks — we received your message.</div>}
            </form>

            <div style={{ minWidth: 240 }}>
              <div style={{ marginBottom: 12 }}><strong>Was this helpful?</strong></div>
              <div className="feedback-row">
                <button className={`feedback-btn ${feedback === 'yes' ? 'active' : ''}`} onClick={() => handleFeedback('yes')}>Yes</button>
                <button className={`feedback-btn ${feedback === 'no' ? 'active' : ''}`} onClick={() => handleFeedback('no')}>No</button>
              </div>

              <div style={{ marginTop: 18 }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Quick links</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <a href="/privacy">Privacy Policy</a>
                  <a href="/terms">Terms</a>
                  <a href="/contact">Contact Us</a>
                </div>
              </div>
            </div>
          </div>

          <div className="help-footer-bar">Our Help Center is continuously updated to serve you better.</div>
        </div>
      </main>
    </div>
  );
};

export default Help;
