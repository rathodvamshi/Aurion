// Modern Sidebar Component with Enhanced UX
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import '../styles/ModernSidebar.css';
import chatService from '../services/chatService';
import { 
  MessageCircle, 
  ClipboardList, 
  UserCircle, 
  Plus, 
  ChevronDown, 
  ChevronRight,
  Sun,
  Moon,
  Trash2,
  MoreHorizontal,
  Pin,
  PinOff,
  Edit3,
  Sparkles,
  Menu
} from 'lucide-react';

const ModernSidebar = ({ 
  collapsed, 
  pinned, 
  currentView, 
  onViewChange, 
  onToggleCollapse,
  theme,
  onToggleTheme,
  user,
  activeSessionId,
  onSessionSelect,
  onSessionDelete: onSessionDeleteProp,
  onNewChat: onNewChatProp
}) => {
  // ========================
  // State
  // ========================
  const [chatSessions, setChatSessions] = useState([]); // raw sessions
  const [savedSessionsExpanded, setSavedSessionsExpanded] = useState(true);
  const [sessionsExpanded, setSessionsExpanded] = useState(true);
  const [taskCounts, setTaskCounts] = useState({ pending: 0, completed: 0 });
  const [unreadChats, setUnreadChats] = useState(0);
  const [hoveredItem, setHoveredItem] = useState(null);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filteredSessions, setFilteredSessions] = useState([]);
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');

  // ========================
  // Effects
  // ========================
  useEffect(() => {
    // Load sessions and counts
    loadChatSessions();
    loadTaskCounts();
    
    // Check for reduced motion preference
    const hasReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
                            localStorage.getItem('maya-reduced-motion') === 'true';
    setReducedMotion(hasReducedMotion);
    // Listen for global session refresh events
    const onRefresh = () => loadChatSessions();
    const onActive = (e) => {
      try {
        const sid = e?.detail?.id;
        if (sid && onSessionSelect) onSessionSelect(sid);
      } catch {}
    };
    window.addEventListener('maya:sessions:refresh', onRefresh);
    window.addEventListener('maya:active-session', onActive);
    return () => {
      window.removeEventListener('maya:sessions:refresh', onRefresh);
      window.removeEventListener('maya:active-session', onActive);
    };
  }, []);

  // ========================
  // Data Loading
  // ========================
  const formatRelativeTime = (dateString) => {
    try {
      const date = new Date(dateString);
      const now = new Date();
      const diffInSeconds = Math.floor((now - date) / 1000);
      
      if (diffInSeconds < 60) return 'Just now';
      if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
      if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
      if (diffInSeconds < 604800) return `${Math.floor(diffInSeconds / 86400)}d ago`;
      
      return date.toLocaleDateString();
    } catch (error) {
      return 'Unknown';
    }
  };

  const loadChatSessions = async () => {
    try {
      setSessionsLoading(true);
      setSessionsError(null);
      
      const response = await chatService.getSessions();
      const sessionsWithTimestamp = response.data.map(session => ({
        ...session,
        timestamp: formatRelativeTime(session.createdAt),
        lastMessage: session.lastMessage || 'No messages yet',
        unread: false // You can implement unread logic based on your requirements
      }));
      
      setChatSessions(sessionsWithTimestamp);
      setUnreadChats(sessionsWithTimestamp.filter(s => s.unread).length);
      
      // Initialize filtered sessions
      setFilteredSessions(sessionsWithTimestamp);
    } catch (error) {
      console.error('Error loading chat sessions:', error);
      setSessionsError('Failed to load chat sessions');
      // Set empty array on error
      setChatSessions([]);
      setUnreadChats(0);
      setFilteredSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  };

  // Filter sessions based on search query
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredSessions(chatSessions);
    } else {
      const filtered = chatSessions.filter(session =>
        session.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        session.lastMessage?.toLowerCase().includes(searchQuery.toLowerCase())
      );
      setFilteredSessions(filtered);
    }
  }, [chatSessions, searchQuery]);

  const loadTaskCounts = async () => {
    try {
      // This would be replaced with actual API call
      setTaskCounts({ pending: 7, completed: 23 });
    } catch (error) {
      console.error('Error loading task counts:', error);
    }
  };

  // ========================
  // Handlers
  // ========================
  const handleSessionSelect = (sessionId) => {
    onViewChange('chat');
    
    // Call parent's session select handler if provided
    if (onSessionSelect) {
      onSessionSelect(sessionId);
    }
    
    // Mark session as read locally
    setChatSessions(prev => 
      prev.map(session => 
        session.id === sessionId 
          ? { ...session, unread: false }
          : session
      )
    );
    
    // Update unread count
    setUnreadChats(prev => {
      const session = chatSessions.find(s => s.id === sessionId);
      return session?.unread ? Math.max(0, prev - 1) : prev;
    });
    
    // Show loading notification
    if (window.addNotification) {
      window.addNotification({
        type: 'info',
        title: 'Loading Session',
        message: 'Fetching chat history...',
        duration: 2000
      });
    }
    
    console.log('Selected session:', sessionId);
  };

  const handleSessionDelete = async (sessionId, e) => {
    if (e) e.stopPropagation();
    if (!window.confirm('Delete this chat? This cannot be undone.')) return;
    // Optimistic removal
    const prev = chatSessions;
    setChatSessions(prev.filter(s => s.id !== sessionId));
    try {
      if (onSessionDeleteProp) {
        onSessionDeleteProp(sessionId);
      } else {
        await chatService.deleteSession(sessionId);
      }
      // Refresh filtered list
      setFilteredSessions(curr => curr.filter(s => s.id !== sessionId));
    } catch (err) {
      console.error('Failed to delete session', err);
      // revert
      setChatSessions(prev);
      if (window.addNotification) {
        window.addNotification({ type: 'error', title: 'Delete Failed', message: 'Could not delete session'});
      }
    }
  };

  const handleSessionRename = (sessionId, e) => {
    e.stopPropagation();
    const session = chatSessions.find(s => s.id === sessionId);
    setEditingSessionId(sessionId);
    setEditingTitle(session?.title || '');
  };

  // Unified rename submit (DB persistence + optimistic UI)
  const handleRenameSubmit = async (sessionId) => {
    const newTitle = (editingTitle || '').trim();
    if (!newTitle) {
      setEditingSessionId(null);
      setEditingTitle('');
      return;
    }
    // Optimistic update
    setChatSessions(prev => prev.map(s => s.id === sessionId ? { ...s, title: newTitle } : s));
    setEditingSessionId(null);
    try {
      await chatService.updateSessionTitle(sessionId, newTitle);
    } catch (error) {
      console.error('Error renaming session:', error);
      // Optionally reload full list if backend failed
      setTimeout(loadChatSessions, 1200);
    }
  };
  const handleNewChat = async () => {
    onViewChange('chat');
    // Prevent creating multiple empty sessions: if current session has no messages, do nothing
    try {
      if (activeSessionId) {
        const s = chatSessions.find((x) => x.id === activeSessionId);
        if (s && (!s.messageCount || s.messageCount === 0)) {
          if (window.addNotification) {
            window.addNotification({ type: 'info', title: 'New Chat', message: 'Current chat is empty — type a message to start.' });
          }
          return;
        }
      }
    } catch {}
    // Do not pre-create empty sessions; the first sent message will create a session.
    // Notify parent to reset chat input area
    if (onNewChatProp) onNewChatProp();
  };

  // Add a method to refresh sessions (can be called from parent components)
  const refreshSessions = () => {
    loadChatSessions();
  };

  const sortSessions = (sessions) => {
    return [...sessions].sort((a, b) => {
      // Saved + pinned highest, then pinned, then saved, then recent
      const aScore = (a.pinned ? 2 : 0) + (a.saved ? 1 : 0);
      const bScore = (b.pinned ? 2 : 0) + (b.saved ? 1 : 0);
      if (aScore !== bScore) return bScore - aScore;
      // fallback: most recent first
      return new Date(b.updatedAt || b.createdAt) - new Date(a.updatedAt || a.createdAt);
    });
  };

  const handleSessionPin = async (sessionId, e) => {
    e.stopPropagation();
    setChatSessions(prev => sortSessions(prev.map(s => s.id === sessionId ? { ...s, pinned: !s.pinned } : s)));
    try {
      const target = chatSessions.find(s => s.id === sessionId);
      await chatService.setSessionPinned(sessionId, !target?.pinned);
    } catch (err) {
      console.error('Failed to persist pin state', err);
      // revert on failure
      setChatSessions(prev => sortSessions(prev.map(s => s.id === sessionId ? { ...s, pinned: !s.pinned } : s)));
    }
  };

  const handleSessionSave = async (sessionId, e) => {
    e.stopPropagation();
    setChatSessions(prev => sortSessions(prev.map(s => s.id === sessionId ? { ...s, saved: !s.saved } : s)));
    try {
      const target = chatSessions.find(s => s.id === sessionId);
      await chatService.setSessionSaved(sessionId, !target?.saved);
    } catch (err) {
      console.error('Failed to persist save state', err);
      // revert
      setChatSessions(prev => sortSessions(prev.map(s => s.id === sessionId ? { ...s, saved: !s.saved } : s)));
    }
  };

  // (Removed duplicate legacy rename handlers - unified version defined earlier)

  const handleRenameCancel = () => {
    setEditingSessionId(null);
    setEditingTitle('');
  };

  const handleGenerateTitle = async (sessionId, e) => {
    e.stopPropagation();
    
    try {
      const response = await chatService.generateSessionTitle(sessionId);
      const generatedTitle = response.data.title || response.data;
      
      setChatSessions(prev =>
        prev.map(session =>
          session.id === sessionId
            ? { ...session, title: generatedTitle }
            : session
        )
      );
      
      if (window.addNotification) {
        window.addNotification({
          type: 'success',
          title: 'Title Generated',
          message: 'Session title updated automatically',
          duration: 3000
        });
      }
      
      console.log('Generated title:', sessionId, generatedTitle);
    } catch (error) {
      console.error('Error generating title:', error);
      if (window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'Generation Failed',
          message: 'Could not generate title. Try again later.',
          duration: 4000
        });
      }
    }
  };

  // Auto-refresh sessions when activeSessionId changes
  useEffect(() => {
    if (activeSessionId) {
      loadChatSessions();
    }
  }, [activeSessionId]);

  // ========================
  // Animation Variants
  // ========================
  const sidebarVariants = {
    expanded: {
      width: 280,
      boxShadow: '0 4px 26px -4px rgba(0,0,0,0.35), 0 0 0 1px var(--color-border)',
      filter: 'brightness(1) saturate(1)',
      transition: {
        type: reducedMotion ? 'tween' : 'spring',
        stiffness: 180,
        damping: 26,
        mass: 0.9,
        width: { duration: reducedMotion ? 0 : 0.42, ease: [0.4, 0.0, 0.2, 1] },
        boxShadow: { duration: reducedMotion ? 0 : 0.5 },
        filter: { duration: reducedMotion ? 0 : 0.4 },
        when: 'beforeChildren'
      }
    },
    collapsed: {
      width: 64,
      boxShadow: '0 2px 12px -2px rgba(0,0,0,0.25), 0 0 0 1px var(--color-border)',
      filter: 'brightness(.96) saturate(.92)',
      transition: {
        type: reducedMotion ? 'tween' : 'spring',
        stiffness: 230,
        damping: 32,
        mass: 0.9,
        width: { duration: reducedMotion ? 0 : 0.38, ease: [0.4, 0.0, 0.2, 1] },
        boxShadow: { duration: reducedMotion ? 0 : 0.4 },
        filter: { duration: reducedMotion ? 0 : 0.3 },
        when: 'afterChildren'
      }
    }
  };

  // Container-level stagger orchestration
  const navContainerVariants = {
    expanded: {
      transition: reducedMotion ? undefined : { 
        staggerChildren: 0.06, 
        delayChildren: 0.08,
        when: "beforeChildren"
      }
    },
    collapsed: {
      transition: reducedMotion ? undefined : { 
        staggerChildren: 0.04, 
        staggerDirection: -1,
        when: "afterChildren"
      }
    }
  };

  const sessionsListVariants = {
    expanded: {
      transition: reducedMotion ? undefined : { 
        staggerChildren: 0.05, 
        delayChildren: 0.1,
        when: "beforeChildren"
      }
    },
    collapsed: {
      transition: reducedMotion ? undefined : { 
        staggerChildren: 0.03, 
        staggerDirection: -1,
        when: "afterChildren" 
      }
    }
  };

  // Individual nav button animation
  const navItemVariants = {
    expanded: {
      opacity: 1,
      y: 0,
      x: 0,
      scale: 1,
      filter: 'blur(0px)',
      transition: { 
        type: "spring",
        stiffness: 400,
        damping: 25,
        duration: reducedMotion ? 0 : 0.42, 
        ease: [0.16, 1, 0.3, 1] 
      }
    },
    collapsed: {
      opacity: 1, // keep icons visible
      y: 0,
      x: 0,
      scale: 0.95,
      filter: 'blur(0px)',
      transition: { 
        type: "spring",
        stiffness: 500,
        damping: 30,
        duration: reducedMotion ? 0 : 0.3, 
        ease: [0.4, 0.0, 0.2, 1] 
      }
    },
    initial: {
      opacity: 0,
      y: 10,
      x: -8,
      scale: 0.95,
      filter: 'blur(2px)',
    }
  };

  // Session list item animation (only meaningful when expanded)
  const sessionItemVariants = {
    expanded: { 
      opacity: 1, 
      x: 0, 
      y: 0,
      scale: 1, 
      filter: 'blur(0px)', 
      transition: { 
        type: "spring",
        stiffness: 380,
        damping: 24,
        duration: reducedMotion ? 0 : 0.35, 
        ease: [0.16, 1, 0.3, 1] 
      } 
    },
    collapsed: { 
      opacity: 0, 
      x: -18, 
      y: 0,
      scale: 0.96, 
      filter: 'blur(4px)', 
      transition: { 
        duration: reducedMotion ? 0 : 0.22, 
        ease: [0.4, 0.0, 0.2, 1] 
      } 
    },
    initial: {
      opacity: 0,
      x: -18,
      y: 5,
      scale: 0.96,
      filter: 'blur(2px)',
    }
  };

  const tooltipVariants = {
    initial: { opacity: 0, x: 10, scale: 0.9 },
    animate: { 
      opacity: 1, 
      x: 0, 
      scale: 1,
      transition: { duration: reducedMotion ? 0 : 0.2 }
    },
    exit: { 
      opacity: 0, 
      x: 10, 
      scale: 0.9,
      transition: { duration: reducedMotion ? 0 : 0.15 }
    }
  };

  // ========================
  // Navigation Items
  // ========================
  const navigationItems = [
    {
      id: 'chat',
      label: 'Chat',
      icon: MessageCircle,
      badge: unreadChats > 0 ? unreadChats : null,
      active: currentView === 'chat',
      color: '#3b82f6', // Blue
      hoverColor: '#2563eb'
    },
    {
      id: 'tasks',
      label: 'Tasks',
      icon: ClipboardList,
      badge: taskCounts.pending > 0 ? taskCounts.pending : null,
      active: currentView === 'tasks',
      color: '#10b981', // Green
      hoverColor: '#059669'
    },
    {
      id: 'profile',
      label: 'Profile',
      icon: UserCircle,
      badge: null,
      active: currentView === 'profile',
      color: '#8b5cf6', // Purple
      hoverColor: '#7c3aed'
    }
  ];

  // ========================
  // Render Components
  // ========================
  const renderNavigationItem = (item) => {
    const Icon = item.icon;
    
    return (
      <motion.div
        key={item.id}
        className={`nav-item ${item.active ? 'active' : ''}`}
        variants={navItemVariants}
        onMouseEnter={() => setHoveredItem(item.id)}
        onMouseLeave={() => setHoveredItem(null)}
        style={{
          '--nav-color': item.color,
          '--nav-hover-color': item.hoverColor
        }}
      >
        <motion.button
          className="nav-button"
          onClick={() => onViewChange(item.id)}
          aria-label={item.label}
          aria-current={item.active ? 'page' : undefined}
          whileHover={{ scale: reducedMotion ? 1 : 1.02 }}
          transition={{ duration: 0.2, ease: 'easeInOut' }}
        >
          <div className="nav-icon">
            <Icon size={22} />
            {item.badge && (
              <span className="nav-badge" aria-label={`${item.badge} unread`}>
                {item.badge > 99 ? '99+' : item.badge}
              </span>
            )}
          </div>
          
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                className="nav-label"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: reducedMotion ? 0 : 0.2 }}
              >
                {item.label}
              </motion.span>
            )}
          </AnimatePresence>
        </motion.button>

        {/* Active Indicator */}
        {item.active && (
          <motion.div
            className="active-indicator"
            initial={{ scaleY: 0 }}
            animate={{ scaleY: 1 }}
            exit={{ scaleY: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.2 }}
            style={{ backgroundColor: item.color }}
          />
        )}

        {/* Tooltip for collapsed state and hover */}
        <AnimatePresence>
          {(collapsed || hoveredItem === item.id) && (
            <motion.div
              className="nav-tooltip"
              variants={tooltipVariants}
              initial="initial"
              animate="animate"
              exit="exit"
            >
              {item.label}
              {item.badge && (
                <span className="tooltip-badge">
                  {item.badge > 99 ? '99+' : item.badge}
                </span>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    );
  };

  const renderChatSessions = () => {
    if (collapsed || currentView !== 'chat') return null;

    return (
      <motion.div
        className="chat-sessions"
        initial={{ opacity: 0, height: 0 }}
        animate={{ opacity: 1, height: 'auto' }}
        exit={{ opacity: 0, height: 0 }}
        transition={{ duration: reducedMotion ? 0 : 0.3 }}
      >
        <div className="section-header">
          <button
            className="new-chat-button"
            onClick={handleNewChat}
            aria-label="Start new chat"
          >
            <Plus size={16} />
            <span>New Chat</span>
          </button>
        </div>

        {/* Search Sessions */}
        {chatSessions.length > 3 && (
          <div className="sessions-search">
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="search-input"
            />
          </div>
        )}

        <div className="sessions-header">
          <button
            className="sessions-toggle"
            onClick={() => setSessionsExpanded(!sessionsExpanded)}
            aria-expanded={sessionsExpanded}
          >
              <motion.span
                style={{ display: 'inline-flex' }}
                animate={{ rotate: sessionsExpanded ? 180 : 0 }}
                transition={{ 
                  type: "spring", 
                  stiffness: 260, 
                  damping: 20,
                  duration: 0.25
                }}
              >
                <ChevronDown size={16} />
              </motion.span>
            <span>Recent Chats</span>
            <span className="sessions-count">
              ({searchQuery ? filteredSessions.length : chatSessions.length})
            </span>
          </button>
        </div>
        <AnimatePresence>
          {sessionsExpanded && (
            <motion.div
              className="sessions-list"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: reducedMotion ? 0 : 0.25 }}
              variants={sessionsListVariants}
            >
              {sessionsLoading ? (
                <div className="sessions-loading">
                  <div className="loading-spinner">Loading...</div>
                </div>
              ) : sessionsError ? (
                <div className="sessions-error">
                  <div className="error-message">{sessionsError}</div>
                  <button 
                    className="retry-button" 
                    onClick={loadChatSessions}
                  >
                    Retry
                  </button>
                </div>
              ) : filteredSessions.length === 0 ? (
                searchQuery ? (
                  <div className="no-sessions">
                    <div className="empty-state">
                      <MessageCircle size={24} />
                      <span>No matching conversations</span>
                      <p>Try a different search term</p>
                    </div>
                  </div>
                ) : (
                  <div className="no-sessions">
                    <div className="empty-state">
                      <MessageCircle size={24} />
                      <span>No chat sessions yet</span>
                      <p>Start a new chat to begin</p>
                    </div>
                  </div>
                )
              ) : (
                (() => {
                  const saved = filteredSessions.filter(s => s.saved);
                  const regular = filteredSessions.filter(s => !s.saved);
                  const ordered = [...saved, ...regular];
                  return (
                    <>
                      {saved.length > 0 && (
                        <div className="sessions-subheader">Saved Chats ({saved.length})</div>
                      )}
                      {ordered.map(session => (
                        <motion.div
                          key={session.id}
                          className={`session-item ${session.unread ? 'unread' : ''} ${session.id === activeSessionId ? 'active' : ''} ${session.pinned ? 'pinned' : ''} ${session.saved ? 'saved' : ''}`}
                          variants={sessionItemVariants}
                          animate={collapsed ? 'collapsed' : 'expanded'}
                          initial={collapsed ? 'collapsed' : 'expanded'}
                          onClick={() => handleSessionSelect(session.id)}
                          whileHover={{ scale: reducedMotion ? 1 : 1.02, x: reducedMotion ? 0 : 4 }}
                          whileTap={{ scale: reducedMotion ? 1 : 0.98 }}
                        >
                    <div className="session-content">
                      <div className="session-title">
                        {editingSessionId === session.id ? (
                          <div className="session-rename">
                            <input
                              type="text"
                              value={editingTitle}
                              onChange={(e) => setEditingTitle(e.target.value)}
                              onKeyPress={(e) => {
                                if (e.key === 'Enter') {
                                  handleRenameSubmit(session.id);
                                } else if (e.key === 'Escape') {
                                  handleRenameCancel();
                                }
                              }}
                              onBlur={() => handleRenameSubmit(session.id)}
                              autoFocus
                              className="rename-input"
                              onClick={(e) => e.stopPropagation()}
                            />
                          </div>
                        ) : (
                          <>
                            {session.title || 'Untitled Chat'}
                            {session.id === activeSessionId && (
                              <span className="active-session-badge">
                                Active
                                <span className="session-loading-dot" />
                              </span>
                            )}
                          </>
                        )}
                      </div>
                      <div className="session-preview">{session.lastMessage}</div>
                      <div className="session-meta">
                        <span className="session-timestamp">{session.timestamp}</span>
                        {session.messageCount && (
                          <span className="message-count">{session.messageCount} messages</span>
                        )}
                      </div>
                    </div>
                    
                    {session.unread && <div className="unread-indicator" />}
                    
                    <div className="session-actions">
                      <button
                        className="session-action-btn pin-btn"
                        onClick={(e) => handleSessionPin(session.id, e)}
                        aria-label={`${session.pinned ? 'Unpin' : 'Pin'} ${session.title || 'Untitled Chat'}`}
                        title={session.pinned ? 'Unpin session' : 'Pin session'}
                      >
                        {session.pinned ? <PinOff size={12} /> : <Pin size={12} />}
                      </button>
                      <button
                        className={`session-action-btn save-btn ${session.saved ? 'active' : ''}`}
                        onClick={(e) => handleSessionSave(session.id, e)}
                        aria-label={`${session.saved ? 'Unsave' : 'Save'} ${session.title || 'Untitled Chat'}`}
                        title={session.saved ? 'Unsave chat' : 'Save chat'}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill={session.saved ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" /></svg>
                      </button>
                      
                      {/* Show generate title button for generic titles */}
                      {(!session.title || session.title.startsWith('Chat') || session.title === 'Untitled Chat') && (
                        <button
                          className="session-action-btn generate-btn"
                          onClick={(e) => handleGenerateTitle(session.id, e)}
                          aria-label={`Generate title for ${session.title || 'Untitled Chat'}`}
                          title="Generate smart title"
                        >
                          <Sparkles size={12} />
                        </button>
                      )}
                      
                      <button
                        className="session-action-btn rename-btn"
                        onClick={(e) => handleSessionRename(session.id, e)}
                        aria-label={`Rename ${session.title || 'Untitled Chat'}`}
                        title="Rename session"
                      >
                        <Edit3 size={12} />
                      </button>
                      
                      <button
                        className="session-action-btn delete-btn"
                        onClick={(e) => handleSessionDelete(session.id, e)}
                        aria-label={`Delete ${session.title || 'Untitled Chat'}`}
                        title="Delete session"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                    
                    {/* Active indicator */}
                    {session.id === activeSessionId && (
                      <motion.div
                        className="session-active-indicator"
                        initial={{ scaleY: 0 }}
                        animate={{ scaleY: 1 }}
                        exit={{ scaleY: 0 }}
                        transition={{ duration: reducedMotion ? 0 : 0.2 }}
                      />
                    )}
                        </motion.div>
                      ))}
                    </>
                  );
                })()
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    );
  };

  const renderUserProfile = () => {
    if (collapsed) {
      return (
        <div className="user-profile collapsed">
          <div className="user-avatar">
            {user?.avatar ? (
              <img src={user.avatar} alt={user.name} />
            ) : (
              <div className="avatar-initials">
                {user?.name?.charAt(0) || user?.email?.charAt(0) || 'U'}
              </div>
            )}
          </div>
        </div>
      );
    }

    return (
      <motion.div
        className="user-profile"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: reducedMotion ? 0 : 0.2 }}
      >
        <div className="user-avatar">
          {user?.avatar ? (
            <img src={user.avatar} alt={user.name} />
          ) : (
            <div className="avatar-initials">
              {user?.name?.charAt(0) || user?.email?.charAt(0) || 'U'}
            </div>
          )}
        </div>
        <div className="user-info">
          <div className="user-name">{user?.name || 'User'}</div>
          <div className="user-email">{user?.email}</div>
        </div>
        <button className="user-menu" aria-label="User menu">
          <MoreHorizontal size={16} />
        </button>
      </motion.div>
    );
  };

  // ========================
  // Main Render
  // ========================
  return (
    <motion.aside
      className={`modern-sidebar ${collapsed ? 'collapsed' : 'expanded'} ${pinned ? 'pinned' : 'overlay'}`}
      variants={sidebarVariants}
      initial={collapsed ? 'collapsed' : 'expanded'}
      animate={collapsed ? 'collapsed' : 'expanded'}
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Sidebar Header */}
      <div className="sidebar-header">
        {/* Toggle Button */}
        <motion.button
          className="sidebar-toggle-btn"
          onClick={onToggleCollapse}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <Menu size={20} />
        </motion.button>

        <AnimatePresence>
          {!collapsed && (
            <motion.div
              className="sidebar-brand sidebar-brand-shifted"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: reducedMotion ? 0 : 0.2 }}
            >
              <div className="brand-logo">Aurion</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation Items */}
      <motion.nav 
        className="sidebar-nav" 
        role="menu" 
        variants={navContainerVariants}
        animate={collapsed ? 'collapsed' : 'expanded'}
        initial={false}
      >
        {navigationItems.map(renderNavigationItem)}
      </motion.nav>

      {/* Chat Sessions (when chat is active) */}
      {renderChatSessions()}

      {/* Spacer */}
      <div className="sidebar-spacer" />

      {/* Theme Toggle */}
      <div className="sidebar-controls">
        <motion.button
          className="theme-toggle"
          onClick={onToggleTheme}
          whileHover={{ scale: reducedMotion ? 1 : 1.05 }}
          whileTap={{ scale: reducedMotion ? 1 : 0.95 }}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          <div className="theme-icons">
            <Sun className={theme === 'light' ? 'active' : ''} size={18} />
            <Moon className={theme === 'dark' ? 'active' : ''} size={18} />
          </div>
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                className="theme-label"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: reducedMotion ? 0 : 0.2 }}
              >
                {theme === 'dark' ? 'Dark' : 'Light'}
              </motion.span>
            )}
          </AnimatePresence>
        </motion.button>
      </div>

      {/* User Profile */}
      <div className="sidebar-footer">
        {renderUserProfile()}
      </div>

      {/* Resize Handle */}
      {pinned && (
        <div className="sidebar-resize-handle" />
      )}
    </motion.aside>
  );
};

export default ModernSidebar;