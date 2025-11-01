// Modern ChatWindow Component

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence, useInView } from 'framer-motion';
import {
  Copy,
  ThumbsUp,
  ThumbsDown,
  Volume2,
  VolumeX,
  Edit3,
  Bot,
  User,
  CheckCircle,
  XCircle,
  MoreVertical,
  Heart,
  Share,
  Bookmark,
  MessageSquare,
  Sparkles,
  Clock,
  Check
} from 'lucide-react';
import '../styles/ChatWindowNew.css';
import VideoEmbed from './VideoEmbed';
import videoControls from '../services/videoControlsService';
import { VideoPiPProvider, useVideoPiP } from '../context/VideoPiPContext';
import VideoMiniPlayer from './VideoMiniPlayer';
import apiClient from '../services/api';

// Animation Variants
const messageVariants = {
  hidden: {
    opacity: 0,
    y: 30,
    scale: 0.95
  },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      duration: 0.4,
      ease: "easeOut"
    }
  },
  exit: {
    opacity: 0,
    y: -20,
    scale: 0.9,
    transition: {
      duration: 0.3,
      ease: "easeIn"
    }
  }
};

const avatarVariants = {
  hidden: {
    scale: 0,
    rotate: -180
  },
  visible: {
    scale: 1,
    rotate: 0,
    transition: {
      duration: 0.5,
      ease: "backOut",
      delay: 0.1
    }
  }
};

const actionButtonVariants = {
  hidden: {
    opacity: 0,
    scale: 0.8,
    x: -10
  },
  visible: {
    opacity: 1,
    scale: 1,
    x: 0,
    transition: {
      duration: 0.3,
      ease: "easeOut"
    }
  },
  hover: {
    scale: 1.1,
    y: -2,
    transition: {
      duration: 0.2,
      ease: "easeOut"
    }
  },
  tap: {
    scale: 0.95
  }
};

const typingVariants = {
  hidden: {
    opacity: 0,
    y: 20
  },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.3,
      ease: "easeOut"
    }
  }
};

// Message Component
const ChatMessage = ({ message, index, onCopy, onLike, onFeedback, onSpeak, onEdit, feedbackState, copiedIndex, likedMessages, speakingIndex, onSystemAppend, activeSessionId }) => {
  const [showActions, setShowActions] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const messageRef = useRef(null);
  const dropdownRef = useRef(null);
  const isInView = useInView(messageRef, { once: true, margin: "-50px" });
  const videoRef = useRef(null);
  const videoInViewport = useInView(videoRef, { margin: "-30% 0px -30% 0px" });
  const { activate, deactivate, pipActive, video: pipVideo } = useVideoPiP();

  // Auto PiP activation/deactivation for this message's video
  useEffect(() => {
    const vid = (message.youtube && message.youtube.videoId) || (message.video && message.video.videoId);
    const title = (message.youtube && message.youtube.title) || (message.video && message.video.title);
    if (!vid) return;
    // If video scrolled out of viewport and not already active with same video, activate PiP
    if (videoRef.current && videoInViewport === false) {
      if (!pipActive || (pipVideo && pipVideo.videoId !== vid)) {
        const restoreFn = () => {
          try { videoRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch {}
        };
        activate({ videoId: vid, title, sessionId: activeSessionId }, restoreFn);
      }
    }
    // If video is visible again and PiP is active for this video, deactivate
    if (videoRef.current && videoInViewport === true) {
      if (pipActive && pipVideo && pipVideo.videoId === vid) {
        deactivate();
      }
    }
  }, [videoInViewport, message, activate, deactivate, pipActive, pipVideo, activeSessionId]);

  const isUser = message.sender === 'user';
  const isAssistant = message.sender === 'assistant';

  // Close dropdown when clicking outside
  React.useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    };
    
    if (showDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showDropdown]);
  
  return (
    <motion.div
      ref={messageRef}
      className={`message-wrapper ${message.sender}`}
      variants={messageVariants}
      initial="hidden"
      animate={isInView ? "visible" : "hidden"}
      exit="exit"
      layout
      onMouseEnter={() => {
        setShowActions(true);
        setIsHovered(true);
      }}
      onMouseLeave={() => {
        setShowActions(false);
        setIsHovered(false);
      }}
    >
      {/* Avatar */}
      <motion.div 
        className="avatar-container"
        variants={avatarVariants}
        initial="hidden"
        animate={isInView ? "visible" : "hidden"}
      >
        <div className={`avatar ${message.sender}`}>
          <motion.div
            animate={{
              rotate: isHovered ? [0, 5, -5, 0] : 0,
              scale: isHovered ? 1.05 : 1
            }}
            transition={{
              duration: 0.6,
              ease: "easeInOut"
            }}
          >
            {isUser ? (
              <User size={18} />
            ) : (
              <>
                <Bot size={18} />
                <motion.div
                  className="avatar-glow"
                  animate={{
                    opacity: [0.5, 1, 0.5],
                    scale: [1, 1.1, 1]
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                    ease: "easeInOut"
                  }}
                />
              </>
            )}
          </motion.div>
          
          {/* Status indicator */}
          <motion.div
            className={`status-dot ${message.sender}`}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.5, type: "spring", bounce: 0.6 }}
          />
        </div>
        
        {/* Sender label */}
        <motion.div
          className="sender-label"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          {isUser ? 'You' : 'Aurion AI'}
        </motion.div>
      </motion.div>

      {/* Message Content */}
      <div className="message-content">
        <motion.div 
          className={`chat-message ${message.sender}`}
          whileHover={{ scale: 1.01 }}
          transition={{ duration: 0.2 }}
        >
          <motion.div
            className="message-text"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2, duration: 0.5 }}
          >
            {message.text}
            {/* Inline server-provided video embedding parity (after text) */}
            {(
              // Prefer explicit youtube payload
              (message.youtube && message.youtube.videoId) ||
              // Or a generic `video` payload from backend
              (message.video && message.video.videoId)
            ) && (
              <div className="video-embed-container" style={{ marginTop: 12 }} ref={videoRef}>
                <VideoEmbed
                  videoId={(message.youtube && message.youtube.videoId) || (message.video && message.video.videoId)}
                  title={(message.youtube && message.youtube.title) || (message.video && message.video.title)}
                  autoplay={Boolean((message.youtube && message.youtube.autoplay) || (message.video && message.video.autoplay))}
                />
                {/* Interactive controls */}
                <div className="video-controls" style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                  {[
                    { key: 'play', label: '⏯️ Play / Pause' },
                    { key: 'replay', label: '🔁 Replay' },
                    { key: 'next', label: '⏭️ Next' },
                    { key: 'lyrics', label: '🗒️ Show Lyrics' },
                  ].map(btn => (
                    <button
                      key={btn.key}
                      className="video-ctrl-btn"
                      style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #e5e7eb', background: 'white', cursor: 'pointer' }}
                      onClick={async () => {
                        const vid = (message.youtube && message.youtube.videoId) || (message.video && message.video.videoId);
                        const title = (message.youtube && message.youtube.title) || (message.video && message.video.title);
                        const ctx = { videoId: vid, title, sessionId: activeSessionId };
                        if (btn.key === 'play') {
                          // Toggle purely on UI: decide resume/pause by simple heuristic (no state tracked here)
                          const res = await videoControls.sendControl('play', ctx);
                          onSystemAppend?.(res, index);
                          return;
                        }
                        const res = await videoControls.sendControl(btn.key, ctx);
                        onSystemAppend?.(res, index);
                      }}
                    >
                      {btn.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </motion.div>

          {/* Message decorations */}
          <div className="message-decorations">
            {isAssistant && (
              <motion.div
                className="ai-indicator"
                initial={{ opacity: 0, scale: 0 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.4, type: "spring" }}
              >
                <Sparkles size={12} />
              </motion.div>
            )}
            
            <motion.div
              className="timestamp"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.6 }}
            >
              <Clock size={10} />
              <span>now</span>
            </motion.div>
          </div>
        </motion.div>

        {/* Action Buttons */}
        <AnimatePresence>
          {showActions && (
            <motion.div 
              className="message-actions"
              initial={{ opacity: 0, y: 10, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.9 }}
              transition={{ duration: 0.3, staggerChildren: 0.05 }}
            >
              {/* Copy Button */}
              <motion.button
                className={`action-btn copy-btn ${copiedIndex === index ? 'active' : ''}`}
                onClick={() => onCopy(message.text, index)}
                variants={actionButtonVariants}
                whileHover="hover"
                whileTap="tap"
                title="Copy message"
              >
                {copiedIndex === index ? <Check size={14} /> : <Copy size={14} />}
              </motion.button>

              {/* Assistant-specific actions */}
              {isAssistant && (
                <>
                  {/* Like Button */}
                  <motion.button
                    className={`action-btn like-btn ${likedMessages.has(index) ? 'active' : ''}`}
                    onClick={() => onLike(index)}
                    variants={actionButtonVariants}
                    whileHover="hover"
                    whileTap="tap"
                    title="Like message"
                  >
                    <Heart size={14} />
                  </motion.button>

                  {/* Feedback Buttons */}
                  <motion.button
                    className={`action-btn feedback-btn good-btn ${feedbackState[index] === 'good' ? 'active' : ''}`}
                    onClick={() => onFeedback(index, 'good')}
                    disabled={feedbackState[index]}
                    variants={actionButtonVariants}
                    whileHover="hover"
                    whileTap="tap"
                    title="Good response"
                  >
                    <ThumbsUp size={14} />
                  </motion.button>

                  <motion.button
                    className={`action-btn feedback-btn bad-btn ${feedbackState[index] === 'bad' ? 'active' : ''}`}
                    onClick={() => onFeedback(index, 'bad')}
                    disabled={feedbackState[index]}
                    variants={actionButtonVariants}
                    whileHover="hover"
                    whileTap="tap"
                    title="Bad response"
                  >
                    <ThumbsDown size={14} />
                  </motion.button>

                  {/* Bookmark Button */}
                  <motion.button
                    className="action-btn bookmark-btn"
                    variants={actionButtonVariants}
                    whileHover="hover"
                    whileTap="tap"
                    title="Bookmark message"
                  >
                    <Bookmark size={14} />
                  </motion.button>
                </>
              )}

              {/* Speak Button */}
              <motion.button
                className={`action-btn speak-btn ${speakingIndex === index ? 'active speaking' : ''}`}
                onClick={() => onSpeak(message.text, index)}
                variants={actionButtonVariants}
                whileHover="hover"
                whileTap="tap"
                title={speakingIndex === index ? 'Stop speaking' : 'Read aloud'}
              >
                <motion.div
                  animate={speakingIndex === index ? {
                    scale: [1, 1.2, 1],
                    rotate: [0, 10, -10, 0]
                  } : {}}
                  transition={{
                    duration: 0.8,
                    repeat: speakingIndex === index ? Infinity : 0
                  }}
                >
                  {speakingIndex === index ? <VolumeX size={14} /> : <Volume2 size={14} />}
                </motion.div>
              </motion.button>

              {/* User-specific actions */}
              {isUser && (
                <motion.button
                  className="action-btn edit-btn"
                  onClick={() => onEdit(index)}
                  variants={actionButtonVariants}
                  whileHover="hover"
                  whileTap="tap"
                  title="Edit message"
                >
                  <Edit3 size={14} />
                </motion.button>
              )}

              {/* More Options */}
              <div className="more-options-container" ref={dropdownRef}>
                <motion.button
                  className="action-btn more-btn"
                  onClick={() => setShowDropdown(!showDropdown)}
                  variants={actionButtonVariants}
                  whileHover="hover"
                  whileTap="tap"
                  title="More options"
                >
                  <MoreVertical size={14} />
                </motion.button>
                
                {/* Dropdown Menu */}
                <AnimatePresence>
                  {showDropdown && (
                    <motion.div
                      className="more-options-dropdown"
                      initial={{ opacity: 0, scale: 0.9, y: -10 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.9, y: -10 }}
                      transition={{ duration: 0.2 }}
                    >
                      <div className="dropdown-item" onClick={() => navigator.share && navigator.share({title: 'Aurion AI Message', text: message.text})}>
                        <Share size={14} />
                        Share
                      </div>
                      <div className="dropdown-item">
                        <MessageSquare size={14} />
                        Quote Reply
                      </div>
                      <div className="dropdown-item">
                        <Bookmark size={14} />
                        Save Message
                      </div>
                      <div className="dropdown-item" style={{color: '#ff6b6b'}}>
                        <XCircle size={14} />
                        Report
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};

// Typing Indicator Component
const TypingIndicator = () => (
  <motion.div
    className="message-wrapper assistant typing-wrapper"
    variants={typingVariants}
    initial="hidden"
    animate="visible"
    exit="hidden"
  >
    <motion.div 
      className="avatar-container"
      variants={avatarVariants}
      initial="hidden"
      animate="visible"
    >
      <div className="avatar assistant">
        <motion.div
          animate={{
            rotate: [0, 360],
            scale: [1, 1.1, 1]
          }}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        >
          <Bot size={18} />
        </motion.div>
        <motion.div
          className="avatar-glow typing"
          animate={{
            opacity: [0.3, 1, 0.3],
            scale: [1, 1.2, 1]
          }}
          transition={{
            duration: 1.5,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
      </div>
  <div className="sender-label">Aurion AI</div>
    </motion.div>

    <div className="message-content">
      <motion.div 
        className="chat-message assistant typing"
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.3 }}
      >
        <div className="typing-content">
          <div className="typing-indicator">
            <motion.span
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 0.6, repeat: Infinity, delay: 0 }}
            />
            <motion.span
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 0.6, repeat: Infinity, delay: 0.2 }}
            />
            <motion.span
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 0.6, repeat: Infinity, delay: 0.4 }}
            />
          </div>
          <motion.p
            className="typing-text"
            animate={{ opacity: [0.7, 1, 0.7] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          >
            Aurion is thinking...
          </motion.p>
        </div>
      </motion.div>
    </div>
  </motion.div>
);

// Notification Component
const FeedbackNotification = ({ notification, onClose }) => (
  <motion.div
    className={`feedback-notification ${notification.type}`}
    initial={{ opacity: 0, x: 50, scale: 0.9 }}
    animate={{ opacity: 1, x: 0, scale: 1 }}
    exit={{ opacity: 0, x: 50, scale: 0.9 }}
    transition={{ duration: 0.3, ease: "easeOut" }}
    layout
  >
    <motion.div 
      className="notification-icon"
      initial={{ rotate: -180, scale: 0 }}
      animate={{ rotate: 0, scale: 1 }}
      transition={{ delay: 0.1, type: "spring", bounce: 0.6 }}
    >
      {notification.type === 'good' ? <CheckCircle size={20} /> : <XCircle size={20} />}
    </motion.div>
    <motion.span 
      className="notification-text"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.2 }}
    >
      {notification.message}
    </motion.span>
    <motion.div
      className="notification-progress"
      initial={{ width: "100%" }}
      animate={{ width: "0%" }}
      transition={{ duration: 3, ease: "linear" }}
    />
  </motion.div>
);

// Empty State Component
const EmptyState = () => (
  <motion.div
    className="empty-state"
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.6, ease: "easeOut" }}
  >
    <motion.div
      className="empty-icon"
      animate={{
        y: [0, -10, 0],
        rotate: [0, 5, -5, 0]
      }}
      transition={{
        duration: 4,
        repeat: Infinity,
        ease: "easeInOut"
      }}
    >
      <MessageSquare size={48} />
      <motion.div
        className="sparkle-1"
        animate={{
          opacity: [0, 1, 0],
          scale: [0.8, 1.2, 0.8],
          rotate: [0, 180, 360]
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: "easeInOut"
        }}
      >
        <Sparkles size={16} />
      </motion.div>
      <motion.div
        className="sparkle-2"
        animate={{
          opacity: [0, 1, 0],
          scale: [1, 0.8, 1],
          rotate: [360, 180, 0]
        }}
        transition={{
          duration: 3,
          repeat: Infinity,
          ease: "easeInOut",
          delay: 1
        }}
      >
        <Sparkles size={12} />
      </motion.div>
    </motion.div>
    <motion.div
      className="empty-content"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
    >
  <h3>Welcome to Aurion AI</h3>
      <p>Start a conversation to unlock the power of AI assistance</p>
    </motion.div>
  </motion.div>
);

// Main ChatWindow Component
const ChatWindow = ({
  messages = [],
  isLoading = false,
  onFetchMore,
  hasMoreMessages = false,
  activeSessionId,
}) => {
  const chatWindowRef = useRef(null);
  const topObserver = useRef(null);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [likedMessages, setLikedMessages] = useState(new Set());
  const [speakingIndex, setSpeakingIndex] = useState(null);
  const [feedbackState, setFeedbackState] = useState({});
  const [feedbackNotifications, setFeedbackNotifications] = useState([]);
  const [localMessages, setLocalMessages] = useState(messages);
  // Local assistant augmentations (e.g., picked video cards)
  const [augmented, setAugmented] = useState([]);
  // Remember last media context to support follow-ups like "next song" or language changes
  const [mediaContext, setMediaContext] = useState({ lastMovie: null, lastTitle: null, lastVideoId: null, lastLanguage: null });

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (chatWindowRef.current && messages.length > 0) {
      const scrollElement = chatWindowRef.current;
      const isNearBottom = scrollElement.scrollTop + scrollElement.clientHeight >= scrollElement.scrollHeight - 100;
      
      if (isNearBottom) {
        setTimeout(() => {
          scrollElement.scrollTo({
            top: scrollElement.scrollHeight,
            behavior: 'smooth'
          });
        }, 100);
      }
    }
  }, [messages]);

  // Compose upstream messages plus local augmentations for rendering
  const combinedMessages = React.useMemo(() => [...messages, ...augmented], [messages, augmented]);

  // append a system message and/or swap video based on control responses
  const handleSystemAppend = useCallback((res, idx) => {
    if (!res) return;
    const sysMsg = {
      sender: 'assistant',
      text: res.response_text || '',
    };
    if (res.video && res.video.videoId) {
      sysMsg.video = res.video;
    }
    if (res.lyrics) {
      sysMsg.text = `${sysMsg.text ? sysMsg.text + '\n\n' : ''}${res.lyrics}`;
    }
    // Append locally so UI reflects control responses immediately
    setAugmented(prev => {
      const arr = [...prev, sysMsg];
      if (res.video && res.video.videoId) {
        arr.push({ sender: 'assistant', video: { ...res.video, autoplay: true }, text: '' });
        setMediaContext(mc => ({ ...mc, lastVideoId: res.video.videoId, lastTitle: res.video.title || mc.lastTitle }));
      }
      return arr;
    });
    if (typeof window !== 'undefined') requestAnimationFrame(() => {
      try { chatWindowRef.current?.scrollTo?.({ top: chatWindowRef.current.scrollHeight, behavior: 'smooth' }); } catch {}
    });
  }, [messages]);

  // ----- Media intent parsing helpers -----
  const parsePlayIntent = useCallback((text) => {
    if (!text) return {};
    const t = text.toLowerCase();
    const intent = /(play|watch|open)\b/.test(t) ? 'PlayVideo' : null;
    if (!intent) return {};
    let language = null;
    if (/\btamil\b/.test(t) || /\bhayyoda\b/.test(t)) language = 'tamil';
    else if (/\bhindi\b/.test(t)) language = 'hindi';
    else if (/\btelugu\b/.test(t)) language = 'telugu';
    let movie = null;
    const mv = t.match(/from\s+([\w\s]+?)(?:\s+(?:movie|film)|$)/);
    if (mv && mv[1]) movie = mv[1].trim();
    let title = null;
    const afterPlay = t.split(/play\s+/)[1] || t;
    if (afterPlay) {
      const cut = afterPlay.split(/\s+from\s+/)[0];
      title = (cut || '').replace(/\b(song|video|the|please|official|video song|full)\b/g, '').trim();
      if (!title) title = null;
    }
    let version = null;
    if (/\btamil\b/.test(t)) version = 'tamil';
    if (/\bhindi\b/.test(t)) version = version || 'hindi';
    if (/\btrailer|teaser\b/.test(t)) version = 'trailer';
    return { intent, title, movie, language, version };
  }, []);

  const buildQuery = (title, movie, language, version) => {
    const parts = [];
    if (title) parts.push(title);
    if (movie) parts.push(movie);
    if (language) parts.push(language);
    parts.push('Official Video');
    parts.push('T-Series Sony Music India Saregama YRF Zee Music');
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  };

  const friendlyCardText = (info) => {
    const views = info?.statistics?.viewCount ? Intl.NumberFormat('en', { notation: 'compact' }).format(+info.statistics.viewCount) : undefined;
    const likes = info?.statistics?.likeCount ? Intl.NumberFormat('en', { notation: 'compact' }).format(+info.statistics.likeCount) : undefined;
    const lines = [];
    if (info?.title) lines.push(`🎶 Playing: ${info.title}`);
    if (info?.channelTitle) lines.push(`🎧 Channel: ${info.channelTitle}`);
    if (views || likes) lines.push(`❤️ ${views ? views + ' views' : ''}${views && likes ? ' | ' : ''}${likes ? likes + ' likes' : ''}`);
    lines.push('▶️ Watch Now on YouTube');
    lines.push('(Auto-playing below...)');
    return lines.join('\n');
  };

  const appendVideoSelection = useCallback((top) => {
    if (!top?.videoId) return;
    setAugmented(prev => ([
      ...prev,
      { sender: 'assistant', text: friendlyCardText(top) },
      { sender: 'assistant', youtube: { videoId: top.videoId, title: top.title, autoplay: true }, text: '' },
    ]));
    setMediaContext(mc => ({ ...mc, lastTitle: top.title || mc.lastTitle, lastVideoId: top.videoId }));
    if (typeof window !== 'undefined') requestAnimationFrame(() => {
      try { chatWindowRef.current?.scrollTo?.({ top: chatWindowRef.current.scrollHeight, behavior: 'smooth' }); } catch {}
    });
  }, []);

  // Show and clear a quick local "searching" indicator message
  const showSearching = useCallback((text) => {
    const id = Date.now() + Math.random();
    setAugmented(prev => ([...prev, { sender: 'assistant', text, ephemeral: true, _id: id }]));
    return id;
  }, []);
  const clearSearching = useCallback((id) => {
    setAugmented(prev => prev.filter(m => m._id !== id));
  }, []);

  // Watch incoming messages for media intents
  useEffect(() => {
    if (!messages?.length) return;
    const last = messages[messages.length - 1];
    if (last?.sender !== 'user' || !last?.text) return;
    // Avoid double-search if backend already supplied a video for this request
    if (typeof window !== 'undefined' && window.__maya_last_play_had_server_video__) {
      try { delete window.__maya_last_play_had_server_video__; } catch {}
      return;
    }
    const { intent, title, movie, language, version } = parsePlayIntent(last.text);
    if (intent !== 'PlayVideo') return;
    const effectiveMovie = movie || mediaContext.lastMovie || undefined;
    const q = buildQuery(title || mediaContext.lastTitle, effectiveMovie, language || mediaContext.lastLanguage, version);
    setMediaContext(mc => ({ ...mc, lastMovie: movie || mc.lastMovie, lastLanguage: language || mc.lastLanguage, lastTitle: title || mc.lastTitle }));
    const searchId = showSearching('🔎 Searching the official video…');
    (async () => {
      try {
        const res = await apiClient.get('/youtube/search', { params: { q, max_results: 5 } });
        const top = res?.data?.top;
        if (language === 'tamil' && top && /chaleya/i.test(title || '') && !/hayyoda/i.test(top.title || '')) {
          const res2 = await apiClient.get('/youtube/search', { params: { q: buildQuery('Hayyoda', effectiveMovie, 'tamil', version), max_results: 5 } });
          appendVideoSelection(res2?.data?.top || top);
        } else {
          appendVideoSelection(top);
        }
      } catch (e) {
        clearSearching(searchId);
        setAugmented(prev => ([...prev, { sender: 'assistant', text: 'I tried to find the official video, but hit a snag. Want me to try again?' }]));
        return;
      } finally {
        clearSearching(searchId);
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // Handle "next" follow-up
  useEffect(() => {
    if (!messages?.length) return;
    const last = messages[messages.length - 1];
    if (last?.sender !== 'user' || !last?.text) return;
    const t = last.text.toLowerCase();
    if (!/(play\s+next|next\s+one|next\s+song|play\s+another)/.test(t)) return;
    const current = mediaContext.lastVideoId;
    if (!current) return;
    const nextId = showSearching('⏭️ Finding the next official track…');
    (async () => {
      try {
        const r = await apiClient.get('/youtube/related', { params: { video_id: current, max_results: 5 } });
        appendVideoSelection(r?.data?.top);
      } catch {
        // swallow error; indicator will be cleared below
      } finally {
        clearSearching(nextId);
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, mediaContext.lastVideoId]);

  // Intersection Observer for infinite scroll
  const topElementRef = useCallback(
    (node) => {
      if (!hasMoreMessages || isLoading) return;
      if (topObserver.current) topObserver.current.disconnect();

      topObserver.current = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
          onFetchMore?.();
        }
      });

      if (node) topObserver.current.observe(node);
    },
    [hasMoreMessages, isLoading, onFetchMore]
  );

  // Actions
  const copyToClipboard = async (text, index) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const toggleLike = (index) => {
    const newLiked = new Set(likedMessages);
    likedMessages.has(index) ? newLiked.delete(index) : newLiked.add(index);
    setLikedMessages(newLiked);
  };

  const toggleSpeak = (text, index) => {
    if (speakingIndex === index) {
      window.speechSynthesis.cancel();
      setSpeakingIndex(null);
    } else {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.onend = () => setSpeakingIndex(null);
      window.speechSynthesis.speak(utterance);
      setSpeakingIndex(index);
    }
  };

  const editMessage = (index) => {
    console.log('Edit message:', index);
  };

  const addFeedbackNotification = (type, index) => {
    const notification = {
      id: Date.now(),
      type,
      index,
      message: type === 'good' ? 'Thanks for your positive feedback!' : 'Thanks for your feedback, we\'ll improve!',
    };

    setFeedbackNotifications((prev) => [...prev, notification]);
    setTimeout(() => {
      setFeedbackNotifications((prev) =>
        prev.filter((notif) => notif.id !== notification.id)
      );
    }, 3000);
  };

  const handleFeedback = async (index, rating) => {
    if (feedbackState[index]) return;

    try {
      await new Promise((resolve) => setTimeout(resolve, 500));
      setFeedbackState((prev) => ({ ...prev, [index]: rating }));
      addFeedbackNotification(rating, index);
      console.log(`Feedback submitted for message ${index}: ${rating}`);
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    }
  };

  return (
    <div className="chat-container">
      {/* Background Effects */}
      <div className="chat-background">
        <motion.div 
          className="bg-gradient bg-gradient-1"
          animate={{
            x: [0, 100, 0],
            y: [0, -50, 0],
            scale: [1, 1.1, 1]
          }}
          transition={{
            duration: 20,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
        <motion.div 
          className="bg-gradient bg-gradient-2"
          animate={{
            x: [0, -80, 0],
            y: [0, 60, 0],
            scale: [1, 0.9, 1]
          }}
          transition={{
            duration: 15,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
      </div>

      {/* Chat Window */}
      <div className="chat-window" ref={chatWindowRef}>
        {hasMoreMessages && (
          <div ref={topElementRef} style={{ height: '1px' }} />
        )}

        <AnimatePresence mode="popLayout">
          {combinedMessages.length === 0 ? (
            <EmptyState key="empty" />
          ) : (
            combinedMessages.map((msg, index) => (
              <ChatMessage
                key={`${activeSessionId}-${index}`}
                message={msg}
                index={index}
                onCopy={copyToClipboard}
                onLike={toggleLike}
                onFeedback={handleFeedback}
                onSpeak={toggleSpeak}
                onEdit={editMessage}
                onSystemAppend={handleSystemAppend}
                activeSessionId={activeSessionId}
                feedbackState={feedbackState}
                copiedIndex={copiedIndex}
                likedMessages={likedMessages}
                speakingIndex={speakingIndex}
              />
            ))
          )}

          {/* Typing Indicator */}
          {isLoading && <TypingIndicator key="typing" />}
        </AnimatePresence>
      </div>

      {/* Feedback Notifications */}
      <div className="feedback-notifications">
        <AnimatePresence>
          {feedbackNotifications.map((notif) => (
            <FeedbackNotification
              key={notif.id}
              notification={notif}
              onClose={() => setFeedbackNotifications(prev =>
                prev.filter(n => n.id !== notif.id)
              )}
            />
          ))}
        </AnimatePresence>
      </div>
      {/* Global PiP overlay */}
      <VideoMiniPlayer />
    </div>
  );
};

// Wrap with PiP provider so mini player is globally available within chat
const ChatWindowWithProvider = (props) => (
  <VideoPiPProvider>
    <ChatWindow {...props} />
  </VideoPiPProvider>
);

export default ChatWindowWithProvider;