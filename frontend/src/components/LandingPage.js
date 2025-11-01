import React, { useState, useEffect, useRef } from 'react';
import { motion, useInView, useScroll, useTransform } from 'framer-motion';
import { 
    Send, 
    Star, 
    Menu, 
    X, 
    ArrowRight, 
    Bot,
    User,
    Zap,
    Brain,
    MessageCircle,
    Shield,
    Sparkles,
    Github,
    Twitter,
    Mail,
    Home,
    Info,
    MessageSquare,
    Phone
} from 'lucide-react';
import AuthModal from './AuthModal';
import MayaLogo from './MayaLogo';
import '../styles/LandingPage.css';

const LandingPage = () => {
    const [authModal, setAuthModal] = useState({ isOpen: false, mode: 'signin' });
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [email, setEmail] = useState('');
    const [isScrolled, setIsScrolled] = useState(false);
    const [chatMessages, setChatMessages] = useState([
        {
            id: 1,
            type: 'bot',
            message: "Hey! I'm Aurion, your personal AI assistant. I can help you with tasks, remember our conversations, and learn your preferences!",
            timestamp: "2:30 pm"
        },
        {
            id: 2,
            type: 'user', 
            message: "That sounds amazing! What makes you different from other AI assistants?",
            timestamp: "2:31 pm"
        },
        {
            id: 3,
            type: 'bot',
            message: "I have conversational memory and use advanced knowledge graphs to understand context deeply. I remember what we talked about yesterday and adapt to your unique style!",
            timestamp: "2:32 pm"
        }
    ]);
    const [newMessage, setNewMessage] = useState('');

    const heroRef = useRef(null);
    const featuresRef = useRef(null);
    const chatRef = useRef(null);
    const contactRef = useRef(null);

    const { scrollYProgress } = useScroll();
    const backgroundY = useTransform(scrollYProgress, [0, 1], ['0%', '50%']);
    const textY = useTransform(scrollYProgress, [0, 0.5], ['0%', '20%']);
    
    // Navbar scroll effects
    const navbarScale = useTransform(scrollYProgress, [0, 0.1], [1, 0.95]);
    const navbarY = useTransform(scrollYProgress, [0, 0.1], [20, 10]);
    
    useEffect(() => {
        const unsubscribe = scrollYProgress.onChange((latest) => {
            setIsScrolled(latest > 0.05);
        });
        return () => unsubscribe();
    }, [scrollYProgress]);

    // Floating stars animation data - optimized for performance
    const [floatingStars] = useState(
        Array.from({ length: 35 }, (_, i) => ({
            id: i,
            x: Math.random() * 100,
            y: Math.random() * 100,
            size: Math.random() * 4 + 2, // Consistent sizes for better performance
            duration: Math.random() * 12 + 10, // Longer, smoother animations
            delay: Math.random() * 6,
            opacity: Math.random() * 0.5 + 0.4 // More visible stars
        }))
    );

    const smoothScroll = (elementRef) => {
        elementRef.current?.scrollIntoView({ 
            behavior: 'smooth',
            block: 'start'
        });
    };

    const handleSendMessage = () => {
        if (!newMessage.trim()) return;
        
        const userMessage = {
            id: chatMessages.length + 1,
            type: 'user',
            message: newMessage,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        
        setChatMessages(prev => [...prev, userMessage]);
        setNewMessage('');
        
        // Simulate AI response
        setTimeout(() => {
            const botResponse = {
                id: chatMessages.length + 2,
                type: 'bot',
                message: "Great question! I'm constantly learning and evolving to provide you with the most personalized and helpful assistance possible.",
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            };
            setChatMessages(prev => [...prev, botResponse]);
        }, 1500);
    };

    const handleJoinBeta = () => {
        if (email) {
            // Handle email subscription logic here
            console.log('Email submitted:', email);
            setEmail('');
            // Show success message or open auth modal
            setAuthModal({ isOpen: true, mode: 'signup' });
        }
    };

    const closeAuthModal = () => {
        setAuthModal({ isOpen: false, mode: 'signin' });
    };

    const handleAuthSuccess = (user) => {
        console.log('Auth successful:', user);
        setAuthModal({ isOpen: false, mode: 'signin' });
    };

    // Side navigation sections
    const sideNavSections = [
        { id: 'hero', label: 'Home', icon: <Home size={20} />, ref: heroRef },
        { id: 'features', label: 'Features', icon: <Info size={20} />, ref: featuresRef },
        { id: 'demo', label: 'Demo', icon: <MessageSquare size={20} />, ref: chatRef },
        { id: 'contact', label: 'Contact', icon: <Phone size={20} />, ref: contactRef }
    ];

    return (
        <div className="landing-page">
            {/* Animated Background */}
            <div className="landing-background">
                <motion.div 
                    className="background-gradient"
                    style={{ y: backgroundY }}
                />
                <div className="grid-pattern" />
                
                {/* Floating Stars */}
                {floatingStars.map(star => (
                    <motion.div
                        key={star.id}
                        className="floating-star"
                        style={{
                            left: `${star.x}%`,
                            top: `${star.y}%`,
                            width: `${star.size}px`,
                            height: `${star.size}px`,
                        }}
                        animate={{
                            y: [-15, 15, -15],
                            opacity: [star.opacity * 0.6, star.opacity, star.opacity * 0.6],
                            scale: [1, 1.1, 1]
                        }}
                        transition={{
                            duration: star.duration,
                            delay: star.delay,
                            repeat: Infinity,
                            ease: "easeInOut",
                            type: "tween" // Use tween for better performance
                        }}
                    />
                ))}
            </div>

            {/* Top navbar removed as per request */}

            {/* Hero Section */}
            <motion.section 
                ref={heroRef}
                className="hero-section"
                style={{ y: textY }}
            >
                <div className="hero-content">
                    <motion.div 
                        className="hero-icon"
                        initial={{ scale: 0, rotate: -180 }}
                        animate={{ scale: 1, rotate: 0 }}
                        transition={{ duration: 0.8, delay: 0.5 }}
                    >
                        <MayaLogo size={80} className="maya-logo" />
                    </motion.div>
                    
                    <motion.h1 
                        className="hero-title"
                        initial={{ opacity: 0, y: 50 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.8, delay: 0.3 }}
                    >
                        Your Personal
                        <br />
                        AI Assistant <span className="maya-text">Aurion</span>
                    </motion.h1>
                    
                    <motion.p 
                        className="hero-subtitle"
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.8, delay: 0.6 }}
                    >
                        Aurion is an intelligent, adaptive AI that remembers your conversations, 
                        learns your preferences, and grows with you to provide truly personalized assistance.
                    </motion.p>
                    
                    <motion.div 
                        className="hero-cta"
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.8, delay: 0.9 }}
                    >
                        <div className="email-input-group">
                            <input
                                type="email"
                                placeholder="Enter your email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="email-input"
                                onKeyPress={(e) => e.key === 'Enter' && handleJoinBeta()}
                            />
                            <button 
                                onClick={handleJoinBeta}
                                className="cta-button"
                            >
                                Join Beta
                                <ArrowRight className="button-icon" />
                            </button>
                        </div>
                    </motion.div>
                </div>
            </motion.section>

            {/* Features Section */}
            <FeatureSection ref={featuresRef} />

            {/* Chat Demo Section */}
            <ChatDemoSection 
                ref={chatRef}
                chatMessages={chatMessages}
                newMessage={newMessage}
                setNewMessage={setNewMessage}
                handleSendMessage={handleSendMessage}
            />

            {/* Contact Section */}
            <ContactSection ref={contactRef} />

            {/* Side navigation removed as per request */}

            {/* Auth Modal */}
            <AuthModal
                isOpen={authModal.isOpen}
                onClose={closeAuthModal}
                onAuthSuccess={handleAuthSuccess}
                initialMode={authModal.mode}
            />
        </div>
    );
};

// Features Section Component
const FeatureSection = React.forwardRef((props, ref) => {
    const isInView = useInView(ref, { once: true, threshold: 0.2 });
    
    const features = [
        {
            icon: <Brain />,
            title: "Conversational Memory",
            description: "Remembers your past interactions for seamless, contextual conversations that build over time."
        },
        {
            icon: <Zap />,
            title: "Adaptive Learning", 
            description: "Learns your preferences, communication style, and needs to provide increasingly personalized responses."
        },
        {
            icon: <MessageCircle />,
            title: "Multi-Format Support",
            description: "Handles text conversations with plans for voice and multimedia interactions in the future."
        },
        {
            icon: <Shield />,
            title: "Privacy First",
            description: "Your data is secure with enterprise-grade encryption and privacy controls you can trust."
        }
    ];

    return (
        <section ref={ref} className="features-section">
            <div className="features-container">
                <motion.h2 
                    className="section-title"
                    initial={{ opacity: 0, y: 50 }}
                    animate={isInView ? { opacity: 1, y: 0 } : {}}
                    transition={{ duration: 0.8 }}
                >
                    Why Choose Aurion?
                </motion.h2>
                
                <div className="features-grid">
                    {features.map((feature, index) => (
                        <motion.div
                            key={index}
                            className="feature-card"
                            initial={{ opacity: 0, y: 50 }}
                            animate={isInView ? { opacity: 1, y: 0 } : {}}
                            transition={{ duration: 0.8, delay: index * 0.2 }}
                            whileHover={{ scale: 1.05, y: -10 }}
                        >
                            <div className="feature-icon">
                                {feature.icon}
                            </div>
                            <h3 className="feature-title">{feature.title}</h3>
                            <p className="feature-description">{feature.description}</p>
                        </motion.div>
                    ))}
                </div>
            </div>
        </section>
    );
});

// Chat Demo Section Component
const ChatDemoSection = React.forwardRef(({ chatMessages, newMessage, setNewMessage, handleSendMessage }, ref) => {
    const isInView = useInView(ref, { once: true, threshold: 0.2 });
    
    return (
        <section ref={ref} className="chat-demo-section">
            <motion.div 
                className="chat-container"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={isInView ? { opacity: 1, scale: 1 } : {}}
                transition={{ duration: 0.8, type: "spring" }}
            >
                <div className="chat-header">
                    <div className="chat-avatar">
                        <Bot className="bot-icon" />
                    </div>
                    <div className="chat-info">
                        <h3>Aurion AI Assistant</h3>
                        <p>Online • Always learning</p>
                    </div>
                </div>
                
                <div className="chat-messages">
                    {chatMessages.map((message, index) => (
                        <motion.div
                            key={message.id}
                            className={`message ${message.type}`}
                            initial={{ opacity: 0, x: message.type === 'bot' ? -50 : 50 }}
                            animate={isInView ? { opacity: 1, x: 0 } : {}}
                            transition={{ duration: 0.5, delay: index * 0.2 }}
                        >
                            <div className="message-avatar">
                                {message.type === 'bot' ? (
                                    <Bot className="avatar-icon" />
                                ) : (
                                    <User className="avatar-icon" />
                                )}
                            </div>
                            <div className="message-content">
                                <p>{message.message}</p>
                                <span className="message-time">{message.timestamp}</span>
                            </div>
                        </motion.div>
                    ))}
                </div>
                
                <div className="chat-input">
                    <input
                        type="text"
                        placeholder="Type your message..."
                        value={newMessage}
                        onChange={(e) => setNewMessage(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                        className="message-input"
                    />
                    <motion.button 
                        onClick={handleSendMessage}
                        className="send-button"
                        whileHover={{ scale: 1.1 }}
                        whileTap={{ scale: 0.9 }}
                    >
                        <Send className="send-icon" />
                    </motion.button>
                </div>
            </motion.div>
        </section>
    );
});

// Contact Section Component
const ContactSection = React.forwardRef((props, ref) => {
    const isInView = useInView(ref, { once: true, threshold: 0.2 });
    
    return (
        <section ref={ref} className="contact-section">
            <motion.div 
                className="contact-container"
                initial={{ opacity: 0, y: 50 }}
                animate={isInView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.8 }}
            >
                <h2 className="section-title">Get in Touch</h2>
                <p className="contact-subtitle">
                    Ready to experience the future of AI assistance? Join our community and stay updated.
                </p>
                
                <div className="social-links">
                    <motion.a 
                        href="#" 
                        className="social-link"
                        whileHover={{ scale: 1.2, y: -5 }}
                    >
                        <Twitter />
                    </motion.a>
                    <motion.a 
                        href="#" 
                        className="social-link"
                        whileHover={{ scale: 1.2, y: -5 }}
                    >
                        <Github />
                    </motion.a>
                    <motion.a 
                        href="#" 
                        className="social-link"
                        whileHover={{ scale: 1.2, y: -5 }}
                    >
                        <Mail />
                    </motion.a>
                </div>
                
                <div className="footer-text">
                    <p>Built with ❤️ by the Aurion Team</p>
                    <p>© 2025 Aurion AI. All rights reserved.</p>
                </div>
            </motion.div>
        </section>
    );
});

// SideNavigation component removed

export default LandingPage;