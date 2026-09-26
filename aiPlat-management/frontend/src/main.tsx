import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './styles/tokens.css';
import { clearChunkReloadFlag, reloadOnceOnChunkError } from './utils/lazyWithRetry';

clearChunkReloadFlag();
window.addEventListener('unhandledrejection', (ev) => {
  if (reloadOnceOnChunkError(ev.reason)) {
    ev.preventDefault();
  }
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
