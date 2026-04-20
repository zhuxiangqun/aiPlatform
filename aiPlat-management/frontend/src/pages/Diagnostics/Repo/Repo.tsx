import { useEffect, useMemo, useState } from 'react';
import { Search, RefreshCw, ClipboardCopy, ExternalLink, FileText, Hammer } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Input, Table, toast } from '../../../components/ui';
import { diagnosticsApi, toolApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

const Repo: React.FC = () => {
  const [repoRoot, setRepoRoot] = useState(() => localStorage.getItem('repo_ctx_root') || '');
  const [loadingIndex, setLoadingIndex] = useState(false);
  const [index, setIndex] = useState<any>(null);

  const [query, setQuery] = useState('');
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [searchResult, setSearchResult] = useState<any>(null);

  const [loadingPatch, setLoadingPatch] = useState(false);
  const [patch, setPatch] = useState<any>(null);

  const [loadingStaged, setLoadingStaged] = useState(false);
  const [staged, setStaged] = useState<any>(null);

  const [loadingTests, setLoadingTests] = useState(false);
  const [tests, setTests] = useState<any>(null);

  const [recording, setRecording] = useState(false);
  const [recordDetails, setRecordDetails] = useState('');
  const [runTestsOnRecord, setRunTestsOnRecord] = useState(true);
  const [lastRecord, setLastRecord] = useState<any>(null);

  const [loadingRecent, setLoadingRecent] = useState(false);
  const [recent, setRecent] = useState<any[]>([]);

  useEffect(() => {
    try {
      localStorage.setItem('repo_ctx_root', repoRoot);
    } catch {}
  }, [repoRoot]);

  const loadIndex = async () => {
    if (!repoRoot.trim()) {
      toast.error('请填写 repo_root');
      return;
    }
    setLoadingIndex(true);
    try {
      const res = await toolApi.execute(
        'repo',
        { operation: 'index', repo_root: repoRoot.trim(), max_files: 5000, include_untracked: true },
        { toolset: 'safe_readonly', context: { repo_root: repoRoot.trim() } }
      );
      if (!res?.success) throw new Error(res?.error || 'index failed');
      setIndex(res.output);
      toast.success('索引完成');
    } catch (e: any) {
      setIndex(null);
      toastGateError(e, '索引失败');
    } finally {
      setLoadingIndex(false);
    }
  };

  const doSearch = async () => {
    if (!repoRoot.trim()) {
      toast.error('请填写 repo_root');
      return;
    }
    if (!query.trim()) {
      toast.error('请输入搜索关键词');
      return;
    }
    setLoadingSearch(true);
    try {
      const res = await toolApi.execute(
        'repo',
        { operation: 'search', repo_root: repoRoot.trim(), query: query.trim(), regex: false, case_sensitive: false, max_results: 200 },
        { toolset: 'safe_readonly', context: { repo_root: repoRoot.trim() } }
      );
      if (!res?.success) throw new Error(res?.error || 'search failed');
      setSearchResult(res.output);
    } catch (e: any) {
      setSearchResult(null);
      toastGateError(e, '搜索失败');
    } finally {
      setLoadingSearch(false);
    }
  };

  const loadPatch = async () => {
    setLoadingPatch(true);
    try {
      const res = await diagnosticsApi.getRepoChangesetPatch();
      setPatch(res);
    } catch (e: any) {
      setPatch(null);
      toastGateError(e, '加载 patch 失败');
    } finally {
      setLoadingPatch(false);
    }
  };

  const loadStaged = async () => {
    setLoadingStaged(true);
    try {
      const res = await diagnosticsApi.getRepoStagedPreview();
      setStaged(res);
    } catch (e: any) {
      setStaged(null);
      toastGateError(e, '加载 staged 失败');
    } finally {
      setLoadingStaged(false);
    }
  };

  const runTests = async () => {
    setLoadingTests(true);
    try {
      const res = await diagnosticsApi.runRepoTests({ details: recordDetails || '' });
      setTests(res);
      toast.success('测试已完成');
    } catch (e: any) {
      setTests(null);
      toastGateError(e, '运行测试失败');
    } finally {
      setLoadingTests(false);
    }
  };

  const recordChangeset = async () => {
    setRecording(true);
    try {
      const res = await diagnosticsApi.recordRepoChangeset({ details: recordDetails || '', run_tests: runTestsOnRecord });
      setLastRecord(res);
      toast.success('已记录 changeset');
      await loadRecent();
    } catch (e: any) {
      setLastRecord(null);
      toastGateError(e, '记录 changeset 失败');
    } finally {
      setRecording(false);
    }
  };

  const loadRecent = async () => {
    setLoadingRecent(true);
    try {
      const res = await diagnosticsApi.listSyscalls({ kind: 'changeset', name: 'repo_changeset_record', limit: 20, offset: 0 });
      setRecent(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setRecent([]);
    } finally {
      setLoadingRecent(false);
    }
  };

  useEffect(() => {
    loadRecent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const files = useMemo(() => (index?.items && Array.isArray(index.items) ? index.items : []), [index]);
  const matches = useMemo(() => (searchResult?.matches && Array.isArray(searchResult.matches) ? searchResult.matches : []), [searchResult]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">Repo 索引 / 搜索</h1>
        <p className="text-sm text-gray-500 mt-1">.gitignore-aware 文件集（tracked + untracked excluding ignored）</p>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">Repo Changeset（审阅 / 记录）</div>
          <div className="text-xs text-gray-500 mt-1">
            说明：changeset/patch/tests 使用服务端配置的 repo_root（AIPLAT_REPO_ROOT），与上面的索引/搜索 repo_root 输入互不影响。
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2 items-center">
            <Button variant="secondary" loading={loadingPatch} icon={<FileText size={14} />} onClick={loadPatch}>
              加载 patch
            </Button>
            <Button variant="secondary" loading={loadingStaged} icon={<FileText size={14} />} onClick={loadStaged}>
              加载 staged
            </Button>
            <Button variant="secondary" loading={loadingTests} icon={<Hammer size={14} />} onClick={runTests}>
              运行测试
            </Button>
            <Button variant="secondary" loading={recording} icon={<ClipboardCopy size={14} />} onClick={recordChangeset}>
              记录 changeset
            </Button>
            <label className="text-xs text-gray-400 flex items-center gap-2 ml-2">
              <input type="checkbox" checked={runTestsOnRecord} onChange={(e) => setRunTestsOnRecord(e.target.checked)} />
              记录时跑测试
            </label>
            <Input className="min-w-[320px]" value={recordDetails} onChange={(e) => setRecordDetails(e.target.value)} placeholder="备注（会写入审计事件/测试 note）" />
          </div>

          {lastRecord?.change_id && (
            <div className="text-xs text-gray-500 mt-3 flex items-center gap-3">
              <div>
                last change_id: <code className="bg-dark-hover px-1.5 py-0.5 rounded">{String(lastRecord.change_id)}</code>
              </div>
              <a className="underline flex items-center gap-1" href={`/diagnostics/change-control/${encodeURIComponent(String(lastRecord.change_id))}`}>
                打开 Change Control <ExternalLink size={12} />
              </a>
              <a className="underline flex items-center gap-1" href={`/diagnostics/syscalls?kind=changeset&name=repo_changeset_record`}>
                查看 Syscalls <ExternalLink size={12} />
              </a>
            </div>
          )}

          {patch?.patch && (
            <pre className="mt-3 text-xs whitespace-pre-wrap bg-dark-hover border border-dark-border rounded-lg p-3 max-h-[360px] overflow-auto">
              {String(patch.patch)}
            </pre>
          )}

          {staged?.patch && (
            <pre className="mt-3 text-xs whitespace-pre-wrap bg-dark-hover border border-dark-border rounded-lg p-3 max-h-[360px] overflow-auto">
              {String(staged.patch)}
            </pre>
          )}

          {tests?.result && (
            <pre className="mt-3 text-xs whitespace-pre-wrap bg-dark-hover border border-dark-border rounded-lg p-3 max-h-[240px] overflow-auto">
              {JSON.stringify(tests.result, null, 2)}
            </pre>
          )}

          <div className="mt-4 text-sm font-semibold text-gray-200 flex items-center gap-2">
            最近记录
            <Button variant="ghost" loading={loadingRecent} icon={<RefreshCw size={14} />} onClick={loadRecent}>
              刷新
            </Button>
          </div>
          <Table
            className="mt-2"
            rowKey={(r: any) => String(r.id || r.created_at || Math.random())}
            loading={loadingRecent}
            data={recent}
            columns={[
              { key: 'created_at', title: 'created_at', dataIndex: 'created_at', width: 170 },
              { key: 'target_id', title: 'change_id', dataIndex: 'target_id', width: 240 },
              { key: 'status', title: 'status', dataIndex: 'status', width: 120 },
              { key: 'error', title: 'error', dataIndex: 'error', width: 180 },
              { key: 'name', title: 'name', dataIndex: 'name', width: 200 },
            ]}
            emptyText="暂无记录"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">上下文</div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="md:col-span-2">
              <div className="text-xs text-gray-500 mb-1">repo_root</div>
              <Input value={repoRoot} onChange={(e) => setRepoRoot(e.target.value)} placeholder="/path/to/repo" />
            </div>
            <div className="flex items-end gap-2">
              <Button variant="secondary" loading={loadingIndex} icon={<RefreshCw size={14} />} onClick={loadIndex}>
                生成索引
              </Button>
            </div>
          </div>

          {index && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 text-sm">
              <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
                <div className="text-xs text-gray-500">tracked</div>
                <div className="text-gray-200 font-semibold">{index.tracked_count}</div>
              </div>
              <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
                <div className="text-xs text-gray-500">untracked</div>
                <div className="text-gray-200 font-semibold">{index.untracked_count}</div>
              </div>
              <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
                <div className="text-xs text-gray-500">indexed</div>
                <div className="text-gray-200 font-semibold">{index.indexed_count}</div>
              </div>
              <div className="bg-dark-hover border border-dark-border rounded-lg p-3">
                <div className="text-xs text-gray-500">total_bytes</div>
                <div className="text-gray-200 font-semibold">{index.total_bytes}</div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">全文搜索</div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-2">
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索关键词（默认不区分大小写）" />
            <Button variant="secondary" loading={loadingSearch} icon={<Search size={14} />} onClick={doSearch}>
              搜索
            </Button>
          </div>
          {searchResult && (
            <div className="text-xs text-gray-500 mt-2">
              returned {searchResult.returned} / max_results {searchResult.max_results}
            </div>
          )}
          <Table
            className="mt-3"
            rowKey={(r: any) => `${r.path}:${r.line}:${r.col}`}
            loading={loadingSearch}
            data={matches}
            columns={[
              { key: 'path', title: 'path', dataIndex: 'path', width: 320 },
              { key: 'line', title: 'line', dataIndex: 'line', width: 70 },
              { key: 'col', title: 'col', dataIndex: 'col', width: 70 },
              { key: 'preview', title: 'preview', dataIndex: 'preview' },
            ]}
            emptyText="暂无匹配"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">文件列表（索引结果）</div>
        </CardHeader>
        <CardContent>
          <Table
            rowKey={(r: any) => `${r.path}`}
            loading={loadingIndex}
            data={files.slice(0, 200)}
            columns={[
              { key: 'path', title: 'path', dataIndex: 'path' },
              { key: 'tracked', title: 'tracked', dataIndex: 'tracked', width: 90 },
              { key: 'size', title: 'size', dataIndex: 'size', width: 100 },
              { key: 'mtime', title: 'mtime', dataIndex: 'mtime', width: 160 },
            ]}
            emptyText="请先生成索引"
          />
          {files.length > 200 && <div className="text-xs text-gray-500 mt-2">仅展示前 200 条（indexed_count={files.length}）</div>}
        </CardContent>
      </Card>
    </div>
  );
};

export default Repo;
