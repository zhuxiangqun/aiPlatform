/**
 * Animation State Machine for Digital Human.
 *
 * States:
 *   IDLE      → 呼吸动画 + 随机眨眼 + 微晃
 *   WAKE      → 抬头 + 眼睛注视 + 缩放弹入
 *   LISTENING → 前倾 + 点头 + 外圈脉冲
 *   THINKING  → 歪头 + 眼睛扫视 + 加载动画
 *   SPEAKING  → 口型开合 + 手势配合
 *
 * Transitions:
 *   IDLE → WAKE (onWake)
 *   WAKE → LISTENING (after 500ms)
 *   LISTENING → THINKING (onSend)
 *   THINKING → SPEAKING (onAnswer)
 *   SPEAKING → IDLE (onDone)
 */
export type AnimState = 'idle' | 'wake' | 'listening' | 'thinking' | 'speaking';

export interface AnimConfig {
  /** Breathing: scale oscillation range [min, max] */
  breathRange: [number, number];
  /** Blink: interval range [min, max] in ms */
  blinkInterval: [number, number];
  /** Blink: duration in ms */
  blinkDuration: number;
  /** Head tilt: degrees when thinking */
  headTilt: number;
  /** Nod: frequency in Hz when listening */
  nodFreq: number;
  /** Mouth openness: range [0, 1] when speaking */
  mouthRange: [number, number];
  /** Pulse: ring opacity oscillation when listening */
  pulseOpacity: [number, number];
}

export const DEFAULT_ANIM_CONFIG: AnimConfig = {
  breathRange: [0.97, 1.03],
  blinkInterval: [3000, 8000],
  blinkDuration: 150,
  headTilt: 15,
  nodFreq: 0.5,
  mouthRange: [0, 0.6],
  pulseOpacity: [0.3, 0.8],
};

/**
 * Derive CSS classes and inline style properties for each animation state.
 * Returns an object of style overrides to apply to the avatar container.
 */
export function getAnimStyles(
  state: AnimState,
  timestamp: number,
  config: AnimConfig = DEFAULT_ANIM_CONFIG,
): Record<string, string | number> {
  const t = timestamp / 1000;
  const styles: Record<string, string | number> = {};

  switch (state) {
    case 'idle': {
      // Breathing (sinusoidal scale)
      const cycle = (t % 4) / 4; // 4-second cycle
      const breath = config.breathRange[0] +
        (config.breathRange[1] - config.breathRange[0]) *
        (Math.sin(cycle * Math.PI * 2) * 0.5 + 0.5);
      styles.transform = `scale(${breath.toFixed(3)})`;
      // Float
      styles.translate = `0 ${Math.sin(t * 0.8) * 3}px`;
      // Blink: check if in blink window
      const blinkPhase = Math.floor(t * 1000 / config.blinkInterval[0]);
      const inBlink = (t * 1000) % config.blinkInterval[0] < config.blinkDuration;
      styles['--eye-scale'] = inBlink ? '0.05 1' : '1 1';
      break;
    }
    case 'wake': {
      // Scale up from idle
      const elapsed = (t * 1000) % 500;
      const scale = 0.98 + Math.min(elapsed / 500, 1) * 0.06;
      styles.transform = `scale(${scale.toFixed(3)})`;
      styles.translate = `0 0px`;
      styles['--eye-scale'] = '1 1';
      break;
    }
    case 'listening': {
      // Slight forward lean + nodding
      styles.transform = `scale(1.02)`;
      styles.translate = `0 ${Math.sin(t * config.nodFreq * Math.PI * 2) * 2}px`;
      styles['--eye-scale'] = '1.05 1.05';
      // Pulse ring opacity
      const pulse = config.pulseOpacity[0] +
        (config.pulseOpacity[1] - config.pulseOpacity[0]) *
        (Math.sin(t * 2 * Math.PI) * 0.5 + 0.5);
      styles['--pulse-opacity'] = pulse.toFixed(2);
      break;
    }
    case 'thinking': {
      // Head tilt + eye scan
      const tilt = Math.sin(t * 0.7) * config.headTilt;
      styles.transform = `scale(1.01) rotate(${tilt.toFixed(1)}deg)`;
      styles['--eye-offset'] = `${Math.sin(t * 1.3) * 3}px`;
      styles['--pulse-opacity'] = '0.8';
      break;
    }
    case 'speaking': {
      // Mouth opens based on audio amplitude (driven externally via --mouth-open)
      styles.transform = 'scale(1.02)';
      styles['--eye-scale'] = '1 1';
      styles['--pulse-opacity'] = '0.6';
      break;
    }
  }

  return styles;
}
