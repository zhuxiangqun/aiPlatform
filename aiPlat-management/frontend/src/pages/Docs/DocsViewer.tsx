import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ChevronRight, ChevronDown, FileText, Folder, FolderOpen, Search, BookOpen, ExternalLink, Download } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API = '/api/docs';

/** Strip YAML frontmatter (---...---) from markdown content */
function stripFrontmatter(md: string): string {
  const trimmed = md.trimStart();
  if (trimmed.startsWith('---')) {
    const end = trimmed.indexOf('---', 3);
    if (end > 0) return trimmed.slice(end + 3).trim();
  }
  return md;
}

interface TreeItem {
  name: string;
  path: string;
  type: 'directory' | 'file';
  children?: TreeItem[];
  category?: string;
}

function _buildCategoryTree(tree: TreeItem[], cats: Record<string, string>): { cat: string; label: string; items: TreeItem[] }[] {
  const groups: Record<string, TreeItem[]> = {};
  for (const item of tree) {
    const cat = item.category || '__other__';
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(item);
  }
  const order = ['gov', 'arch', 'layers', 'manuals', 'design', 'knowledge', 'compliance', 'tools', 'reports', '__other__'];
  return order
    .filter(cat => groups[cat]?.length)
    .map(cat => ({ cat, label: cats[cat] || '📂 其他', items: groups[cat] }));
}

const DocsViewer: React.FC = () => {
  const [searchParams] = useSearchParams();
  const urlPath = searchParams.get('path') || 'README.md';
  const [tree, setTree] = useState<TreeItem[]>([]);
  const [selectedPath, setSelectedPath] = useState<string>(urlPath);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set(['manuals']));
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set(['gov', 'arch', 'manuals']));
  const [categories, setCategories] = useState<Record<string, string>>({});

  // Load tree
  useEffect(() => {
    fetch(`${API}/tree`)
      .then(r => r.json())
      .then(d => {
        setTree(d.tree || []);
        setCategories(d.categories || {});
      })
      .catch(() => {});
  }, []);

  // Load content
  const loadContent = useCallback((path: string) => {
    setLoading(true);
    setSelectedPath(path);
    fetch(`${API}/content?path=${encodeURIComponent(path)}`)
      .then(r => r.json())
      .then(d => setContent(d.content || ''))
      .catch(() => setContent('# 加载失败\n\n文档不可用'))
      .finally(() => setLoading(false));
  }, []);

  // Auto-load document from URL param or default to README
  useEffect(() => {
    loadContent(urlPath);
  }, [loadContent, urlPath]);

  const cleanContent = useMemo(() => stripFrontmatter(content), [content]);

  const toggleDir = (path: string) => {
    setExpandedDirs(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleDownload = useCallback(() => {
    const a = document.createElement('a');
    a.href = `/api/docs/download?path=${encodeURIComponent(selectedPath)}`;
    a.download = selectedPath.split('/').pop() || selectedPath;
    a.click();
  }, [selectedPath]);

  const filteredTree = search
    ? tree.map(d => _filterTree(d, search.toLowerCase())).filter(Boolean) as TreeItem[]
    : tree;

  const categoryTree = useMemo(() => _buildCategoryTree(filteredTree, categories), [filteredTree, categories]);

  const toggleCat = (cat: string) => {
    setExpandedCats(prev => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-72' : 'w-0'} border-r border-gray-800 bg-dark-bg flex flex-col transition-all overflow-hidden`}>
        <div className="p-3 border-b border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-semibold text-gray-200">文档系统</span>
          </div>
          <button onClick={() => setSidebarOpen(false)} className="text-gray-600 hover:text-gray-400 text-xs">收起</button>
        </div>
        <div className="p-2">
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-gray-600" />
            <input
              className="w-full bg-gray-900 border border-gray-700 rounded px-7 py-1 text-xs text-gray-300 placeholder-gray-600"
              placeholder="搜索文档..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-1">
          {categoryTree.map(group => {
            const isCatExpanded = expandedCats.has(group.cat);
            return (
              <div key={group.cat} className="mb-1">
                <button
                  onClick={() => toggleCat(group.cat)}
                  className="w-full flex items-center gap-1 px-2 py-1.5 rounded text-xs hover:bg-gray-800/50 text-gray-300 font-medium"
                >
                  {isCatExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  <span>{group.label}</span>
                  <span className="ml-auto text-gray-600">{group.items.length}</span>
                </button>
                {isCatExpanded && group.items.map(item => (
                  <TreeNode
                    key={item.path}
                    item={item}
                    depth={0}
                    selectedPath={selectedPath}
                    expandedDirs={expandedDirs}
                    onToggle={toggleDir}
                    onSelect={loadContent}
                  />
                ))}
              </div>
            );
          })}
        </div>
      </div>

      {/* Toggle sidebar button (when collapsed) */}
      {!sidebarOpen && (
        <button
          onClick={() => setSidebarOpen(true)}
          className="absolute left-0 top-16 z-10 p-2 bg-dark-bg border border-gray-800 rounded-r text-gray-400 hover:text-gray-200"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      )}

      {/* Content area */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full text-gray-500">加载中...</div>
        ) : (
          <div className="max-w-4xl mx-auto p-6 md:p-10">
            {/* Breadcrumb */}
            <div className="text-xs text-gray-600 mb-4 flex items-center gap-1">
              <BookOpen className="w-3 h-3" />
              {(() => {
                // Find the category of the current document
                const findCat = (items: TreeItem[], targetPath: string): string => {
                  for (const item of items) {
                    if (item.path === targetPath) return item.category || '';
                    if (item.children) {
                      const found = findCat(item.children, targetPath);
                      if (found) return found;
                    }
                  }
                  return '';
                };
                const cat = findCat(tree, selectedPath);
                if (cat && categories[cat]) {
                  return <span className="text-gray-500 mr-1">{categories[cat]}</span>;
                }
                return null;
              })()}
              {selectedPath.startsWith('./') ? (
                // Workspace root files — show actual relative path without docs prefix
                selectedPath.replace('./', '').split('/').map((part, i, arr) => (
                  <React.Fragment key={i}>
                    {i > 0 && <span>/</span>}
                    <span className={i === arr.length - 1 ? 'text-gray-300' : ''}>{part}</span>
                  </React.Fragment>
                ))
              ) : (
                // docs/ files — show docs + full path
                <>
                  <span>docs</span>
                  {selectedPath.split('/').map((part, i, arr) => (
                    <React.Fragment key={i}>
                      <span>/</span>
                      <span className={i === arr.length - 1 ? 'text-gray-300' : ''}>{part}</span>
                    </React.Fragment>
                  ))}
                </>
              )}
              <a href={`/api/docs/content?path=${encodeURIComponent(selectedPath)}`} target="_blank" className="ml-2 text-blue-400 hover:text-blue-300" title="新窗口打开">
                <ExternalLink className="w-3 h-3 inline" />
              </a>
              <button onClick={handleDownload} className="ml-2 text-blue-400 hover:text-blue-300" title="下载文件">
                <Download className="w-3 h-3 inline" />
              </button>
            </div>
            {/* Markdown content */}
            <article className="prose prose-invert prose-sm max-w-none
              prose-headings:text-gray-100 prose-headings:border-b prose-headings:border-gray-800 prose-headings:pb-2
              prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg
              prose-p:text-gray-300 prose-p:leading-relaxed
              prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline
              prose-code:text-blue-300 prose-code:bg-gray-900 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs
              prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-800 prose-pre:rounded-lg
              prose-pre:overflow-x-auto
              prose-table:border-collapse prose-th:bg-gray-900 prose-th:text-gray-200 prose-th:px-3 prose-th:py-2
              prose-th:border prose-th:border-gray-700 prose-td:border prose-td:border-gray-700 prose-td:px-3 prose-td:py-2
              prose-td:text-gray-300 prose-tr:even:bg-gray-900/30
              prose-blockquote:border-l-4 prose-blockquote:border-blue-500/50 prose-blockquote:bg-blue-500/5 prose-blockquote:px-4 prose-blockquote:py-1 prose-blockquote:rounded-r
              prose-li:text-gray-300 prose-strong:text-gray-200
              [&_table]:w-full [&_table]:my-4 [&_code]:before:content-none [&_code]:after:content-none">
               <ReactMarkdown
                 remarkPlugins={[remarkGfm]}
                 components={{
                   a: ({ href, children }) => {
                     if (!href) return <span>{children}</span>;
                     if (href.startsWith('http://') || href.startsWith('https://')) {
                       return <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">{children}</a>;
                     }
                     // Internal doc link: resolve relative path and load via API
                     if (href.match(/\.(md|yaml|yml|json|txt)$/i) || !href.includes('.') || href.endsWith('/')) {
                       const base = selectedPath.includes('/')
                         ? selectedPath.substring(0, selectedPath.lastIndexOf('/') + 1)
                         : '';
                       const raw = base + href;
                       const parts = raw.split('/');
                       const resolved = parts.reduce((acc: string[], p: string) => {
                         if (p === '.' || p === '') return acc;
                         if (p === '..') { acc.pop(); return acc; }
                         acc.push(p);
                         return acc;
                       }, []).join('/');
                       return (
                         <span className="text-blue-400 cursor-pointer hover:underline"
                               onClick={() => loadContent(resolved)}>
                           {children}
                         </span>
                       );
                     }
                     return <a href={href} className="text-blue-400 hover:underline">{children}</a>;
                   },
                   img: ({ src, alt }) => {
                     if (!src) return null;
                     const imgSrc = src.startsWith('http') ? src
                       : `/api/docs/content?path=${encodeURIComponent(src)}`;
                     return <img src={imgSrc} alt={alt || ''} className="max-w-full rounded border border-gray-700" />;
                   }
                 }}
              >{cleanContent}</ReactMarkdown>
            </article>
          </div>
        )}
      </div>
    </div>
  );
};

// Tree node component
const TreeNode: React.FC<{
  item: TreeItem;
  depth: number;
  selectedPath: string;
  expandedDirs: Set<string>;
  onToggle: (path: string) => void;
  onSelect: (path: string) => void;
}> = ({ item, depth, selectedPath, expandedDirs, onToggle, onSelect }) => {
  const isExpanded = expandedDirs.has(item.path);
  const isSelected = selectedPath === item.path;

  if (item.type === 'directory') {
    return (
      <div>
        <button
          onClick={() => onToggle(item.path)}
          className={`w-full flex items-center gap-1 px-2 py-1 rounded text-xs hover:bg-gray-800/50 text-gray-400`}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          {isExpanded ? <FolderOpen className="w-3 h-3 text-yellow-500" /> : <Folder className="w-3 h-3 text-yellow-600" />}
          <span className="truncate">{item.name}</span>
        </button>
        {isExpanded && item.children?.map(child => (
          <TreeNode
            key={child.path}
            item={child}
            depth={depth + 1}
            selectedPath={selectedPath}
            expandedDirs={expandedDirs}
            onToggle={onToggle}
            onSelect={onSelect}
          />
        ))}
      </div>
    );
  }

  return (
    <button
      onClick={() => onSelect(item.path)}
      className={`w-full flex items-center gap-1 px-2 py-1 rounded text-xs hover:bg-gray-800/50 ${
        isSelected ? 'bg-blue-500/10 text-blue-300' : 'text-gray-400'
      }`}
      style={{ paddingLeft: `${depth * 12 + 8}px` }}
    >
      <FileText className="w-3 h-3 flex-shrink-0" />
      <span className="truncate">{item.name}</span>
    </button>
  );
};

// Filter helper
function _filterTree(item: TreeItem, query: string): TreeItem | null {
  if (item.type === 'file') {
    return item.name.toLowerCase().includes(query) ? item : null;
  }
  const filtered = (item.children || [])
    .map(c => _filterTree(c, query))
    .filter(Boolean) as TreeItem[];
  if (filtered.length > 0) {
    return { ...item, children: filtered };
  }
  return null;
}

export default DocsViewer;
