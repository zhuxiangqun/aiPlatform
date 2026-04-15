import React from 'react';
import { motion } from 'framer-motion';

interface CardProps {
  hoverable?: boolean;
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export const Card: React.FC<CardProps> = ({
  hoverable = false,
  children,
  className = '',
  onClick,
}) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15 }}
      className={`
        bg-dark-card rounded-xl border border-dark-border p-5
        ${hoverable ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}
        ${className}
      `}
      onClick={onClick}
    >
      {children}
    </motion.div>
  );
};

export default Card;
