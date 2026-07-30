import React, { useEffect, useRef, useState } from 'react';
import { AnimState, AnimConfig, DEFAULT_ANIM_CONFIG } from './AnimationFSM';

interface AnimatedAvatarProps {
  state: AnimState;
  audioAmplitude?: number;
  config?: AnimConfig;
  size?: number;
}

/**
 * Human-style avatar with life-like CSS animations.
 * Uses DiceBear Lorelei style by default — free, no API key, SVG-based.
 * Replace with a custom image by changing the `src` prop in FloatingDigitalHuman.
 */
export default function AnimatedAvatar({
  state,
  audioAmplitude = 0,
  config = DEFAULT_ANIM_CONFIG,
  size = 200,
}: AnimatedAvatarProps) {
  const [timestamp, setTimestamp] = useState(Date.now());
  const [blink, setBlink] = useState(false);
  const rafRef = useRef<number>(0);
  const blinkRef = useRef<any>(null);
  const avatarSize = size * 0.65;

  // 60fps animation loop
  useEffect(() => {
    const loop = () => {
      setTimestamp(Date.now());
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // Random blink timer
  useEffect(() => {
    const schedule = () => {
      const [min, max] = config.blinkInterval;
      blinkRef.current = setTimeout(() => {
        setBlink(true);
        setTimeout(() => setBlink(false), config.blinkDuration);
        schedule();
      }, Math.random() * (max - min) + min);
    };
    schedule();
    return () => clearTimeout(blinkRef.current);
  }, [config]);

  const t = timestamp / 1000;
  const isActive = state !== 'idle';

  // Breathing (idle)
  const breathScale = 1 + Math.sin(t * 0.6) * 0.015;

  // Head tilt (thinking)
  const headTilt = state === 'thinking'
    ? Math.sin(t * 0.7) * 6
    : 0;

  // Nodding (listening)
  const nodY = state === 'listening'
    ? Math.sin(t * config.nodFreq * Math.PI * 2) * 1.5
    : 0;

  // Mouth open (speaking)
  const mouthScale = state === 'speaking'
    ? 0.95 + audioAmplitude * 0.1
    : 1;

  // Float up/down
  const floatY = Math.sin(t * 0.8) * 2;

  return (
    <div
      style={{
        width: size,
        height: size,
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transform: `translateY(${floatY + nodY}px) rotate(${headTilt}deg)`,
        transition: state === 'wake' ? 'transform 0.3s ease-out' : 'transform 0.05s linear',
      }}
    >
      {/* Pulse ring when active */}
      {isActive && (
        <div
          style={{
            position: 'absolute',
            inset: -6,
            borderRadius: '50%',
            border: '2px solid rgba(59,130,246,0.3)',
            opacity: 0.5 + Math.sin(t * 2) * 0.3,
            animation: 'pulse-ring 2s ease-in-out infinite',
          }}
        />
      )}

      {/* Avatar image */}
      <div
        style={{
          width: avatarSize,
          height: avatarSize,
          borderRadius: '50%',
          overflow: 'hidden',
          border: '3px solid rgba(59,130,246,0.3)',
          boxShadow: isActive
            ? '0 4px 24px rgba(59,130,246,0.3)'
            : '0 2px 12px rgba(0,0,0,0.15)',
          transform: `scale(${breathScale})`,
          background: '#f0f4ff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <img
          src="/avatar-lorelei.svg"
          alt="小朱"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: `scale(${mouthScale})`,
          }}
          draggable={false}
        />
      </div>

      {/* Blink overlay */}
      {blink && state === 'idle' && (
        <div
          style={{
            position: 'absolute',
            top: '40%',
            left: '25%',
            right: '25%',
            height: 3,
            background: '#333',
            borderRadius: 2,
            zIndex: 2,
          }}
        />
      )}

      <style>{`
        @keyframes pulse-ring {
          0%, 100% { transform: scale(1); opacity: 0.3; }
          50% { transform: scale(1.06); opacity: 0.7; }
        }
      `}</style>
    </div>
  );
}
