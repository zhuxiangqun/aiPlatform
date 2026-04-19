import { useEffect, useMemo, useState } from 'react';
import { Search, RefreshCw } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Input, Table, toast } from '../../../components/ui';
import { toolApi } from '../../../services';

const Repo: React.FC = () => {
  const [repoRoot, setRepoRoot] = useState(() => localStorage.getItem('repo_ctx_root') || '');
  const [loadingIndex, setLoadingIndex] = useState(false);
  const [index, setIndex] = useState<any>(null);

  const [query, setQuery] = useState('');
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [searchResult, setSearchResult] = useState<any>(null);

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
      toast.error('索引失败', String(e?.message || ''));
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
      toast.error('搜索失败', String(e?.message || ''));
    } finally {
      setLoadingSearch(false);
    }
  };

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
