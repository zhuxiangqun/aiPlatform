import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ConfigProvider, App as AntApp, theme } from 'antd';
import App from './App.tsx';
import './styles/tokens.css';

const themeConfig = {
  token: {
    colorPrimary: '#3B82F6',
    borderRadius: 6,
    fontFamily: 'var(--font-sans)',
    colorBgContainer: '#1C2128',
    colorBgElevated: '#161B22',
    colorBgLayout: '#0D1117',
    colorBorder: '#30363D',
    colorBorderSecondary: '#21262D',
    colorText: '#E6EDF3',
    colorTextSecondary: '#8B949E',
    colorTextTertiary: '#6E7681',
    colorTextPlaceholder: '#6E7681',
    colorFill: '#1C2128',
    colorFillSecondary: '#161B22',
    colorFillTertiary: '#0D1117',
    colorFillQuaternary: '#0D1117',
  },
  algorithm: theme.darkAlgorithm,
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider theme={themeConfig}>
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </StrictMode>,
);