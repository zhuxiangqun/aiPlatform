import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, Button, Badge, toast } from "../../components/ui";
import { Activity, RefreshCw, CheckCircle, AlertTriangle, Cpu, Search, Shield, FileText } from "lucide-react";
import { apiClient } from "../../services/apiClient";

interface AutoCap {
  id: string;
  description?: string;
  paths: string[];
  status?: string;
}

interface ConfigCap {
  field?: string;
  schema_default?: any;
  consumed_at?: string[];
  engine_consumed?: boolean;
}

const CapabilitiesPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [autoList, setAutoList] = useState<AutoCap[]>([]);
  const [cfgConsumed, setCfgConsumed] = useState<ConfigCap[]>([]);
  const [cfgOrphan, setCfgOrphan] = useState<ConfigCap[]>([]);
  const [activeTab, setActiveTab] = useState<"auto" | "consumed" | "orphan">("auto");

  const fetchScan = async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<any>("/api/core/capabilities/scan");
      setAutoList(data.auto || []);
      setCfgConsumed(data.configurable?.consumed || []);
      setCfgOrphan(data.configurable?.orphan || []);
    } catch (e: any) {
      toast.error("Scan failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRescan = async () => {
    setLoading(true);
    try {
      await apiClient.post("/api/core/capabilities/rescan");
      toast.success("Rescan & merge complete");
      await fetchScan();
    } catch (e: any) {
      toast.error("Rescan failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchScan(); }, []);

  const totalAuto = autoList.filter(a => a.status === "active").length;
  const totalCfgOk = cfgConsumed.length;
  const totalCfgBad = cfgOrphan.length;

  const statusBg = (s: string) => s === "active" ? "text-green-600" : "text-red-600";

  return (
    <div className="p-6 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">核心能力管理</h1>
        <div className="flex gap-3">
          <Button variant="outline" onClick={fetchScan} disabled={loading}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button onClick={handleRescan} disabled={loading}>
            <RefreshCw className="w-4 h-4 mr-1" /> Rescan & Merge
          </Button>
        </div>
      </div>

      <div className="flex gap-4 mb-6">
        <Badge>
          <CheckCircle className="w-3 h-3 mr-1" /> AUTO: {totalAuto}
        </Badge>
        <Badge>
          <Cpu className="w-3 h-3 mr-1" /> CONFIG: {totalCfgOk}
        </Badge>
        {totalCfgBad > 0 && (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
            <AlertTriangle className="w-3 h-3 mr-1" /> ORPHAN: {totalCfgBad}
          </span>
        )}
      </div>

      <div className="flex gap-2 mb-4 border-b">
        {(["auto", "consumed", ...(totalCfgBad > 0 ? ["orphan"] : [])] as const).map(tab => (
          <button
            key={tab}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "auto" ? `AUTO (${totalAuto})` : tab === "consumed" ? `CONFIGURABLE (${totalCfgOk})` : `⚠️ Orphan (${totalCfgBad})`}
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-gray-500"><RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin" /> Loading...</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  {activeTab === "auto" && (
                    <>
                      <th className="text-left p-3 font-medium">能力 ID</th>
                      <th className="text-left p-3 font-medium w-20">状态</th>
                      <th className="text-left p-3 font-medium">代码位置</th>
                    </>
                  )}
                  {(activeTab === "consumed" || activeTab === "orphan") && (
                    <>
                      <th className="text-left p-3 font-medium">Schema 字段</th>
                      <th className="text-left p-3 font-medium w-24">引擎消费</th>
                      <th className="text-left p-3 font-medium">默认值</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {activeTab === "auto" && autoList.map((item) => (
                  <tr key={item.id} className="border-b hover:bg-gray-50">
                    <td className="p-3 font-mono text-xs">{item.id}</td>
                    <td className={`p-3 ${statusBg(item.status || "")}`}>
                      {item.status === "active" ? <CheckCircle className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                    </td>
                    <td className="p-3 text-xs text-gray-500">
                      {item.paths?.slice(0, 3).map((p, i) => (
                        <div key={i} className="truncate">{p}</div>
                      ))}
                      {item.paths?.length > 3 && <div className="text-gray-400">+{item.paths.length - 3} more</div>}
                    </td>
                  </tr>
                ))}
                {(activeTab === "consumed" || activeTab === "orphan") && 
                  (activeTab === "consumed" ? cfgConsumed : cfgOrphan).map((item, i) => (
                  <tr key={item.field || i} className="border-b hover:bg-gray-50">
                    <td className="p-3 font-mono text-xs">{item.field || "-"}</td>
                    <td className="p-3">
                      {item.engine_consumed
                        ? <span className="text-green-600 text-xs">✓ {item.consumed_at?.length || 0} refs</span>
                        : <span className="text-red-600 text-xs">✗ 0 refs</span>
                      }
                    </td>
                    <td className="p-3 text-xs text-gray-500 max-w-xs truncate">
                      {item.schema_default !== undefined && item.schema_default !== null
                        ? typeof item.schema_default === "string" ? item.schema_default : JSON.stringify(item.schema_default).slice(0, 100)
                        : "-"}
                    </td>
                  </tr>
                ))}
                {activeTab === "auto" && autoList.length === 0 && (
                  <tr><td colSpan={3} className="p-8 text-center text-gray-400">No data. Click Refresh to scan.</td></tr>
                )}
                {activeTab === "consumed" && cfgConsumed.length === 0 && (
                  <tr><td colSpan={3} className="p-8 text-center text-gray-400">No consumed configurable fields found.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {activeTab === "orphan" && totalCfgBad > 0 && (
        <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 inline mr-1" />
          These Schema fields are defined but never read by the pipeline engine. 
          Either wire the engine to consume them, or remove them from core_guarantees.
        </div>
      )}
    </div>
  );
};

export default CapabilitiesPage;
