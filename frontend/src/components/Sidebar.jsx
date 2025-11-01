import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare, Plus, Clock, Bookmark, User, Settings,
  HelpCircle, LogOut, ChevronDown, ChevronUp, Menu,
  Trash2, Pin, PinOff, Check, Edit3, Save as SaveIcon, AlertTriangle, X
} from 'lucide-react';
import '../styles/Sidebar.css';
import sessionService from '../services/sessionService';
import taskService from '../services/taskService';
import profileService from '../services/profileService';
import authService from '../services/auth';
import userService from '../services/userService';

/**
 * Sidebar component with desktop collapse (width shrink) & mobile slide-in behaviors.
 * Extended: task actions (delete/pin/complete) + history item options menu (delete/pin/save/rename)
 */
const Sidebar = ({
  isOpen: controlledOpen,
  onToggle,
  mobile = false,
  onRequestClose,
  onNewChat,
  onSelectChat,
  onNavigate,
  onLogout,
  activeView,
}) => {
  const navigate = useNavigate();
  // Allow uncontrolled fallback
  const [uncontrolledOpen, setUncontrolledOpen] = useState(true);
  const isControlled = typeof controlledOpen === 'boolean';
  const isOpen = isControlled ? controlledOpen : uncontrolledOpen;

  const [historyExpanded, setHistoryExpanded] = useState(true);
  const [tasksExpanded, setTasksExpanded] = useState(true);
  const [historyType, setHistoryType] = useState('history');
  const [taskTab, setTaskTab] = useState('pending');
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [sessionsError, setSessionsError] = useState('');
  const historyMenuRef = useRef(null);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [creatingNew, setCreatingNew] = useState(false);
  // removed unused chatHasContent state (was used to gate New Chat UI)
  // User profile (name/email/avatar)
  const [userName, setUserName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [userInitials, setUserInitials] = useState('');
  const [userAvatarUrl, setUserAvatarUrl] = useState('');
  const [avatarError, setAvatarError] = useState(false);

  // Tasks state (now fetched from backend; no defaults)
  const [pendingTasks, setPendingTasks] = useState([]);
  const [completedTasks, setCompletedTasks] = useState([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState('');

  // UI state for modals/menus
  const [taskConfirm, setTaskConfirm] = useState(null); // {type:'delete', task}
  // (legacy popover state removed)
  const [historyConfirm, setHistoryConfirm] = useState(null); // {type:'delete'|'save', session}
  const [renameTarget, setRenameTarget] = useState(null); // {session, newName}
  const renameInputRef = useRef(null);

  const currentTasks = taskTab === 'pending' ? pendingTasks : completedTasks;
  // Derived collections (saved removed from history listing per requirement)
  const savedSessions = sessions.filter(s => s.saved);
  const historyChats = sessions.filter(s => !s.saved);
  const currentChats = historyType === 'history' ? historyChats : savedSessions;

  // ---- Local persistence helpers ----
  const SESSION_META_KEY = 'maya_session_meta_v1';
  const ACTIVE_SESSION_KEY = 'maya_active_session_id';
  const loadMeta = () => {
    try { return JSON.parse(localStorage.getItem(SESSION_META_KEY)) || { pinned: [], saved: [], titles: {} }; }
    catch { return { pinned: [], saved: [], titles: {} }; }
  };
  const persistMeta = (meta) => {
    try { localStorage.setItem(SESSION_META_KEY, JSON.stringify(meta)); } catch {/* ignore */}
  };
  const applyMeta = (list, meta) => {
    return list.map(s => ({
      ...s,
      pinned: meta.pinned.includes(s.id),
      saved: meta.saved.includes(s.id),
      title: meta.titles[s.id] ? meta.titles[s.id] : s.title,
    }));
  };
  const sortSessions = (list) => {
    return [...list].sort((a,b) => {
      if ((b.pinned === true) - (a.pinned === true) !== 0) return (b.pinned === true) - (a.pinned === true);
      // fallback: newest updated first (if available)
      const at = a.updatedAt ? new Date(a.updatedAt).getTime() : 0;
      const bt = b.updatedAt ? new Date(b.updatedAt).getTime() : 0;
      return bt - at;
    });
  };

  const collapseForMobile = () => {
    if (mobile) {
      if (isControlled) onRequestClose?.(); else setUncontrolledOpen(false);
    }
  };

  // Debounce rapid session switching to avoid overlapping fetches
  const lastClickRef = useRef(0);
  const handleChatClick = (chatId) => {
    const now = Date.now();
    if (now - lastClickRef.current < 150) return; // debounce 150ms
    lastClickRef.current = now;
    onSelectChat?.(chatId);
    setActiveSessionId(chatId);
    try { localStorage.setItem(ACTIVE_SESSION_KEY, chatId); } catch {/* ignore */}
    try { window.dispatchEvent(new CustomEvent('maya:active-session', { detail: { id: chatId } })); } catch {}
    collapseForMobile();
  };

  const handleNavigation = (view) => {
    onNavigate?.(view);
    const map = { profile: '/profile', tasks: '/tasks', settings: '/settings', help: '/help' };
    if (map[view]) navigate(map[view]);
    setShowUserMenu(false);
    collapseForMobile();
  };

  const fetchSessions = useCallback(async () => {
    setLoadingSessions(true);
    setSessionsError('');
    try {
      const res = await sessionService.getSessions();
      const raw = res?.data || [];
      const list = Array.isArray(raw) ? raw : raw.items || [];
      const normalized = list.map((s) => ({
        id: s.id || s._id,
        title: s.title || 'Untitled Chat',
        saved: false, // will be overridden by local meta
        pinned: Boolean(s.pinned), // overridden by meta if set
        messageCount: typeof s.messageCount === 'number' ? s.messageCount : (Array.isArray(s.messages) ? s.messages.length : 0),
        updatedAt: s.updatedAt || s.updated_at || s.createdAt || s.created_at || null,
      }));
      const meta = loadMeta();
      const withMeta = applyMeta(normalized, meta);
      setSessions(sortSessions(withMeta));
    } catch (e) {
      setSessionsError(e?.message || 'Failed to load sessions');
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
    // restore active session id
    try {
      const stored = localStorage.getItem(ACTIVE_SESSION_KEY);
      if (stored) setActiveSessionId(stored);
    } catch {/* ignore */}
  }, [fetchSessions]);

  // Load user profile (name, email) for sidebar footer
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Fetch from users collection first (auth /me), then profile details
        const [me, prof] = await Promise.allSettled([
          userService.getMe(),
          profileService.getProfile(),
        ]);
        const meOk = me.status === 'fulfilled' && me.value?.success;
        const profOk = prof.status === 'fulfilled' && prof.value?.success;
        const meData = meOk ? (me.value.data || {}) : {};
        const data = profOk ? (prof.value.data || {}) : {};
        // Prefer backend-provided fields; fallback to auth local storage for email
  const name = meData.username || data.name || data.full_name || meData.profile?.name || '';
        let email = data.email || meData.email || '';
        // Attempt to resolve avatar URL from common fields
        let avatar = data.avatar_url || data.avatar || data.picture || data.image_url || '';
        if (!email) {
          try {
            const u = authService.getCurrentUser();
            if (u?.email) email = u.email;
            if (!avatar) {
              avatar = u?.avatar_url || u?.avatar || u?.picture || u?.image_url || '';
            }
          } catch {}
        }
        // Derive name from email if needed
  const finalName = (name || '').toString().trim() || (email ? email.split('@')[0] : 'User');
        if (!cancelled) {
          setUserName(finalName);
          setUserEmail(email || '');
          setUserAvatarUrl(typeof avatar === 'string' ? avatar : '');
          setAvatarError(false);
          try {
            const initials = profileService.generateAvatarInitials(finalName);
            setUserInitials(initials || '?');
          } catch { setUserInitials(finalName?.[0]?.toUpperCase?.() || '?'); }
        }
      } catch {
        // Fallback to local only
        try {
          const u = authService.getCurrentUser();
          const email = u?.email || '';
          const name = email ? email.split('@')[0] : 'User';
          const avatar = u?.avatar_url || u?.avatar || u?.picture || u?.image_url || '';
          if (!cancelled) {
            setUserName(name);
            setUserEmail(email);
            setUserAvatarUrl(typeof avatar === 'string' ? avatar : '');
            setAvatarError(false);
            setUserInitials((name?.[0] || '?').toUpperCase());
          }
        } catch {}
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Removed chat content subscription; New Chat gating moved out.

  // Live updates without full page refresh
  useEffect(() => {
    const onSessionsRefresh = () => { fetchSessions(); };
    const onActiveSession = (e) => {
      const id = e?.detail?.id;
      if (id) {
        setActiveSessionId(id);
        try { localStorage.setItem(ACTIVE_SESSION_KEY, id); } catch {}
      }
    };
    try {
      window.addEventListener('maya:sessions:refresh', onSessionsRefresh);
      window.addEventListener('maya:active-session', onActiveSession);
    } catch {}
    return () => {
      try {
        window.removeEventListener('maya:sessions:refresh', onSessionsRefresh);
        window.removeEventListener('maya:active-session', onActiveSession);
      } catch {}
    };
  }, [fetchSessions]);

  // Fetch tasks for sidebar on mount
  const loadTasks = useCallback(async () => {
    setTasksLoading(true);
    setTasksError('');
    try {
      // Use the new summary endpoint for upcoming tasks
      const res = await taskService.getUpcomingTasksSummary();
      if (res.success) {
        const raw = Array.isArray(res.data) ? res.data : (res.data?.items || []);
        const normalized = raw.map((t) => ({
          id: t.id || t._id,
          title: t.title || t.name || 'Untitled Task',
          completed: t.status ? (t.status === 'done' || t.completed === true) : !!t.completed,
          status: t.status || (t.completed ? 'done' : 'todo'),
          due_date: t.due_date,
          priority: t.priority,
          metadata: t.metadata,
        }));
        const pending = normalized.filter((t) => !t.completed);
        const completed = normalized.filter((t) => t.completed);
        setPendingTasks(pending);
        setCompletedTasks(completed);
      } else {
        setTasksError(res.error || 'Failed to load tasks');
      }
    } catch (e) {
      setTasksError(e?.message || 'Failed to load tasks');
    } finally {
      setTasksLoading(false);
    }
  }, []);

  useEffect(() => {
    const fetchTasks = async () => {
      setTasksLoading(true);
      setTasksError('');
      try {
        await loadTasks();
      } catch (e) {
        setTasksError(e?.message || 'Failed to load tasks');
      } finally {
        setTasksLoading(false);
      }
    };
    fetchTasks();
    // subscribe to global tasks updates to keep sidebar in sync
    const handler = () => { loadTasks(); };
    try { window.addEventListener('maya:tasks-updated', handler); } catch {}
    let bc;
    try {
      bc = new BroadcastChannel('maya_tasks');
      bc.onmessage = () => loadTasks();
    } catch {}
    return () => {
      try { window.removeEventListener('maya:tasks-updated', handler); } catch {}
      try { if (bc) { bc.close(); } } catch {}
    };
  }, [loadTasks]);

  // If the active session disappears (deleted or filtered), clear it
  useEffect(() => {
    if (activeSessionId && !sessions.some(s => s.id === activeSessionId)) {
      setActiveSessionId(null);
      try { localStorage.removeItem(ACTIVE_SESSION_KEY); } catch {/* ignore */}
    }
  }, [sessions, activeSessionId]);

  /* -------------------------
     Task action handlers
     ------------------------- */
  const handleTaskDeleteRequest = (task, fromTab = 'pending') => {
    setTaskConfirm({ type: 'delete', task, fromTab });
  };

  const handleTaskDeleteConfirm = async () => {
    if (!taskConfirm) return;
    const { task, fromTab } = taskConfirm;
    try {
      await taskService.deleteTask(task.id);
      if (fromTab === 'pending') {
        setPendingTasks(prev => prev.filter(t => t.id !== task.id));
      } else {
        setCompletedTasks(prev => prev.filter(t => t.id !== task.id));
      }
      // Notify others (e.g., profile) that tasks changed
      try { window.dispatchEvent(new CustomEvent('maya:tasks-updated')); } catch {}
    } catch (e) {
      // Optional: surface error UI
      console.warn('Failed to delete task', e);
    } finally {
      setTaskConfirm(null);
    }
  };

  const handleTaskPin = (task, fromTab = 'pending') => {
    // Bring pinned task to top of pendingTasks list (or completed if pinned there)
    if (fromTab === 'pending') {
      setPendingTasks(prev => {
        const filtered = prev.filter(t => t.id !== task.id);
        return [ { ...task }, ...filtered ];
      });
    } else {
      setCompletedTasks(prev => {
        const filtered = prev.filter(t => t.id !== task.id);
        return [ { ...task }, ...filtered ];
      });
    }
  };

  const handleTaskToggleComplete = async (task, fromTab = 'pending') => {
    const targetCompleted = fromTab === 'pending';
    try {
      await taskService.updateTask(task.id, { status: targetCompleted ? 'done' : 'todo', completed: targetCompleted });
      if (fromTab === 'pending') {
        // remove from pending and add to completed
        setPendingTasks(prev => prev.filter(t => t.id !== task.id));
        setCompletedTasks(prev => [{ ...task, completed: true }, ...prev]);
      } else {
        // mark as incomplete -> move to pending
        setCompletedTasks(prev => prev.filter(t => t.id !== task.id));
        setPendingTasks(prev => [{ ...task, completed: false }, ...prev]);
      }
      try { window.dispatchEvent(new CustomEvent('maya:tasks-updated')); } catch {}
    } catch (e) {
      console.warn('Failed to toggle task complete', e);
    }
  };

  const handleTaskOtpVerification = async (task) => {
    const otp = prompt(`Enter OTP for task: ${task.title}`);
    if (!otp) return;
    
    try {
      const result = await taskService.verifyOtp(task.id, otp);
      if (result.success) {
        if (window.addNotification) {
          window.addNotification({
            type: 'success',
            title: 'OTP Verified',
            message: 'Task reminder verified successfully!'
          });
        }
        await loadTasks(); // Refresh tasks
      } else {
        if (window.addNotification) {
          window.addNotification({
            type: 'error',
            title: 'Invalid OTP',
            message: result.error || 'Please check your OTP and try again'
          });
        }
      }
    } catch (e) {
      console.warn('Failed to verify OTP', e);
    }
  };

  const handleTaskReschedule = async (task) => {
    const newDate = prompt(`Enter new date/time for task: ${task.title}\nFormat: YYYY-MM-DD HH:MM`);
    if (!newDate) return;
    
    try {
      const result = await taskService.rescheduleTask(task.id, {
        due_date: new Date(newDate).toISOString()
      });
      
      if (result.success) {
        if (window.addNotification) {
          window.addNotification({
            type: 'success',
            title: 'Task Rescheduled',
            message: 'Task has been rescheduled successfully!'
          });
        }
        await loadTasks(); // Refresh tasks
      } else {
        throw new Error(result.error);
      }
    } catch (e) {
      console.warn('Failed to reschedule task', e);
      if (window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'Reschedule Failed',
          message: e.message || 'Unable to reschedule task. Please try again.'
        });
      }
    }
  };

  /* -------------------------
     History action handlers
     ------------------------- */
  const handleHistoryDeleteRequest = (session) => {
    setHistoryConfirm({ type: 'delete', session });
  };

  const handleHistorySaveRequest = (session) => { setHistoryConfirm({ type: 'save', session }); };

  const handleHistoryUnsave = (session) => {
    // remove from saved -> appears back in History list
    setSessions(prev => sortSessions(prev.map(s => s.id === session.id ? { ...s, saved: false } : s)));
    const meta = loadMeta();
    meta.saved = meta.saved.filter(id => id !== session.id);
    persistMeta(meta);
  };

  const handleHistoryDeleteConfirm = async () => {
    if (!historyConfirm) return;
    const { session } = historyConfirm;
    try {
      // attempt backend delete if available
      if (sessionService.deleteSession) {
        await sessionService.deleteSession(session.id);
      }
    } catch (e) {
      console.warn('deleteSession failed:', e);
    } finally {
      setSessions(prev => prev.filter(s => s.id !== session.id));
      setHistoryConfirm(null);
    }
  };

  const handleHistorySaveConfirm = async () => {
    if (!historyConfirm) return;
    const { session } = historyConfirm;
    try {
      // mark saved locally & persist if API exists
      setSessions(prev => sortSessions(prev.map(s => s.id === session.id ? { ...s, saved: true } : s)));
      // persist locally
      const meta = loadMeta();
      if (!meta.saved.includes(session.id)) meta.saved.push(session.id);
      persistMeta(meta);
      // backend placeholder (no endpoint currently)
    } catch (e) {
      console.warn('saveSession failed:', e);
    } finally {
      setHistoryConfirm(null);
    }
  };

  const handleHistoryPin = (session) => {
    // toggle pin
    setSessions(prev => {
      const updated = prev.map(s => s.id === session.id ? { ...s, pinned: !s.pinned } : s);
      return sortSessions(updated);
    });
    const meta = loadMeta();
    if (session.pinned) {
      // was pinned -> now unpin
      meta.pinned = meta.pinned.filter(id => id !== session.id);
    } else {
      if (!meta.pinned.includes(session.id)) meta.pinned.push(session.id);
    }
    persistMeta(meta);
  };

  const handleHistoryRenameOpen = (session) => {
    setRenameTarget({ session, newName: session.title || '' });
    // focus input after render
    setTimeout(() => renameInputRef.current?.focus?.(), 50);
  };

  const handleHistoryRenameSave = async () => {
    if (!renameTarget) return;
    const { session, newName } = renameTarget;
    setSessions(prev => sortSessions(prev.map(s => s.id === session.id ? { ...s, title: newName } : s)));
    // persist mapping locally
    const meta = loadMeta();
    meta.titles[session.id] = newName;
    persistMeta(meta);
    // backend update placeholder (no endpoint exposed in sessionService yet)
    setRenameTarget(null);
  };

  /* -------------------------
     Small helpers & UI
     ------------------------- */
  const closeAllOverlays = () => {
    setShowUserMenu(false);
    setTaskConfirm(null);
    setHistoryConfirm(null);
    setRenameTarget(null);
  };

  // Close history menus on outside click
  // (History contextual menu removed; inline hover actions instead)

  return (
    <>
      <button
        className={`sidebar-toggle ${mobile ? 'mobile' : ''}`}
        onClick={() => {
          if (isControlled) onToggle?.(); else setUncontrolledOpen(o => !o);
        }}
        aria-label={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        aria-expanded={isOpen}
      >
        <Menu size={20} />
      </button>
      {mobile && isOpen && <div className="sidebar-backdrop" onClick={onRequestClose} />}
  <div className={`sidebar-container modern-theme ${isOpen ? 'open' : 'closed'} ${mobile ? 'mobile' : 'desktop'}`}
           role="complementary" onKeyDown={(e) => { if (e.key === 'Escape') closeAllOverlays(); }}>
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <div className="logo-icon">A</div>
            {isOpen && <span className="logo-text">Aurion</span>}
          </div>
        </div>
        <div className="sidebar-content">
          <button
            className={`new-chat-btn ${creatingNew ? 'loading' : ''}`}
            disabled={creatingNew}
            onClick={async () => {
              if (creatingNew) return;
              setCreatingNew(true);
              setSessionsError('');
              try {
                // Immediate UI: switch ChatWindow into fresh mode without affecting other sessions
                onNewChat?.();
                const res = await sessionService.createEmpty();
                const data = res?.data || {};
                const sid = data.id || data.session_id || data._id;
                const nowIso = new Date().toISOString();
                if (!sid) throw new Error('Failed to create session');
                // Build the new session and apply local meta
                const rawNew = {
                  id: sid,
                  title: data.title || 'New Chat',
                  saved: false,
                  pinned: false,
                  messageCount: 0,
                  updatedAt: nowIso,
                };
                const meta = loadMeta();
                const withMeta = applyMeta([rawNew], meta)[0];
                setSessions(prev => sortSessions([withMeta, ...prev.filter(s => s.id !== sid)]));
                // Activate it everywhere
                setActiveSessionId(sid);
                onSelectChat?.(sid);
                try {
                  localStorage.setItem(ACTIVE_SESSION_KEY, sid);
                  window.dispatchEvent(new CustomEvent('maya:active-session', { detail: { id: sid } }));
                  window.dispatchEvent(new CustomEvent('maya:sessions:refresh'));
                } catch {}
                // Optionally refresh sessions list from backend to get canonical data quickly (best effort)
                try { fetchSessions(); } catch {}
                collapseForMobile();
              } catch (e) {
                const msg = e?.response?.data?.detail || e?.message || 'Unable to create a new chat';
                setSessionsError(msg);
                if (window.addNotification) {
                  window.addNotification({ type: 'error', title: 'New Chat', message: msg });
                }
              } finally {
                setCreatingNew(false);
              }
            }}
          >
            {creatingNew ? (
              <span className="btn-loader" aria-hidden="true"><span /><span /><span /></span>
            ) : (
              <Plus size={20} />
            )}
            {isOpen && <span>{creatingNew ? 'Creating…' : 'New Chat'}</span>}
          </button>

          <div className="sidebar-section tasks-section" data-section="tasks">
            <div
              className={`section-header clickable ${tasksExpanded ? 'open' : 'closed'}`}
              role="button"
              tabIndex={0}
              aria-expanded={tasksExpanded}
              aria-controls="tasks-collapse-panel"
              onClick={() => setTasksExpanded(o => !o)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTasksExpanded(o => !o);} }}
            >
              <MessageSquare size={18} />
              {isOpen && (
                <>
                  <span>Task</span>
                  {tasksExpanded ? <ChevronUp size={16} className="chevron" /> : <ChevronDown size={16} className="chevron" />}
                </>
              )}
            </div>
            {isOpen && (
              <div
                className={`tasks-collapse collapsible ${tasksExpanded ? 'open' : ''}`}
                id="tasks-collapse-panel"
                aria-hidden={!tasksExpanded}
              >
                <div className="collapsible-inner">
                  <div className="task-tabs">
                    <button className={`task-tab ${taskTab === 'pending' ? 'active' : ''}`}
                            onClick={(e) => { e.stopPropagation(); setTaskTab('pending'); }}>Pending ({pendingTasks.length})</button>
                    <button className={`task-tab ${taskTab === 'completed' ? 'active' : ''}`}
                            onClick={(e) => { e.stopPropagation(); setTaskTab('completed'); }}>Completed ({completedTasks.length})</button>
                  </div>
                  <div className="task-scroll">
                    <div className={`task-list ${isOpen && tasksExpanded ? 'two-col' : ''}`}>
                      {currentTasks.map((task) => {
                        const fromTab = taskTab === 'pending' ? 'pending' : 'completed';
                        return (
                          <div key={task.id} className={`task-item ${task.completed ? 'completed' : 'pending'}`}>
                            <input
                              type="checkbox"
                              checked={!!task.completed}
                              onChange={() => handleTaskToggleComplete(task, fromTab)}
                              className="task-checkbox"
                              aria-label={task.completed ? 'Mark incomplete' : 'Mark complete'}
                            />
                            <span className={task.completed ? 'task-completed' : ''}>{task.title}</span>
                            <div className="task-actions">
                              <button className="icon-btn tiny" title="Pin" aria-label="Pin task" onClick={() => handleTaskPin(task, fromTab)}>
                                <Pin size={14} />
                              </button>
                              <button className="icon-btn tiny" title={task.completed ? 'Mark incomplete' : 'Complete'} aria-label={task.completed ? 'Mark incomplete' : 'Complete task'} onClick={() => handleTaskToggleComplete(task, fromTab)}>
                                <Check size={14} />
                              </button>
                              {task.due_date && !task.completed && (
                                <button className="icon-btn tiny" title="Reschedule" aria-label="Reschedule task" onClick={() => handleTaskReschedule(task)}>
                                  <Clock size={14} />
                                </button>
                              )}
                              {task.metadata?.otp_verified_at ? (
                                <button className="icon-btn success tiny" title="OTP Verified" disabled>
                                  <Check size={14} />
                                </button>
                              ) : task.due_date && !task.completed ? (
                                <button className="icon-btn tiny" title="Verify OTP" aria-label="Verify OTP" onClick={() => handleTaskOtpVerification(task)}>
                                  <Check size={14} />
                                </button>
                              ) : null}
                              <button className="icon-btn danger tiny" title="Delete" aria-label="Delete task" onClick={() => handleTaskDeleteRequest(task, fromTab)}>
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                      {tasksError && <div className="chat-error">{tasksError}</div>}
                      {tasksLoading && <div className="chat-loading">Loading…</div>}
                      {!tasksLoading && currentTasks.length === 0 && <div className="chat-empty">No tasks</div>}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="sidebar-section history-section" data-section="history">
            <div
              className={`section-header clickable ${historyExpanded ? 'open' : 'closed'}`}
              role="button"
              tabIndex={0}
              aria-expanded={historyExpanded}
              aria-controls="history-collapse-panel"
              onClick={() => setHistoryExpanded(o => !o)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setHistoryExpanded(o => !o);} }}
            >
              <Clock size={18} />
              {isOpen && <><span>History</span>{historyExpanded ? <ChevronUp size={16} className="chevron" /> : <ChevronDown size={16} className="chevron" />}</>}
            </div>
            {isOpen && (
              <div
                className={`history-collapse collapsible ${historyExpanded ? 'open' : ''}`}
                id="history-collapse-panel"
                aria-hidden={!historyExpanded}
              >
                <div className="collapsible-inner">
                  <div className="history-tabs">
                    <button className={`history-tab ${historyType === 'history' ? 'active' : ''}`}
                            onClick={() => setHistoryType('history')}><Clock size={14} /> History</button>
                    <button className={`history-tab ${historyType === 'saved' ? 'active' : ''}`}
                            onClick={() => setHistoryType('saved')}><Bookmark size={14} /> Saved</button>
                  </div>
                  <div className="history-scroll" ref={historyMenuRef}>
                    {/* Animated tab panel (key forces re-animation on switch) */}
                    <div key={historyType} className="history-tab-panel">
                      <div className="history-list two-col-match">
                        {sessionsError && <div className="chat-error">{sessionsError}</div>}
                        {loadingSessions && <div className="chat-loading">Loading…</div>}
                        {!loadingSessions && currentChats.length === 0 && <div className="chat-empty">No conversations yet</div>}
                        {!loadingSessions && currentChats.map(chat => {
                          return (
                            <div
                              key={chat.id}
                              className={`history-item ${chat.pinned ? 'pinned' : ''} ${chat.saved ? 'saved' : ''} ${chat.id === activeSessionId ? 'active' : ''}`}
                              onClick={() => handleChatClick(chat.id)}
                              tabIndex={0}
                              aria-label={`Open conversation ${chat.title}`}
                              {...(chat.id === activeSessionId ? { 'aria-current': 'true' } : {})}
                            >
                              <div className="history-main-row">
                                <div className="history-icon" aria-hidden="true">💬</div>
                                <div className="history-text">
                                  <div className="history-title" title={chat.title}>{chat.title}</div>
                                  <div className="history-meta">{chat.updatedAt ? new Date(chat.updatedAt).toLocaleString() : ''}</div>
                                </div>
                              </div>
                              <div className="history-item-actions" onClick={(e)=> e.stopPropagation()}>
                                <button className="icon-btn tiny" aria-label="Rename conversation" title="Rename" onClick={() => handleHistoryRenameOpen(chat)}>
                                  <Edit3 size={14} />
                                </button>
                                <button
                                  className={`icon-btn tiny ${chat.pinned ? 'active-pin' : ''}`}
                                  aria-label={chat.pinned ? 'Unpin conversation' : 'Pin conversation'}
                                  title={chat.pinned ? 'Unpin' : 'Pin'}
                                  onClick={() => handleHistoryPin(chat)}
                                >
                                  {chat.pinned ? <PinOff size={14} /> : <Pin size={14} />}
                                </button>
                                {historyType === 'history' && !chat.saved && (
                                  <button className="icon-btn tiny" aria-label="Save conversation" title="Save" onClick={() => handleHistorySaveRequest(chat)}>
                                    <SaveIcon size={14} />
                                  </button>
                                )}
                                {historyType === 'saved' && chat.saved && (
                                  <button className="icon-btn tiny" aria-label="Unsave conversation" title="Unsave" onClick={() => handleHistoryUnsave(chat)}>
                                    <Bookmark size={14} />
                                  </button>
                                )}
                                <button className="icon-btn danger tiny" aria-label="Delete conversation" title="Delete" onClick={() => handleHistoryDeleteRequest(chat)}>
                                  <Trash2 size={14} />
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="user-profile" onClick={() => setShowUserMenu(!showUserMenu)}>
            <div className="user-avatar" aria-label="User avatar">
              {userAvatarUrl && !avatarError ? (
                <img src={userAvatarUrl} alt={userName || 'User'} onError={() => setAvatarError(true)} />
              ) : (
                userInitials || '?'
              )}
            </div>
            {isOpen && (
              <div className="user-info">
                <div className="user-name">{userName || 'User'}</div>
                <div className="user-email">{userEmail || ''}</div>
              </div>
            )}
          </div>
          {showUserMenu && isOpen && (
            <div className="user-menu">
              <button className="menu-item" onClick={() => handleNavigation('profile')}><User size={18} /><span>Profile</span></button>
              <button className="menu-item" onClick={() => handleNavigation('tasks')}><MessageSquare size={18} /><span>Tasks</span></button>
              <button className="menu-item" onClick={() => handleNavigation('settings')}><Settings size={18} /><span>Settings</span></button>
              <button className="menu-item" onClick={() => handleNavigation('help')}><HelpCircle size={18} /><span>Help</span></button>
              <div className="menu-divider" />
              <button className="menu-item logout" onClick={onLogout}><LogOut size={18} /><span>Logout</span></button>
            </div>
          )}
        </div>
      </div>

      {/* Confirmation modal for tasks */}
      {taskConfirm && (
        <div className="overlay-modal">
          <div className="modal-card">
            <div className="modal-head">
              <AlertTriangle size={18} />
              <h3>Confirm Delete</h3>
              <button className="modal-close" onClick={() => setTaskConfirm(null)}><X size={16} /></button>
            </div>
            <div className="modal-body">
              Are you sure you want to delete the task "<strong>{taskConfirm.task.title}</strong>"?
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setTaskConfirm(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={handleTaskDeleteConfirm}>Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation modal for history (delete/save) */}
      {historyConfirm && (
        <div className="overlay-modal">
          <div className="modal-card">
            <div className="modal-head">
              <AlertTriangle size={18} />
              <h3>{historyConfirm.type === 'delete' ? 'Confirm Delete' : 'Confirm Save'}</h3>
              <button className="modal-close" onClick={() => setHistoryConfirm(null)}><X size={16} /></button>
            </div>
            <div className="modal-body">
              {historyConfirm.type === 'delete'
                ? <>Are you sure you want to delete the conversation "<strong>{historyConfirm.session.title}</strong>"?</>
                : <>Save this conversation "<strong>{historyConfirm.session.title}</strong>" to Saved?</>}
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setHistoryConfirm(null)}>Cancel</button>
              {historyConfirm.type === 'delete'
                ? <button className="btn btn-danger" onClick={handleHistoryDeleteConfirm}>Delete</button>
                : <button className="btn btn-primary" onClick={handleHistorySaveConfirm}>Save</button>}
            </div>
          </div>
        </div>
      )}

      {/* Rename modal */}
      {renameTarget && (
        <div className="overlay-modal">
          <div className="modal-card">
            <div className="modal-head">
              <Edit3 size={18} />
              <h3>Rename Conversation</h3>
              <button className="modal-close" onClick={() => setRenameTarget(null)}><X size={16} /></button>
            </div>
            <div className="modal-body">
              <input
                ref={renameInputRef}
                className="rename-input"
                value={renameTarget.newName}
                onChange={(e) => setRenameTarget(prev => ({ ...prev, newName: e.target.value }))}
                placeholder="New conversation name"
              />
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setRenameTarget(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleHistoryRenameSave}>Save</button>
            </div>
          </div>
        </div>
      )}

    </>
  );
};

export default Sidebar;
