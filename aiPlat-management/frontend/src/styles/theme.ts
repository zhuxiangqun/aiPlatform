/**
 * AI Platform Theme Configuration - Dark Theme
 * 
 * JavaScript constants for use in components.
 * Values are synchronized with CSS tokens in /styles/tokens.css
 * Theme: Black Background / White Text
 */

export const theme = {
  colors: {
    primary: '#3B82F6',
    primaryHover: '#2563EB',
    primaryActive: '#1D4ED8',
    primaryLight: '#1C2128',
    primaryBorder: '#388BFD33',

    success: '#10B981',
    successHover: '#059669',
    successActive: '#047857',
    successLight: '#0D1117',
    successBorder: '#23863633',

    warning: '#F59E0B',
    warningHover: '#D97706',
    warningActive: '#B45309',
    warningLight: '#0D1117',
    warningBorder: '#9E6A0333',

    error: '#EF4444',
    errorHover: '#DC2626',
    errorActive: '#B91C1C',
    errorLight: '#0D1117',
    errorBorder: '#F8514966',

    info: '#3B82F6',
    infoLight: '#0D1117',

    gray: {
      50: '#161B22',
      100: '#1C2128',
      200: '#22272E',
      300: '#30363D',
      400: '#484F58',
      500: '#6E7681',
      600: '#8B949E',
      700: '#B1BAC4',
      800: '#C9D1D9',
      900: '#E6EDF3',
    },

    text: {
      primary: '#E6EDF3',
      secondary: '#8B949E',
      tertiary: '#6E7681',
      disabled: '#484F58',
      inverse: '#0D1117',
      placeholder: '#6E7681',
      link: '#3B82F6',
    },

    bg: {
      primary: '#0D1117',
      secondary: '#161B22',
      tertiary: '#1C2128',
      layout: '#0D1117',
      overlay: 'rgba(0, 0, 0, 0.75)',
      hover: '#1C2128',
      active: '#1C2128',
    },

    border: {
      default: '#30363D',
      hover: '#484F58',
      active: '#3B82F6',
      focus: 'rgba(59, 130, 246, 0.15)',
      light: '#21262D',
    },

    badge: {
      success: { bg: '#0D1117', text: '#10B981' },
      warning: { bg: '#0D1117', text: '#F59E0B' },
      error: { bg: '#0D1117', text: '#EF4444' },
      info: { bg: '#0D1117', text: '#3B82F6' },
      neutral: { bg: '#1C2128', text: '#B1BAC4' },
    },
  },

  font: {
    family: "'Geist Variable', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    mono: "'JetBrains Mono', 'Fira Code', Consolas, monospace",

    size: {
      xs: 12,
      sm: 13,
      base: 14,
      lg: 16,
      xl: 18,
      '2xl': 20,
      '3xl': 24,
      '4xl': 30,
    },

    lineHeight: {
      xs: 16,
      sm: 20,
      base: 22,
      lg: 24,
      xl: 28,
      '2xl': 28,
      '3xl': 32,
      '4xl': 36,
    },

    weight: {
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },

    tracking: {
      tight: '-0.025em',
      normal: '0',
      wide: '0.025em',
    },
  },

  spacing: {
    0: 0,
    1: 4,
    2: 8,
    3: 12,
    4: 16,
    5: 20,
    6: 24,
    8: 32,
    10: 40,
    12: 48,
  },

  radius: {
    none: 0,
    sm: 6,
    md: 8,
    lg: 12,
    xl: 16,
    '2xl': 20,
    full: 9999,
  },

  shadow: {
    xs: '0 1px 2px rgba(0, 0, 0, 0.3)',
    sm: '0 1px 3px rgba(0, 0, 0, 0.4), 0 1px 2px rgba(0, 0, 0, 0.3)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -2px rgba(0, 0, 0, 0.3)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -4px rgba(0, 0, 0, 0.3)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.3)',
  },

  layout: {
    headerHeight: 60,
    siderWidth: 240,
    siderCollapsedWidth: 64,
    contentPadding: 32,
  },

  zIndex: {
    base: 0,
    dropdown: 100,
    sticky: 200,
    fixed: 300,
    modalBackdrop: 400,
    modal: 500,
    popover: 600,
    tooltip: 700,
    notification: 800,
  },

  animation: {
    duration: {
      fast: '100ms',
      normal: '150ms',
      slow: '200ms',
      slower: '300ms',
    },
    easing: {
      default: 'cubic-bezier(0.4, 0, 0.2, 1)',
      in: 'cubic-bezier(0.4, 0, 1, 1)',
      out: 'cubic-bezier(0, 0, 0.2, 1)',
      bounce: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
    },
  },

  legacy: {
    textPrimary: 'rgba(255, 255, 255, 0.9)',
    textSecondary: '#8B949E',
    textTertiary: '#6E7681',
    textDisabled: '#484F58',
    bgSecondary: '#161B22',
    border: '#30363D',
    borderLight: '#21262D',
  },
} as const;

export type Theme = typeof theme;

export default theme;
