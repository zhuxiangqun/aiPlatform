/**
 * Shared readability policy for code / system graph force layouts.
 * Understanding-first: no full-label hairball by default.
 */

/** Hard cap on nodes drawn in ego / explore neighborhood. */
export const CODE_GRAPH_EGO_NODE_CAP = 80;

/** Default explore depth (hops from center). */
export const CODE_GRAPH_DEFAULT_DEPTH = 1;

/** Edge line opacity by link count (neighborhood-only graphs). */
export function codeGraphEdgeOpacity(edgeCount: number): number {
  if (edgeCount > 1200) return 0.05;
  if (edgeCount > 600) return 0.08;
  if (edgeCount > 200) return 0.12;
  return 0.2;
}

/**
 * ECharts graph label options: hide by default; show on emphasis (hover/select).
 * Pass forceShow=true only for expert “show all labels” toggle.
 */
export function codeGraphLabelOption(forceShow = false): {
  show: boolean;
  position: string;
  fontSize: number;
  color: string;
  formatter?: (p: any) => string;
} {
  return {
    show: forceShow,
    position: 'right',
    fontSize: 10,
    color: 'rgba(255,255,255,0.75)',
    formatter: (p: any) => String(p?.data?.name || p?.name || ''),
  };
}

export function codeGraphEmphasisLabel(): { focus: string; label: { show: boolean }; lineStyle: { width: number; opacity: number } } {
  return {
    focus: 'adjacency',
    label: { show: true },
    lineStyle: { width: 2, opacity: 0.9 },
  };
}

/** Keep center + neighbors; hard-cap total nodes (prefer higher degree). */
export function capEgoNodes<T extends { id?: string; path?: string; degree?: number; value?: { degree?: number } }>(
  nodes: T[],
  centerId: string,
  cap = CODE_GRAPH_EGO_NODE_CAP,
): T[] {
  if (nodes.length <= cap) return nodes;
  const center = (centerId || '').trim();
  const scored = nodes.map((n) => {
    const id = String(n.path || n.id || '');
    const deg = Number(n.degree ?? n.value?.degree ?? 0);
    // Exact / path-suffix / basename only — avoid substring false positives (f5 ⊂ f59).
    const base = id.split('/').pop() || id;
    const centerBase = center.split('/').pop() || center;
    const isCenter =
      Boolean(center) &&
      (id === center ||
        id.endsWith('/' + center) ||
        base === center ||
        base === centerBase ||
        id.endsWith(center));
    return { n, id, deg, isCenter };
  });
  scored.sort((a, b) => {
    if (a.isCenter !== b.isCenter) return a.isCenter ? -1 : 1;
    return b.deg - a.deg;
  });
  return scored.slice(0, cap).map((x) => x.n);
}
