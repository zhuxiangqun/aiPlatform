/**
 * Pi slash `/aiplat-duty` — L3 customer-facing duty desk via platform
 * GET /platform/delivery/l3-duty-desk (HYBRID_ENTERPRISE_DELIVERY §5 L3).
 *
 * Soft-fails when enterprise off or platform unreachable.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { normalizePlatformBaseUrl, platformFetch } from "./enterprise_http";
import {
  loadEnterpriseConfig,
  type EnterpriseConfig,
} from "./enterprise_kb";
import { httpJsonObject } from "./json_body.mjs";

function joinPlatform(base: string, path: string): string {
  const b = normalizePlatformBaseUrl(base).replace(/\/+$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  if (b.endsWith("/api")) {
    return `${b}${p.startsWith("/platform") ? p : `/platform${p}`}`;
  }
  return `${b}${p.startsWith("/platform") ? p : `/platform${p}`}`;
}

export async function fetchL3DutySummary(
  cfg?: EnterpriseConfig,
): Promise<{ ok: boolean; text: string }> {
  const c = cfg || loadEnterpriseConfig();
  if (!c.enabled) {
    return {
      ok: false,
      text: "L3 值班台暂不可用（未启用企业回连：AIPLAT_ENTERPRISE=1）",
    };
  }
  if (!c.baseUrl || !c.token) {
    return { ok: false, text: "L3 值班台暂不可用（缺少 PLATFORM_URL / token）" };
  }
  const url = new URL(joinPlatform(c.baseUrl, "/platform/delivery/l3-duty-desk"));
  url.searchParams.set("window_hours", "720");
  url.searchParams.set("format", "json");
  try {
    const res = await platformFetch(url.toString(), {
      headers: {
        authorization: `Bearer ${c.token}`,
        accept: "application/json",
      },
    });
    const text = await res.text();
    const body = httpJsonObject(res.status, text);
    if (!body.ok || !body.value) {
      if (String(body.error || "").startsWith("http_")) {
        return { ok: false, text: `L3 值班台暂不可用（http=${res.status}）` };
      }
      return { ok: false, text: "L3 值班台暂不可用（响应非 JSON 对象）" };
    }
    const parsed = body.value as Record<string, unknown>;
    const contact = (parsed.duty_contact || {}) as Record<string, unknown>;
    const iterations = (parsed.iterations || {}) as Record<string, unknown>;
    const evalSnap = (parsed.eval || {}) as Record<string, unknown>;
    const tips = Array.isArray(parsed.quarterly_suggestions)
      ? (parsed.quarterly_suggestions as string[])
      : [];
    const contactLine = contact.available
      ? `值班入口: ${contact.contact || contact.channel || "已配置"}`
      : `值班入口: unavailable（${contact.reason ?? "未配置"}）`;
    const iterLine = iterations.available
      ? `迭代记录: ${iterations.count ?? 0} 条`
      : `迭代记录: unavailable`;
    const srcLine = evalSnap.available
      ? `观测源 ${evalSnap.sources_present ?? 0}/${evalSnap.sources_total ?? 0}`
      : "观测源 unavailable";
    const lines = [
      `L3 专属值班台 ${parsed.period ?? ""}`.trim(),
      contactLine,
      iterLine,
      srcLine,
      "",
      `建议: ${tips[0] || "维持巡检与入库节奏"}`,
    ];
    return { ok: true, text: lines.join("\n") };
  } catch (e) {
    return {
      ok: false,
      text: `L3 值班台暂不可用（${e && (e as Error).message ? (e as Error).message : e}）`,
    };
  }
}

export function registerEnterpriseL3Duty(pi: ExtensionAPI): boolean {
  const cfg = loadEnterpriseConfig();
  if (!cfg.enabled) return false;

  pi.registerCommand("aiplat-duty", {
    description: "Show L3 duty desk summary (enterprise on-call entry)",
    handler: async (_args, ctx) => {
      const r = await fetchL3DutySummary(loadEnterpriseConfig());
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
