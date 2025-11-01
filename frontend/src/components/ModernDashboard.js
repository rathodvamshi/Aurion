// Modern Dashboard Component - Responsive & Well-Structured
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Menu, 
  X, 
  Search, 
  Bell, 
  HelpCircle, 
  Sun, 
  Moon, 
  User,
  ChevronDown,
  MessageSquare,
  CheckSquare,
  Settings,
  LogOut
} from 'lucide-react';

// Components
import ModernSidebar from './ModernSidebar';
import ChatLayout from './ChatLayout.jsx';
import TasksInterface from './TasksInterface';
import ProfileInterface from './ProfileInterface';
import CommandPalette from './CommandPalette';
import ToastSystem from './ToastSystem';
import authService from '../services/auth';
import dashboardService from '../services/dashboardService';
import profileService from '../services/profileService';
import chatService from '../services/chatService';

// Styles
import '../styles/ModernDashboard.css';

// Main Dashboard Layout Component
const ModernDashboard = () => {
  // ========================
  // State Management
  // ========================
  const [currentView, setCurrentView] = useState('chat');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarPinned, setSidebarPinned] = useState(true);
  const [theme, setTheme] = useState('dark');
  const [highContrast, setHighContrast] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [user, setUser] = useState(null);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [notifications, setNotifications] = useState([]);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [loading, setLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  
  // Session Management State
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [sessionHistory, setSessionHistory] = useState([]);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionCache, setSessionCache] = useState(new Map());

  // ========================
  // Refs
  // ========================
  const profileDropdownRef = useRef(null);

  // ========================
  // Data Loading Functions
  // ========================
  
  const loadDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      
      // Load user profile and dashboard data in parallel
      const [profileResult, dashboardResult, notificationsResult] = await Promise.allSettled([
        profileService.getProfile(),
        dashboardService.getCompleteDashboardData(),
        dashboardService.getImportantNotifications()
      ]);

      // Handle profile data
      if (profileResult.status === 'fulfilled' && profileResult.value.success) {
        setUser({
          ...authService.getCurrentUser(),
          profile: profileResult.value.data
        });
      }

      // Handle dashboard data
      if (dashboardResult.status === 'fulfilled' && dashboardResult.value.success) {
        setDashboardData(dashboardResult.value.data);
      }

      // Handle notifications
      if (notificationsResult.status === 'fulfilled' && notificationsResult.value.success) {
        setNotifications(notificationsResult.value.data);
      }

      setLastRefresh(new Date());
    } catch (error) {
      console.error('Error loading dashboard data:', error);
      if (window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'Data Loading Error',
          message: 'Failed to load dashboard data. Please refresh the page.',
          duration: 5000
        });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshDashboard = useCallback(async () => {
    await loadDashboardData();
    if (window.addNotification) {
      window.addNotification({
        type: 'success',
        title: 'Dashboard Refreshed',
        message: 'All data has been updated successfully.',
        duration: 3000
      });
    }
  }, [loadDashboardData]);

  // ========================
  // Session Management Functions
  // ========================
  
  const loadSessionHistory = useCallback(async (sessionId) => {
    try {
      setSessionLoading(true);
      
      // Check cache first
      if (sessionCache.has(sessionId)) {
        const cachedData = sessionCache.get(sessionId);
        const cacheAge = Date.now() - cachedData.timestamp;
        
        // Use cached data if less than 30 seconds old
        if (cacheAge < 30000) {
          setSessionHistory(cachedData.messages);
          setActiveSessionId(sessionId);
          localStorage.setItem('maya-active-session', sessionId);
          return cachedData.messages;
        }
      }
      
    // Fetch from API
  const response = await chatService.getSessionHistory(sessionId, 30, 0);
  const payload = response.data || {};
  const messages = payload.messages || payload || [];
  const hasMore = payload.has_more || payload.hasMore;
      
      // Format messages for display
      const formattedMessages = messages.map(msg => ({
        id: msg._id || msg.id,
        content: msg.text || msg.content || '',  // Ensure content exists
        text: msg.text || msg.content || '',     // Keep text for compatibility
        role: msg.sender === 'user' ? 'user' : 'assistant',  // Convert sender to role
        sender: msg.sender,
        timestamp: (() => {
          const ts = msg.timestamp || msg.createdAt;
          return ts instanceof Date ? ts : new Date(ts || Date.now());
        })(),
        sessionId: sessionId,
        ...msg // Include any additional properties
      })).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
      
      // Update cache (store hasMore flag for pagination)
      setSessionCache(prev => new Map(prev.set(sessionId, {
        messages: formattedMessages,
        timestamp: Date.now(),
        hasMore
      })));
      
      setSessionHistory(formattedMessages);
      setActiveSessionId(sessionId);
      localStorage.setItem('maya-active-session', sessionId);
      
      // Background prefetch next slice if hasMore for instant scroll
      if (hasMore) {
        setTimeout(async () => {
          try {
            const nextResp = await chatService.getSessionHistory(sessionId, 70, 30); // fetch next chunk
            const nextData = nextResp.data || {};
            const nextMessages = (nextData.messages || []).map(msg => ({
              id: msg._id || msg.id,
              content: msg.text || msg.content || '',
              text: msg.text || msg.content || '',
              role: msg.sender === 'user' ? 'user' : 'assistant',
              sender: msg.sender,
              timestamp: (() => { const ts = msg.timestamp || msg.createdAt; return ts instanceof Date ? ts : new Date(ts || Date.now()); })(),
              sessionId: sessionId,
              ...msg
            }));
            if (nextMessages.length) {
              setSessionCache(prev => {
                const clone = new Map(prev);
                const cached = clone.get(sessionId);
                if (cached) {
                  const merged = [...cached.messages, ...nextMessages].sort((a,b)=> new Date(a.timestamp)-new Date(b.timestamp));
                  clone.set(sessionId, { ...cached, messages: merged, prefetch: true });
                }
                return clone;
              });
            }
          } catch (e) {
            // silent fail
          }
        }, 50);
      }
      return formattedMessages;
    } catch (error) {
      const status = error?.response?.status;
      console.error('Error loading session history:', status, error?.message || error);
      // If the session no longer exists (404), clear stale cache and localStorage
      if (status === 404) {
        try {
          setSessionCache(prev => {
            const next = new Map(prev);
            next.delete(sessionId);
            return next;
          });
        } catch {}
        if (localStorage.getItem('maya-active-session') === sessionId) {
          localStorage.removeItem('maya-active-session');
        }
        // Inform user softly
        if (window.addNotification) {
          window.addNotification({
            type: 'warning',
            title: 'Session Not Found',
            message: 'That chat session may have been deleted. Starting a new chat.',
            duration: 3000
          });
        }
        // Reset to a clean state
        setActiveSessionId(null);
        setSessionHistory([]);
        return [];
      }
      // For unauthorized, a global interceptor will prompt login; avoid duplicate toasts here
      if (status !== 401 && window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'Session Load Error',
          message: 'Failed to load chat history. Please try again.',
          duration: 4000
        });
      }
      return [];
    } finally {
      setSessionLoading(false);
    }
  }, [sessionCache]);

  const handleSessionSelect = useCallback(async (sessionId) => {
    if (sessionId === activeSessionId) return;
    
    console.log('Loading session:', sessionId);
    await loadSessionHistory(sessionId);
    
    // Switch to chat view if not already there
    if (currentView !== 'chat') {
      setCurrentView('chat');
    }
    
    if (window.addNotification) {
      window.addNotification({
        type: 'info',
        title: 'Session Loaded',
        message: 'Chat history has been loaded successfully.',
        duration: 2000
      });
    }
  }, [activeSessionId, currentView, loadSessionHistory]);

  const handleNewChat = useCallback(() => {
    setActiveSessionId(null);
    setSessionHistory([]);
    localStorage.removeItem('maya-active-session');
    
    // Clear cache for quick new chats
    setSessionCache(new Map());
    
    if (currentView !== 'chat') {
      setCurrentView('chat');
    }
    
    console.log('Starting new chat session');
  }, [currentView]);

  const handleSessionDelete = useCallback((sessionId) => {
    // Remove from cache
    setSessionCache(prev => {
      const newCache = new Map(prev);
      newCache.delete(sessionId);
      return newCache;
    });
    
    // If deleted session was active, start new chat
    if (sessionId === activeSessionId) {
      handleNewChat();
    }
    
    console.log('Session deleted:', sessionId);
  }, [activeSessionId, handleNewChat]);

  const addMessageToSession = useCallback((message) => {
    if (!activeSessionId || !message) return;
    
    // Ensure message has the correct format
    const formattedMessage = {
      id: message.id || `msg_${Date.now()}`,
      content: message.content || message.text || '',
      text: message.text || message.content || '',
      role: message.role || (message.sender === 'user' ? 'user' : 'assistant'),
      sender: message.sender || (message.role === 'user' ? 'user' : 'assistant'),
      sessionId: activeSessionId,
      timestamp: message.timestamp ? (message.timestamp instanceof Date ? message.timestamp : new Date(message.timestamp)) : new Date(),
      ...message
    };
    
    setSessionHistory(prev => [...prev, formattedMessage]);
    
    // Update cache
    setSessionCache(prev => {
      const newCache = new Map(prev);
      const cachedData = newCache.get(activeSessionId);
      if (cachedData) {
        newCache.set(activeSessionId, {
          ...cachedData,
          messages: [...cachedData.messages, formattedMessage],
          timestamp: Date.now()
        });
      }
      return newCache;
    });
  }, [activeSessionId]);

  // ========================
  // Effects
  // ========================

  // Window resize monitoring for mobile responsiveness
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
      if (window.innerWidth >= 768) {
        // On larger screens, auto-expand sidebar if it was collapsed due to mobile view
        if (!sidebarCollapsed && !sidebarPinned) {
          setSidebarCollapsed(false);
        }
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [sidebarCollapsed, sidebarPinned]);
  
  // Initialize user and preferences
  useEffect(() => {
    const initializeDashboard = async () => {
      // Get user data
      const currentUser = authService.getCurrentUser();
      if (currentUser) {
        setUser(currentUser);
      }

      // Load preferences from localStorage
      const savedTheme = localStorage.getItem('maya-theme') || 'dark';
      const savedSidebarCollapsed = localStorage.getItem('maya-sidebar-collapsed') === 'true';
      const savedSidebarPinned = localStorage.getItem('maya-sidebar-pinned') !== 'false';
      const savedHighContrast = localStorage.getItem('maya-high-contrast') === 'true';
      const savedReducedMotion = localStorage.getItem('maya-reduced-motion') === 'true';

      setTheme(savedTheme);
      setSidebarCollapsed(savedSidebarCollapsed);
      setSidebarPinned(savedSidebarPinned);
      setHighContrast(savedHighContrast);
      setReducedMotion(savedReducedMotion);

      // Apply theme to document
      document.documentElement.setAttribute('data-theme', savedTheme);
      if (savedHighContrast) {
        document.documentElement.setAttribute('data-contrast', 'high');
      }
      if (savedReducedMotion) {
        document.documentElement.setAttribute('data-motion', 'reduced');
      }

      // Load dashboard data
      await loadDashboardData();
    };

    initializeDashboard();
  }, [loadDashboardData]);

  // Restore last active session
  useEffect(() => {
    const restoreSession = async () => {
      const savedSessionId = localStorage.getItem('maya-active-session');
      if (savedSessionId && user) {
        try {
          await loadSessionHistory(savedSessionId);
          // Only consider restored if it actually became active
          setTimeout(() => {
            if (activeSessionId === savedSessionId) {
              console.log('Restored session:', savedSessionId);
            } else {
              // History failed to load or session not found; clear stale ID
              localStorage.removeItem('maya-active-session');
            }
          }, 0);
        } catch (error) {
          console.error('Failed to restore session:', error);
          localStorage.removeItem('maya-active-session');
        }
      }
    };

    if (user && !loading) {
      restoreSession();
    }
  }, [user, loading, loadSessionHistory]);

  // Detect system preference changes
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handleChange = (e) => {
      if (!localStorage.getItem('maya-reduced-motion')) {
        setReducedMotion(e.matches);
        document.documentElement.setAttribute('data-motion', e.matches ? 'reduced' : 'normal');
      }
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  // Online/offline detection
  useEffect(() => {
    const handleOnlineStatus = () => setIsOffline(!navigator.onLine);
    
    window.addEventListener('online', handleOnlineStatus);
    window.addEventListener('offline', handleOnlineStatus);
    
    return () => {
      window.removeEventListener('online', handleOnlineStatus);
      window.removeEventListener('offline', handleOnlineStatus);
    };
  }, []);

  // Click outside handler for profile dropdown
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (profileDropdownRef.current && !profileDropdownRef.current.contains(event.target)) {
        setProfileDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // ========================
  // Handlers
  // ========================
  
  const toggleSidebar = useCallback(() => {
    const newCollapsed = !sidebarCollapsed;
    setSidebarCollapsed(newCollapsed);
    localStorage.setItem('maya-sidebar-collapsed', newCollapsed.toString());
  }, [sidebarCollapsed]);

  const toggleTheme = useCallback(() => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('maya-theme', newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  }, [theme]);

  const toggleHighContrast = useCallback(() => {
    const newHighContrast = !highContrast;
    setHighContrast(newHighContrast);
    localStorage.setItem('maya-high-contrast', newHighContrast.toString());
    document.documentElement.setAttribute('data-contrast', newHighContrast ? 'high' : 'normal');
  }, [highContrast]);

  const handleLogout = useCallback(() => {
    authService.logout();
    window.location.href = '/';
  }, []);

  const handleViewChange = useCallback((view) => {
    setCurrentView(view);
    localStorage.setItem('maya-last-view', view);
  }, []);

  // ========================
  // Keyboard Shortcuts
  // ========================
  useEffect(() => {
    const handleKeyboardShortcuts = (e) => {
      if (e.ctrlKey || e.metaKey) {
        switch (e.key) {
          case 'k':
            e.preventDefault();
            setCommandPaletteOpen(true);
            break;
          case 'b':
            e.preventDefault();
            toggleSidebar();
            break;
          case '/':
            e.preventDefault();
            document.querySelector('.header-search input')?.focus();
            break;
          default:
            break;
        }
      }
      
      if (e.key === 'Escape') {
        setCommandPaletteOpen(false);
        setProfileDropdownOpen(false);
      }
    };

    document.addEventListener('keydown', handleKeyboardShortcuts);
    return () => document.removeEventListener('keydown', handleKeyboardShortcuts);
  }, [toggleSidebar]);

  // ========================
  // Animation Variants
  // ========================
  const containerVariants = {
    initial: { opacity: 0 },
    animate: { 
      opacity: 1,
      transition: { duration: reducedMotion ? 0 : 0.3 }
    },
    exit: { 
      opacity: 0,
      transition: { duration: reducedMotion ? 0 : 0.2 }
    }
  };

  const headerVariants = {
    initial: { y: -20, opacity: 0 },
    animate: { 
      y: 0, 
      opacity: 1,
      transition: { duration: reducedMotion ? 0 : 0.4, delay: 0.1 }
    }
  };

  const contentVariants = {
    initial: { x: 20, opacity: 0 },
    animate: { 
      x: 0, 
      opacity: 1,
      transition: { duration: reducedMotion ? 0 : 0.4, delay: 0.2 }
    }
  };

  // ========================
  // Render Methods
  // ========================
  
  const renderProfileDropdown = () => (
    <AnimatePresence>
      {profileDropdownOpen && (
        <motion.div
          className="profile-dropdown"
          initial={{ opacity: 0, y: -10, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.95 }}
          transition={{ duration: reducedMotion ? 0 : 0.2 }}
        >
          <div className="dropdown-header">
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
          </div>
          
          <div className="dropdown-divider" />
          
          <div className="dropdown-menu">
            <button 
              className="dropdown-item"
              onClick={() => {
                handleViewChange('profile');
                setProfileDropdownOpen(false);
              }}
            >
              <User size={16} />
              <span>Profile</span>
            </button>
            <button className="dropdown-item">
              <Settings size={16} />
              <span>Settings</span>
            </button>
            <div className="dropdown-divider" />
            <button className="dropdown-item danger" onClick={handleLogout}>
              <LogOut size={16} />
              <span>Logout</span>
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  const renderCurrentView = () => {
    switch (currentView) {
      case 'chat':
        // Use the full chat layout and pass active session to load its history
        return <ChatLayout initialChatId={activeSessionId || ''} />;
      case 'tasks':
        return <TasksInterface />;
      case 'profile':
        return <ProfileInterface />;
      default:
        return <ChatLayout initialChatId={activeSessionId || ''} />;
    }
  };

  // ========================
  // Main Render
  // ========================
  // Sidebar animation variants
  const sidebarVariants = {
    hidden: { 
      x: '-100%', 
      opacity: 0, 
      transition: { 
        duration: 0.3, 
        ease: [0.4, 0.0, 0.2, 1] // Enhanced easing
      } 
    },
    collapsed: {
      width: 72,
      x: 0,
      opacity: 1,
      transition: {
        type: 'spring',
        stiffness: 300, 
        damping: 30,
        width: { duration: 0.35, ease: [0.4, 0.0, 0.2, 1] },
        opacity: { duration: 0.2, ease: [0.4, 0.0, 0.2, 1] }
      }
    },
    expanded: {
      width: 280,
      x: 0,
      opacity: 1,
      transition: {
        type: 'spring',
        stiffness: 280, 
        damping: 28,
        width: { duration: 0.4, ease: [0.16, 1, 0.3, 1] }, // Smoother ease-out
        opacity: { duration: 0.25, ease: [0.16, 1, 0.3, 1] }
      }
    }
  };

  const toggleSidebarAnimated = () => setSidebarCollapsed(c => !c);

  // Smooth chat width compression variants
  const chatShellVariants = {
    expanded: {
      maxWidth: '1320px',
      scale: 0.985,
      transition: { type: 'spring', stiffness: 140, damping: 20 }
    },
    collapsed: {
      maxWidth: '1480px',
      scale: 1,
      transition: { type: 'spring', stiffness: 160, damping: 18 }
    }
  };
  
  // Backdrop overlay variants for mobile sidebar
  const backdropVariants = {
    hidden: { opacity: 0 },
    visible: { 
      opacity: 0.7,
      transition: { duration: 0.3, ease: [0.4, 0.0, 0.2, 1] }
    }
  };

  return (
    <motion.div 
      className={`dashboard-container ${currentView === 'chat' ? 'full-screen-chat' : 'chat-with-sidebar'} ${sidebarCollapsed ? 'sidebar-collapsed' : 'sidebar-expanded'}`}
      variants={containerVariants}
      initial="initial"
      animate="animate"
      exit="exit"
    >
      {/* Mobile Backdrop Overlay */}
      <AnimatePresence>
        {!sidebarCollapsed && isMobile && (
          <motion.div
            key="backdrop"
            className="sidebar-backdrop"
            variants={backdropVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
            onClick={toggleSidebarAnimated}
          />
        )}
      </AnimatePresence>

      {/* Hide dashboard sidebar when in chat view to avoid double sidebars */}
      {currentView !== 'chat' && (
        <AnimatePresence initial={false}>
          <motion.aside
            key="sidebar"
            className={`modern-sidebar ${sidebarCollapsed ? 'collapsed' : 'expanded'}`}
            variants={sidebarVariants}
            initial={sidebarCollapsed ? 'collapsed' : 'expanded'}
            animate={sidebarCollapsed ? 'collapsed' : 'expanded'}
            exit="hidden"
          >
            <div className="sidebar-header-mini">
              <button
                className="sidebar-toggle-btn"
                onClick={toggleSidebarAnimated}
                title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              >
                {sidebarCollapsed ? <Menu size={18} /> : <X size={18} />}
              </button>
              {!sidebarCollapsed && <h2 className="sidebar-title">Aurion</h2>}
            </div>
            <ModernSidebar
              collapsed={sidebarCollapsed}
              pinned={sidebarPinned}
              currentView={currentView}
              onViewChange={handleViewChange}
              onToggleCollapse={toggleSidebarAnimated}
              theme={theme}
              onToggleTheme={toggleTheme}
              user={user}
              activeSessionId={activeSessionId}
              onSessionSelect={handleSessionSelect}
              onSessionDelete={handleSessionDelete}
              onNewChat={handleNewChat}
            />
          </motion.aside>
        </AnimatePresence>
      )}

      {/* Main Chat Content */}
  <div className={`main-content ${currentView === 'chat' ? 'full-screen' : 'chat-surface'}`}>
        {/* Hide top bar and dashboard wrappers in chat view */}
        {currentView !== 'chat' && (
          <div className="chat-top-bar">
            <button
              className="sidebar-toggle-floating"
              onClick={toggleSidebarAnimated}
              title={sidebarCollapsed ? 'Show sidebar' : 'Hide sidebar'}
            >
              {sidebarCollapsed ? <Menu size={18} /> : <X size={18} />}
            </button>
            <div className="chat-top-bar-spacer" />
          </div>
        )}
  <motion.main className={`dashboard-content ${currentView === 'chat' ? 'full-screen-content chat-main' : 'chat-main'}`} variants={contentVariants} initial="initial" animate="animate">
          <motion.div
            className="chat-shell-width-anim"
            variants={chatShellVariants}
            initial={sidebarCollapsed ? 'collapsed' : 'expanded'}
            animate={sidebarCollapsed ? 'collapsed' : 'expanded'}
            style={{ margin: 0, width: '100%', alignSelf: 'flex-start' }}
          >
            {renderCurrentView()}
          </motion.div>
        </motion.main>
      </div>

      {/* Command Palette */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onViewChange={handleViewChange}
        searchQuery={searchQuery}
      />

      {/* ToastSystem & accessibility toggle removed per request */}
    </motion.div>
  );
};

export default ModernDashboard;