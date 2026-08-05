import React, { useEffect, useState } from "react";
import { message, Table, Tag, Button, Space, Spin, Tabs } from "antd";
import { ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined, WarningOutlined } from "@ant-design/icons";
import axios from "axios";

const API_BASE = "/api/core/capabilities";

interface AutoCap {
  id: string;
  description?: string;
  paths: string[];
  status?: string;
}

interface ConfigCap {
  id: string;
  field?: string;
  schema_default?: any;
  consumed_at?: string[];
  engine_consumed?: boolean;
}

interface ScanResult {
  auto: AutoCap[];
  configurable: { consumed: ConfigCap[]; orphan: ConfigCap[] };
}

const CapabilitiesPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [scanData, setScanData] = useState<ScanResult | null>(null);
  const [autoList, setAutoList] = useState<AutoCap[]>([]);
  const [cfgConsumed, setCfgConsumed] = useState<ConfigCap[]>([]);
  const [cfgOrphan, setCfgOrphan] = useState<ConfigCap[]>([]);

  const fetchScan = async () => {
    setLoading(true);
    try {
      const resp = await axios.get(`${API_BASE}/scan`);
      const data = resp.data;
      setScanData(data);
      setAutoList(data.auto || []);
      setCfgConsumed(data.configurable?.consumed || []);
      setCfgOrphan(data.configurable?.orphan || []);
    } catch (e: any) {
      message.error("Scan failed: " + (e.message || "unknown"));
    } finally {
      setLoading(false);
    }
  };

  const handleRescan = async () => {
    setLoading(true);
    try {
      await axios.post(`${API_BASE}/rescan`);
      message.success("Rescan complete — frontmatter updated");
      await fetchScan();
    } catch (e: any) {
      message.error("Rescan failed: " + (e.message || "unknown"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchScan(); }, []);

  const autoColumns = [
    { title: "能力", dataIndex: "id", key: "id", width: 220 },
    {
      title: "状态", dataIndex: "status", key: "status", width: 100,
      render: (s: string) => s === "active"
        ? <Tag color="green" icon={<CheckCircleOutlined />}>active</Tag>
        : <Tag color="red" icon={<CloseCircleOutlined />}>missing</Tag>
    },
    {
      title: "代码位置", key: "paths",
      render: (_: any, r: AutoCap) => (
        <span style={{ fontSize: 12, color: "#666" }}>
          {r.paths?.slice(0, 3).join(", ")}{r.paths?.length > 3 ? ` ...+${r.paths.length - 3}` : ""}
        </span>
      )
    },
  ];

  const cfgColumns = [
    { title: "字段", dataIndex: "field", key: "field", width: 200, render: (v: string) => v || "-" },
    {
      title: "状态", key: "status", width: 120,
      render: (_: any, r: ConfigCap) => r.engine_consumed
        ? <Tag color="green">consumed</Tag>
        : <Tag color="red" icon={<WarningOutlined />}>orphan</Tag>
    },
    {
      title: "默认值", dataIndex: "schema_default", key: "default", width: 300,
      render: (v: any) => {
        if (v === undefined || v === null) return <span style={{ color: "#999" }}>-</span>;
        const s = typeof v === "string" ? v : JSON.stringify(v);
        return <span style={{ fontSize: 12 }}>{s.length > 80 ? s.slice(0, 80) + "..." : s}</span>;
      }
    },
    {
      title: "引擎引用", key: "consumed",
      render: (_: any, r: ConfigCap) => r.consumed_at?.length
        ? <span style={{ fontSize: 11, color: "#52c41a" }}>{r.consumed_at.length} refs</span>
        : <span style={{ color: "#ff4d4f" }}>0</span>
    },
  ];

  const totalAuto = autoList.filter(a => a.status === "active").length;
  const totalCfgOk = cfgConsumed.length;
  const totalCfgBad = cfgOrphan.length;

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<ReloadOutlined />} loading={loading} onClick={fetchScan}>
          Refresh
        </Button>
        <Button icon={<ReloadOutlined />} onClick={handleRescan}>
          Rescan & Merge
        </Button>
      </Space>

      <div style={{ marginBottom: 16, display: "flex", gap: 24 }}>
        <Tag color="green">AUTO: {totalAuto} active</Tag>
        <Tag color="blue">CONFIG: {totalCfgOk} consumed</Tag>
        {totalCfgBad > 0 && <Tag color="red">ORPHAN: {totalCfgBad}</Tag>}
      </div>

      <Spin spinning={loading}>
        <Tabs defaultActiveKey="auto" items={[
          {
            key: "auto",
            label: `AUTO 能力 (${totalAuto})`,
            children: <Table dataSource={autoList} columns={autoColumns} rowKey="id" size="small" pagination={false} />
          },
          {
            key: "consumed",
            label: `CONFIGURABLE (${totalCfgOk})`,
            children: <Table dataSource={cfgConsumed} columns={cfgColumns} rowKey="field" size="small" pagination={false} />
          },
          ...(totalCfgBad > 0 ? [{
            key: "orphan",
            label: `⚠️ Orphan (${totalCfgBad})`,
            children: <Table dataSource={cfgOrphan} columns={cfgColumns.filter(c => c.key !== "consumed")} rowKey="field" size="small" pagination={false} />
          }] : []),
        ]} />
      </Spin>
    </div>
  );
};

export default CapabilitiesPage;
