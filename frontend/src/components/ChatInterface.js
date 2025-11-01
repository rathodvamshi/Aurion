// 
// Yes. It’s the main chat UI component: displays messages, streams AI replies, handles sending (text/files/voice), embeds YouTube, feedback, scrolling, and attachments.

// Modern Chat Interface with Streaming and Enhanced UX
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import '../styles/ChatInterface.css';
import '../styles/AIThinkingIndicator.css';
import '../styles/TypingIndicator.css';
import chatService from '../services/chatService';
import authService from '../services/auth';
import AIThinkingIndicator from './AIThinkingIndicator';
import TypingIndicator from './TypingIndicator';
import {
  Send,
  Paperclip,
  Smile,
  Copy,
  Edit3,
  Trash2,
  ThumbsUp,
  ThumbsDown,
  Square,
  User,
  Bot,
  Volume2,
  Loader2,
  ArrowDown,
  Mic,
  X,
  Image as ImageIcon
} from 'lucide-react';
import VideoEmbed from './VideoEmbed';
import { searchYouTube } from '../services/youtubeService';

const ChatInterface = ({
  activeSessionId,
  sessionHistory = [],
  sessionLoading = false,
  onSessionChange,
  onMessageSent,
  onNewSession
}) => {
  // ========================
  // State Management
  // ========================
  const [messages, setMessages] = useState(sessionHistory);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState(null);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(sessionLoading);
  const [hoveredMessage, setHoveredMessage] = useState(null);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [userIsAnchored, setUserIsAnchored] = useState(true);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const [showDetailedThinking, setShowDetailedThinking] = useState(false);
  
  // File and media state
  const [attachedFiles, setAttachedFiles] = useState([]);
  const [showImagePreview, setShowImagePreview] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);
  const [isRecording, setIsRecording] = useState(false);

  // ========================
  // Refs
  // ========================
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const inputRef = useRef(null);
  const topSentinelRef = useRef(null);
  const streamingRef = useRef(null);
  const fileInputRef = useRef(null);
  const mediaRecorderRef = useRef(null);

  // ========================
  // Scroll Management (moved up to fix reference error)
  // ========================
  const scrollToBottom = useCallback((behavior = 'auto') => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ 
        behavior: reducedMotion ? 'auto' : behavior,
        block: 'end'
      });
    }
  }, [reducedMotion]);

  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    
    const threshold = 60;
    const isAtBottom = (container.scrollHeight - container.scrollTop - container.clientHeight) < threshold;
    
    setUserIsAnchored(isAtBottom);
    setShowJumpToBottom(!isAtBottom && messages.length > 0);
  }, [messages.length]);

  const jumpToBottom = useCallback(() => {
    scrollToBottom('smooth');
    setShowJumpToBottom(false);
  }, [scrollToBottom]);

  // ========================
  // Effects
  // ========================
  useEffect(() => {
    // Initialize chat
    initializeChat();
    
    // Check reduced motion preference
    const hasReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
                            localStorage.getItem('maya-reduced-motion') === 'true';
    setReducedMotion(hasReducedMotion);
  }, []);

  // Setup intersection observer for infinite scroll
  useEffect(() => {
    if (!topSentinelRef.current || !hasMoreHistory) return;

    const observer = new IntersectionObserver(
      async (entries) => {
        if (entries[0].isIntersecting && hasMoreHistory && !isLoadingHistory) {
          setIsLoadingHistory(true);
          try {
            const olderMessages = await chatService.getSessionHistory?.(
              activeSessionId, 
              { 
                before: messages[0]?.timestamp, 
                limit: 50 
              }
            ) || [];
            
            if (olderMessages.length === 0) {
              setHasMoreHistory(false);
            } else {
              setMessages(prev => [...olderMessages, ...prev]);
            }
          } catch (error) {
            console.error('Error loading older messages:', error);
            if (window.addNotification) {
              window.addNotification({
                type: 'error',
                title: 'Load Failed',
                message: 'Could not load older messages'
              });
            }
          } finally {
            setIsLoadingHistory(false);
          }
        }
      },
      { 
        root: messagesContainerRef.current,
        threshold: 0.1 
      }
    );

    observer.observe(topSentinelRef.current);

    return () => observer.disconnect();
  }, [activeSessionId, hasMoreHistory, isLoadingHistory, messages]);

  // Sync with session history changes
  useEffect(() => {
    if (sessionHistory && sessionHistory.length >= 0) {
      setMessages(sessionHistory);
      setIsLoadingHistory(sessionLoading);
      
      // Scroll to bottom after session loads
      setTimeout(() => {
        scrollToBottom();
      }, 100);
    }
  }, [sessionHistory, sessionLoading]);

  // Sync loading state with session loading
  useEffect(() => {
    setIsLoadingHistory(sessionLoading);
  }, [sessionLoading]);

  // Auto-scroll to bottom when new messages arrive (unless user is scrolled up)
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (container && messages.length > 0) {
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
      const lastMessage = messages[messages.length - 1];
      
      if (isNearBottom || lastMessage?.role === 'user' || isStreaming) {
        scrollToBottom('auto');
      }
    }
  }, [messages, isStreaming, scrollToBottom]);

  // Auto-scroll when session history loads
  useEffect(() => {
    if (!isLoadingHistory && activeSessionId && sessionHistory.length > 0) {
      // Delay scroll to ensure DOM is updated
      setTimeout(() => {
        scrollToBottom('auto');
      }, 100);
    }
  }, [isLoadingHistory, activeSessionId, sessionHistory.length, scrollToBottom]);

  // Auto-scroll when anchored
  useEffect(() => {
    if (userIsAnchored && !isLoadingHistory) {
      scrollToBottom('auto');
    }
  }, [messages, userIsAnchored, isLoadingHistory, scrollToBottom]);

  // ========================
  // Animation Variants
  // ========================
  const messageVariants = {
    initial: { opacity: 0, y: 16, scale: 0.98 },
    animate: { 
      opacity: 1, 
      y: 0, 
      scale: 1,
      transition: { 
        type: "spring",
        damping: 26,
        stiffness: 350,
        mass: 0.8,
        duration: 0.3, 
        ease: [0.2, 0.9, 0.3, 1] 
      } 
    },
    exit: { 
      opacity: 0, 
      y: -12, 
      scale: 0.96,
      filter: "blur(2px)",
      transition: { 
        duration: 0.25, 
        ease: [0.4, 0.0, 0.2, 1] 
      } 
    }
  };
  
  // User and assistant messages can have slightly different animations
  const userMessageVariants = {
    ...messageVariants,
    initial: { opacity: 0, y: 12, scale: 0.97 },
    animate: {
      ...messageVariants.animate,
      transition: {
        ...messageVariants.animate.transition,
        damping: 28,
        stiffness: 380
      }
    }
  };
  
  const assistantMessageVariants = {
    ...messageVariants,
    initial: { opacity: 0, y: 16, scale: 0.98 },
  };
  
  const listStagger = { 
    animate: { 
      transition: { 
        staggerChildren: 0.05, 
        delayChildren: 0.02 
      } 
    } 
  };

  // ========================
  // Initialization
  // ========================
  const initializeChat = async () => {
    try {
      setLoading(true);
      
      // Load user data
      const currentUser = authService.getCurrentUser();
      if (currentUser) {
        setUser(currentUser);
      }

      // Load chat history
      await loadChatHistory();
      
    } catch (error) {
      console.error('Error initializing chat:', error);
      if (window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'Chat Initialization Error',
          message: 'Failed to load chat data'
        });
      }
    } finally {
      setLoading(false);
    }
  };

  const loadChatHistory = async () => {
    try {
      // Clear any local cached messages
      localStorage.removeItem('maya-chat-messages');
      
      const response = await chatService.getHistory();
      if (response.data && response.data.length > 0) {
        // Transform backend message format to frontend format
        const formattedMessages = response.data.map((msg, idx) => {
          // Support both new shape {role, content, timestamp} and legacy {sender, text}
          const role = msg.role || (msg.sender === 'user' ? 'user' : 'assistant');
          const content = msg.content || msg.text || '';
          const ts = msg.timestamp ? new Date(msg.timestamp) : new Date(Date.now() - (response.data.length - idx) * 1000);
          return {
            id: msg.id || `hist-${Date.now()}-${idx}`,
            role,
            content,
            timestamp: ts,
            sessionId: msg.session_id || undefined,
          };
        });
        setMessages(formattedMessages);
      } else {
        // No history, start with empty state
        setMessages([]);
      }
    } catch (error) {
      console.error('Error loading chat history:', error);
      // If unauthorized, prompt re-auth
      if (error?.response?.status === 401) {
        if (window.addNotification) {
          window.addNotification({
            type: 'warning',
            title: 'Sign-in required',
            message: 'Your session expired. Please sign in again.'
          });
        }
      }
      // Start with empty messages if history fails to load
      setMessages([]);
    }
  };

  // ========================
  // Data Loading
  // ========================
  const loadMoreHistory = async () => {
    if (!hasMoreHistory || isLoadingHistory) return;

    setIsLoadingHistory(true);
    try {
      // Future enhancement: implement pagination with backend API
      setHasMoreHistory(false);
    } catch (error) {
      console.error('Error loading history:', error);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  // ========================
  // Message Handlers
  // ========================
  const handleSendMessage = async () => {
    if ((!input.trim() && attachedFiles.length === 0) || isStreaming) return;

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
      sessionId: activeSessionId,
      attachments: attachedFiles.map(file => ({
        id: file.id,
        name: file.name,
        type: file.type,
        size: file.size,
        url: file.url
      }))
    };

    // Add user message locally
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    
    // Clear attachments
    attachedFiles.forEach(file => URL.revokeObjectURL(file.url));
    setAttachedFiles([]);
    
    // Notify parent component about new message
    if (onMessageSent) {
      onMessageSent(userMessage);
    }
    
  // Note: Do not auto-embed videos from user text.
  // We rely on the backend to return a video payload only when it's confident,
  // and we will append it AFTER the assistant's reply is rendered.

    // Start streaming response
    await streamAIResponse(userMessage);
  };

  // --- YouTube auto-embed helpers ---
  const shouldAutoEmbedYouTube = (text) => {
    if (!text) return false;
    const low = String(text).toLowerCase();
    const cues = /(\byoutube\b|\bvideo\b|\bsearch\b|\bshow me\b|\bplay\b)/i.test(low);
    const neg = /(don['’]t|do not|no)\s+(video|play)/i.test(low);
    // Also skip when message looks like code or multi-line
    const tooLong = low.length > 300;
    return cues && !neg && !tooLong;
  };

  const extractYouTubeVideoIdFromText = (text) => {
    if (!text) return null;
    try {
      // Match youtu.be short links
      const short = text.match(/https?:\/\/youtu\.be\/([\w-]{6,})/i);
      if (short && short[1]) return short[1];
      // Match youtube.com/watch?v=...
      const long = text.match(/https?:\/\/(?:www\.)?youtube\.com\/watch\?[^\s]*v=([\w-]{6,})/i);
      if (long && long[1]) return long[1];
      // Match embed URLs
      const emb = text.match(/https?:\/\/(?:www\.)?youtube\.com\/embed\/([\w-]{6,})/i);
      if (emb && emb[1]) return emb[1];
    } catch {}
    return null;
  };

  const maybeAutoEmbedYouTube = async (text) => {
    try {
      // If the user pasted a YouTube link directly, embed it immediately
      const directId = extractYouTubeVideoIdFromText(text);
      if (directId) {
        const ytMessage = {
          id: `yt_${Date.now()}`,
          role: 'assistant',
          type: 'youtube',
          content: 'YouTube video',
          youtube: {
            videoId: directId,
            url: `https://www.youtube.com/watch?v=${directId}`,
            title: 'YouTube video',
            channelTitle: '',
            thumbnail: '',
          },
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, ytMessage]);
        return;
      }

      if (!shouldAutoEmbedYouTube(text)) return;
      const data = await searchYouTube(text, { maxResults: 5 });
      const top = data?.top;
      if (!top?.videoId) return;
      const ytMessage = {
        id: `yt_${Date.now()}`,
        role: 'assistant',
        type: 'youtube',
        content: `${top.title}${top.channelTitle ? ` • ${top.channelTitle}` : ''}`,
        youtube: {
          videoId: top.videoId,
          url: top.url,
          title: top.title,
          channelTitle: top.channelTitle,
          thumbnail: top.thumbnail,
        },
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, ytMessage]);
    } catch (e) {
      // Silent fail to avoid interrupting chat flow
      // console.warn('YouTube auto-embed failed', e);
    }
  };

  const streamAIResponse = async (userMessage) => {
    const messageId = `ai-${Date.now()}`;
    setIsStreaming(true);
    setStreamingMessageId(messageId);
    setShowThinking(true);

    try {
      let response;
      let sessionId = activeSessionId;
      
      if (!activeSessionId) {
        // Start new chat session
        response = await chatService.startNewChat(userMessage.content);
        sessionId = response.data.session_id;
        
        // Notify parent about new session
        if (onSessionChange && sessionId) {
          onSessionChange(sessionId);
        }
      } else {
        // Continue existing session
        response = await chatService.sendMessage(activeSessionId, userMessage.content);
      }

      const aiResponse = response.data.response_text || response.data.content || 'I apologize, but I encountered an issue processing your request.';
      // Hold any server-provided video to append AFTER the assistant reply finishes
      const serverVideo = (() => {
        try { return response?.data?.video; } catch { return null; }
      })();

      // Add AI message while keeping thinking indicator active
      const aiMessage = {
        id: messageId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isStreaming: true,
        sessionId: sessionId
      };

      setMessages(prev => [...prev, aiMessage]);

      // Small delay to show thinking completion, then hide and start streaming
      setTimeout(() => {
        setShowThinking(false);
      }, 300);

      // Simulate streaming by updating content gradually
      await simulateStreamingText(messageId, aiResponse, sessionId);

      // After the assistant reply is fully rendered, append the video if provided by server
      try {
        const v = serverVideo;
        if (v && v.videoId) {
          setMessages(prev => {
            const already = prev.slice(-5).some(m => m.youtube?.videoId === v.videoId);
            if (already) return prev;
            const ytMsg = {
              id: `yt_${Date.now()}`,
              role: 'assistant',
              type: 'youtube',
              content: '🎬 Playing your requested video',
              timestamp: new Date(),
              youtube: {
                videoId: v.videoId,
                url: v.url,
                // Keep metadata for hover/tooltips if needed, but do not render in text
                title: v.title,
                channelTitle: v.channelTitle,
                thumbnail: v.thumbnail,
              }
            };
            return [...prev, ytMsg];
          });
          // Mark that this user request already yielded a server-side video to avoid client auto-search
          if (typeof window !== 'undefined') {
            window.__maya_last_play_had_server_video__ = true;
            setTimeout(() => { try { delete window.__maya_last_play_had_server_video__; } catch {} }, 4000);
          }
        }
      } catch {}

    } catch (error) {
      console.error('Error getting AI response:', error);
      
      // Hide thinking indicator on error
      setShowThinking(false);

      // Add error message
      const errorMessage = {
        id: messageId,
        role: 'assistant',
        content: 'I apologize, but I encountered an error processing your request. Please try again later.',
        timestamp: new Date(),
        isStreaming: false,
        error: true,
        sessionId: activeSessionId
      };

      setMessages(prev => [...prev, errorMessage]);

      if (window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'Chat Error',
          message: 'Failed to get AI response'
        });
      }
    } finally {
      setIsStreaming(false);
      setStreamingMessageId(null);
    }
  };

  const simulateStreamingText = async (messageId, fullText, sessionId) => {
    const words = fullText.split(' ');
    let currentText = '';
    
    // Add a small initial delay to show the transition from thinking to streaming
    await new Promise(resolve => setTimeout(resolve, 400));
    
    for (let i = 0; i < words.length; i++) {
      currentText += (i > 0 ? ' ' : '') + words[i];
      
      setMessages(prev => prev.map(msg => 
        msg.id === messageId 
          ? { ...msg, content: currentText }
          : msg
      ));
      
      // Add small delay for streaming effect
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    
    // Mark streaming as complete and create final message
    const finalMessage = {
      id: messageId,
      role: 'assistant',
      content: fullText,
      timestamp: new Date(),
      isStreaming: false,
      sessionId: sessionId
    };
    
    setMessages(prev => prev.map(msg => 
      msg.id === messageId ? finalMessage : msg
    ));
    
    // Notify parent about AI response
    if (onMessageSent) {
      onMessageSent(finalMessage);
    }
    
    setIsStreaming(false);
    setStreamingMessageId(null);
  };

  const stopStreaming = useCallback(() => {
    if (streamingRef.current) {
      streamingRef.current.abort?.();
    }
    
    // Mark current streaming message as incomplete
    if (streamingMessageId) {
      setMessages(prev => prev.map(msg => 
        msg.id === streamingMessageId 
          ? { ...msg, isStreaming: false, incomplete: true }
          : msg
      ));
    }
    
    setIsStreaming(false);
    setStreamingMessageId(null);
  }, [streamingMessageId]);

  // ========================
  // Action Handlers
  // ========================
  const handleCopyMessage = useCallback((message) => {
    const content = message.content || message.text || '';
    navigator.clipboard.writeText(content).then(() => {
      if (window.addNotification) {
        window.addNotification({
          type: 'success',
          title: 'Copied!',
          message: 'Message copied to clipboard'
        });
      }
    }).catch(() => {
      if (window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'Copy Failed',
          message: 'Could not copy to clipboard'
        });
      }
    });
  }, []);

  const handleEditResend = useCallback((message) => {
    const content = message.content || message.text || '';
    setInput(content);
    if (inputRef.current) {
      inputRef.current.focus();
    }
    
    // Mark original as edited
    setMessages(prev => prev.map(m => 
      m.id === message.id ? { ...m, edited: true } : m
    ));
  }, []);

  const handleFeedback = useCallback(async (message, direction) => {
    // Optimistic update
    setMessages(prev => prev.map(m => 
      m.id === message.id ? { ...m, feedback: direction } : m
    ));

    try {
      await chatService.submitFeedback?.(
        message.sessionId || activeSessionId,
        message.id,
        { rating: direction }
      );

      if (window.addNotification) {
        window.addNotification({
          type: 'success',
          title: 'Feedback Sent',
          message: `Thank you for your ${direction === 'up' ? 'positive' : 'negative'} feedback!`
        });
      }
    } catch (error) {
      // Revert optimistic update
      setMessages(prev => prev.map(m => 
        m.id === message.id ? { ...m, feedback: null } : m
      ));

      if (window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'Feedback Failed',
          message: 'Could not submit feedback. Please try again.'
        });
      }
    }
  }, [activeSessionId]);

  const handleSpeak = useCallback((message) => {
    if (!window.speechSynthesis) {
      if (window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'TTS Not Supported',
          message: 'Text-to-speech is not supported in this browser'
        });
      }
      return;
    }

    // Cancel any ongoing speech
    speechSynthesis.cancel();
    
    const content = message.content || message.text || '';
    const utterance = new SpeechSynthesisUtterance(content);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 0.8;
    
    speechSynthesis.speak(utterance);
  }, []);

  const handleDeleteMessage = useCallback(async (message) => {
    if (!window.confirm('Are you sure you want to delete this message?')) {
      return;
    }

    // Optimistic removal
    const originalMessages = messages;
    setMessages(prev => prev.filter(m => m.id !== message.id));

    try {
      await chatService.deleteMessage?.(
        message.sessionId || activeSessionId,
        message.id
      );

      if (window.addNotification) {
        window.addNotification({
          type: 'success',
          title: 'Message Deleted',
          message: 'Message has been removed'
        });
      }
    } catch (error) {
      // Revert deletion
      setMessages(originalMessages);

      if (window.addNotification) {
        window.addNotification({
          type: 'error',
          title: 'Delete Failed',
          message: 'Could not delete message. Please try again.'
        });
      }
    }
  }, [messages, activeSessionId]);
  // Session helper functions (moved up so clearChat can call resetChat safely)
  function resetChat() {
    setMessages([]);
    setIsStreaming(false);
    setStreamingMessageId(null);
    // Clear all localStorage related to chat
    localStorage.removeItem('maya-chat-messages');
    localStorage.removeItem('maya-chat-session');
    if (onNewSession) {
      onNewSession();
    }
  }

  const startNewSession = () => {
    setMessages([]);
    localStorage.removeItem('maya-chat-messages');
    localStorage.removeItem('maya-chat-session');
    if (onNewSession) {
      onNewSession();
    }
    if (window.addNotification) {
      window.addNotification({
        type: 'info',
        title: 'New Session',
        message: 'Started a new chat session'
      });
    }
  };

  const clearChat = async () => {
    if (window.confirm('Are you sure you want to clear all chat history? This action cannot be undone.')) {
      try {
        // Clear from backend if session exists
        if (activeSessionId) {
          await chatService.clearHistory(activeSessionId);
        }
        
        // Reset local state using existing resetChat function
        resetChat();
        
        if (window.addNotification) {
          window.addNotification({
            type: 'success',
            title: 'Chat Cleared',
            message: 'All chat history has been cleared'
          });
        }
        
        console.log('Chat cleared successfully');
      } catch (error) {
        console.error('Failed to clear chat:', error);
        // Even if backend clear fails, reset local state
        resetChat();
        
        if (window.addNotification) {
          window.addNotification({
            type: 'error',
            title: 'Clear Failed',
            message: 'Chat has been cleared locally but may still exist on server'
          });
        }
      }
    }
  };

  // ========================
  // File and Media Handlers
  // ========================
  const handleFileSelect = useCallback((e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    const newFiles = files.map(file => ({
      id: Date.now() + Math.random(),
      file,
      name: file.name,
      size: file.size,
      type: file.type,
      url: URL.createObjectURL(file)
    }));

    setAttachedFiles(prev => [...prev, ...newFiles]);
    
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  const handleFileRemove = useCallback((fileId) => {
    setAttachedFiles(prev => {
      const updatedFiles = prev.filter(f => f.id !== fileId);
      // Clean up object URLs to prevent memory leaks
      const removedFile = prev.find(f => f.id === fileId);
      if (removedFile) {
        URL.revokeObjectURL(removedFile.url);
      }
      return updatedFiles;
    });
  }, []);

  const handleImagePreview = useCallback((file) => {
    setPreviewImage(file);
    setShowImagePreview(true);
  }, []);

  const handleCloseImagePreview = useCallback(() => {
    setShowImagePreview(false);
    setPreviewImage(null);
  }, []);

  const handleAttachClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleMicClick = useCallback(async () => {
    if (isRecording) {
      // Stop recording
      if (mediaRecorderRef.current) {
        mediaRecorderRef.current.stop();
      }
      setIsRecording(false);
    } else {
      // Start recording
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mediaRecorder = new MediaRecorder(stream);
        mediaRecorderRef.current = mediaRecorder;

        const chunks = [];
        mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
        mediaRecorder.onstop = () => {
          const audioBlob = new Blob(chunks, { type: 'audio/wav' });
          const audioFile = {
            id: Date.now(),
            file: audioBlob,
            name: `voice-note-${Date.now()}.wav`,
            size: audioBlob.size,
            type: 'audio/wav',
            url: URL.createObjectURL(audioBlob)
          };
          setAttachedFiles(prev => [...prev, audioFile]);
          
          // Clean up stream
          stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        setIsRecording(true);
      } catch (error) {
        console.error('Error accessing microphone:', error);
        if (window.addNotification) {
          window.addNotification({
            type: 'error',
            title: 'Microphone Access Denied',
            message: 'Please allow microphone access to record voice notes'
          });
        }
      }
    }
  }, [isRecording]);
  // (Removed duplicate clearChat/startNewSession/resetChat definitions below – consolidated above)

  const reactToMessage = async (messageId, reaction) => {
    // Legacy function - replaced by handleFeedback
    const message = messages.find(m => m.id === messageId);
    if (message) {
      await handleFeedback(message, reaction);
    }
  };

  const toggleMessageExpansion = (messageId) => {
    // Future enhancement: handle long message expansion
    console.log('Toggle expansion for message:', messageId);
  };

  // ========================
  // Keyboard Handlers
  // ========================
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

// Reusable action bar component (appears below message)
const MessageActionBar = React.memo(function MessageActionBar({
  visible,
  isStreaming,
  message,
  onCopy,
  onEdit,
  onFeedback,
  onSpeak,
  onDelete
}) {
  return (
    <div
      className={`message-action-bar${visible ? ' visible' : ''}`}
      role="toolbar"
      aria-hidden={!visible}
      aria-label="Message actions"
    >
      <button
        className="action-icon"
        onClick={() => onCopy(message)}
        aria-label="Copy message"
        title="Copy"
        tabIndex={visible ? 0 : -1}
      >
        <Copy size={16} />
      </button>

      {message.role === 'assistant' && (
        <>
          <button
            className={`action-icon ${message.feedback === 'up' ? 'reaction-active' : ''}`}
            onClick={() => onFeedback(message, 'up')}
            aria-label="Mark as helpful"
            title="Good response"
            tabIndex={visible ? 0 : -1}
          >
            <ThumbsUp size={16} />
          </button>

          <button
            className={`action-icon ${message.feedback === 'down' ? 'reaction-active' : ''}`}
            onClick={() => onFeedback(message, 'down')}
            aria-label="Mark as not helpful"
            title="Poor response"
            tabIndex={visible ? 0 : -1}
          >
            <ThumbsDown size={16} />
          </button>

          <button
            className="action-icon"
            onClick={() => onSpeak(message)}
            aria-label="Read message aloud"
            title="Speak"
            tabIndex={visible ? 0 : -1}
          >
            <Volume2 size={16} />
          </button>
        </>
      )}

      {message.role === 'user' && (
        <button
          className="action-icon"
          onClick={() => onEdit(message)}
          aria-label="Edit and resend message"
          title="Edit & Resend"
          tabIndex={visible ? 0 : -1}
        >
          <Edit3 size={16} />
        </button>
      )}

      {!isStreaming && (
        <button
          className="action-icon danger"
          onClick={() => onDelete(message)}
          aria-label="Delete message"
          title="Delete"
          tabIndex={visible ? 0 : -1}
        >
          <Trash2 size={16} />
        </button>
      )}

      {isStreaming && (
        <div className="streaming-mini" aria-label="Message is being generated">
          <Loader2 size={14} className="spin" />
        </div>
      )}
    </div>
  );
});

// Individual message row component
const MessageRow = React.memo(function MessageRow({
  message,
  isStreaming,
  user,
  onCopy,
  onEdit,
  onFeedback,
  onSpeak,
  onDelete,
  onPreviewAttachment
}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const isUser = message.role === 'user';
  
  const timestamp = useMemo(() => {
    try {
      const date = message.timestamp instanceof Date 
        ? message.timestamp 
        : new Date(message.timestamp);
      return isNaN(date.getTime()) ? new Date() : date;
    } catch {
      return new Date();
    }
  }, [message.timestamp]);

  const messageContent = message.content || message.text || '';
  // Action bar revealed via hover/focus (CSS handles opacity/transform)

  const handleFocus = useCallback(() => setFocused(true), []);
  const handleBlur = useCallback((e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setFocused(false);
    }
  }, []);

  // Select the appropriate animation variant based on message role
  const messageVariant = isUser ? userMessageVariants : assistantMessageVariants;

  return (
    <motion.div
      className={`message-wrapper ${isUser ? 'user' : 'assistant'}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={handleFocus}
      onBlur={handleBlur}
      tabIndex={0}
      role="article"
      aria-label={`${isUser ? 'User' : 'Assistant'} message at ${timestamp.toLocaleTimeString()}`}
      variants={messageVariant}
      initial="initial"
      animate="animate"
      exit="exit"
    >
      <div className="message-container-static">
        <div className="message-avatar">
          {isUser ? <User size={20} /> : <Bot size={20} />}
        </div>
        <div className="message-content">
          <div className="message-header">
            <span className="message-sender">
              {isUser ? (user?.name || 'You') : 'Aurion AI'}
            </span>
            <span className="message-timestamp">
              {timestamp.toLocaleTimeString([], { 
                hour: '2-digit', 
                minute: '2-digit' 
              })}
            </span>
            {message.edited && (
              <span className="message-edited" aria-label="This message was edited">
                (Edited)
              </span>
            )}
          </div>
          <div className="message-body">
            {/* Display attachments */}
            {message.attachments && message.attachments.length > 0 && (
              <div className="message-attachments">
                {message.attachments.map(attachment => (
                  <div key={attachment.id} className="message-attachment">
                    {attachment.type.startsWith('image/') ? (
                      <img 
                        src={attachment.url} 
                        alt={attachment.name}
                        className="attachment-image"
                        onClick={() => onPreviewAttachment && onPreviewAttachment(attachment)}
                      />
                    ) : (
                      <div className="attachment-file">
                        <Paperclip size={16} />
                        <span className="attachment-name">{attachment.name}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div 
              className="message-text"
              dangerouslySetInnerHTML={{ 
                __html: messageContent
                  .replace(/\n/g, '<br>')
                  .replace(/`([^`]+)`/g, '<code>$1</code>')
              }}
            />
            
            {/* Streaming indicator */}
            {isStreaming && message.role === 'assistant' && (
              <div className="streaming-indicator" aria-live="polite">
                <div className="typing-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            )}

            {/* Mark incomplete if stopped */}
            {message.incomplete && (
              <div className="message-incomplete" aria-label="Message was stopped">
                <span>Message incomplete</span>
              </div>
            )}
          </div>
        </div>
      </div>
      
      <MessageActionBar
        message={message}
        isStreaming={isStreaming}
        onCopy={onCopy}
        onEdit={onEdit}
        onFeedback={onFeedback}
        onSpeak={onSpeak}
        onDelete={onDelete}
      />
    </motion.div>
  );
});

  // ========================
  // Main Render
  // ========================
  return (
    <div className="chat-interface">{/* Header removed for full-screen experience */}

      {/* Messages Container */}
      <div 
        className="messages-container" 
        ref={messagesContainerRef}
        onScroll={handleScroll}
      >
        {/* Top sentinel for infinite scroll */}
        <div 
          ref={topSentinelRef} 
          className="history-observer"
          aria-hidden="true"
        />

        {/* History Loading Indicator */}
        {isLoadingHistory && (
          <div className="history-loader">
            <div className="loader-spinner" />
            <span>Loading older messages...</span>
          </div>
        )}

        {/* Messages */}
        <AnimatePresence initial={false}>
          {(loading || isLoadingHistory) && messages.length === 0 ? (
            <motion.div
              className="loading-skeleton-group"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className={`message-skeleton ${i % 2 ? 'right' : 'left'}`}>
                  <div className="avatar-skeleton" />
                  <div className="lines">
                    <div className="line w1" />
                    <div className="line w2" />
                    {i % 2 === 0 && <div className="line w3" />}
                  </div>
                </div>
              ))}
            </motion.div>
          ) : messages.length === 0 ? (
            <motion.div 
              className="empty-state"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              <div className="empty-state-content">
                <Bot size={48} className="empty-state-icon" />
                <h3>
                  {activeSessionId ? 'Continue Your Session' : 'Start a Conversation'}
                </h3>
                <p>
                  {activeSessionId 
                    ? "This session is ready for you to continue the conversation."
                    : "Hi there! I'm Aurion, your AI assistant. Ask me anything and I'll do my best to help you."
                  }
                </p>
                <div className="empty-state-suggestions">
                  <button onClick={() => setInput("How can you help me today?")}>
                    How can you help me?
                  </button>
                  <button onClick={() => setInput("Tell me about this project")}>
                    About this project
                  </button>
                  <button onClick={() => setInput("Help me with coding")}>
                    Help with coding
                  </button>
                </div>
              </div>
            </motion.div>
          ) : (
            <motion.div variants={listStagger} initial={false} animate="animate">
              <AnimatePresence mode="sync">
                {messages.map((message) => (
                  message && message.id ? (
                    message.type === 'youtube' && message.youtube?.videoId ? (
                      <motion.div key={message.id} className="message-wrapper assistant" variants={assistantMessageVariants} initial="initial" animate="animate" exit="exit">
                        <div className="message-container-static">
                          <div className="message-avatar">
                            <Bot size={20} />
                          </div>
                          <div className="message-content">
                            <div className="message-header">
                              <span className="message-sender">Aurion AI</span>
                              <span className="message-timestamp">{new Date(message.timestamp).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</span>
                            </div>
                            <div className="message-body">
                              <div className="message-text">{message.content}</div>
                              <div style={{ marginTop: 8 }}>
                                <VideoEmbed videoId={message.youtube.videoId} title={message.youtube.title} autoplay={true} />
                              </div>
                            </div>
                          </div>
                        </div>
                        <MessageActionBar
                          message={message}
                          isStreaming={false}
                          onCopy={handleCopyMessage}
                          onEdit={handleEditResend}
                          onFeedback={handleFeedback}
                          onSpeak={handleSpeak}
                          onDelete={handleDeleteMessage}
                        />
                      </motion.div>
                    ) : (
                      <MessageRow
                        key={message.id}
                        message={message}
                        isStreaming={streamingMessageId === message.id}
                        user={user}
                        onCopy={handleCopyMessage}
                        onEdit={handleEditResend}
                        onFeedback={handleFeedback}
                        onSpeak={handleSpeak}
                        onDelete={handleDeleteMessage}
                        onPreviewAttachment={handleImagePreview}
                      />
                    )
                  ) : null
                ))}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>

        {/* AI Thinking Indicator */}
        {/* Use a more modern typing indicator for regular thinking */}
        <TypingIndicator isVisible={showThinking} />
        
        {/* Keep this for detailed processing steps when needed */}
        <AIThinkingIndicator
          isActive={showThinking && showDetailedThinking}
          fastMode={true}
          showDetails={true}
          enableSounds={true}
        />

        {/* Jump to bottom button */}
        <AnimatePresence>
          {showJumpToBottom && (
            <motion.button
              className="jump-to-bottom"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              onClick={jumpToBottom}
              aria-label="Jump to latest message"
            >
              <ArrowDown size={16} />
              <span>New messages</span>
            </motion.button>
          )}
        </AnimatePresence>

        {/* Scroll anchor */}
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>

      {/* Enhanced Input Area */}
      <div className="chat-input-container">
        {/* File Attachments Preview */}
        {attachedFiles.length > 0 && (
          <div className="attached-files">
            {attachedFiles.map(file => (
              <div key={file.id} className="attached-file">
                {file.type.startsWith('image/') ? (
                  <div 
                    className="file-preview image-preview"
                    onClick={() => handleImagePreview(file)}
                  >
                    <img src={file.url} alt={file.name} />
                    <div className="file-overlay">
                      <ImageIcon size={16} />
                    </div>
                  </div>
                ) : (
                  <div className="file-preview file-icon">
                    <Paperclip size={16} />
                    <span className="file-name">{file.name}</span>
                  </div>
                )}
                <button
                  className="remove-file"
                  onClick={() => handleFileRemove(file.id)}
                  title="Remove file"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="input-wrapper">
          {/* File Input (Hidden) */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,audio/*,video/*,.pdf,.doc,.docx,.txt"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />

          {/* Left side buttons */}
          <div className="input-buttons-left">
            <button 
              className="input-button" 
              onClick={handleAttachClick}
              title="Attach files"
            >
              <Paperclip size={20} />
            </button>

            <button className="input-button" title="Add emoji">
              <Smile size={20} />
            </button>
          </div>

          {/* Text Input */}
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder="Type your message... (Shift+Enter for new line)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isStreaming}
            rows={1}
            style={{
              height: 'auto',
              minHeight: '48px',
              maxHeight: '120px'
            }}
            onInput={(e) => {
              e.target.style.height = 'auto';
              e.target.style.height = e.target.scrollHeight + 'px';
            }}
          />

          {/* Right side buttons */}
          <div className="input-buttons-right">
            <motion.button
              className={`input-button mic-button ${isRecording ? 'recording' : ''}`}
              onClick={handleMicClick}
              title={isRecording ? 'Stop recording' : 'Record voice note'}
              whileHover={{ scale: reducedMotion ? 1 : 1.05 }}
              whileTap={{ scale: reducedMotion ? 1 : 0.95 }}
            >
              <Mic size={20} />
              {isRecording && <div className="recording-pulse" />}
            </motion.button>

            <motion.button
              className={`send-button ${(input.trim() || attachedFiles.length > 0 || isStreaming) ? 'active' : ''}`}
              onClick={isStreaming ? stopStreaming : handleSendMessage}
              disabled={!isStreaming && !(input.trim() || attachedFiles.length > 0)}
              whileHover={{ scale: reducedMotion ? 1 : 1.05 }}
              whileTap={{ scale: reducedMotion ? 1 : 0.95 }}
              title={isStreaming ? 'Stop generating' : 'Send message (Enter)'}
            >
              {isStreaming ? (
                <Square size={20} />
              ) : (
                <Send size={20} />
              )}
            </motion.button>
          </div>
        </div>

        {/* Input Footer */}
        <div className="input-footer">
          <span className="input-hint">
            Press Enter to send, Shift+Enter for new line
          </span>
        </div>
      </div>

      {/* Image Preview Modal */}
      <AnimatePresence>
        {showImagePreview && previewImage && (
          <motion.div
            className="image-preview-modal"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={handleCloseImagePreview}
          >
            <motion.div
              className="image-preview-content"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                className="close-preview"
                onClick={handleCloseImagePreview}
              >
                <X size={24} />
              </button>
              <img 
                src={previewImage.url} 
                alt={previewImage.name}
                className="preview-image"
              />
              <div className="preview-info">
                <span className="preview-name">{previewImage.name}</span>
                <span className="preview-size">
                  {(previewImage.size / 1024 / 1024).toFixed(2)} MB
                </span>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ChatInterface;