import React, { useState } from 'react';
import { Button, Card, Input } from '../ui';
import { Save } from 'lucide-react';

interface FieldConfig {
  name: string;
  label: string;
  type: string;
  required?: boolean;
  hint?: string;
  placeholder?: string;
  options?: { label: string; value: string }[];
  min_length?: number;
  pattern?: string;
  /** 仅当 values 匹配时显示，如 { source_type: "url" } */
  show_when?: Record<string, string>;
}

interface StageConfig {
  fields?: FieldConfig[];
  tabs?: {
    key: string;
    label: string;
    fields?: FieldConfig[];
    submit_label?: string;
  }[];
  submit_label?: string;
  success_action?: string;
}

interface Props {
  config: StageConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  projectId?: string;
  onNext?: (result: any) => void;
  onComplete?: (result: any) => void;
}

function isUploadSource(values: Record<string, any>): boolean {
  const t = String(values.source_type || values.source || '').toLowerCase();
  return (
    t === 'upload' ||
    t === 'local' ||
    t === 'file' ||
    t === 'local_file' ||
    t === '本地上传' ||
    t.includes('local') ||
    t.includes('upload') ||
    t.includes('file')
  );
}

function isUrlLikeField(f: FieldConfig): boolean {
  if (f.type === 'url') return true;
  const n = f.name.toLowerCase();
  return n.includes('url') || n.includes('link') || n === 'video_url' || n === 'source_url';
}

export const DataFormStage: React.FC<Props> = ({
  config,
  onExecute,
  skill,
  onNext,
  onComplete,
}) => {
  const [values, setValues] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState(config.tabs?.[0]?.key || '');

  const advance = onNext || onComplete;

  const visibleFields = (fields: FieldConfig[]) =>
    fields.filter((f) => {
      if (f.show_when) {
        return Object.entries(f.show_when).every(([k, v]) => String(values[k] ?? '') === String(v));
      }
      // 无 show_when 时：选「本地上传」则隐藏 URL 类字段，避免误填/误校验
      if (isUploadSource(values) && isUrlLikeField(f)) return false;
      return true;
    });

  const validate = (fields: FieldConfig[]) => {
    const errs: Record<string, string> = {};
    const shown = visibleFields(fields);
    for (const f of shown) {
      const v = values[f.name];
      const required =
        f.required ||
        // URL 路径下 URL 字段视为必填（即使 JSON 里 required=false）
        (!isUploadSource(values) && isUrlLikeField(f));
      if (required && !v) errs[f.name] = '必填';
      if (f.min_length && v && String(v).length < f.min_length) errs[f.name] = `至少${f.min_length}位`;
      if (f.pattern && v && !new RegExp(f.pattern).test(String(v))) errs[f.name] = '格式不正确';
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async () => {
    const currentFields = activeTab
      ? config.tabs?.find((t) => t.key === activeTab)?.fields
      : config.fields;
    if (!currentFields) return;
    if (!validate(currentFields)) return;

    setSubmitting(true);
    try {
      // 本地上传：本步只确认来源，进入下一阶段 file_upload，不在此调 skill
      if (isUploadSource(values)) {
        advance?.({ ...values, source_type: values.source_type || 'upload' });
        return;
      }

      const resp = await onExecute(skill, values);
      advance?.({ ...values, ...resp, source_type: values.source_type || 'url' });
    } catch {
      /* handled by parent / toast */
    } finally {
      setSubmitting(false);
    }
  };

  const renderFields = (fields: FieldConfig[]) => (
    <div className="space-y-3">
      {visibleFields(fields).map((f) => (
        <div key={f.name}>
          <label className="block text-xs text-gray-400 mb-1">
            {f.label}{' '}
            {(f.required || (!isUploadSource(values) && isUrlLikeField(f))) && (
              <span className="text-red-400">*</span>
            )}
          </label>
          {f.type === 'radio' && f.options ? (
            <div className="flex flex-wrap gap-2">
              {f.options.map((o) => (
                <label
                  key={o.value}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs cursor-pointer border transition-colors ${
                    values[f.name] === o.value
                      ? 'bg-primary/20 border-primary text-primary'
                      : 'bg-dark-hover border-dark-border text-gray-300 hover:border-gray-500'
                  }`}
                >
                  <input
                    type="radio"
                    name={f.name}
                    value={o.value}
                    checked={values[f.name] === o.value}
                    onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                    className="hidden"
                  />
                  {o.label}
                </label>
              ))}
            </div>
          ) : f.type === 'select' && f.options ? (
            <select
              value={values[f.name] || ''}
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
              className="w-full px-3 py-1.5 rounded text-xs bg-dark-hover border border-dark-border text-gray-200 focus:outline-none focus:border-primary"
            >
              <option value="">{f.hint || '请选择...'}</option>
              {f.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : f.type === 'textarea' ? (
            <textarea
              value={values[f.name] || ''}
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
              placeholder={f.placeholder || f.hint || ''}
              rows={f.min_length && f.min_length > 50 ? 6 : 3}
              className="w-full px-3 py-1.5 rounded text-xs bg-dark-hover border border-dark-border text-gray-200 focus:outline-none focus:border-primary resize-y"
            />
          ) : (
            <Input
              type={
                f.type === 'password'
                  ? 'password'
                  : f.type === 'email'
                    ? 'email'
                    : f.type === 'number'
                      ? 'number'
                      : f.type === 'date'
                        ? 'date'
                        : f.type === 'url'
                          ? 'url'
                          : 'text'
              }
              value={values[f.name] || ''}
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
              placeholder={f.placeholder || f.hint || ''}
              className="text-xs"
            />
          )}
          {errors[f.name] && <p className="text-[10px] text-red-400 mt-0.5">{errors[f.name]}</p>}
          {f.hint && !errors[f.name] && <p className="text-[10px] text-gray-500 mt-0.5">{f.hint}</p>}
        </div>
      ))}
    </div>
  );

  const currentTab = config.tabs?.find((t) => t.key === activeTab);
  const submitLabel = isUploadSource(values)
    ? '下一步：上传文件'
    : currentTab?.submit_label || config.submit_label || '提交';

  return (
    <Card className="p-4 space-y-3">
      {config.tabs ? (
        <>
          <div className="flex gap-1 border-b border-dark-border pb-2">
            {config.tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={`text-xs px-3 py-1 rounded-t ${
                  activeTab === t.key ? 'bg-dark-hover text-gray-100' : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {currentTab?.fields && renderFields(currentTab.fields)}
          <Button
            variant="primary"
            size="sm"
            onClick={() => handleSubmit()}
            loading={submitting}
            icon={<Save className="w-3.5 h-3.5" />}
          >
            {submitLabel}
          </Button>
        </>
      ) : (
        <>
          {config.fields && renderFields(config.fields)}
          <Button
            variant="primary"
            size="sm"
            onClick={() => handleSubmit()}
            loading={submitting}
            icon={<Save className="w-3.5 h-3.5" />}
          >
            {submitLabel}
          </Button>
        </>
      )}
    </Card>
  );
};
