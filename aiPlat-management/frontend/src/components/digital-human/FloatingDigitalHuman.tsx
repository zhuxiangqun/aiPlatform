import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Mic, Minimize2, ChevronUp, ChevronDown, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useWakeWord } from '../../hooks/useWakeWord';
import { useVoiceChat, ChatStatus } from '../../hooks/useVoiceChat';
import { getPageInfo } from '../../pageManifest';
import { getPageData, pageDataToText } from '../../lib/pageDataBridge';
import AnimatedAvatar from './AnimatedAvatar';

const POS_STORAGE_KEY = 'aiplat.digital_human.pos';
const ICON_SIZE = 56;
const PANEL_WIDTH = 260;
const PANEL_HEIGHT_APPROX = 380;
const DRAG_THRESHOLD_PX = 5;

function clampPos(x: number, y: number, w: number, h: number) {
  const maxX = Math.max(8, window.innerWidth - w - 8);
  const maxY = Math.max(8, window.innerHeight - h - 8);
  return {
    x: Math.min(Math.max(8, x), maxX),
    y: Math.min(Math.max(8, y), maxY),
  };
}

function loadSavedPos(): { x: number; y: number } | null {
  try {
    const raw = localStorage.getItem(POS_STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    if (typeof p?.x === 'number' && typeof p?.y === 'number') return { x: p.x, y: p.y };
  } catch {
    /* ignore */
  }
  return null;
}

function savePos(p: { x: number; y: number }) {
  try {
    localStorage.setItem(POS_STORAGE_KEY, JSON.stringify(p));
  } catch {
    /* ignore */
  }
}

export default function FloatingDigitalHuman({ currentRoute }: { currentRoute?: string }) {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [minimized, setMinimized] = useState(true);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [activated, setActivated] = useState(false);
  const dragRef = useRef({
    startX: 0,
    startY: 0,
    posX: 0,
    posY: 0,
    moved: false,
    pointerId: -1,
  });
  const suppressClickRef = useRef(false);

  const { status, messages, error, answer, wake, sendText, sendContext, minimize, audioRef } = useVoiceChat();

  // Send enriched page context on mount and route change
  useEffect(() => {
    if (currentRoute) {
      const meta = getPageInfo(currentRoute);
      // P2-4: 附带当前页面上报的实时数据（页面自愿上报，未上报则为空字符串）
      const pageData = pageDataToText(getPageData(currentRoute));
      if (meta) {
        sendContext({ route: currentRoute, label: meta.label, group: meta.group, groupLabel: meta.groupLabel, data: pageData });
      } else {
        sendContext({ route: currentRoute, data: pageData });
      }
    }
  }, [currentRoute, sendContext]);

  // Parse and execute UI actions from answers: [ACTION:navigate:/path]
  useEffect(() => {
    if (!answer) return;
    const actionMatch = answer.match(/\[ACTION:(\w+):([^\]]+)\]/);
    if (actionMatch) {
      const [, action, target] = actionMatch;
      if (action === 'navigate' && target.startsWith('/')) {
        navigate(target);
      }
    }
  }, [answer, navigate]);

  const { lastResult, isListening, stopRecognition } = useWakeWord({
    keyword: '小朱',
    onWake: () => {
      setMinimized(false);
      wake();
    },
    enabled: activated && minimized,
  });

  // Default / restore position (bottom-right for icon)
  useEffect(() => {
    const saved = loadSavedPos();
    if (saved) {
      setPosition(clampPos(saved.x, saved.y, ICON_SIZE, ICON_SIZE + 28));
      return;
    }
    setPosition(
      clampPos(
        window.innerWidth - ICON_SIZE - 20,
        window.innerHeight - ICON_SIZE - 20,
        ICON_SIZE,
        ICON_SIZE,
      ),
    );
  }, []);

  // Keep on-screen when viewport resizes
  useEffect(() => {
    const onResize = () => {
      setPosition((p) =>
        clampPos(
          p.x,
          p.y,
          minimized ? ICON_SIZE : collapsed ? 48 : PANEL_WIDTH,
          minimized ? ICON_SIZE : PANEL_HEIGHT_APPROX,
        ),
      );
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [minimized, collapsed]);

  const boxSize = minimized
    ? { w: ICON_SIZE, h: ICON_SIZE }
    : { w: collapsed ? 48 : PANEL_WIDTH, h: collapsed ? 40 : PANEL_HEIGHT_APPROX };

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      // Only primary button / touch
      if (e.button !== 0 && e.pointerType === 'mouse') return;
      e.currentTarget.setPointerCapture?.(e.pointerId);
      setDragging(true);
      dragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        posX: position.x,
        posY: position.y,
        moved: false,
        pointerId: e.pointerId,
      };
      suppressClickRef.current = false;
    },
    [position.x, position.y],
  );

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: PointerEvent) => {
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      if (!dragRef.current.moved && Math.hypot(dx, dy) >= DRAG_THRESHOLD_PX) {
        dragRef.current.moved = true;
        suppressClickRef.current = true;
      }
      if (!dragRef.current.moved) return;
      setPosition(
        clampPos(dragRef.current.posX + dx, dragRef.current.posY + dy, boxSize.w, boxSize.h),
      );
    };
    const onUp = () => {
      setDragging(false);
      setPosition((p) => {
        const next = clampPos(p.x, p.y, boxSize.w, boxSize.h);
        savePos(next);
        return next;
      });
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
    };
  }, [dragging, boxSize.w, boxSize.h]);

  const isActive = status !== 'idle';
  const statusText: Record<ChatStatus, string> = {
    idle: minimized ? '待机中...' : '我在听...',
    wake: '唤醒中...',
    listening: '正在听...',
    thinking: '思考中...',
    speaking: '回答中...',
  };

  // ── Audio amplitude tracking (for mouth sync) ──
  const [audioAmplitude, setAudioAmplitude] = useState(0);
  useEffect(() => {
    if (!audioRef.current) return;
    let audioCtx: AudioContext | null = null;
    let analyser: AnalyserNode | null = null;
    let raf = 0;

    const setup = () => {
      if (!audioRef.current) return;
      audioCtx = new AudioContext();
      const source = audioCtx.createMediaElementSource(audioRef.current);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      source.connect(analyser);
      analyser.connect(audioCtx.destination);

      const data = new Uint8Array(analyser.frequencyBinCount);
      let frameSkip = 0;
      const loop = () => {
        if (!analyser) return;
        frameSkip++;
        analyser.getByteTimeDomainData(data);
        // Update React state at ~20fps (skip 2 of every 3 rAF frames)
        if (frameSkip % 3 === 0) {
          let sum = 0;
          for (let i = 0; i < data.length; i++) {
            sum += Math.abs(data[i] - 128);
          }
          setAudioAmplitude(sum / data.length / 128);
        }
        raf = requestAnimationFrame(loop);
      };
      loop();
    };

    audioRef.current.addEventListener('play', setup, { once: true });
    return () => {
      cancelAnimationFrame(raf);
      audioCtx?.close();
    };
  }, [status]);

  // ── Minimized: circle avatar (draggable) ──
  if (minimized) {
    const handleActivate = () => {
      if (suppressClickRef.current) {
        suppressClickRef.current = false;
        return;
      }
      if (!activated) {
        setActivated(true);
        // useWakeWord useEffect will auto-start recognition when enabled flips to true
      } else {
        setMinimized(false);
      }
    };

    return (
      <div
        style={{
          position: 'fixed',
          left: position.x,
          top: position.y,
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 6,
          touchAction: 'none',
        }}
      >
        {!activated && (
          <div
            style={{
              position: 'absolute',
              bottom: '100%',
              marginBottom: 6,
              background: 'rgba(22,27,34,0.9)',
              color: '#9CA3AF',
              padding: '4px 10px',
              borderRadius: 8,
              fontSize: 11,
              whiteSpace: 'nowrap',
              pointerEvents: 'none',
            }}
          >
            拖动可移动 · 点击唤醒小朱
          </div>
        )}
        <div
          onPointerDown={onPointerDown}
          onClick={handleActivate}
          title="拖动移动位置；点击唤醒"
          style={{
            width: ICON_SIZE,
            height: ICON_SIZE,
            borderRadius: '50%',
            border: '2px solid',
            borderColor: isListening ? '#10B981' : activated ? 'rgba(59,130,246,0.4)' : 'rgba(75,85,99,0.3)',
            boxShadow: isListening
              ? '0 4px 24px rgba(16,185,129,0.3)'
              : activated
                ? '0 4px 24px rgba(59,130,246,0.2)'
                : '0 4px 24px rgba(0,0,0,0.2)',
            cursor: dragging ? 'grabbing' : 'grab',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
            position: 'relative',
            transition: dragging ? 'none' : 'transform 0.2s, box-shadow 0.2s, border-color 0.2s',
            userSelect: 'none',
          }}
          onMouseEnter={(e) => {
            if (!dragging) e.currentTarget.style.transform = 'scale(1.08)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'scale(1.0)';
          }}
        >
          <img
            src="/avatar-lorelei.svg"
            alt="小朱"
            draggable={false}
            style={{ width: 52, height: 52, borderRadius: '50%', objectFit: 'cover', pointerEvents: 'none' }}
          />
          {isListening && (
            <div
              style={{
                position: 'absolute',
                top: -3,
                right: -3,
                width: 12,
                height: 12,
                borderRadius: '50%',
                background: '#10B981',
                border: '2px solid #0D1117',
              }}
            />
          )}
        </div>
      </div>
    );
  }

  // ── Expanded: floating card ──
  return (
    <div
      style={{
        position: 'fixed',
        zIndex: 9999,
        left: position.x,
        top: position.y,
        width: collapsed ? 48 : PANEL_WIDTH,
        transition: collapsed && !dragging ? 'width 0.3s' : 'none',
        background: 'rgba(22,27,34,0.95)',
        backdropFilter: 'blur(12px)',
        border: `1px solid ${isActive ? 'rgba(59,130,246,0.5)' : 'rgba(48,54,61,0.8)'}`,
        borderRadius: 16,
        boxShadow: isActive
          ? '0 8px 40px rgba(59,130,246,0.25)'
          : '0 4px 20px rgba(0,0,0,0.3)',
        overflow: 'hidden',
        userSelect: 'none',
        touchAction: 'none',
      }}
    >
      {/* Header bar — drag handle */}
      <div
        onPointerDown={onPointerDown}
        style={{
          height: 40,
          padding: '0 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'rgba(59,130,246,0.08)',
          borderBottom: '1px solid rgba(48,54,61,0.5)',
          cursor: dragging ? 'grabbing' : 'grab',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div
            style={{
              width: 24,
              height: 24,
              borderRadius: '50%',
              background: 'radial-gradient(circle at 30% 30%, #3B82F6, #1D4ED8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 14,
              lineHeight: 1,
            }}
          >
            <img
              src="/avatar-lorelei.svg"
              alt="小朱"
              draggable={false}
              style={{ width: 24, height: 24, borderRadius: '50%', objectFit: 'cover' }}
            />
          </div>
          {!collapsed && (
            <span style={{ fontSize: 13, fontWeight: 600, color: '#E5E7EB' }}>小朱</span>
          )}
          {!collapsed && isActive && (
            <span
              style={{
                fontSize: 10,
                color: '#60A5FA',
                background: 'rgba(59,130,246,0.15)',
                borderRadius: 4,
                padding: '1px 6px',
              }}
            >
              {statusText[status]}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          <button
            onClick={() => setMinimized(true)}
            style={{ background: 'none', border: 'none', color: '#6B7280', cursor: 'pointer', padding: 4 }}
            title="最小化"
          >
            <Minimize2 size={14} />
          </button>
          <button
            onClick={() => setCollapsed(!collapsed)}
            style={{ background: 'none', border: 'none', color: '#6B7280', cursor: 'pointer', padding: 4 }}
            title={collapsed ? '展开' : '折叠'}
          >
            {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Avatar */}
      {!collapsed && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            padding: '16px 0 8px',
          }}
        >
          <AnimatedAvatar state={status} audioAmplitude={audioAmplitude} size={120} />
        </div>
      )}

      {!collapsed && (
        <>
          {/* Answer display */}
          {answer && (
            <div
              style={{
                margin: '8px 12px 0',
                padding: '8px 12px',
                background: 'rgba(59,130,246,0.08)',
                border: '1px solid rgba(59,130,246,0.2)',
                borderRadius: 10,
                fontSize: 13,
                color: '#D1D5DB',
                lineHeight: 1.5,
                maxHeight: 120,
                overflowY: 'auto',
              }}
            >
              {answer}
            </div>
          )}

          {/* Messages history */}
          {messages.length > 0 && !answer && (
            <div
              style={{
                margin: '8px 12px 0',
                maxHeight: 150,
                overflowY: 'auto',
              }}
            >
              {messages.slice(-3).map((m, i) => (
                <div
                  key={i}
                  style={{
                    padding: '6px 10px',
                    marginBottom: 4,
                    borderRadius: 8,
                    fontSize: 12,
                    lineHeight: 1.4,
                    background: m.role === 'user' ? 'rgba(59,130,246,0.1)' : 'rgba(75,85,99,0.1)',
                    color: m.role === 'user' ? '#93C5FD' : '#D1D5DB',
                  }}
                >
                  {m.role === 'user' ? '👤 ' : '🤖 '}
                  {m.text}
                </div>
              ))}
            </div>
          )}

          {/* Status bar */}
          {isActive && (
            <div
              style={{
                margin: '8px 12px',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 12,
                color: '#9CA3AF',
              }}
            >
              {status === 'thinking' && <Loader2 size={14} className="animate-spin" />}
              <span>{statusText[status]}</span>
              {lastResult && <span style={{ fontSize: 10, opacity: 0.6 }}>听到: {lastResult}</span>}
            </div>
          )}

          {/* Controls */}
          <div
            style={{
              padding: '8px 12px 12px',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              borderTop: '1px solid rgba(48,54,61,0.3)',
            }}
          >
            <button
              onClick={() => {
                wake();
              }}
              disabled={status === 'thinking' || status === 'speaking'}
              style={{
                width: 40,
                height: 40,
                borderRadius: '50%',
                border: '2px solid',
                borderColor: status === 'listening' ? '#EF4444' : isListening ? '#10B981' : '#3B82F6',
                background: status === 'listening' ? 'rgba(239,68,68,0.1)' : 'rgba(59,130,246,0.1)',
                cursor: status === 'thinking' || status === 'speaking' ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: status === 'thinking' || status === 'speaking' ? 0.5 : 1,
              }}
              title="点击说话"
            >
              <Mic size={18} color={status === 'listening' ? '#EF4444' : '#3B82F6'} />
            </button>

            <input
              type="text"
              placeholder="输入文字..."
              style={{
                flex: 1,
                height: 36,
                padding: '0 10px',
                background: 'rgba(48,54,61,0.5)',
                border: '1px solid rgba(48,54,61,0.8)',
                borderRadius: 8,
                fontSize: 13,
                color: '#E5E7EB',
                outline: 'none',
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  sendText((e.target as HTMLInputElement).value);
                  (e.target as HTMLInputElement).value = '';
                }
              }}
            />
          </div>
        </>
      )}

      {error && (
        <div
          style={{
            margin: '0 12px 8px',
            padding: '6px 10px',
            background: 'rgba(239,68,68,0.1)',
            borderRadius: 8,
            fontSize: 11,
            color: '#FCA5A5',
          }}
        >
          {error}
        </div>
      )}

      <audio ref={audioRef} style={{ display: 'none' }} />
    </div>
  );
}
