import React, { useEffect, useState } from "react";
import { Card, CardContent, Button, toast } from "../../components/ui";
import { Activity, RefreshCw, CheckCircle, AlertTriangle, Cpu, Trash2, Edit3, Save, X, History } from "lucide-react";
import { apiClient } from "../../services/apiClient";

interface AutoCap { id: string; description?: string; paths: string[]; status?: string; reviewed?: boolean; }
interface ConfigCap { field?: string; schema_default?: any; consumed_at?: string[]; engine_consumed?: boolean; reviewed?: boolean; _editing?: boolean; _editValue?: string; }

const REVIEW_STORAGE_KEY = "capability_review_state";

const CapabilitiesPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [autoList, setAutoList] = useState<AutoCap[]>([]);
  const [cfgConsumed, setCfgConsumed] = useState<ConfigCap[]>([]);
  const [cfgOrphan, setCfgOrphan] = useState<ConfigCap[]>([]);
  const [activeTab, setActiveTab] = useState<"auto" | "consumed" | "orphan">("auto");
  const [saving, setSaving] = useState(false);

  // Load persisted review state from localStorage
  const loadReviewState = () => {
    try {
      const raw = localStorage.getItem(REVIEW_STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  };

  const saveReviewState = (state: Record<string, boolean>) => {
    localStorage.setItem(REVIEW_STORAGE_KEY, JSON.stringify(state));
  };

  const markReviewed = (id: string, reviewed: boolean) => {
    const state = loadReviewState();
    state[id] = reviewed;
    saveReviewState(state);
    // Update in-memory lists
    setAutoList(prev => prev.map(a => a.id === id ? { ...a, reviewed } : a));
    setCfgConsumed(prev => prev.map(c => (c.field || c.id) === id ? { ...c, reviewed } : c));
    setCfgOrphan(prev => prev.map(c => (c.field || c.id) === id ? { ...c, reviewed } : c));
  };

  const fetchScan = async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<any>("/core/capabilities/scan");
      const reviewState = loadReviewState();
      const mergeReview = (items: any[], key: string) =>
        items.map((item: any) => ({ ...item, reviewed: !!reviewState[item[key] || item.id] }));
      
      setAutoList(mergeReview(data.auto || [], "id"));
      setCfgConsumed(mergeReview(data.configurable?.consumed || [], "field"));
      setCfgOrphan(mergeReview(data.configurable?.orphan || [], "field"));
    } catch {
      toast.error("Scan failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRescan = async () => {
    setLoading(true);
    try {
      await apiClient.post("/core/capabilities/rescan");
      toast.success("Rescan & merge complete");
      await fetchScan();
    } catch {
      toast.error("Rescan failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveAuto = async (id: string) => {
    const updated = autoList.filter(a => a.id !== id);
    setAutoList(updated);
    toast.success(`Removed ${id}`);
  };

  const handleRemoveConfig = async (field: string, source: "consumed" | "orphan") => {
    if (source === "consumed") {
      setCfgConsumed(prev => prev.filter(c => c.field !== field));
    } else {
      setCfgOrphan(prev => prev.filter(c => c.field !== field));
    }
    toast.success(`Removed ${field}`);
  };

  const startEdit = (item: ConfigCap) => {
    const val = typeof item.schema_default === "string" ? item.schema_default : JSON.stringify(item.schema_default || "");
    item._editing = true;
    item._editValue = val;
    if (activeTab === "consumed") setCfgConsumed([...cfgConsumed]);
    else setCfgOrphan([...cfgOrphan]);
  };

  const cancelEdit = (item: ConfigCap) => {
    item._editing = false;
    item._editValue = undefined;
    if (activeTab === "consumed") setCfgConsumed([...cfgConsumed]);
    else setCfgOrphan([...cfgOrphan]);
  };

  const saveEdit = (item: ConfigCap) => {
    const raw = item._editValue || "{}";
    try {
      const parsed = JSON.parse(raw);
      item.schema_default = parsed;
    } catch {
      item.schema_default = raw;
    }
    item._editing = false;
    item._editValue = undefined;
    if (activeTab === "consumed") setCfgConsumed([...cfgConsumed]);
    else setCfgOrphan([...cfgOrphan]);
    toast.success(`Updated ${item.field}`);
  };

  const handleSubmitReview = async () => {
    setSaving(true);
    try {
      // Build clean payload
      const auto = autoList.map(({ reviewed, _editing, _editValue, ...rest }) => rest);
      const configurable = cfgConsumed.map(({ reviewed, _editing, _editValue, ...rest }) => rest);
      
      await apiClient.post("/core/capabilities/guarantees", { auto, configurable });
      toast.success("Review submitted — frontmatter updated");
    } catch {
      toast.error("Submit failed");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => { fetchScan(); }, []);

  const totalAuto = autoList.filter(a => a.status === "active").length;
  const totalCfgOk = cfgConsumed.length;
  const totalCfgBad = cfgOrphan.length;
  const reviewedAuto = autoList.filter(a => a.reviewed).length;
  const reviewedCfg = cfgConsumed.filter(c => c.reviewed).length + cfgOrphan.filter(c => c.reviewed).length;
  const totalReviewed = reviewedAuto + reviewedCfg;
  const totalItems = totalAuto + totalCfgOk + totalCfgBad;

  return (
    <div className="p-6 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">核心能力管理</h1>
          <p className="text-sm text-gray-500 mt-1">
            扫描 AIPLAT_CAPABILITIES.md 中声明的能力在代码中是否真实存在。审核: {totalReviewed}/{totalItems} · 
            <button className="ml-2 text-blue-600 hover:underline" onClick={() => localStorage.removeItem(REVIEW_STORAGE_KEY)}>重置审核状态</button>
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={fetchScan} disabled={loading}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button variant="outline" onClick={handleRescan} disabled={loading}>
            <RefreshCw className="w-4 h-4 mr-1" /> Rescan
          </Button>
          <Button onClick={handleSubmitReview} disabled={saving}>
            <Save className="w-4 h-4 mr-1" /> 提交审核
          </Button>
        </div>
      </div>

      <div className="flex gap-4 mb-6">
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
          <CheckCircle className="w-3 h-3 mr-1" /> 绿色 = 代码存在 (active)
        </span>
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
          <AlertTriangle className="w-3 h-3 mr-1" /> 红色 = 代码缺失 (missing)
        </span>
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
          AUTO: {totalAuto}
        </span>
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
          CONFIG: {totalCfgOk}
        </span>
        {totalCfgBad > 0 && (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
            ORPHAN: {totalCfgBad}
          </span>
        )}
      </div>

      <div className="flex gap-2 mb-4 border-b">
        {(["auto", "consumed", ...(totalCfgBad > 0 ? ["orphan"] : [])] as const).map(tab => (
          <button key={tab} className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === tab ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"
          }`} onClick={() => setActiveTab(tab)}>
            {tab === "auto" ? `AUTO (${totalAuto})` : tab === "consumed" ? `CONFIG (${totalCfgOk})` : `⚠️ Orphan (${totalCfgBad})`}
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-gray-500"><RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin" /> Loading...</div>
          ) : (
               <table className="w-full text-sm">
              <thead className="bg-gray-100 border-b-2 border-gray-300 text-gray-700 text-xs uppercase tracking-wider">
                <tr>
                  <th className="text-center p-3 w-8 text-gray-400">#</th>
                  <th className="text-center p-3 w-8 text-gray-400">
                    <input type="checkbox" 
                      title="全选/取消"
                      onChange={e => {
                        const items = activeTab === "auto" ? autoList : activeTab === "consumed" ? cfgConsumed : cfgOrphan;
                        const allChecked = items.every(a => a.reviewed);
                        items.forEach(a => markReviewed((a as any).id || (a as any).field || "", !allChecked));
                      }}
                      checked={(() => {
                        const items = activeTab === "auto" ? autoList : activeTab === "consumed" ? cfgConsumed : cfgOrphan;
                        return items.length > 0 && items.every(a => a.reviewed);
                      })()}
                    />
                  </th>
                  {activeTab === "auto" && (
                    <>
                      <th className="text-left p-3 font-semibold text-gray-700">能力 ID</th>
                      <th className="text-left p-3 font-semibold text-gray-700">说明</th>
                      <th className="text-left p-3 font-semibold text-gray-700">代码存在</th>
                      <th className="text-left p-3 font-semibold text-gray-700">代码位置</th>
                    </>
                  )}
                  {(activeTab === "consumed" || activeTab === "orphan") && (
                    <>
                      <th className="text-left p-3 font-semibold text-gray-700">Schema 字段</th>
                      <th className="text-left p-3 font-semibold text-gray-700">说明</th>
                      <th className="text-left p-3 font-semibold text-gray-700 w-24">引擎消费</th>
                      <th className="text-left p-3 font-semibold text-gray-700">默认值</th>
                    </>
                  )}
                  <th className="p-3 w-24 font-semibold text-gray-700">操作</th>
                </tr>
              </thead>
              <tbody>
                {activeTab === "auto" && autoList.map((item, idx) => (
                  <tr key={item.id} className={`border-b hover:bg-gray-50 ${item.reviewed ? "bg-green-50" : ""}`}>
                    <td className="p-3 text-center text-gray-400 text-xs">{idx + 1}</td>
                    <td className="p-3">
                      <input type="checkbox" checked={!!item.reviewed} onChange={e => markReviewed(item.id, e.target.checked)} />
                    </td>
                    <td className="p-3 font-mono text-xs">{item.id}</td>
                    <td className="p-3 text-xs text-gray-500 max-w-[220px] truncate" title={(item as any).description || ""}>
                      {(item as any).description || "-"}
                    </td>
                    <td className="p-3">
                      {item.status === "active"
                        ? <span className="inline-flex items-center text-xs text-green-700"><CheckCircle className="w-3 h-3 mr-1" /> 已找到</span>
                        : <span className="inline-flex items-center text-xs text-red-700"><AlertTriangle className="w-3 h-3 mr-1" /> 未找到</span>}
                    </td>
                    <td className="p-3 text-xs text-gray-500">
                      {(item.found_at || item.paths || [])?.slice(0, 2).map((p: any, i: number) => (
                        <div key={i} className="truncate" title={typeof p === "string" ? p : `${p.file}:${p.line}`}>
                          {typeof p === "string" ? p : `${p.file.split("/").pop()}:${p.line}`}
                        </div>
                      ))}
                      {(item.found_at || item.paths || []).length > 2 && (
                        <div className="text-gray-400">+{(item.found_at || item.paths).length - 2} more</div>
                      )}
                    </td>
                    <td className="p-3">
                      <button onClick={() => handleRemoveAuto(item.id)} className="text-red-500 hover:text-red-700" title="Remove">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {(activeTab === "consumed" || activeTab === "orphan") && 
                  (activeTab === "consumed" ? cfgConsumed : cfgOrphan).map((item, idx) => (
                  <tr key={item.field || idx} className={`border-b hover:bg-gray-50 ${item.reviewed ? "bg-green-50" : ""}`}>
                    <td className="p-3 text-center text-gray-400 text-xs">{idx + 1}</td>
                    <td className="p-3">
                      <input type="checkbox" checked={!!item.reviewed} onChange={e => markReviewed(item.field || "", e.target.checked)} />
                    </td>
                    <td className="p-3 font-mono text-xs">{item.field || "-"}</td>
                    <td className="p-3 text-xs text-gray-500 max-w-[200px] truncate" title={(item as any).description || ""}>
                      {(item as any).description || "-"}
                    </td>
                    <td className="p-3">
                      {item.engine_consumed
                        ? <span className="text-green-600 text-xs">✓ {item.consumed_at?.length || 0} refs</span>
                        : <span className="text-red-600 text-xs">✗ 0 refs</span>}
                    </td>
                    <td className="p-3 text-xs text-gray-500 max-w-xs">
                      {item._editing ? (
                        <div className="flex gap-1">
                          <input
                            className="border rounded px-1 py-0.5 text-xs w-full"
                            value={item._editValue || ""}
                            onChange={e => { item._editValue = e.target.value; activeTab === "consumed" ? setCfgConsumed([...cfgConsumed]) : setCfgOrphan([...cfgOrphan]); }}
                            autoFocus
                          />
                          <button onClick={() => saveEdit(item)} className="text-green-600"><Save className="w-3 h-3" /></button>
                          <button onClick={() => cancelEdit(item)} className="text-red-500"><X className="w-3 h-3" /></button>
                        </div>
                      ) : (
                        <span>
                          {item.schema_default !== undefined && item.schema_default !== null
                            ? typeof item.schema_default === "string" ? item.schema_default : JSON.stringify(item.schema_default).slice(0, 80)
                            : "-"}
                        </span>
                      )}
                    </td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        {!item._editing && (
                          <button onClick={() => startEdit(item)} className="text-blue-500 hover:text-blue-700" title="Edit default">
                            <Edit3 className="w-4 h-4" />
                          </button>
                        )}
                        <button onClick={() => handleRemoveConfig(item.field || "", activeTab === "consumed" ? "consumed" : "orphan")} className="text-red-500 hover:text-red-700" title="Remove">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {activeTab === "auto" && autoList.length === 0 && (
                  <tr><td colSpan={7} className="p-8 text-center text-gray-400">No data. Click Refresh to scan.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {activeTab === "orphan" && totalCfgBad > 0 && (
        <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 inline mr-1" />
          These Schema fields are never read by the pipeline engine. Either wire the engine or remove them.
        </div>
      )}

      <div className="mt-6 p-4 bg-gray-50 border rounded text-sm text-gray-600">
        <History className="w-4 h-4 inline mr-1" />
        <strong>审核流程：</strong>勾选 checkbox 标记已审核 → 编辑默认值（铅笔图标）→ 删除不需要的承诺（垃圾桶） → 点「提交审核」写入 AIPLAT_CAPABILITIES.md。
        Rescan 会重新从代码扫描并覆盖手工修改——审核通过后应避免再次 Rescan。
      </div>
    </div>
  );
};

export default CapabilitiesPage;
