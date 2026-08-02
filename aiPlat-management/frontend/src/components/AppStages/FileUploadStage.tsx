import React, { useState, useRef } from 'react';
import { Button, Card } from '../ui';
import { Upload, File, AlertCircle } from 'lucide-react';
import { projectApi } from '../../services';

interface FileUploadConfig {
  accept?: string;
  max_size_mb?: number;
  label?: string;
  hint?: string;
}

interface Props {
  config: FileUploadConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  projectId?: string;
}

export const FileUploadStage: React.FC<Props> = ({ config, onExecute, skill, projectId = '' }) => {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<any>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (config.max_size_mb && f.size > config.max_size_mb * 1024 * 1024) {
      setError(`文件超过 ${config.max_size_mb}MB 限制`);
      return;
    }
    setFile(f);
    setError('');
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      // Step 1: Upload file bytes via FormData
      const formData = new FormData();
      formData.append('file', file, file.name);
      const uploadRes = await projectApi.uploadFile(projectId, formData);

      if (!uploadRes.ok) {
        throw new Error(uploadRes.error || '上传失败');
      }

      // Step 2: Execute skill with file reference
      const skillRes = await onExecute(skill, {
        file_name: uploadRes.file_name,
        file_size: uploadRes.file_size,
        file_url: uploadRes.file_url,
        file_path: uploadRes.file_path,
        content_type: uploadRes.content_type,
      });
      setResult(skillRes);
    } catch (e: any) {
      setError(e?.message || '上传失败');
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card className="p-6 max-w-lg mx-auto">
      <h2 className="text-lg font-semibold mb-4 text-gray-100">{config.label || '上传文件'}</h2>
      <div
        className="border-2 border-dashed border-dark-border rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 transition-colors mb-4"
        onClick={() => inputRef.current?.click()}
      >
        <input ref={inputRef} type="file" accept={config.accept} onChange={handleFile} className="hidden" />
        {file ? (
          <div className="space-y-2">
            <File className="w-8 h-8 mx-auto text-primary" />
            <p className="text-sm font-medium text-gray-200">{file.name}</p>
            <p className="text-xs text-gray-500">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
          </div>
        ) : (
          <div className="space-y-2">
            <Upload className="w-8 h-8 mx-auto text-gray-500" />
            <p className="text-sm text-gray-400">{config.hint || '点击选择文件'}</p>
          </div>
        )}
      </div>
      {error && <div className="flex items-center gap-2 text-red-400 text-sm mb-3"><AlertCircle className="w-4 h-4" />{error}</div>}
      {result && !result.error && (
        <div className="bg-green-500/10 border border-green-500/30 rounded p-3 text-sm text-green-400 mb-3">
          上传成功 {result.task_id ? `(任务ID: ${result.task_id})` : ''}
        </div>
      )}
      <Button variant="primary" onClick={handleUpload} loading={uploading} disabled={!file || uploading} className="w-full">
        {uploading ? '上传中...' : '开始上传'}
      </Button>
    </Card>
  );
};
