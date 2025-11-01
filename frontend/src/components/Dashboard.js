// frontend/src/components/Dashboard.js

import React, { useEffect, useReducer, useCallback, useMemo, useState } from 'react';
// ... (all other imports remain the same)
import chatService from '../services/chatService';
import sessionService from '../services/sessionService';
import authService from '../services/auth';
import '../styles/Dashboard.css';

import { motion, AnimatePresence } from 'framer-motion';
import ChatWindowNew from './ChatWindowNew';
import LeftSidebarNew from './LeftSidebarNew';
import LoadingSpinner from './LoadingSpinner';
import ErrorDisplay from './ErrorDisplay';
import ChatSkeletonLoader from './ChatSkeletonLoader';

// Utility function to format relative time
const formatRelativeTime = (dateString) => {
  const now = new Date();
  const date = new Date(dateString);
  const diffInSeconds = Math.floor((now - date) / 1000);
  
  if (diffInSeconds < 60) {
    return 'Just now';
  } else if (diffInSeconds < 3600) {
    const minutes = Math.floor(diffInSeconds / 60);
    return `${minutes}m ago`;
  } else if (diffInSeconds < 86400) {
    const hours = Math.floor(diffInSeconds / 3600);
    return `${hours}h ago`;
  } else if (diffInSeconds < 604800) {
    const days = Math.floor(diffInSeconds / 86400);
    return `${days}d ago`;
  } else {
    return date.toLocaleDateString();
  }
};

// --- The Reducer and Custom Hook sections remain completely the same ---
// No changes are needed in this logic.

const initialState = {
  messages: [],
  sessions: [],
  activeSessionId: null,
  input: '',
  status: 'idle', 
  error: null,
  currentUserEmail: '',
  pendingTasks: [], // Can populate with dummy data if needed, e.g., ['Task 1', 'Task 2']
  currentPage: 1,
  hasMoreMessages: true,
};

function chatReducer(state, action) {
  // ... (no changes in the reducer logic)
  switch (action.type) {
    case 'INITIAL_LOAD_START':
      return { ...state, status: 'pageLoading' };
    case 'INITIAL_LOAD_SUCCESS':
      return { ...state, status: 'idle', sessions: action.payload.sessions, messages: [action.payload.initialMessage] };
    case 'INITIAL_LOAD_ERROR':
      return { ...state, status: 'error', error: action.payload };
    
    case 'SELECT_SESSION_START':
      return { ...state, status: 'sessionLoading', activeSessionId: action.payload, messages: [], currentPage: 1, hasMoreMessages: true };
    case 'SELECT_SESSION_SUCCESS':
      // Add timestamps if not present from service
      const messagesWithTimestamps = action.payload.messages.map(msg => ({
        ...msg,
        timestamp: msg.timestamp || new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true })
      }));
      return { ...state, status: 'idle', messages: messagesWithTimestamps, hasMoreMessages: action.payload.hasMore };
    case 'SELECT_SESSION_ERROR':
      return { ...state, status: 'error', error: action.payload };

    case 'SEND_MESSAGE_START':
      return { ...state, status: 'loading', input: '', messages: [...state.messages, action.payload.userMessage] };
    case 'SEND_MESSAGE_SUCCESS':
      return { ...state, status: 'idle', messages: [...state.messages, action.payload.assistantMessage] };
    case 'SEND_MESSAGE_ERROR':
      return { ...state, status: 'error', error: action.payload, messages: [...state.messages, { sender: 'assistant', text: 'Sorry, an error occurred.' }] };
    
    case 'NEW_SESSION_CREATED':
      return { ...state, activeSessionId: action.payload.sessionId, sessions: action.payload.updatedSessions };

    case 'NEW_CHAT':
      return { ...state, activeSessionId: null, messages: action.payload, status: 'idle' };

    case 'UPDATE_SESSIONS':
      return { ...state, sessions: action.payload };
    
    case 'SET_INPUT':
      return { ...state, input: action.payload };

    case 'SET_USER_EMAIL':
      return { ...state, currentUserEmail: action.payload };
      
    default:
      throw new Error(`Unhandled action type: ${action.type}`);
  }
}

const useChatManager = ({ state, dispatch }) => {
    // ... (no changes in the custom hook logic)
    const initialMessage = useMemo(
        () => ({ 
          sender: 'assistant', 
          text: 'Hello! How can I assist you today?', 
          timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true }) 
        }),
        []
      );
    
      const loadSessions = useCallback(async () => {
        try {
          const response = await chatService.getSessions();
          
          // Transform sessions to include formatted timestamp
          const transformedSessions = response.data.map(session => ({
            ...session,
            timestamp: formatRelativeTime(session.createdAt)
          }));
          
          dispatch({ type: 'UPDATE_SESSIONS', payload: transformedSessions });
          return transformedSessions;
        } catch (err) {
          console.error("Failed to load sessions:", err);
          throw new Error("Could not load sessions.");
        }
      }, [dispatch]);
    
      const loadInitialData = useCallback(async () => {
        dispatch({ type: 'INITIAL_LOAD_START' });
        try {
          const sessions = await loadSessions();
          dispatch({ type: 'INITIAL_LOAD_SUCCESS', payload: { sessions, initialMessage } });
        } catch (err) {
          dispatch({ type: 'INITIAL_LOAD_ERROR', payload: err.message });
        }
      }, [dispatch, loadSessions, initialMessage]);
    
      const handleSelectSession = useCallback(async (sessionId) => {
        if (!sessionId || sessionId === state.activeSessionId) return;
        dispatch({ type: 'SELECT_SESSION_START', payload: sessionId });
        try {
          const response = await sessionService.getSessionMessages(sessionId, 1);
          const hasMore = (response.data.messages?.length || 0) < response.data.totalMessages;
          dispatch({ type: 'SELECT_SESSION_SUCCESS', payload: { messages: response.data.messages, hasMore } });
        } catch (err) {
          console.error("Failed to load session:", err);
          dispatch({ type: 'SELECT_SESSION_ERROR', payload: 'Could not load chat history.' });
        }
      }, [state.activeSessionId, dispatch]);
    
      const handleNewChat = useCallback(() => {
        dispatch({ type: 'NEW_CHAT', payload: [initialMessage] });
      }, [dispatch, initialMessage]);
    
      const handleDeleteSession = useCallback(async (sessionId) => {
        try {
          await chatService.deleteSession(sessionId);
          if (state.activeSessionId === sessionId) {
            handleNewChat();
          }
          await loadSessions();
        } catch (err) {
          dispatch({ type: 'INITIAL_LOAD_ERROR', payload: 'Could not delete the session.' });
        }
      }, [state.activeSessionId, dispatch, loadSessions, handleNewChat]);
    
      const handleSendMessage = useCallback(async (e) => {
        e.preventDefault();
        if (!state.input.trim() || state.status === 'loading') return;
    
        const userMessage = { 
          sender: 'user', 
          text: state.input, 
          timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true }) 
        };
        dispatch({ type: 'SEND_MESSAGE_START', payload: { userMessage } });
        
        try {
          if (!state.activeSessionId) {
            const newChatResponse = await chatService.startNewChat(userMessage.text);
            const assistantMessage = { 
              sender: 'assistant', 
              text: newChatResponse.data.response_text, 
              timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true }) 
            };
            const updatedSessions = await loadSessions();
            dispatch({ type: 'NEW_SESSION_CREATED', payload: { sessionId: newChatResponse.data.session_id, updatedSessions } });
            dispatch({ type: 'SEND_MESSAGE_SUCCESS', payload: { assistantMessage } });
            // If backend provided a confident video selection, append it after the reply
            const v = newChatResponse?.data?.video;
            if (v && v.videoId) {
              const videoMessage = {
                sender: 'assistant',
                text: v.title || 'Video',
                youtube: { videoId: v.videoId },
                timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true })
              };
              dispatch({ type: 'SEND_MESSAGE_SUCCESS', payload: { assistantMessage: videoMessage } });
            }
          } else {
            const continueChatResponse = await chatService.sendMessage(state.activeSessionId, userMessage.text);
            const assistantMessage = { 
              sender: 'assistant', 
              text: continueChatResponse.data.response_text, 
              timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true }) 
            };
            dispatch({ type: 'SEND_MESSAGE_SUCCESS', payload: { assistantMessage } });
            const v = continueChatResponse?.data?.video;
            if (v && v.videoId) {
              const videoMessage = {
                sender: 'assistant',
                text: v.title || 'Video',
                youtube: { videoId: v.videoId },
                timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true })
              };
              dispatch({ type: 'SEND_MESSAGE_SUCCESS', payload: { assistantMessage: videoMessage } });
            }
          }
        } catch (error) {
          console.error("Error sending message:", error);
          dispatch({ type: 'SEND_MESSAGE_ERROR', payload: error.message });
        }
      }, [state.activeSessionId, state.input, state.status, dispatch, loadSessions]);
      
      return useMemo(() => ({
        loadInitialData,
        handleSelectSession,
        handleNewChat,
        handleDeleteSession,
        handleSendMessage,
      }), [loadInitialData, handleSelectSession, handleNewChat, handleDeleteSession, handleSendMessage]);
};


// ==================================================
// 🔹 Main Dashboard Component
// ==================================================

const Dashboard = () => {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const handlers = useChatManager({ state, dispatch });
  const [showUploadPopup, setShowUploadPopup] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [leftSidebarExpanded, setLeftSidebarExpanded] = useState(() => localStorage.getItem('sidebarExpanded') === 'true');
  const [isDark, setIsDark] = useState(() => localStorage.getItem('theme') === 'dark');
  const [currentTab, setCurrentTab] = useState(() => localStorage.getItem('currentTab') || 'chat');
  
  const { 
    status, error, sessions, activeSessionId, 
    messages, input, currentUserEmail, pendingTasks 
  } = state;

  const tabs = useMemo(() => [
    { id: 'dashboard', label: 'Dashboard', icon: 'bi-house-door' },
    { id: 'chat', label: 'Chat', icon: 'bi-chat-dots' },
    { id: 'tasks', label: 'Tasks', icon: 'bi-list-task' },
  ], []);

  // Save preferences to localStorage
  useEffect(() => {
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  useEffect(() => {
    localStorage.setItem('currentTab', currentTab);
  }, [currentTab]);

  useEffect(() => {
    localStorage.setItem('sidebarExpanded', leftSidebarExpanded);
  }, [leftSidebarExpanded]);

  // Close upload popup when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (showUploadPopup && !event.target.closest('.chat-input-container')) {
        setShowUploadPopup(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showUploadPopup]);

  useEffect(() => {
    const user = authService.getCurrentUser();
    if (user?.access_token) {
      try {
        const tokenData = JSON.parse(atob(user.access_token.split('.')[1]));
        dispatch({ type: 'SET_USER_EMAIL', payload: tokenData.sub });
      } catch (e) { console.error("Failed to decode token:", e); }
    }
    handlers.loadInitialData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Handle file uploads (simulated response for now)
  const handleUpload = useCallback((type) => (e) => {
    const file = e.target.files[0];
    if (file) {
      const messageText = `Uploaded ${type}: ${file.name}`;
      const userMessage = { 
        sender: 'user', 
        text: messageText, 
        timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true }) 
      };
      dispatch({ type: 'SEND_MESSAGE_START', payload: { userMessage } });
      // Simulate assistant response (replace with actual service call if available)
      setTimeout(() => {
        const assistantMessage = { 
          sender: 'assistant', 
          text: `Received your ${type} upload: ${file.name}. How can I help with it?`, 
          timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true }) 
        };
        dispatch({ type: 'SEND_MESSAGE_SUCCESS', payload: { assistantMessage } });
      }, 1000);
    }
    setShowUploadPopup(false);
  }, [dispatch]);

  // Handle recording toggle (placeholder for actual speech-to-text)
  const handleToggleRecording = useCallback(() => {
    setIsRecording(prev => !prev);
    if (!isRecording) {
      console.log('Recording started');
      // Implement speech recognition here (e.g., using Web Speech API)
    } else {
      console.log('Recording stopped');
      // Process recorded audio to text and set input
    }
  }, [isRecording]);

  if (status === 'pageLoading') return <LoadingSpinner />;
  if (status === 'error') return <ErrorDisplay message={error} onRetry={handlers.loadInitialData} />;

  return (
    <div className={`dashboard-container ${isDark ? 'dark' : ''}`}>
      {/* Mini Navbar */}
      <nav className="mini-navbar">
        <div className="logo-title">
          <i className="bi bi-robot"></i>
          <h1>Aurion</h1>
        </div>
        <ul className="tabs">
          {tabs.map(tab => (
            <li 
              key={tab.id} 
              className={currentTab === tab.id ? 'active' : ''} 
              onClick={() => setCurrentTab(tab.id)}
            >
              <i className={`bi ${tab.icon}`}></i>
              {tab.label}
              {tab.id === 'tasks' && pendingTasks.length > 0 && (
                <span className="badge">{pendingTasks.length}</span>
              )}
            </li>
          ))}
        </ul>
        <div className="user-section">
          <span className="user-email">{currentUserEmail}</span>
          <button className="theme-toggle" onClick={() => setIsDark(!isDark)}>
            <i className={`bi ${isDark ? 'bi-sun' : 'bi-moon'}`}></i>
          </button>
        </div>
      </nav>

      {/* Main Content with Animations */}
      <AnimatePresence mode="wait">
        <motion.div
          key={currentTab}
          initial={{ opacity: 0, x: 100 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -100 }}
          transition={{ duration: 0.3 }}
          className="content-wrapper"
        >
          {currentTab === 'chat' ? (
            <div className="chat-container">
              <LeftSidebarNew
                sessions={sessions}
                activeSessionId={activeSessionId}
                onNewChat={handlers.handleNewChat}
                onSelectSession={handlers.handleSelectSession}
                onDeleteSession={handlers.handleDeleteSession}
                isExpanded={leftSidebarExpanded}
                onToggleExpanded={setLeftSidebarExpanded}
              />
              <main className="dashboard-main">
                {status === 'sessionLoading' ? (
                  <ChatSkeletonLoader />
                ) : (
                  <ChatWindowNew
                    messages={messages}
                    isLoading={status === 'loading'}
                    activeSessionId={activeSessionId}
                  />
                )}
                <div className="chat-input-container">
                  {showUploadPopup && (
                    <div className="upload-popup">
                      <div className="upload-option" onClick={() => document.getElementById('image-upload').click()}>
                        <span className="upload-icon">🖼️</span>
                        <span>Upload Image</span>
                      </div>
                      <div className="upload-option" onClick={() => document.getElementById('file-upload').click()}>
                        <span className="upload-icon">📁</span>
                        <span>Upload File</span>
                      </div>
                    </div>
                  )}
                  <input id="image-upload" type="file" accept="image/*" style={{ display: 'none' }} onChange={handleUpload('image')} />
                  <input id="file-upload" type="file" style={{ display: 'none' }} onChange={handleUpload('file')} />
                  <form className="chat-input-area" onSubmit={handlers.handleSendMessage}>
                    <button 
                      type="button" 
                      className={`upload-toggle-btn ${showUploadPopup ? 'active' : ''}`}
                      onClick={() => setShowUploadPopup(!showUploadPopup)}
                    >
                      <i className={`bi ${showUploadPopup ? 'bi-x' : 'bi-plus'}`}></i>
                    </button>
                    <input
                      type="text"
                      className="chat-input"
                      placeholder="Type your message here..."
                      value={input}
                      onChange={(e) => dispatch({ type: 'SET_INPUT', payload: e.target.value })}
                    />
                    <button 
                      type="button" 
                      className={`mic-button ${isRecording ? 'recording' : ''}`}
                      onClick={handleToggleRecording}
                    >
                      <i className={`bi ${isRecording ? 'bi-mic-fill' : 'bi-mic'}`}></i>
                    </button>
                    <button type="submit" className="send-button" disabled={!input.trim()}>
                      <span className="send-icon">
                        {status === 'loading' ? '⏳' : '➤'}
                      </span>
                      <span className="send-text">
                        {status === 'loading' ? 'Sending...' : 'Send'}
                      </span>
                    </button>
                  </form>
                </div>
              </main>
            </div>
          ) : currentTab === 'dashboard' ? (
            <div className="dashboard-content">
              <h2>Dashboard Overview</h2>
              <p>👋 Welcome, {currentUserEmail}! Here's your quick overview.</p>
              {/* Add stats or widgets here as needed */}
            </div>
          ) : (
            <div className="tasks-content">
              <h2>Tasks</h2>
              {pendingTasks.length > 0 ? (
                <ul>
                  {pendingTasks.map((task, index) => (
                    <li key={index}>{task}</li>
                  ))}
                </ul>
              ) : (
                <p>No pending tasks.</p>
              )}
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
};

export default Dashboard;