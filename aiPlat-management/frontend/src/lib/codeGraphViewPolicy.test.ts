import { describe, expect, it } from 'vitest';
import {
  CODE_GRAPH_EGO_NODE_CAP,
  capEgoNodes,
  codeGraphEdgeOpacity,
  codeGraphLabelOption,
} from './codeGraphViewPolicy';

describe('codeGraphViewPolicy', () => {
  it('caps ego neighborhood preferring center + high degree', () => {
    const nodes = Array.from({ length: 120 }, (_, i) => ({
      id: `f${i}`,
      degree: i,
    }));
    const capped = capEgoNodes(nodes, 'f5', 20);
    expect(capped.length).toBe(20);
    expect(capped.some((n) => n.id === 'f5')).toBe(true);
    expect(capped[0].id).toBe('f5');
  });

  it('default ego cap is 80', () => {
    expect(CODE_GRAPH_EGO_NODE_CAP).toBe(80);
  });

  it('hides labels unless forceShow', () => {
    expect(codeGraphLabelOption(false).show).toBe(false);
    expect(codeGraphLabelOption(true).show).toBe(true);
  });

  it('reduces edge opacity as density grows', () => {
    expect(codeGraphEdgeOpacity(10)).toBeGreaterThan(codeGraphEdgeOpacity(300));
    expect(codeGraphEdgeOpacity(300)).toBeGreaterThan(codeGraphEdgeOpacity(900));
  });
});
