// Yes. It shows the auth page top bar with a back button and animated brand title for navigation.

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft } from 'lucide-react';
import '../styles/AuthNavbar.css';

const AuthNavbar = ({ title = "Aurion", showBack = true, backUrl = "/" }) => {
    const navigate = useNavigate();

    const handleBack = () => {
        navigate(backUrl);
    };

    return (
        <motion.nav 
            className="auth-navbar"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
        >
            <div className="auth-navbar-content">
                {showBack && (
                    <motion.button 
                        className="back-button"
                        onClick={handleBack}
                        whileHover={{ scale: 1.05, x: -2 }}
                        whileTap={{ scale: 0.95 }}
                        transition={{ duration: 0.2 }}
                    >
                        <ArrowLeft size={20} />
                        <span>Back</span>
                    </motion.button>
                )}
                
                <motion.div 
                    className="navbar-brand"
                    whileHover={{ scale: 1.02 }}
                    transition={{ duration: 0.2 }}
                >
                    <span className="brand-text">{title}</span>
                </motion.div>

                <div className="navbar-spacer"></div>
            </div>
        </motion.nav>
    );
};

export default AuthNavbar;