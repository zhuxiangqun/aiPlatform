export const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  
  if (days > 0) {
    return `${days}天 ${hours}小时`;
  }
  if (hours > 0) {
    return `${hours}小时 ${minutes}分钟`;
  }
  return `${minutes}分钟`;
};

export const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
};

export const formatNumber = (num: number): string => {
  return new Intl.NumberFormat('zh-CN').format(num);
};

export const formatPercent = (value: number, decimals = 1): string => {
  return `${value.toFixed(decimals)}%`;
};

export const formatTimestamp = (timestamp: string): string => {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('zh-CN', { 
    hour: '2-digit', 
    minute: '2-digit', 
    second: '2-digit' 
  });
};

export const getStatusColor = (status: string): string => {
  switch (status) {
    case 'healthy':
      return '#52c41a';
    case 'degraded':
      return '#faad14';
    case 'unhealthy':
      return '#ff4d4f';
    default:
      return '#8c8c8c';
  }
};

export const getComponentColor = (component: string): string => {
  const colors: Record<string, string> = {
    database: '#1677ff',
    cache: '#52c41a',
    llm: '#722ed1',
    vector: '#fa8c16',
    messaging: '#eb2f96',
    storage: '#13c2c2',
    network: '#2f54eb',
    memory: '#fa541c',
    compute: '#f5222d',
  };
  return colors[component] || '#1677ff';
};

export const getComponentIcon = (component: string): string => {
  const icons: Record<string, string> = {
    database: '💾',
    cache: '⚡',
    llm: '🧠',
    vector: '🔍',
    messaging: '📨',
    storage: '💿',
    network: '🌐',
    memory: '🗃️',
    compute: '🎮',
  };
  return icons[component] || '🔧';
};