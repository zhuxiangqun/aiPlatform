import React from 'react';
import { motion } from 'framer-motion';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hoverable?: boolean;
  onClick?: () => void;
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  hoverable = false,
  onClick,
}) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15 }}
      className={`
        bg-dark-card rounded-xl shadow-sm border border-dark-border
        ${hoverable ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}
        ${className}
      `}
      onClick={onClick}
    >
      {children}
    </motion.div>
  );
};

interface CardHeaderProps {
  title?: string;
  extra?: React.ReactNode;
  children?: React.ReactNode;
}

export const CardHeader: React.FC<CardHeaderProps> = ({ title, extra, children }) => {
  return (
    <div className="px-5 py-4 border-b border-dark-border flex items-center justify-between">
      {children || (
        <>
          <h3 className="font-semibold text-gray-100">{title}</h3>
          {extra && <div>{extra}</div>}
        </>
      )}
    </div>
  );
};

interface CardContentProps {
  children: React.ReactNode;
  className?: string;
}

export const CardContent: React.FC<CardContentProps> = ({ children, className = '' }) => {
  return <div className={`p-5 ${className}`}>{children}</div>;
};

export default Card;
