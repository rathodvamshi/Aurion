import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import '../styles/ResponsiveNavbar.css';

/**
 * Responsive glassmorphism navbar with mobile drawer.
 */
const ResponsiveNavbar = ({ onLogin, onSignup }) => {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => { setOpen(false); }, [location.pathname]);

  const navItems = [
    { label: 'Home', to: '/' },
    { label: 'Explore', to: '/#explore' },
    { label: 'Contact', to: '/#contact' }
  ];

  return (
    <nav className={`glassmorphism-navbar ${scrolled ? 'scrolled' : ''}`}>      
      <div className="glassmorphism-navbar-content">
        <div className="navbar-brand" onClick={() => navigate('/')}>          
          <motion.span className="brand-text" whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>Aurion</motion.span>
        </div>

        <div className="navbar-menu desktop-only">
          {navItems.map(item => (
            <button key={item.label} className="nav-menu-item" onClick={() => navigate(item.to)}>{item.label}</button>
          ))}
          <button className="nav-menu-item auth-item" onClick={onLogin}>Login</button>
          <button className="nav-menu-item auth-item signup-btn" onClick={onSignup}>Sign Up</button>
        </div>

        {/* Hamburger */}
        <button className={`hamburger ${open ? 'active' : ''}`} onClick={() => setOpen(o => !o)} aria-label="Toggle navigation" aria-expanded={open}>
          <span></span><span></span><span></span>
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            className="mobile-drawer"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.25 }}
          >
            {navItems.map(item => (
              <button key={item.label} className="drawer-item" onClick={() => navigate(item.to)}>{item.label}</button>
            ))}
            <div className="drawer-auth">
              <button className="drawer-login" onClick={onLogin}>Login</button>
              <button className="drawer-signup" onClick={onSignup}>Sign Up</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
};

export default ResponsiveNavbar;
