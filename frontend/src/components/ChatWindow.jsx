import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { Send, Mic, Plus, Camera, Image as ImageIcon, File, Copy, ThumbsUp, ThumbsDown, Share2, Edit2, X, ArrowDown, Check, Square, Highlighter, Play, Bot } from 'lucide-react';
import '../styles/ChatWindow.css';
import ThinkingProcess from './ThinkingProcess';
import chatService from '../services/chatService';
import sessionService from '../services/sessionService';
import AIMessage from './AIMessage';
import VideoEmbed from './VideoEmbed';
import highlightService from '../services/highlightService';
import sessionCache from '../services/sessionCache';
import realtime from '../services/realtimeClient';
// No client-side YouTube auto-embed: we rely on backend-provided video payloads only.



// Simple chat window component based on the provided design
const ChatWindow = ({ chatId, onToggleSidebar }) => {
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const [isFetching, setIsFetching] = useState(false); // loading overlay for fetch/new chat
  const [loaderText, setLoaderText] = useState('Fetching your conversation…');
  const [, setError] = useState(''); // retained setter only; no top banner
  const [inputValue, setInputValue] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [hoveredMessage, setHoveredMessage] = useState(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState(null);
  const [speechState, setSpeechState] = useState({ messageId: null, isPlaying: false });
  const [showToast, setShowToast] = useState({ show: false, message: '' });
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const topSentinelRef = useRef(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);
  const imageInputRef = useRef(null);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const thinkingCancelRef = useRef(null);
  const thinkingStartRef = useRef(null);
  // Map message.id -> ref for AIMessage instances so we can open highlights panel from action bar
  const aiMessageRefs = useRef({});
  const [messageIndicators, setMessageIndicators] = useState({}); // id -> {hasMini, hasHighlights}
  const currentSessionIdRef = useRef(null);

  const quote = 'The future belongs to those who believe in the beauty of their dreams.';

  // In-memory cache for session histories to make switching instant
  const historyCacheRef = useRef(new Map()); // legacy local cache (kept for hot state); global cache used via sessionCache
  const currentLoadAbortRef = useRef(null);

  const scrollToBottom = useCallback((behavior = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadHistory = async (sid) => {
  setError('');
      setLoaderText('Fetching your conversation…');
      setIsFetching(true);
      // Abort any previous in-flight history fetch
      try { currentLoadAbortRef.current?.abort?.(); } catch {}
      const ac = new AbortController();
      currentLoadAbortRef.current = ac;
      try {
  // Immediately bind the selected session id to avoid races with send()
  setSessionId(sid);
  currentSessionIdRef.current = sid;
        // Serve instantly from cache if present
        // 1) Serve instantly from global session cache if present
        const globalCached = sessionCache.get(sid);
        if (globalCached && Array.isArray(globalCached.messages)) {
          setMessages(globalCached.messages);
          setHasMore(!!globalCached.hasMore);
          setNextOffset(typeof globalCached.offset === 'number' ? globalCached.offset : 0);
          // Soft hide loader for instant feel
          setTimeout(() => { if (!cancelled) setIsFetching(false); }, 40);
        } else {
          // Fallback to ephemeral cache (component-level) if any
          const cached = historyCacheRef.current.get(sid);
          if (cached && Array.isArray(cached.messages)) {
            setMessages(cached.messages);
            setTimeout(() => { if (!cancelled) setIsFetching(false); }, 40);
          }
        }
        // Prefer chatService.getSessionHistory if available on backend; fallback to sessionService.getSessionMessages
        let res;
        try {
          res = await chatService.getSessionHistory(sid, { limit: 100, offset: 0, signal: ac.signal });
        } catch {
          res = await sessionService.getSessionMessages(sid, { limit: 100, offset: 0, signal: ac.signal });
        }
        const data = res?.data;
        // Normalize various possible response shapes
        const msgs = Array.isArray(data?.messages) ? data.messages : Array.isArray(data) ? data : (data?.items || []);
        const withDay = (d) => {
          try {
            const dt = d ? new Date(d) : new Date();
            const now = new Date();
            const dayKey = dt.toISOString().slice(0,10);
            const isToday = dt.toDateString() === now.toDateString();
            const yest = new Date(now);
            yest.setDate(now.getDate() - 1);
            const isYesterday = dt.toDateString() === yest.toDateString();
            const dayLabel = isToday ? 'Today' : isYesterday ? 'Yesterday' : dt.toLocaleDateString();
            return { dayKey, dayLabel };
          } catch {
            const dt = new Date();
            return { dayKey: dt.toISOString().slice(0,10), dayLabel: 'Today' };
          }
        };

        const isLikelyObjectId = (v) => typeof v === 'string' && /^[a-f\d]{24}$/i.test(v);
        let normalized = msgs.map((m, idx) => {
          const dmeta = withDay(m.created_at);
          const backendId = (typeof m._id === 'string' && m._id) || (typeof m.id === 'string' && m.id) || null;
          return ({
          id: m.id || m._id || `${sid}-${idx}`,
          backendId,
          type: (m.sender === 'assistant' || m.role === 'assistant' || m.role === 'ai') ? 'ai' : 'user',
          content: m.content || m.text || m.message || '',
          annotatedHtml: m.annotatedHtml || null,
          highlights: Array.isArray(m.highlights) ? m.highlights : [],
          timestamp: m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) :
                     new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          dayKey: dmeta.dayKey,
          dayLabel: dmeta.dayLabel,
          status: m.status || (m.sender ? 'delivered' : 'sent')
        })}).filter((m) => m.content);
        // Hydrate missing annotations by fetching per-message from backend (best-effort)
        try {
          const fetches = normalized
            .filter((m) => m.type === 'ai' && !m.annotatedHtml && isLikelyObjectId(m.backendId) && isLikelyObjectId(sid))
            .map(async (m) => {
              try {
                const r = await highlightService.getMessage(sid, m.backendId);
                const d = r?.data;
                if (d?.annotatedHtml) {
                  return { backendId: m.backendId, annotatedHtml: d.annotatedHtml, highlights: Array.isArray(d.highlights) ? d.highlights : [] };
                }
              } catch {}
              return null;
            });
          const results = await Promise.all(fetches);
          const byId = new Map();
          results.forEach((r) => { if (r && r.backendId) byId.set(r.backendId, r); });
          if (byId.size > 0) {
            normalized = normalized.map((m) => byId.has(m.backendId) ? { ...m, ...byId.get(m.backendId) } : m);
          }
        } catch {}
        if (!cancelled) {
          // Merge with any messages that might have been added while fetching (avoid wiping optimistic ones)
          setMessages((prev) => {
            // Build a map by message signature (id or content+type+timestamp) to de-dup
            const keyOf = (m) => m.id || `${m.type}|${m.content}|${m.timestamp}`;
            const seen = new Set();
            const merged = [];
            // First, older (fetched, which are chronological), then existing that aren't present
            for (const m of normalized) {
              const k = keyOf(m);
              if (!seen.has(k)) { seen.add(k); merged.push(m); }
            }
            for (const m of prev) {
              const k = keyOf(m);
              if (!seen.has(k)) { seen.add(k); merged.push(m); }
            }
            return merged;
          });
          const total = typeof data?.total === 'number' ? data.total : (data?.totalMessages || normalized.length);
          const has_more = !!(data?.has_more || (total > normalized.length));
          setHasMore(has_more);
          setNextOffset(typeof data?.offset === 'number' ? data.offset + (data?.limit || normalized.length) : normalized.length);
          // Update both local and global caches
          // Reuse merged view for caches to keep parity with UI
          const mergedForCache = (Array.isArray(normalized) ? normalized : []).slice();
          historyCacheRef.current.set(sid, { messages: mergedForCache, ts: Date.now() });
          sessionCache.set(sid, { messages: mergedForCache, total, hasMore: has_more, limit: data?.limit, offset: data?.offset });
          // Smooth scroll to bottom once after load
          requestAnimationFrame(() => scrollToBottom('auto'));
        }
      } catch (e) {
        if (!cancelled) {
          const msg = e?.response?.data?.detail || e?.message || 'Failed to load conversation';
          const errMessage = {
            id: `hist-err-${Date.now()}`,
            type: 'ai',
            content: `Could not load this conversation. ${msg}`,
            isError: true,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            dayKey: new Date().toISOString().slice(0,10),
            dayLabel: 'Today',
          };
          setMessages([errMessage]);
          setSessionId(sid);
        }
      } finally {
        if (!cancelled) setIsFetching(false);
      }
    };

    if (chatId && typeof chatId === 'string' && chatId.trim() !== '') {
      // Treat chatId as a backend session id
      currentSessionIdRef.current = chatId;
      loadHistory(chatId);
    } else {
      // New chat created: briefly show a setup loader to make the transition feel intentional
      setMessages([]);
  setSessionId(null);
  currentSessionIdRef.current = null;
      setError('');
      setLoaderText('Setting up your chat…');
      setIsFetching(true);
      const t = setTimeout(() => {
        if (!cancelled) setIsFetching(false);
      }, 700);
      return () => { cancelled = true; clearTimeout(t); };
    }

    return () => { cancelled = true; try { currentLoadAbortRef.current?.abort?.(); } catch {} };
  }, [chatId, scrollToBottom]);

  useEffect(() => {
    scrollToBottom('smooth');
  }, [messages, scrollToBottom]);

  // Keep a ref of the latest active session id for realtime handler comparisons
  useEffect(() => {
    currentSessionIdRef.current = sessionId || (typeof chatId === 'string' && chatId.trim() ? chatId : null);
  }, [sessionId, chatId]);

  // Realtime: append incoming messages for the active session
  useEffect(() => {
    const off = realtime.on('message.appended', (payload) => {
      try {
        const sid = payload?.sessionId;
        const active = currentSessionIdRef.current;
        if (!sid || !active || sid !== active) return;
        const arr = Array.isArray(payload?.messages) ? payload.messages : [];
        if (!arr.length) return;
        const now = new Date();
        const normalize = (m, idx) => {
          const content = m.content || m.text || '';
          const role = (m.role || m.sender || '').toLowerCase();
          const type = role === 'assistant' || role === 'ai' ? 'ai' : 'user';
          const created = m.created_at ? new Date(m.created_at) : now;
          const dk = created.toISOString().slice(0,10);
          const dayLabel = (() => {
            const today = new Date();
            const y = new Date(today); y.setDate(today.getDate() - 1);
            if (created.toDateString() === today.toDateString()) return 'Today';
            if (created.toDateString() === y.toDateString()) return 'Yesterday';
            return created.toLocaleDateString();
          })();
          const id = m.id || m._id || `${sid}-sse-${Date.now()}-${idx}`;
          return {
            id,
            type,
            content,
            timestamp: created.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            dayKey: dk,
            dayLabel,
            status: type === 'user' ? 'delivered' : undefined,
          };
        };
        const inc = arr.map(normalize).filter(x => x.content);
        if (!inc.length) return;
        setMessages((prev) => {
          const seen = new Set(prev.map(m => m.id));
          // Also create a lightweight signature to avoid dupes when ids differ but content identical in immediate succession
          const sigSeen = new Set(prev.map(m => `${m.type}|${m.content}`));
          const merged = [...prev];
          for (const m of inc) {
            const sig = `${m.type}|${m.content}`;
            if (!seen.has(m.id) && !sigSeen.has(sig)) {
              seen.add(m.id);
              sigSeen.add(sig);
              merged.push(m);
            }
          }
          return merged;
        });
        // Update cache
        try { sessionCache.append(sid, inc); } catch {}
        // Nudge scroll
        requestAnimationFrame(() => scrollToBottom('auto'));
      } catch {}
    });
    return () => { try { off?.(); } catch {} };
  }, [scrollToBottom]);

  // Broadcast whether the current chat window has any messages so Sidebar can gate "New Chat"
  useEffect(() => {
    const hasContent = Array.isArray(messages) && messages.length > 0;
    try {
      localStorage.setItem('maya_chat_has_content', hasContent ? '1' : '0');
      window.dispatchEvent(new CustomEvent('maya:chat-has-content', { detail: { hasContent } }));
    } catch {}
  }, [messages]);

  // Show FAB when scrolled up
  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const onScroll = () => {
      const threshold = 80;
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
      setShowScrollToBottom(!atBottom && messages.length > 0);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => el.removeEventListener('scroll', onScroll);
  }, [messages.length]);

  // Lazy load older messages when the user scrolls to the top sentinel
  useEffect(() => {
    if (!sessionId) return;
    const el = messagesContainerRef.current;
    const sentinel = topSentinelRef.current;
    if (!el || !sentinel) return;
    let loadingOlder = false;

    const io = new IntersectionObserver(async (entries) => {
      const e = entries[0];
      if (!e || !e.isIntersecting) return;
      if (loadingOlder || !hasMore) return;
      loadingOlder = true;
      try {
        const prevScrollHeight = el.scrollHeight;
        // Determine next page using offset; backend returns slice by offset,limit
        const limit = 100;
        const offset = nextOffset;
        let res;
        try {
          res = await chatService.getSessionHistory(sessionId, { limit, offset });
        } catch {
          res = await sessionService.getSessionMessages(sessionId, { limit, offset });
        }
        const data = res?.data;
        const raw = Array.isArray(data?.messages) ? data.messages : [];
        const older = raw.map((m, idx) => {
          const d = m.created_at ? new Date(m.created_at) : new Date();
          const now = new Date();
          const yest = new Date(now); yest.setDate(now.getDate() - 1);
          const isToday = d.toDateString() === now.toDateString();
          const isY = d.toDateString() === yest.toDateString();
          const dayLabel = isToday ? 'Today' : isY ? 'Yesterday' : d.toLocaleDateString();
          return {
            id: m.id || m._id || `${sessionId}-${offset + idx}`,
            type: (m.sender === 'assistant' || m.role === 'assistant' || m.role === 'ai') ? 'ai' : 'user',
            content: m.content || m.text || m.message || '',
            annotatedHtml: m.annotatedHtml || null,
            highlights: Array.isArray(m.highlights) ? m.highlights : [],
            timestamp: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            dayKey: d.toISOString().slice(0,10),
            dayLabel,
            status: m.status || (m.sender ? 'delivered' : 'sent'),
          };
        }).filter(m => m.content);
        if (older.length) {
          // Prepend and maintain scroll position
          setMessages(prev => [...older, ...prev]);
          sessionCache.prepend(sessionId, older, offset + older.length);
          setNextOffset(offset + (data?.limit || older.length));
          setHasMore(!!data?.has_more && (data.total > offset + older.length));
          // Restore scroll position so content doesn't jump
          requestAnimationFrame(() => {
            const newScrollHeight = el.scrollHeight;
            const delta = newScrollHeight - prevScrollHeight;
            el.scrollTop = el.scrollTop + delta;
          });
        } else {
          setHasMore(false);
        }
      } catch (err) {
        // best-effort: stop trying further
        setHasMore(false);
      } finally {
        loadingOlder = false;
      }
    }, { root: el, threshold: 0 });

    io.observe(sentinel);
    return () => io.disconnect();
  }, [sessionId, hasMore, nextOffset]);

  const handleSend = async () => {
  const content = inputValue.trim();
    if (!content && attachments.length === 0) return;

    // Push user message immediately (optimistic UI)
    const userMsg = {
      id: `${Date.now()}`,
      type: 'user',
      content,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      dayKey: new Date().toISOString().slice(0,10),
      dayLabel: 'Today',
      status: 'sent',
      attachments: attachments.length > 0 ? [...attachments] : undefined,
    };
    setMessages((prev) => [...prev, userMsg]);
    // Optimistically update cache with the user message if session id is known
    try {
      const sidForCache = sessionId || (typeof chatId === 'string' && chatId.trim() ? chatId : null);
      if (sidForCache) {
        sessionCache.append(sidForCache, [userMsg]);
      }
    } catch {}
    setInputValue('');
    setAttachments([]);
    const sentId = userMsg.id;
    thinkingStartRef.current = performance.now();
    setIsSending(true);
    setError('');
    // keep view anchored
    scrollToBottom('auto');

    // No client-side auto-embed; wait for backend to respond with a video payload

    try {
      let resp;
      // Use the most up-to-date session id: prefer internal state, else the active chatId prop
      const effectiveSessionId = sessionId || (typeof chatId === 'string' && chatId.trim() ? chatId : null);
      if (!effectiveSessionId) {
        // Start a new backend chat session with the first message
        resp = await chatService.startNewChat(content);
        const data = resp?.data || {};
        const sid = data.session_id || data.sessionId || data.id;
        const reply = data.response_text || data.reply || data.content || '';
        const aiMessageId = data.ai_message_id || data.aiMessageId || null;
        if (sid) {
          setSessionId(sid);
          try { localStorage.setItem('maya_active_session_id', sid); } catch {}
          try {
            window.dispatchEvent(new CustomEvent('maya:active-session', { detail: { id: sid } }));
            window.dispatchEvent(new CustomEvent('maya:sessions:refresh'));
          } catch {}
          // Seed cache for the new session with the user message we just sent
          try { sessionCache.append(sid, [userMsg]); } catch {}
        }
        if (reply) {
          const info = extractReminderInfoFromReply(reply);
          if (info) {
            showToastNotification(`Reminder set: ${info.title} at ${info.when}`);
            // Notify other views (Tasks sidebar/page) to refresh immediately
            try { window.dispatchEvent(new CustomEvent('maya:tasks-updated')); } catch {}
            try { const bc = new BroadcastChannel('maya_tasks'); bc.postMessage({ type: 'created', ts: Date.now() }); bc.close?.(); } catch {}
          }
          const genMs = thinkingStartRef.current ? performance.now() - thinkingStartRef.current : undefined;
          const aiMsg = {
            id: aiMessageId || `${Date.now()}-ai`,
            type: 'ai',
            content: reply,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            dayKey: new Date().toISOString().slice(0,10),
            dayLabel: 'Today',
            generationMs: genMs
          };
          setMessages((prev) => [...prev, aiMsg]);
          // Seed/append cache for the new session so switching away/back is instant
          if (sid) {
            sessionCache.append(sid, [aiMsg]);
          }
          // If backend returned a confident video pick, append exactly one video message
          const v = data?.video;
          if (v && v.videoId) {
            const ytMsg = {
              id: `yt_${Date.now()}`,
              type: 'ai',
              content: v.title || 'Video',
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              dayKey: new Date().toISOString().slice(0,10),
              dayLabel: 'Today',
              youtube: { videoId: v.videoId, title: v.title, autoplay: true }
            };
            setMessages((prev) => [...prev, ytMsg]);
          }
        }
      } else {
        // Continue existing session
        resp = await chatService.sendMessage(effectiveSessionId, content);
        const data = resp?.data || {};
        const reply = data.response_text || data.reply || data.content || '';
        const aiMessageId = data.ai_message_id || data.aiMessageId || null;
        if (reply) {
          const info = extractReminderInfoFromReply(reply);
          if (info) {
            showToastNotification(`Reminder set: ${info.title} at ${info.when}`);
            try { window.dispatchEvent(new CustomEvent('maya:tasks-updated')); } catch {}
            try { const bc = new BroadcastChannel('maya_tasks'); bc.postMessage({ type: 'created', ts: Date.now() }); bc.close?.(); } catch {}
          }
          const genMs = thinkingStartRef.current ? performance.now() - thinkingStartRef.current : undefined;
          const aiMsg = {
            id: aiMessageId || `${Date.now()}-ai`,
            type: 'ai',
            content: reply,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            dayKey: new Date().toISOString().slice(0,10),
            dayLabel: 'Today',
            generationMs: genMs
          };
          setMessages((prev) => [...prev, aiMsg]);
          // Let sidebar refresh session list (message counts, updatedAt) quickly
          try { window.dispatchEvent(new CustomEvent('maya:sessions:refresh')); } catch {}
          // Update cache for this session
          sessionCache.append(effectiveSessionId, [aiMsg]);
          const v = data?.video;
          if (v && v.videoId) {
            const ytMsg = {
              id: `yt_${Date.now()}`,
              type: 'ai',
              content: v.title || 'Video',
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              dayKey: new Date().toISOString().slice(0,10),
              dayLabel: 'Today',
              youtube: { videoId: v.videoId, title: v.title, autoplay: true }
            };
            setMessages((prev) => [...prev, ytMsg]);
          }
        }
      }
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || 'Network error while sending';
      // Mark last user message as failed and append an inline error bubble
      setMessages((prev) => {
        const updated = prev.map((m) => m.id === sentId ? { ...m, status: 'failed' } : m);
        const errMsg = {
          id: `err-${Date.now()}`,
          type: 'ai',
          content: msg,
          isError: true,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          dayKey: new Date().toISOString().slice(0,10),
          dayLabel: 'Today',
        };
        return [...updated, errMsg];
      });
    } finally {
      // Stop the thinking animation (if still running) then hide overlay
      try { thinkingCancelRef.current && thinkingCancelRef.current(); } catch {}
      setIsSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = (e, type) => {
    const files = e.target.files;
    if (files) {
      Array.from(files).forEach((file) => {
        const url = URL.createObjectURL(file);
        setAttachments((prev) => [...prev, { type, url, name: file.name }]);
      });
    }
    setShowAttachMenu(false);
  };

  const removeAttachment = (index) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleMicClick = () => {
    setIsRecording((prev) => !prev);
    if (!isRecording) {
      setTimeout(() => {
        setIsRecording(false);
      }, 3000);
    }
  };

  const handleCopy = (content, messageId) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      setTimeout(() => setCopiedMessageId(null), 1500);
    }
  };

  const handleSpeak = (content, messageId) => {
    try {
      if (speechState.isPlaying && speechState.messageId === messageId) {
        // Stop current speech
        window.speechSynthesis.cancel();
        setSpeechState({ messageId: null, isPlaying: false });
      } else {
        // Start new speech
        window.speechSynthesis.cancel(); // Stop any ongoing speech
        const utterance = new SpeechSynthesisUtterance(content);
        utterance.onstart = () => setSpeechState({ messageId, isPlaying: true });
        utterance.onend = () => setSpeechState({ messageId: null, isPlaying: false });
        utterance.onerror = () => setSpeechState({ messageId: null, isPlaying: false });
        window.speechSynthesis.speak(utterance);
      }
    } catch (e) {
      // no-op
    }
  };

  // Manual YouTube trigger removed to avoid duplicate embeds; rely on backend video payloads only.

  const handleFeedback = (messageId, type) => {
    const message = type === 'up' ? 'Thanks for your positive feedback!' : 'Thanks for your feedback!';
    setShowToast({ show: true, message });
    setTimeout(() => setShowToast({ show: false, message: '' }), 3000);
    
    // Here you could also send feedback to your backend
    // feedbackService.submitFeedback(messageId, type);
  };

  const showToastNotification = (message) => {
    setShowToast({ show: true, message });
    setTimeout(() => setShowToast({ show: false, message: '' }), 3000);
  };

  // Parse reminder confirmation appended by backend in AI reply
  const extractReminderInfoFromReply = useCallback((replyText) => {
    if (!replyText) return null;
    try {
      const idx = replyText.lastIndexOf("I've set a reminder:");
      if (idx === -1) return null;
      const tail = replyText.slice(idx);
    // Example: "I've set a reminder: Drink water at 2025-01-01 09:30 UTC. You'll get an email then."
  const m = tail.match(/I've set a reminder:\s*(.+?)\s+at\s+([^.\n]+)\./i);
      if (m && m[1] && m[2]) return { title: m[1].trim(), when: m[2].trim() };
      const m2 = tail.match(/I've set a reminder:\s*(.+?)\s+at\s+([^\n]+)/i);
      if (m2 && m2[1] && m2[2]) return { title: m2[1].trim(), when: m2[2].trim() };
    } catch {}
    return null;
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    const ta = inputRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(180, ta.scrollHeight) + 'px';
  }, [inputValue]);

  // Prepare messages with date dividers
  const itemsWithDividers = useMemo(() => {
    const out = [];
    let lastKey = null;
    for (const m of messages) {
      const dk = m.dayKey || new Date().toISOString().slice(0,10);
      if (dk !== lastKey) {
        out.push({ kind: 'divider', key: dk, label: m.dayLabel || new Date().toLocaleDateString() });
        lastKey = dk;
      }
      out.push({ kind: 'message', data: m });
    }
    return out;
  }, [messages]);

  return (
    <div className="chat-window">
      {/* Toast Notification */}
      {showToast.show && (
        <div className="toast-notification">
          {showToast.message}
        </div>
      )}

      <div className="chat-header chat-header--compact">
        <div className="chat-header-left">
          <h1 className="chat-title">Aurion</h1>
        </div>
        <button className="share-icon-btn" aria-label="Share conversation" title="Share">
          <Share2 size={18} />
        </button>
      </div>

      <div className="chat-messages" role="log" aria-live="polite" aria-relevant="additions" ref={messagesContainerRef}>
        {messages.length === 0 ? (
          <div className="welcome-screen">
            <div className="welcome-logo">A</div>
            <h1 className="welcome-title">Welcome to Aurion</h1>
            <p className="welcome-quote">"{quote}"</p>
            <p className="welcome-subtitle">Start a conversation to begin your journey</p>
          </div>
        ) : (
          <>
            {/* top-level banner error removed; errors render inline as message bubbles */}
            {itemsWithDividers.map((item, idx) => item.kind === 'divider' ? (
              <div key={`div-${item.key}-${idx}`} className="date-divider" aria-label={item.label}>
                <span>{item.label}</span>
              </div>
            ) : (
              (() => { const message = item.data; 
                const videoId = message?.youtube?.videoId || null;
                const isUser = message.type === 'user';
                const isAI = message.type === 'ai';
                return (
              <div
                key={message.id}
                className={`message ${message.type} ${isUser && message.status === 'failed' ? 'failed' : ''}`}
                onMouseEnter={() => setHoveredMessage(message.id)}
                onMouseLeave={() => setHoveredMessage(null)}
              >
                <div className={`message-bubble ${isAI && message.isError ? 'error' : ''}`}>
                  {message.attachments && message.attachments.length > 0 && (
                    <div className="message-attachments">
                      {message.attachments.map((att, idx) => (
                        <div key={idx} className="attachment-preview">
                          {att.type === 'image' ? (
                            <img src={att.url} alt={att.name} />
                          ) : (
                            <div className="file-preview">
                              <File size={24} />
                              <span>{att.name}</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="message-content">
                    {message.type === 'ai' ? (
                      <AIMessage
                        ref={(el) => { if (el) aiMessageRefs.current[message.id] = el; else delete aiMessageRefs.current[message.id]; }}
                        sessionId={sessionId}
                        message={message}
                        onUpdated={(delta) => {
                          setMessages((prev) => prev.map((mm) => mm.id === message.id ? { ...mm, ...delta } : mm));
                        }}
                        onIndicatorsChange={(id, flags) => setMessageIndicators((prev) => {
                          const mid = id || message.id;
                          const cur = prev[mid];
                          if (cur && cur.hasMini === flags.hasMini && cur.hasHighlights === flags.hasHighlights) {
                            return prev; // no change -> avoid re-render loop
                          }
                          return { ...prev, [mid]: flags };
                        })}
                      />
                    ) : (
                      <p>{message.content}</p>
                    )}
                    {videoId ? (
                      <div className="video-embed-container">
                        <VideoEmbed videoId={videoId} autoplay />
                      </div>
                    ) : null}
                  </div>
                  <span className="message-timestamp" aria-label={`Sent at ${message.timestamp}${message.generationMs ? ` • generated in ${(message.generationMs/1000).toFixed(1)} seconds` : ''}`}>
                    {message.timestamp}
                    {message.generationMs && (
                      <span className="gen-time" title={`Generated in ${(message.generationMs/1000).toFixed(2)}s`}>
                        {' '}• {(message.generationMs/1000).toFixed(1)}s
                      </span>
                    )}
                    {message.type === 'user' && (
                      <span className="message-status" title={message.status || 'sent'}>
                        {message.status === 'delivered' ? ' ✓✓' : ' ✓'}
                      </span>
                    )}
                  </span>
                </div>
                {/* Removed manual Play on YouTube to prevent duplicate embeds */}
                {/* Corner icons at top-left of the message (outside bubble) */}
                {message.type === 'ai' && (messageIndicators[message.id]?.hasMini || messageIndicators[message.id]?.hasHighlights) && (
                  <div className="message-corner-icons outer" aria-hidden={false}>
                    {messageIndicators[message.id]?.hasMini && (
                      <button
                        className="mini-pinned"
                        title="Open Mini Agent"
                        aria-label="Open Mini Agent"
                        onClick={() => aiMessageRefs.current[message.id]?.openMiniAgent()}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                          <defs>
                            <linearGradient id={`miniGrad-${message.id}`} x1="0" y1="0" x2="1" y2="1">
                              <stop offset="0%" stopColor="#1976d2" />
                              <stop offset="100%" stopColor="#4caf50" />
                            </linearGradient>
                          </defs>
                          <rect x="5" y="7" width="14" height="10" rx="5" stroke={`url(#miniGrad-${message.id})`} strokeWidth="2" />
                          <circle cx="10" cy="12" r="1.5" fill="#1976d2" />
                          <circle cx="14" cy="12" r="1.5" fill="#1976d2" />
                          <path d="M12 5v2" stroke="#1976d2" strokeWidth="2" strokeLinecap="round" />
                        </svg>
                      </button>
                    )}
                    {messageIndicators[message.id]?.hasHighlights && (
                      <button
                        className="hl-pinned"
                        title="Manage highlights"
                        aria-label="Manage highlights"
                        onClick={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect();
                          aiMessageRefs.current[message.id]?.openHighlightsAt(rect.left, rect.bottom + 6);
                        }}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                          <defs>
                            <linearGradient id={`hlGrad-${message.id}`} x1="0" y1="0" x2="1" y2="1">
                              <stop offset="0%" stopColor="#ffc107" />
                              <stop offset="100%" stopColor="#ff9800" />
                            </linearGradient>
                          </defs>
                          <path d="M12 3l2.472 4.91 5.428.79-3.93 3.83.928 5.41L12 16.77l-4.898 2.17.928-5.41L4.1 8.7l5.428-.79L12 3z" stroke={`url(#hlGrad-${message.id})`} strokeWidth="1.6" fill="rgba(255,193,7,0.15)"/>
                        </svg>
                      </button>
                    )}
                  </div>
                )}

                {/* Message Actions Toolbar */}
                {hoveredMessage === message.id && (
                  <div className={`message-actions ${isUser ? 'user-actions' : 'ai-actions'}`}>
                      <button 
                        onClick={() => handleCopy(message.content, message.id)} 
                        title="Copy"
                        className={`action-btn copy ${copiedMessageId === message.id ? 'copied' : ''}`}
                      >
                        {copiedMessageId === message.id ? <Check size={16} /> : <Copy size={16} />}
                      </button>
                      <button 
                        onClick={() => handleSpeak(message.content, message.id)} 
                        title={speechState.isPlaying && speechState.messageId === message.id ? "Stop" : "Speak"}
                        className="action-btn speak"
                      >
                        {speechState.isPlaying && speechState.messageId === message.id ? 
                          <Square size={16} /> : <Play size={16} />}
                      </button>
                      {isAI && (
                        <button
                          title="Manage highlights"
                          aria-label="Manage highlights"
                          className="action-btn manage-highlights"
                          onClick={(e) => {
                            const rect = e.currentTarget.getBoundingClientRect();
                            aiMessageRefs.current[message.id]?.openHighlightsAt(rect.left, rect.bottom + 6);
                          }}
                        >
                          <Highlighter size={16} />
                        </button>
                      )}
                      {isAI && (
                        <button
                          title="Mini Agent"
                          aria-label="Open Mini Agent"
                          className="action-btn agent"
                          onClick={() => aiMessageRefs.current[message.id]?.openMiniAgent()}
                        >
                          <Bot size={16} />
                        </button>
                      )}
                      {isUser ? (
                        <button title="Edit" className="action-btn">
                          <Edit2 size={16} />
                        </button>
                      ) : (
                        <>
                          <button 
                            onClick={() => handleFeedback(message.id, 'up')} 
                            title="Good response" 
                            className="action-btn good"
                          >
                            <ThumbsUp size={16} />
                          </button>
                          <button 
                            onClick={() => handleFeedback(message.id, 'down')} 
                            title="Poor response" 
                            className="action-btn bad"
                          >
                            <ThumbsDown size={16} />
                          </button>
                          
                          <button title="Share" className="action-btn share">
                            <Share2 size={16} />
                          </button>
                        </>
                      )}
                  </div>
                )}
              </div>
              ); })()
            ))}
            {isSending && (
              <ThinkingProcess
                onComplete={() => { /* Additional hook: e.g., prepare streaming */ }}
                developerMode={false}
                cancelRef={thinkingCancelRef}
                loop={true}
                variant="inline"
                startTime={thinkingStartRef.current}
              />
            )}
            <div ref={messagesEndRef} />
          </>
  )}
  {/* Top sentinel for lazy-loading older messages */}
  <div ref={topSentinelRef} style={{ height: 1 }} />
  {/* Fetching overlay: covers messages area until data is ready */}
        <div className={`chat-loading-overlay ${isFetching ? 'show' : ''}`} aria-live="polite" role="status">
          <div className="loader-card" aria-hidden={!isFetching}>
            <div className="typing-dots" aria-label={loaderText}>
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
            <div className="loader-text">{loaderText}</div>
            <div className="loader-progress" aria-hidden="true" />
            {/* Optional skeleton rows for visual richness */}
            <div className="skeleton-lines" aria-hidden="true">
              <div className="skeleton-line" style={{ width: '72%' }} />
              <div className="skeleton-line" style={{ width: '54%' }} />
              <div className="skeleton-line" style={{ width: '64%' }} />
            </div>
          </div>
        </div>
        {showScrollToBottom && (
          <button className="scroll-to-bottom" onClick={() => scrollToBottom('smooth')} aria-label="Scroll to latest">
            <ArrowDown size={18} />
          </button>
        )}
      </div>


      <div className="chat-input-container">
        {attachments.length > 0 && (
          <div className="attachments-preview">
            {attachments.map((att, idx) => (
              <div key={idx} className="attachment-item">
                {att.type === 'image' ? (
                  <img src={att.url} alt={att.name} />
                ) : (
                  <div className="file-item">
                    <File size={20} />
                    <span>{att.name}</span>
                  </div>
                )}
                <button className="remove-attachment" onClick={() => removeAttachment(idx)}>
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="chat-input-wrapper">
          <div className="input-actions-left">
            <button className="action-btn attach-btn" onClick={() => setShowAttachMenu(!showAttachMenu)}>
              <Plus size={20} />
            </button>

            {showAttachMenu && (
              <div className="attach-menu">
                <button onClick={() => imageInputRef.current?.click()}>
                  <Camera size={18} />
                  <span>Camera</span>
                </button>
                <button onClick={() => imageInputRef.current?.click()}>
                  <ImageIcon size={18} />
                  <span>Photos</span>
                </button>
                <button onClick={() => fileInputRef.current?.click()}>
                  <File size={18} />
                  <span>Files</span>
                </button>
              </div>
            )}

            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              multiple
              style={{ display: 'none' }}
              onChange={(e) => handleFileSelect(e, 'image')}
            />
            <input
              ref={fileInputRef}
              type="file"
              multiple
              style={{ display: 'none' }}
              onChange={(e) => handleFileSelect(e, 'file')}
            />
          </div>

          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder="Type your message..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
          />

          <div className="input-actions-right">
            <button className={`action-btn mic-btn ${isRecording ? 'recording' : ''}`} onClick={handleMicClick}>
              <Mic size={20} />
            </button>
            <button 
              className="send-btn" 
              onClick={handleSend} 
              disabled={!inputValue.trim() && attachments.length === 0}
            >
              <Send size={20} />
            </button>
          </div>
        </div>
        <div className="composer-hint" role="status" aria-live="polite">
          <div>
            <p style={{ margin: 0, fontSize: '16px', color: '#333' }}>
              Aurion may be wrong—check info and cookies.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatWindow;
