/**
 * Shared platform HTTP helpers for hybrid enterprise bridges.
 *
 * - URL normalize (+ optional AIPLAT_PLATFORM_BASE_PATH, skips port guessing)
 * - Per-origin circuit breaker (skip fetch while open to avoid timeout pile-up)
 */

export type CircuitState = "closed" | "open" | "half_open";

export type CircuitSnapshot = {
  origin: string;
  state: CircuitState;
  consecutiveFailures: number;
  openedAt: number;
  cooldownMs: number;
  failureThreshold: number;
};

function envInt(name: string, fallback: number): number {
  const raw = (process.env[name] || "").trim();
  if (!raw) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

function envCircuitEnabled(): boolean {
  const v = (process.env.AIPLAT_PLATFORM_CIRCUIT || "").trim().toLowerCase();
  if (v === "0" || v === "false" || v === "off" || v === "no") return false;
  return true;
}

function originKey(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return "default";
  }
}

export class PlatformCircuitBreaker {
  state: CircuitState = "closed";
  consecutiveFailures = 0;
  openedAt = 0;
  /** Half-open allows a single in-flight probe. */
  probeInFlight = false;
  readonly failureThreshold: number;
  readonly cooldownMs: number;
  readonly origin: string;

  constructor(origin: string, opts?: { failureThreshold?: number; cooldownMs?: number }) {
    this.origin = origin;
    this.failureThreshold = opts?.failureThreshold ?? envInt("AIPLAT_PLATFORM_CIRCUIT_FAILURES", 3);
    this.cooldownMs = opts?.cooldownMs ?? envInt("AIPLAT_PLATFORM_CIRCUIT_COOLDOWN_MS", 30_000);
  }

  snapshot(): CircuitSnapshot {
    return {
      origin: this.origin,
      state: this.state,
      consecutiveFailures: this.consecutiveFailures,
      openedAt: this.openedAt,
      cooldownMs: this.cooldownMs,
      failureThreshold: this.failureThreshold,
    };
  }

  /** Whether a new request may proceed. */
  allow(now = Date.now()): boolean {
    if (!envCircuitEnabled()) return true;
    if (this.state === "closed") return true;
    if (this.state === "open") {
      if (now - this.openedAt < this.cooldownMs) return false;
      this.state = "half_open";
      this.probeInFlight = false;
    }
    if (this.state === "half_open") {
      if (this.probeInFlight) return false;
      this.probeInFlight = true;
      return true;
    }
    return true;
  }

  recordSuccess(): void {
    if (!envCircuitEnabled()) return;
    this.consecutiveFailures = 0;
    this.state = "closed";
    this.openedAt = 0;
    this.probeInFlight = false;
  }

  recordFailure(now = Date.now()): void {
    if (!envCircuitEnabled()) return;
    this.probeInFlight = false;
    this.consecutiveFailures += 1;
    if (
      this.state === "half_open" ||
      this.consecutiveFailures >= this.failureThreshold
    ) {
      this.state = "open";
      this.openedAt = now;
    }
  }
}

const _breakers = new Map<string, PlatformCircuitBreaker>();

/** Test helper: clear all breakers. */
export function resetPlatformCircuits(): void {
  _breakers.clear();
}

export function getPlatformCircuit(urlOrOrigin: string): PlatformCircuitBreaker {
  const key = originKey(urlOrOrigin);
  let b = _breakers.get(key);
  if (!b) {
    b = new PlatformCircuitBreaker(key);
    _breakers.set(key, b);
  }
  return b;
}

export class CircuitOpenError extends Error {
  readonly circuit: CircuitSnapshot;
  constructor(snap: CircuitSnapshot) {
    const left = Math.max(0, snap.cooldownMs - (Date.now() - snap.openedAt));
    super(
      `platform_circuit_open origin=${snap.origin} retry_in_ms≈${left}`,
    );
    this.name = "CircuitOpenError";
    this.circuit = snap;
  }
}

/**
 * Normalize AIPLAT_PLATFORM_URL so joining `/platform/*` hits the real mount.
 *
 * When ``AIPLAT_PLATFORM_BASE_PATH`` is set (e.g. `/api`), apply it when the URL
 * path is bare `/` — port heuristics are skipped for mount selection.
 *
 * Legacy heuristics (when BASE_PATH unset):
 * - Platform (:8003) serves `/platform/...` (NOT `/api/platform/...`)
 * - Management GW (:8000) serves `/api/platform/...`
 * - Footgun: `http://host:8003/api` → strip `/api`
 */
export function normalizePlatformBaseUrl(raw: string): string {
  const b = String(raw || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  const explicit = (process.env.AIPLAT_PLATFORM_BASE_PATH || "").trim();
  try {
    const u = new URL(b);
    const path = (u.pathname || "/").replace(/\/+$/, "") || "/";

    if (explicit) {
      let want = explicit.startsWith("/") ? explicit : `/${explicit}`;
      want = want.replace(/\/+$/, "") || "/";
      // Only stamp when URL has no meaningful path yet
      if (path === "/" || path === "") {
        u.pathname = want === "/" ? "/" : want;
        return u.toString().replace(/\/+$/, "");
      }
      return u.toString().replace(/\/+$/, "");
    }

    if (u.port === "8003" && (path === "/api" || path.startsWith("/api/"))) {
      if (path === "/api") {
        u.pathname = "/";
      } else if (path.startsWith("/api/platform")) {
        u.pathname = path.slice("/api".length) || "/";
      } else {
        u.pathname = path.slice("/api".length) || "/";
      }
      return u.toString().replace(/\/+$/, "");
    }
    if (u.port === "8000" && path === "/") {
      u.pathname = "/api";
      return u.toString().replace(/\/+$/, "");
    }
  } catch {
    /* keep raw */
  }
  return b;
}

/**
 * fetch with per-origin circuit breaker. Throws CircuitOpenError when open;
 * records network/5xx as failures, 2xx/3xx/4xx as success (4xx = app up).
 */
export async function platformFetch(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const circuit = getPlatformCircuit(url);
  if (!circuit.allow()) {
    throw new CircuitOpenError(circuit.snapshot());
  }
  try {
    const res = await fetch(url, init);
    if (res.status >= 500) {
      circuit.recordFailure();
    } else {
      circuit.recordSuccess();
    }
    return res;
  } catch (e) {
    if (e instanceof CircuitOpenError) throw e;
    circuit.recordFailure();
    throw e;
  }
}
