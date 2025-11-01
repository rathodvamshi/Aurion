import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Moon,
  Sun,
  Bell,
  Lock,
  Globe,
  Key,
  Trash2,
  User,
  Zap,
  Database,
  CreditCard,
  LifeBuoy,
} from 'lucide-react';
import '../styles/Settings.css';

const translations = {
  en: {
    settings: 'Settings',
    accountSettings: 'Account Settings',
    profile: 'Profile',
    uploadPhoto: 'Upload photo',
    username: 'Username',
    email: 'Email',
    cancel: 'Cancel',
    save: 'Save',
  // removed delete/change actions per request
    preferences: 'Preferences',
    theme: 'Theme',
    fontSize: 'Font size',
    language: 'Language',
    personalization: 'Personalization',
    enableCustomization: 'Enable customization',
    assistantPersonality: 'Assistant personality',
    customInstructions: 'Custom instructions',
    aboutYou: 'About you',
    nickname: 'Nickname',
    occupation: 'Occupation',
    savePersonalization: 'Save personalization',
    notifications: 'Notifications',
    emailNotifications: 'Email notifications',
    systemNotifications: 'System notifications',
    soundAlerts: 'Sound alerts',
    weeklySummary: 'Weekly summary',
    privacy: 'Privacy & Security',
    twoFA: 'Two-factor authentication',
    activeSessions: 'Active sessions',
    requestData: 'Request data download',
    clearHistory: 'Clear chat history',
    aboutSupport: 'About & Support',
    contactSupport: 'Contact support',
    terms: 'Terms of Service',
    privacyPolicy: 'Privacy Policy',
    reportBug: 'Report a bug',
  },
  te: {
    settings: 'అమరికలు',
    accountSettings: 'ఖాతా సెట్టింగ్‌లు',
    profile: 'ప్రొఫైల్',
    uploadPhoto: 'ఫొటో అప్లోడ్ చేయండి',
    username: 'వాడుకరిపేరు',
    email: 'ఇమెయిల్',
    cancel: 'రద్దు చేయి',
    save: 'సేవ్ చేయి',
  // removed
    preferences: 'అభిరుచులు',
    theme: 'థీమ్',
    fontSize: 'ఫాంట్ పరిమాణం',
    language: 'భాష',
    personalization: 'వ్యక్తిగతీకరణ',
    enableCustomization: 'అనుకూలీకరణ పని చేయనివ్వు',
    assistantPersonality: 'సహాయక వ్యక్తిత్వం',
    customInstructions: 'అనుకూల సూచనలు',
    aboutYou: 'మీ గురించి',
    nickname: 'పేరు',
    occupation: 'వ్యవసాయం/ఉద్యోగం',
    savePersonalization: 'వ్యక్తిగతీకరణ సేవ్ చేయండి',
    notifications: 'నోటిఫికేషన్లు',
    emailNotifications: 'ఇమెయిల్ నోటిఫికేషన్లు',
    systemNotifications: 'సిస్టమ్ నోటిఫికేషన్లు',
    soundAlerts: 'ఆడియో అలర్ట్స్',
    weeklySummary: 'వారపు సారాంశం',
    privacy: 'గోప్యత & భద్రత',
    twoFA: 'రెండు-స్టెప్ పరిశీలన',
    activeSessions: 'చాలించే సెషన్లు',
    requestData: 'డేటా డౌన్లోడ్ అభ్యర్థన',
    clearHistory: 'చాట్ హిస్ట్రీ ని క్లియర్ చేయి',
    aboutSupport: 'గురించి & మద్దతు',
    contactSupport: 'మద్దతును సంప్రదించండి',
    terms: 'సేవా షరతులు',
    privacyPolicy: 'గోప్యత విధానము',
    reportBug: 'బగ్ నివేదించండి',
  },
  hi: {
    settings: 'सेटिंग्स',
    accountSettings: 'खाता सेटिंग्स',
    profile: 'प्रोफ़ाइल',
    uploadPhoto: 'फ़ोटो अपलोड करें',
    username: 'उपयोगकर्ता नाम',
    email: 'ईमेल',
    cancel: 'रद्द करें',
    save: 'सेव',
  // removed
    preferences: 'प्रेफ़रेंसेज़',
    theme: 'थीम',
    fontSize: 'फ़ॉन्ट आकार',
    language: 'भाषा',
    personalization: 'व्यक्तिगतकरण',
    enableCustomization: 'अनुकूलन सक्षम करें',
    assistantPersonality: 'सहायक व्यक्तित्व',
    customInstructions: 'कस्टम निर्देश',
    aboutYou: 'आपके बारे में',
    nickname: 'उपनाम',
    occupation: 'पेशा',
    savePersonalization: 'व्यक्तिगतकरण सहेजें',
    notifications: 'सूचनाएं',
    emailNotifications: 'ईमेल सूचनाएं',
    systemNotifications: 'सिस्टम सूचनाएं',
    soundAlerts: 'ध्वनि अलर्ट',
    weeklySummary: 'साप्ताहिक सारांश',
    privacy: 'गोपनीयता और सुरक्षा',
    twoFA: 'दो-चरण प्रमाणीकरण',
    activeSessions: 'सक्रिय सत्र',
    requestData: 'डेटा डाउनलोड का अनुरोध करें',
    clearHistory: 'चैट इतिहास साफ़ करें',
    aboutSupport: 'बारे में और सहायता',
    contactSupport: 'संपर्क सहायता',
    terms: 'सेवा की शर्तें',
    privacyPolicy: 'गोपनीयता नीति',
    reportBug: 'बग रिपोर्ट करें',
  }
};

const t = (key, lang) => {
  try {
    return translations[lang || 'en'][key] || translations.en[key] || key;
  } catch (e) { return translations.en[key] || key; }
};

const GradientHeading = ({ icon, title }) => (
  <div className="section-title">
    <div className="title-icon gradient">{icon}</div>
    <h2 className="gradient-text">{title}</h2>
  </div>
);

const Toggle = ({ checked, onChange, label }) => (
  <label className="toggle-switch">
    <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    <span className="slider"></span>
    {label && <span className="toggle-label">{label}</span>}
  </label>
);

const Settings = ({ onNavigate }) => {
  const navigate = useNavigate();

  // Profile
  const [profile, setProfile] = useState({ username: 'You', email: 'you@example.com' });
  const [avatarPreview, setAvatarPreview] = useState(null);

  // Preferences
  const [theme, setTheme] = useState('system'); // light | dark | system
  const [fontSize, setFontSize] = useState('medium');
  const [language, setLanguage] = useState('en');

  // Personalization
  const [customizationEnabled, setCustomizationEnabled] = useState(true);
  const [personality, setPersonality] = useState('default');
  const [customInstructions, setCustomInstructions] = useState('');
  const [about, setAbout] = useState({ nickname: '', occupation: '' });

  // Notifications
  const [notifications, setNotifications] = useState({
    email: true,
    system: true,
    sound: false,
    weekly: false,
  });

  // Security & Privacy
  const [twoFA, setTwoFA] = useState(false);
  const [sessions] = useState([
    { id: 'laptop-1', device: 'Windows • Chrome', when: 'Today, 10:43', location: 'Home' },
    { id: 'phone-1', device: 'iPhone • Safari', when: 'Yesterday, 21:02', location: 'Remote' },
  ]);

  // Integrations / API keys (client-only demo)
  const [apiKeys, setApiKeys] = useState([{ id: 'k_123', name: 'Default key', created: '2025-02-01' }]);

  // Billing / subscription
  const [plan] = useState({ name: 'Pro', price: '$9/mo', renewed: 'Nov 2, 2025' });

  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');
  const [toast, setToast] = useState('');

  // accent color removed per request to simplify UI

  const saveChanges = async (area) => {
    setSaving(true);
    setSavedMsg('');
    // simulate async save
    await new Promise((res) => setTimeout(res, 500));

    // persist only the requested area for clarity
    try {
      const stored = JSON.parse(localStorage.getItem('app_settings') || '{}');
      let toSave = { ...stored };
      if (area === 'preferences') {
        toSave = { ...toSave, theme, fontSize, language };
      } else if (area === 'personalization') {
        toSave = { ...toSave, customizationEnabled, personality, customInstructions, about };
      } else if (area === 'profile') {
        toSave = { ...toSave, profile, avatarPreview };
      } else if (area === 'notifications') {
        toSave = { ...toSave, notifications };
      } else if (area === 'integrations') {
        toSave = { ...toSave, apiKeys };
      } else {
        // fallback save all
        toSave = { ...toSave, theme, fontSize, language, customizationEnabled, personality, customInstructions, about, profile, notifications, apiKeys };
      }
      localStorage.setItem('app_settings', JSON.stringify(toSave));
    } catch (e) {
      // ignore
    }

    setSaving(false);
    setToast('Changes saved');
    setTimeout(() => setToast(''), 2200);
  };

  // persist preferences & personalization to localStorage
  useEffect(() => {
    // load saved settings on mount
    try {
      const saved = JSON.parse(localStorage.getItem('app_settings') || '{}');
  if (saved.theme) setTheme(saved.theme);
      if (saved.fontSize) setFontSize(saved.fontSize);
      if (saved.language) setLanguage(saved.language || 'en');
      if (saved.customizationEnabled !== undefined) setCustomizationEnabled(saved.customizationEnabled);
      if (saved.personality) setPersonality(saved.personality);
      if (saved.customInstructions) setCustomInstructions(saved.customInstructions);
      if (saved.about) setAbout(saved.about);
    } catch (e) {
      // ignore
    }
  }, []);

  useEffect(() => {
    // apply theme, font and language
    const root = document.documentElement;
    root.style.setProperty('--app-font-size', fontSize === 'small' ? '13px' : fontSize === 'large' ? '16px' : '14px');

    // theme: light/dark/system (soft toggle)
    if (theme === 'dark') document.documentElement.classList.add('theme-dark');
    else if (theme === 'light') document.documentElement.classList.remove('theme-dark');
    else {
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) document.documentElement.classList.add('theme-dark');
      else document.documentElement.classList.remove('theme-dark');
    }

    // language — apply to document
    try {
      document.documentElement.lang = language || 'en';
    } catch (e) {}

    // persist basic settings
    const toSave = JSON.parse(localStorage.getItem('app_settings') || '{}');
    const merged = {
      ...toSave,
      theme,
      fontSize,
      language,
      customizationEnabled,
      personality,
      customInstructions,
      about,
    };
    localStorage.setItem('app_settings', JSON.stringify(merged));
  }, [theme, fontSize, language, customizationEnabled, personality, customInstructions, about]);

  const handleAvatarUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    setAvatarPreview(url);
  };

  const generateApiKey = () => {
    const id = 'k_' + Math.random().toString(36).slice(2, 10);
    setApiKeys((s) => [{ id, name: 'New key', created: new Date().toISOString().slice(0, 10) }, ...s]);
  };

  const revokeApiKey = (id) => setApiKeys((s) => s.filter((k) => k.id !== id));

  return (
    <div className="settings-page modern">
      <div className="settings-header">
        <button className="profile-back-btn" aria-label="Go back" onClick={() => navigate(-1)}>
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m12 19-7-7 7-7"></path>
            <path d="M19 12H5"></path>
          </svg>
          <span className="profile-back-text">Back</span>
        </button>
        <div className="header-meta">
          <h1 className="gradient-main-heading">Settings</h1>
          <p className="subtitle">Control your account, preferences, security, and integrations.</p>
        </div>
        <div className="save-indicator">
          {saving ? <span className="saving">Saving...</span> : null}
        </div>
        {toast ? <div className="toast">{toast}</div> : null}
      </div>

      <div className="settings-content">
        <div className="settings-panel single-card">
          <div className="section-title gradient-main">
            <div className="title-icon gradient-main-bg"><User size={24} color="white" /></div>
            <h2 className="gradient-main-heading">{t('accountSettings', language)}</h2>
          </div>
          <div className="panel-grid single">
            <div className="card unified-card">
              {/* Profile (unified card content) */}
              <div className="profile-section">
                <div className="profile-grid">
                  <div className="avatar-column">
                    <label className="avatar-upload">
                      <input type="file" accept="image/*" onChange={handleAvatarUpload} />
                      <div className="avatar-preview">
                        {avatarPreview ? <img src={avatarPreview} alt="avatar" /> : <User size={48} />}
                      </div>
                      <div className="avatar-cta">{t('uploadPhoto', language)}</div>
                    </label>
                  </div>
                  <div className="fields-column">
                    <div className="form-row">
                      <label>{t('username', language)}</label>
                      <input value={profile.username} onChange={(e) => setProfile({ ...profile, username: e.target.value })} />
                    </div>
                    <div className="form-row">
                      <label>{t('email', language)}</label>
                      <input value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
                    </div>
                    <div className="form-actions profile-actions">
                      <button className="btn-secondary" onClick={() => {}}>{t('cancel', language)}</button>
                      <button className="btn-primary" onClick={() => saveChanges('profile')}>{t('save', language)}</button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Memory Management Section */}
              <div className="memory-section">
                <h3 className="gradient-subheading">Memory Management</h3>
                <div className="memory-row">
                  <div className="memory-meta">
                    <div><strong>124</strong> items</div>
                    <div className="muted">Capacity: 1024 MB</div>
                  </div>
                  <div className="memory-controls">
                    <div className="muted">Context retention and stored embeddings</div>
                    <div className="memory-actions">
                      <button className="btn-secondary">Clear Memory</button>
                      <button className="btn-secondary">Manage Context</button>
                      <button className="btn-primary">Optimize Retention</button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Usage Statistics Section */}
              <div className="usage-section">
                <h3 className="gradient-subheading">Usage Statistics</h3>
                <div className="usage-row">
                  <div className="usage-meta">
                    <div><strong>42</strong> tasks completed</div>
                    <div className="muted">Last active: Today, 13:12</div>
                  </div>
                </div>
              </div>
              {/* Preferences */}
              <div className="preferences-section">
                <h3 className="gradient-subheading">{t('preferences', language)}</h3>
                <div className="form-row">
                  <label>Theme</label>
                  <select value={theme} onChange={(e) => setTheme(e.target.value)}>
                    <option value="system">System</option>
                    <option value="light">Light</option>
                    <option value="dark">Dark</option>
                  </select>
                </div>
                {/* Accent color removed to simplify UI */}
                <div className="form-row">
                  <label>Font size</label>
                  <select value={fontSize} onChange={(e) => setFontSize(e.target.value)} className="compact-select">
                    <option value="small">Small</option>
                    <option value="medium">Medium</option>
                    <option value="large">Large</option>
                  </select>
                </div>
                <div className="form-row">
                  <label>Language</label>
                  <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                    <option value="en">English</option>
                    <option value="te">Telugu</option>
                    <option value="hi">Hindi</option>
                  </select>
                </div>
                <div className="form-actions">
                  <button className="btn-secondary" onClick={() => {}}>{t('cancel', language)}</button>
                  <button className="btn-primary" onClick={() => saveChanges('preferences')}>{t('save', language)}</button>
                </div>
              </div>
              {/* Notifications */}
              <div className="notifications-section">
                <h3 className="gradient-subheading">{t('notifications', language)}</h3>
                <div className="setting-row"><div><h4>{t('emailNotifications', language)}</h4><p>Receive important emails</p></div><Toggle checked={notifications.email} onChange={(v) => setNotifications({ ...notifications, email: v })} /></div>
                <div className="setting-row"><div><h4>{t('systemNotifications', language)}</h4><p>Show in-app banners</p></div><Toggle checked={notifications.system} onChange={(v) => setNotifications({ ...notifications, system: v })} /></div>
                <div className="setting-row"><div><h4>{t('soundAlerts', language)}</h4><p>Play sounds for new messages</p></div><Toggle checked={notifications.sound} onChange={(v) => setNotifications({ ...notifications, sound: v })} /></div>
                <div className="setting-row"><div><h4>{t('weeklySummary', language)}</h4><p>Receive a weekly summary email</p></div><Toggle checked={notifications.weekly} onChange={(v) => setNotifications({ ...notifications, weekly: v })} /></div>
                <div className="form-actions"><button className="btn-secondary" onClick={() => {}}>{t('cancel', language)}</button><button className="btn-primary" onClick={() => saveChanges('notifications')}>{t('save', language)}</button></div>
              </div>
              {/* Privacy & Security */}
              <div className="privacy-section">
                <h3 className="gradient-subheading">{t('privacy', language)}</h3>
                <div className="setting-row"><div><h4>{t('twoFA', language)}</h4><p>Require 2FA at sign-in</p></div><Toggle checked={twoFA} onChange={setTwoFA} /></div>
                <div className="setting-row"><div><h4>{t('activeSessions', language)}</h4><p>Manage devices where you're signed in</p></div></div>
                <div className="sessions-list">{sessions.map((s) => (<div key={s.id} className="session-item"><div><strong>{s.device}</strong><div className="muted">{s.when} • {s.location}</div></div><button className="btn-ghost" onClick={() => window.alert('Revoked session ' + s.id)}>Revoke</button></div>))}</div>
                <div className="card-actions"><button className="btn-ghost" onClick={() => window.alert('Download request placeholder')}>Request data download</button><button className="btn-ghost" onClick={() => { if (window.confirm('Clear chat history?')) window.alert('Cleared (placeholder)'); }}>Clear chat history</button></div>
              </div>
              {/* Personalization */}
              <div className="personalization-section">
                <h3 className="gradient-subheading">Personalization</h3>
                <div className="personalization-row">
                  <div>
                    <div style={{fontWeight:600}}>Enable customization</div>
                    <div className="muted">Customize how the assistant responds to you.</div>
                  </div>
                  <Toggle checked={customizationEnabled} onChange={setCustomizationEnabled} />
                </div>

                <div style={{marginTop:12}}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                    <div style={{fontWeight:600}}>Assistant personality</div>
                    <select value={personality} onChange={(e) => setPersonality(e.target.value)}>
                      <option value="default">Default</option>
                      <option value="formal">Formal</option>
                      <option value="casual">Casual</option>
                    </select>
                  </div>
                  <div className="muted" style={{marginTop:6}}>Set the style and tone the assistant uses when responding.</div>
                </div>

                <div style={{marginTop:12}}>
                  <div style={{fontWeight:600}}>Custom instructions</div>
                  <textarea className="custom-instructions" value={customInstructions} onChange={(e) => setCustomInstructions(e.target.value)} placeholder="Additional behavior, style, and tone preferences" />
                </div>

                <div style={{marginTop:16}}>
                  <h4>About you</h4>
                  <div className="form-row">
                    <label>Nickname</label>
                    <input className="about-input" value={about.nickname} onChange={(e) => setAbout({...about, nickname: e.target.value})} placeholder="What should we call you?" />
                  </div>
                  <div className="form-row" style={{marginTop:8}}>
                    <label>Occupation</label>
                    <input className="about-input" value={about.occupation} onChange={(e) => setAbout({...about, occupation: e.target.value})} placeholder="Your job or role (optional)" />
                  </div>
                </div>

                <div className="form-actions" style={{marginTop:12}}>
                  <button className="btn-secondary" onClick={() => {}}>Cancel</button>
                  <button className="btn-primary" onClick={() => saveChanges('personalization')}>Save personalization</button>
                </div>
              </div>
              {/* About / Support */}
              <div className="about-section">
                <h3 className="gradient-subheading">{t('aboutSupport', language)}</h3>
                <div className="about-row"><div><strong>App version</strong><div className="muted">v1.4.2</div></div><div><button className="btn-ghost" onClick={() => alert('Contact support placeholder')}>{t('contactSupport', language)}</button></div></div>
                <div className="links-row"><a href="/terms" target="_blank" rel="noreferrer">{t('terms', language)}</a><a href="/privacy" target="_blank" rel="noreferrer">{t('privacyPolicy', language)}</a><a href="#" onClick={() => alert('Report bug placeholder')}>{t('reportBug', language)}</a></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
