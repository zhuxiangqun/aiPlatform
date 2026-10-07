import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Minimize2, ChevronUp, ChevronDown, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useVoiceChat, ChatStatus } from '../../hooks/useVoiceChat';
import { getPageInfo } from '../../pageManifest';
import { consultantPagePayload, subscribePageData } from '../../lib/pageDataBridge';
import AnimatedAvatar from './AnimatedAvatar';

const POS_STORAGE_KEY = 'aiplat.digital_human.pos';
const ICON_SIZE = 56;
const PANEL_WIDTH = 320;
const PANEL_HEIGHT_APPROX = 420;
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
  const dragRef = useRef({
    startX: 0,
    startY: 0,
    posX: 0,
    posY: 0,
    moved: false,
    pointerId: -1,
  });
  const suppressClickRef = useRef(false);

  const {
    status,
    messages,
    error,
    answer,
    modelName,
    modelPurpose,
    sendText,
    sendContext,
    sendFeedback,
    audioRef,
  } = useVoiceChat({
    textOnly: true,
  });
  const [ratedLast, setRatedLast] = useState<'good' | 'bad' | ''>('');

  useEffect(() => {
    setRatedLast('');
  }, [answer]);

  useEffect(() => {
    const send = () => {
      if (!currentRoute) return;
      const meta = getPageInfo(currentRoute);
      const pageData = consultantPagePayload(currentRoute);
      if (meta) {
        sendContext({
          route: currentRoute,
          label: meta.label,
          group: meta.group,
          groupLabel: meta.groupLabel,
          purpose: meta.purpose,
          data: pageData,
        });
      } else {
        sendContext({ route: currentRoute, data: pageData });
      }
    };
    send();
    return subscribePageData(send);
  }, [currentRoute, sendContext]);

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

  /** Hide machine ACTION markers from chat bubbles; navigate still runs above. */
  const displayText = (text: string) =>
    (text || '').replace(/\s*\[ACTION:\w+:[^\]]+\]\s*/g, '\n').trim();

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

  const isActive = status === 'thinking';
  const statusText: Record<ChatStatus, string> = {
    idle: '文字咨询',
    wake: '连接中...',
    listening: '输入中...',
    thinking: '思考中...',
    speaking: '回答中...',
  };

  if (minimized) {
    const handleActivate = () => {
      if (suppressClickRef.current) {
        suppressClickRef.current = false;
        return;
      }
      setMinimized(false);
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
          拖动可移动 · 点击打开小朱（文字咨询）
        </div>
        <div
          onPointerDown={onPointerDown}
          onClick={handleActivate}
          title="拖动移动位置；点击打开文字咨询"
          style={{
            width: ICON_SIZE,
            height: ICON_SIZE,
            borderRadius: '50%',
            border: '2px solid rgba(59,130,246,0.4)',
            boxShadow: '0 4px 24px rgba(59,130,246,0.2)',
            cursor: dragging ? 'grabbing' : 'grab',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
            position: 'relative',
            transition: dragging ? 'none' : 'transform 0.2s, box-shadow 0.2s',
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
        </div>
      </div>
    );
  }

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
      }}
    >
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
          userSelect: 'none',
          touchAction: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <img
            src="/avatar-lorelei.svg"
            alt="小朱"
            draggable={false}
            style={{ width: 24, height: 24, borderRadius: '50%', objectFit: 'cover' }}
          />
          {!collapsed && (
            <span style={{ fontSize: 13, fontWeight: 600, color: '#E5E7EB' }}>小朱</span>
          )}
          {!collapsed && (
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
          {!collapsed && modelName && (
            <span
              title={modelPurpose ? `${modelName} · ${modelPurpose}` : modelName}
              style={{
                fontSize: 10,
                color: '#9CA3AF',
                maxWidth: 168,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {modelPurpose ? `${modelName} · ${modelPurpose}` : modelName}
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

      {!collapsed && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 4px' }}>
          <AnimatedAvatar state={status === 'thinking' ? 'thinking' : 'idle'} audioAmplitude={0} size={96} />
        </div>
      )}

      {!collapsed && (
        <>
          {(messages.length > 0 || answer) && (
            <div style={{ margin: '8px 12px 0', maxHeight: 220, overflowY: 'auto' }}>
              {(messages.length > 0 ? messages.slice(-8) : [{ role: 'assistant' as const, text: answer }]).map((m, i, arr) => {
                const isLastAssistant = m.role === 'assistant' && i === arr.length - 1;
                return (
                  <div
                    key={i}
                    style={{
                      padding: '6px 10px',
                      marginBottom: 4,
                      borderRadius: 8,
                      fontSize: 12,
                      lineHeight: 1.4,
                      background: m.role === 'user' ? 'rgba(59,130,246,0.1)' : 'rgba(59,130,246,0.08)',
                      border: m.role === 'assistant' ? '1px solid rgba(59,130,246,0.2)' : 'none',
                      color: m.role === 'user' ? '#93C5FD' : '#D1D5DB',
                      whiteSpace: 'pre-wrap',
                      userSelect: 'text',
                      WebkitUserSelect: 'text',
                      cursor: 'text',
                    }}
                  >
                    {m.role === 'user' ? '你：' : '小朱：'}
                    {m.role === 'assistant' ? displayText(m.text) : m.text}
                    {isLastAssistant && status === 'idle' && (
                      <div style={{ marginTop: 6, display: 'flex', gap: 8, alignItems: 'center' }}>
                        <button
                          type="button"
                          disabled={!!ratedLast}
                          onClick={() => {
                            void sendFeedback('good').then((ok) => {
                              if (ok) setRatedLast('good');
                            });
                          }}
                          style={{
                            fontSize: 11,
                            padding: '2px 8px',
                            borderRadius: 6,
                            border: '1px solid rgba(52,211,153,0.35)',
                            background: ratedLast === 'good' ? 'rgba(52,211,153,0.2)' : 'transparent',
                            color: '#6EE7B7',
                            cursor: ratedLast ? 'default' : 'pointer',
                          }}
                          title="答得有用，记入策展样本"
                        >
                          有用
                        </button>
                        <button
                          type="button"
                          disabled={!!ratedLast}
                          onClick={() => {
                            void sendFeedback('bad').then((ok) => {
                              if (ok) setRatedLast('bad');
                            });
                          }}
                          style={{
                            fontSize: 11,
                            padding: '2px 8px',
                            borderRadius: 6,
                            border: '1px solid rgba(248,113,113,0.35)',
                            background: ratedLast === 'bad' ? 'rgba(248,113,113,0.2)' : 'transparent',
                            color: '#FCA5A5',
                            cursor: ratedLast ? 'default' : 'pointer',
                          }}
                          title="答得不对；可再打字「不对，应该是…」写入金标"
                        >
                          不对
                        </button>
                        {ratedLast === 'good' && (
                          <span style={{ fontSize: 10, color: '#6B7280' }}>已记入策展</span>
                        )}
                        {ratedLast === 'bad' && (
                          <span style={{ fontSize: 10, color: '#6B7280' }}>可打字纠正</span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

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
              <Loader2 size={14} className="animate-spin" />
              <span>{statusText[status]}</span>
            </div>
          )}

          <div
            style={{
              padding: '8px 12px 12px',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              borderTop: '1px solid rgba(48,54,61,0.3)',
            }}
          >
            <input
              type="text"
              placeholder="问平台怎么建、这个页面怎么用…"
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
              disabled={status === 'thinking'}
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
