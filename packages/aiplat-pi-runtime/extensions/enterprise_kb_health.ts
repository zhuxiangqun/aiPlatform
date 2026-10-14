/**
 * Pi slash `/aiplat-kb-health` — customer-facing KB health summary via platform
 * GET /platform/delivery/kb-health (HYBRID_ENTERPRISE_KB_HEALTH §4.3).
 *
 * Soft-fails when enterprise off or platform unreachable.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { CircuitOpenError, normalizePlatformBaseUrl, platformFetch } from "./enterprise_http";
import {
  loadEnterpriseConfig,
  type EnterpriseConfig,
} from "./enterprise_kb";

function joinPlatform(base: string, path: string): string {
  const b = normalizePlatformBaseUrl(base).replace(/\/+$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  // GW base ends with /api → /api/platform/...
  if (b.endsWith("/api")) {
    return `${b}${p.startsWith("/platform") ? p : `/platform${p}`}`;
  }
  return `${b}${p.startsWith("/platform") ? p : `/platform${p}`}`;
}

export async function fetchKbHealthSummary(
  cfg?: EnterpriseConfig,
): Promise<{ ok: boolean; text: string }> {
  const c = cfg || loadEnterpriseConfig();
  if (!c.enabled) {
    return {
      ok: false,
      text: "知识库健康面板暂不可用（未启用企业回连：AIPLAT_ENTERPRISE=1）",
    };
  }
  if (!c.baseUrl || !c.token) {
    return { ok: false, text: "知识库健康面板暂不可用（缺少 PLATFORM_URL / token）" };
  }
  const url = new URL(joinPlatform(c.baseUrl, "/platform/delivery/kb-health"));
  url.searchParams.set("collection_id", c.collectionId || "default");
  url.searchParams.set("window_hours", "168");
  url.searchParams.set("format", "json");
  try {
    const res = await platformFetch(url.toString(), {
      headers: {
        authorization: `Bearer ${c.token}`,
        accept: "application/json",
      },
    });
    const text = await res.text();
    if (!res.ok) {
      return {
        ok: false,
        text: `知识库健康面板暂不可用（http=${res.status}）`,
      };
    }
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(text) as Record<string, unknown>;
    } catch {
      return { ok: false, text: "知识库健康面板暂不可用（响应非 JSON）" };
    }
    const health = (parsed.health || {}) as Record<string, unknown>;
    const metrics = (parsed.metrics || {}) as Record<string, unknown>;
    const stats = (parsed.stats || {}) as Record<string, unknown>;
    const week = (parsed.docs_this_week || {}) as Record<string, unknown>;
    const tips = Array.isArray(parsed.suggestions)
      ? (parsed.suggestions as string[])
      : [];
    const insufficient = Boolean(health.insufficient_data) || health.score == null;
    const scoreLine = insufficient
      ? `知识库健康分: —/100（${health.label ?? "数据不足"}）`
      : `知识库健康分: ${health.score}/100（${health.label ?? "-"}）`;
    const rateLine = insufficient
      ? "漏召/引用比率: n/a（无检索流量）"
      : `漏召率 ${metrics.no_answer_rate_pct ?? "n/a"}% | 引用覆盖率 ${metrics.citation_coverage_pct ?? "n/a"}%`;
    const lines = [
      scoreLine,
      `本周查询 ${metrics.total_queries ?? "n/a"} 次 | 文档 ${stats.documents ?? "n/a"} 篇 | 新增 ${week.count ?? "n/a"} 篇`,
      rateLine,
      "",
      `建议: ${tips[0] || "维持当前入库节奏"}`,
    ];
    return { ok: true, text: lines.join("\n") };
  } catch (e) {
    return {
      ok: false,
      text: `知识库健康面板暂不可用（${e && (e as Error).message ? (e as Error).message : e}）`,
    };
  }
}

export function registerEnterpriseKbHealth(pi: ExtensionAPI): boolean {
  const cfg = loadEnterpriseConfig();
  if (!cfg.enabled) return false;

  pi.registerCommand("aiplat-kb-health", {
    description: "Show customer-facing KB health score summary (enterprise)",
    handler: async (_args, ctx) => {
      const r = await fetchKbHealthSummary(loadEnterpriseConfig());
      console.log(r.text);
      try {
        ctx.ui.notify(r.text, r.ok ? "info" : "warning");
      } catch {
        /* no UI */
      }
    },
  });
  return true;
}
