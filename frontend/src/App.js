import React, { useState, useEffect, useCallback, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useNavigationType } from 'react-router-dom';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import AuthModal from './components/AuthModal';
import LandingPage from './components/LandingPage';
// Removed old Dashboard; modern dashboard is the default now.
import ModernDashboard from './components/ModernDashboard';
import LoadingSpinner from './components/LoadingSpinner';
import ChatLayout from './components/ChatLayout.jsx';
import Profile from './components/ProfileInterface';
import Tasks from './components/Tasks';
import Help from './components/Help';
import Settings from './components/Settings';
import NotFound from './components/NotFound';
import ForgotPassword from './components/ForgotPassword';
// Removed temporary SidebarTest component.
import authService from './services/auth';
import './styles/variables.css';
import './styles/App.css';
import realtimeClient from './services/realtimeClient';
import ResponsiveNavbar from './components/ResponsiveNavbar';
import { SelectionProvider } from './contexts/SelectionContext';
// Removed TransitionOverlay for a cleaner, minimal transition
// InlineAgent removed

// Renders the global navbar on public pages only (hide on app pages like dashboard/settings/profile/tasks/help)
const NavbarGate = ({ onLogin, onSignup }) => {
    const location = useLocation();
    const hidePrefixes = ['/dashboard', '/settings', '/profile', '/tasks', '/help'];
    if (hidePrefixes.some(p => location.pathname === p || location.pathname.startsWith(p + '/'))) return null;
    return (
        <ResponsiveNavbar 
            onLogin={onLogin}
            onSignup={onSignup}
        />
    );
};

/* 
// Old Home component - replaced with LandingPage
const Home = ({ setAuthModal }) => {
    const [showScrollTop, setShowScrollTop] = useState(false);
    const mountRef = useRef(null);

    const handleScroll = useCallback(() => {
        setShowScrollTop(window.scrollY > 300);
    }, []);

    useEffect(() => {
        window.addEventListener('scroll', handleScroll);

        // Setup 3D background animation
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.z = 15;

        const renderer = new THREE.WebGLRenderer({ alpha: true });
        renderer.setSize(window.innerWidth, window.innerHeight);
        const mount = mountRef.current;
        mount.appendChild(renderer.domElement);

        // Lights
        const directionalLight = new THREE.DirectionalLight(0x3b82f6, 1);
        directionalLight.position.set(5, 5, 5);
        scene.add(directionalLight);

        const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
        scene.add(ambientLight);

        // Particle system for trails
        const particleGeometry = new THREE.BufferGeometry();
        const particleCount = 1000;
        const particlePositions = new Float32Array(particleCount * 3);
        const particleVelocities = new Float32Array(particleCount * 3);
        for (let i = 0; i < particleCount; i++) {
            particlePositions[i * 3] = (Math.random() - 0.5) * 20;
            particlePositions[i * 3 + 1] = (Math.random() - 0.5) * 20;
            particlePositions[i * 3 + 2] = (Math.random() - 0.5) * 20;
            particleVelocities[i * 3] = (Math.random() - 0.5) * 0.01;
            particleVelocities[i * 3 + 1] = (Math.random() - 0.5) * 0.01;
            particleVelocities[i * 3 + 2] = (Math.random() - 0.5) * 0.01;
        }
        particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
        const particleMaterial = new THREE.PointsMaterial({
            color: 0x3b82f6,
            size: 0.05,
            transparent: true,
            opacity: 0.3,
        });
        const particles = new THREE.Points(particleGeometry, particleMaterial);
        scene.add(particles);

        // Symbols and tools
        const symbols = ['∑', 'π', '√', '∞', '∫', '≈', 'θ', '🧭', '📏', '🖩', '📐'];
        const meshes = [];
        const targetPositions = [];
        const initialPositions = [];
        const timeOffsets = symbols.map(() => Math.random() * 2 * Math.PI);

        // Simulate brain shape with a point cloud
        const brainRadius = 3;
        symbols.forEach((_, i) => {
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos(2 * Math.random() - 1);
            const r = brainRadius * Math.cbrt(Math.random());
            const x = r * Math.sin(phi) * Math.cos(theta);
            const y = r * Math.sin(phi) * Math.sin(theta);
            const z = r * Math.cos(phi);
            targetPositions.push(new THREE.Vector3(x, y, z));
        });

        const fontLoader = new FontLoader();
        fontLoader.load('https://threejs.org/examples/fonts/helvetiker_regular.typeface.json', (font) => {
            symbols.forEach((sym, i) => {
                const textGeo = new TextGeometry(sym, {
                    font,
                    size: 0.3,
                    depth: 0.1,
                    curveSegments: 12,
                    bevelEnabled: true,
                    bevelThickness: 0.01,
                    bevelSize: 0.01,
                    bevelOffset: 0,
                    bevelSegments: 5,
                });

                const material = new THREE.MeshStandardMaterial({
                    color: 0x3b82f6,
                    metalness: 0.9,
                    roughness: 0.2,
                    emissive: 0x3b82f6,
                    emissiveIntensity: 0.8,
                });

                const mesh = new THREE.Mesh(textGeo, material);
                mesh.position.set((Math.random() - 0.5) * 20, (Math.random() - 0.5) * 20, (Math.random() - 0.5) * 20);
                initialPositions.push(mesh.position.clone());
                scene.add(mesh);
                meshes.push(mesh);
            });
        });

        // Animation loop
        const animate = (time) => {
            requestAnimationFrame(animate);

            const scrollFraction = Math.min(document.documentElement.scrollTop / (document.documentElement.scrollHeight - document.documentElement.clientHeight), 1);

            meshes.forEach((mesh, i) => {
                const target = targetPositions[i];
                const initial = initialPositions[i];
                mesh.position.lerpVectors(target, initial, scrollFraction);
                mesh.rotation.y = scrollFraction * Math.PI * 2 + Math.sin(time / 1000 + timeOffsets[i]) * 0.2;
                mesh.rotation.x = Math.sin(time / 1000 + timeOffsets[i]) * 0.1;
                mesh.material.emissiveIntensity = 0.8 + Math.sin(time / 500 + timeOffsets[i]) * 0.2 * (1 - scrollFraction);
            });

            // Update particles
            for (let i = 0; i < particleCount; i++) {
                particlePositions[i * 3] += particleVelocities[i * 3] * (1 - scrollFraction);
                particlePositions[i * 3 + 1] += particleVelocities[i * 3 + 1] * (1 - scrollFraction);
                particlePositions[i * 3 + 2] += particleVelocities[i * 3 + 2] * (1 - scrollFraction);
                if (Math.abs(particlePositions[i * 3]) > 10 || Math.abs(particlePositions[i * 3 + 1]) > 10 || Math.abs(particlePositions[i * 3 + 2]) > 10) {
                    particlePositions[i * 3] = (Math.random() - 0.5) * 20;
                    particlePositions[i * 3 + 1] = (Math.random() - 0.5) * 20;
                    particlePositions[i * 3 + 2] = (Math.random() - 0.5) * 20;
                }
            }
            particleGeometry.attributes.position.needsUpdate = true;

            renderer.render(scene, camera);
        };
        requestAnimationFrame(animate);

        // Handle resize
        const handleResize = () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        };
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('scroll', handleScroll);
            window.removeEventListener('resize', handleResize);
            if (mount && renderer.domElement) {
                mount.removeChild(renderer.domElement);
            }
        };
    }, [handleScroll]);

    const scrollToTop = () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    return (
        <div className="home-container">
            <div ref={mountRef} className="bg-canvas"></div>

            <div className="hero-section">
                <h1 className="hero-title">Aurion: Your Personal AI Assistant</h1>
                <p className="hero-subtitle">An intelligent, adaptive partner for managing tasks and memories with a human touch.</p>
                <div className="hero-cta">
                    <button 
                        onClick={() => setAuthModal({ isOpen: true, mode: 'signin' })} 
                        className="cta-button login-link"
                    >
                        Get Started
                    </button>
                    <button 
                        onClick={() => setAuthModal({ isOpen: true, mode: 'signup' })} 
                        className="cta-button register-link"
                    >
                        Sign Up
                    </button>
                </div>
            </div>

            <section className="about-section">
                <h2 className="section-title">About Aurion</h2>
                <p className="section-text">
                    Aurion is a cutting-edge personal AI assistant designed to understand you deeply. Powered by advanced AI technologies, Aurion remembers your conversations, learns your preferences, and adapts to your unique style, making every interaction feel natural and personalized.
                </p>
                <div className="feature-cards">
                    <div className="feature-card">
                        <h3>Conversational Memory</h3>
                        <p>Recalls past interactions for seamless, natural conversations.</p>
                    </div>
                    <div className="feature-card">
                        <h3>Personalized Learning</h3>
                        <p>Adapts to your preferences, tone, and frequent tasks.</p>
                    </div>
                    <div className="feature-card">
                        <h3>Multi-Format Support</h3>
                        <p>Handles text, voice, and potentially images or videos.</p>
                    </div>
                </div>
            </section>

            <section className="goals-section">
                <h2 className="section-title">Our Goals</h2>
                <ul className="goals-list">
                    <li>Deliver highly contextual and personalized responses.</li>
                    <li>Support a wide range of tasks, from reminders to complex queries.</li>
                    <li>Continuously improve through learning from user interactions.</li>
                    <li>Provide a fast, efficient, and reliable experience.</li>
                </ul>
            </section>

            <section className="why-best-section">
                <h2 className="section-title">Why Aurion is the Best</h2>
                <p className="section-text">
                    Aurion stands out by combining a powerful language model (Google Gemini Pro) with a sophisticated memory system and knowledge graph. This allows Aurion to understand relationships, learn over time, and deliver responses that feel uniquely tailored to you. Our real-time backend and intuitive interface ensure a seamless experience, whether you're managing tasks or having a casual chat.
                </p>
            </section>

            <section className="tech-stack-section">
                <h2 className="section-title">Tech Stack</h2>
                <div className="tech-stack-grid">
                    <div className="tech-item">Google Gemini Pro: Language Engine</div>
                    <div className="tech-item">Redis +PostgreSQL: Memory Storage</div>
                    <div className="tech-item">Neo4j/ArangoDB: Knowledge Graph</div>
                    <div className="tech-item">FastAPI + WebSocket: Real-Time Backend</div>
                    <div className="tech-item">React: Intuitive Frontend</div>
                    <div className="tech-item">Celery: Task Management</div>
                    <div className="tech-item">ELK Stack: Performance Monitoring</div>
                </div>
            </section>

            <footer className="footer">
                <p>Built with ❤️ by the Aurion Team</p>
                <p>Empowering you with AI that grows with you.</p>
                <div className="footer-links">
                    <a href="https://x.ai" target="_blank" rel="noopener noreferrer">About xAI</a>
                    <a href="https://x.ai/api" target="_blank" rel="noopener noreferrer">API Access</a>
                    <a href="https://help.x.com/en/using-x/x-premium" target="_blank" rel="noopener noreferrer">Premium Plans</a>
                </div>
            </footer>

            {showScrollTop && (
                <button onClick={scrollToTop} className="back-to-top">
                    ↑
                </button>
            )}
        </div>
    );
};
*/ 

// Direction-aware, reduced-motion friendly route animations
const AnimatedRoute = ({ children }) => {
    // Determine navigation intent: PUSH (forward) vs POP (back)
    const navigationType = useNavigationType();
    const prefersReduced = useReducedMotion();
    const direction = navigationType === 'POP' ? -1 : 1; // -1 back, 1 forward/replace

    // Allow quick toggling without code edits: localStorage.setItem('aurion-transition', 'sleek'|'minimal')
    const [pref, setPref] = React.useState(() => {
        try { return localStorage.getItem('aurion-transition') || 'sleek'; } catch { return 'sleek'; }
    });
    useEffect(() => {
        const onStorage = (e) => {
            if (e.key === 'maya-transition') setPref(e.newValue || 'sleek');
        };
        window.addEventListener('storage', onStorage);
        return () => window.removeEventListener('storage', onStorage);
    }, []);

    // Variant presets
    const variants = React.useMemo(() => {
        if (prefersReduced) {
            return {
                initial: { opacity: 0 },
                animate: { opacity: 1 },
                exit: { opacity: 0 }
            };
        }

        if (pref === 'minimal') {
            return {
                initial: (dir) => ({ opacity: 0, y: dir > 0 ? 8 : -8 }),
                animate: { opacity: 1, y: 0, transition: { y: { type: 'spring', stiffness: 340, damping: 34 }, opacity: { duration: 0.28 } } },
                exit: (dir) => ({ opacity: 0, y: dir > 0 ? -6 : 6, transition: { duration: 0.2 } })
            };
        }

        // 'sleek' default: gentle scale + vertical slide, premium feel
        return {
            initial: (dir) => ({ opacity: 0, y: dir > 0 ? 22 : -22, scale: 0.985 }),
            animate: {
                opacity: 1,
                y: 0,
                scale: 1,
                transition: {
                    y: { type: 'spring', stiffness: 420, damping: 36, mass: 0.9 },
                    scale: { duration: 0.36, ease: [0.22, 1, 0.36, 1] },
                    opacity: { duration: 0.34, ease: [0.22, 1, 0.36, 1] }
                }
            },
            exit: (dir) => ({ opacity: 0, y: dir > 0 ? -14 : 14, scale: 0.986, transition: { y: { duration: 0.24, ease: [0.4, 0, 1, 1] }, opacity: { duration: 0.22 }, scale: { duration: 0.22 } } })
        };
    }, [pref, prefersReduced]);

    return (
        <motion.div
            custom={direction}
            initial="initial"
            animate="animate"
            exit="exit"
            variants={variants}
            style={{ width: '100%', height: '100%', overflow: 'hidden', willChange: 'transform, opacity' }}
        >
            {children}
        </motion.div>
    );
};

// Enhanced private route wrapper with loading state
const PrivateRoute = ({ children }) => {
    const [isLoading, setIsLoading] = useState(true);
    const [isAuthenticated, setIsAuthenticated] = useState(false);

    useEffect(() => {
        const checkAuth = async () => {
            try {
                const user = authService.getCurrentUser();
                setIsAuthenticated(!!user);
            } catch (error) {
                setIsAuthenticated(false);
            } finally {
                setIsLoading(false);
            }
        };

        checkAuth();
    }, []);

    if (isLoading) {
        return (
            <div className="auth-loading">
                <LoadingSpinner />
            </div>
        );
    }

    // Redirect unauthenticated users to landing page now that standalone login page is removed
    return isAuthenticated ? children : <Navigate to="/" replace />;
};


function App() {
    // currentUser value not needed here after navigation removal; keep setter for auth flow
    const [, setCurrentUser] = useState(undefined);
    const [isInitializing, setIsInitializing] = useState(true);
    const [authModal, setAuthModal] = useState({ isOpen: false, mode: 'signin' });

    useEffect(() => {
        const initializeAuth = async () => {
            try {
                const user = authService.getCurrentUser();
                setCurrentUser(user);
                // Start realtime SSE after we know auth state; EventSource uses cookies
                try { realtimeClient.start(); } catch {}
            } catch (error) {
                console.error('Auth initialization error:', error);
            } finally {
                setIsInitializing(false);
            }
        };

        initializeAuth();

        // Listen for auth state changes
        const handleStorageChange = (e) => {
            if (e.key === 'user' || e.key === 'access_token') {
                const user = authService.getCurrentUser();
                setCurrentUser(user);
            }
        };

        window.addEventListener('storage', handleStorageChange);
        return () => window.removeEventListener('storage', handleStorageChange);
    }, []);

    // Initialize theme system
    useEffect(() => {
        const initializeTheme = () => {
            const savedTheme = localStorage.getItem('maya-theme') || 'system';
            
            if (savedTheme === 'system') {
                const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
                document.documentElement.setAttribute('data-theme', systemTheme);
            } else {
                document.documentElement.setAttribute('data-theme', savedTheme);
            }
        };

        initializeTheme();
    }, []);

    const handleLogout = useCallback(() => {
        authService.logout();
        setCurrentUser(null);
        window.location.href = "/";
    }, []);

    const handleAuthSuccess = useCallback((user) => {
        setCurrentUser(user);
        setAuthModal({ isOpen: false, mode: 'signin' });
    }, []);

    const closeAuthModal = useCallback(() => {
        setAuthModal({ isOpen: false, mode: 'signin' });
    }, []);

    if (isInitializing) {
        return (
            <div className="app-initializing">
                <LoadingSpinner />
            </div>
        );
    }

    // Component to key routes by location for correct exit/enter animations
    const RoutesWithAnimation = () => {
        const location = useLocation();
        return (
            <AnimatePresence initial={false} mode="sync">
                <Routes location={location} key={location.pathname}>
                                    <Route 
                                        path="/" 
                                        element={
                                            <AnimatedRoute>
                                                <LandingPage />
                                            </AnimatedRoute>
                                        } 
                                    />
                                    <Route 
                                        path="/dashboard" 
                                        element={
                                            <PrivateRoute>
                                                <AnimatedRoute>
                                                    <ModernDashboard />
                                                </AnimatedRoute>
                                            </PrivateRoute>
                                        } 
                                    />
                                    <Route 
                                        path="/chat" 
                                        element={
                                            <PrivateRoute>
                                                <AnimatedRoute>
                                                    <ChatLayout onNavigate={() => {}} onLogout={handleLogout} />
                                                </AnimatedRoute>
                                            </PrivateRoute>
                                        } 
                                    />
                                    <Route 
                                        path="/profile" 
                                        element={
                                            <PrivateRoute>
                                                <AnimatedRoute>
                                                    <Profile />
                                                </AnimatedRoute>
                                            </PrivateRoute>
                                        } 
                                    />
                                    <Route 
                                        path="/tasks" 
                                        element={
                                            <PrivateRoute>
                                                <AnimatedRoute>
                                                    <Tasks />
                                                </AnimatedRoute>
                                            </PrivateRoute>
                                        } 
                                    />
                                    <Route 
                                        path="/help" 
                                        element={
                                            <PrivateRoute>
                                                <AnimatedRoute>
                                                    <Help />
                                                </AnimatedRoute>
                                            </PrivateRoute>
                                        } 
                                    />
                                    <Route 
                                        path="/settings" 
                                        element={
                                            <PrivateRoute>
                                                <AnimatedRoute>
                                                    <Settings onNavigate={(view) => {
                                                        if (view === 'api-keys') {
                                                            window.location.href = '/settings#api-keys';
                                                        }
                                                    }} />
                                                </AnimatedRoute>
                                            </PrivateRoute>
                                        } 
                                    />
                                    <Route 
                                        path="/forgot-password" 
                                        element={
                                            <AnimatedRoute>
                                                <ForgotPassword onNavigate={(view)=>{
                                                    if(view==='login') setAuthModal({ isOpen: true, mode: 'signin' });
                                                    if(view==='landing') window.location.href='/';
                                                }} />
                                            </AnimatedRoute>
                                        }
                                    />
                                    {/** Legacy dashboard route removed **/}
                                    {/** Sidebar test route removed **/}
                                    <Route path="*" element={<AnimatedRoute><NotFound /></AnimatedRoute>} />
                </Routes>
            </AnimatePresence>
        );
    };

    return (
        <SelectionProvider>
            <Router>
                <div className="app-container">
                    <NavbarGate onLogin={() => setAuthModal({ isOpen: true, mode: 'signin' })}
                                onSignup={() => setAuthModal({ isOpen: true, mode: 'signup' })} />
                    <main className="app-content">
                        <Suspense fallback={<LoadingSpinner />}>
                            <RoutesWithAnimation />
                        </Suspense>
                        {/* Overlay removed for a cleaner look */}
                    </main>

                    {/* Auth Modal */}
                    <AuthModal
                        isOpen={authModal.isOpen}
                        onClose={closeAuthModal}
                        onAuthSuccess={handleAuthSuccess}
                        initialMode={authModal.mode}
                    />
                </div>
            </Router>
        </SelectionProvider>
    );
}

export default App;