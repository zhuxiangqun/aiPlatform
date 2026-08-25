import React, { useState } from 'react';
import { Button, Card, Input } from '../ui';
import { Save, AlertCircle } from 'lucide-react';

interface FieldConfig {
  name: string;
  label: string;
  type: string;
  required?: boolean;
  hint?: string;
  options?: { label: string; value: string }[];
  min_length?: number;
  pattern?: string;
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
}

export const DataFormStage: React.FC<Props> = ({ config, onExecute, skill, projectId = '', onNext }) => {
  const [values, setValues] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState(config.tabs?.[0]?.key || '');

  const validate = (fields: FieldConfig[]) => {
    const errs: Record<string, string> = {};
    for (const f of fields) {
      const v = values[f.name];
      if (f.required && !v) errs[f.name] = '必填';
      if (f.min_length && v && v.length < f.min_length) errs[f.name] = `至少${f.min_length}位`;
      if (f.pattern && v && !new RegExp(f.pattern).test(v)) errs[f.name] = '格式不正确';
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (submitLabel?: string) => {
    const currentFields = activeTab
      ? config.tabs?.find(t => t.key === activeTab)?.fields
      : config.fields;
    if (!currentFields) return;
    if (!validate(currentFields)) return;

    setSubmitting(true);
    try {
      const resp = await onExecute(skill, values);
      onNext?.(resp);
    } catch { /* handled by parent */ }
    finally { setSubmitting(false); }
  };

  const renderFields = (fields: FieldConfig[]) => (
    <div className="space-y-3">
      {fields.map((f) => (
        <div key={f.name}>
          <label className="block text-xs text-gray-400 mb-1">
            {f.label} {f.required && <span className="text-red-400">*</span>}
          </label>
          {f.type === 'radio' && f.options ? (
            <div className="flex flex-wrap gap-2">
              {f.options.map(o => (
                <label key={o.value} className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs cursor-pointer border transition-colors ${
                  values[f.name] === o.value ? 'bg-primary/20 border-primary text-primary' : 'bg-dark-hover border-dark-border text-gray-300 hover:border-gray-500'
                }`}>
                  <input type="radio" name={f.name} value={o.value} checked={values[f.name] === o.value}
                    onChange={e => setValues(v => ({ ...v, [f.name]: e.target.value }))} className="hidden" />
                  {o.label}
                </label>
              ))}
            </div>
          ) : f.type === 'select' && f.options ? (
            <select
              value={values[f.name] || ''}
              onChange={e => setValues(v => ({ ...v, [f.name]: e.target.value }))}
              className="w-full px-3 py-1.5 rounded text-xs bg-dark-hover border border-dark-border text-gray-200 focus:outline-none focus:border-primary"
            >
              <option value="">{f.hint || '请选择...'}</option>
              {f.options.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          ) : f.type === 'textarea' ? (
            <textarea
              value={values[f.name] || ''}
              onChange={e => setValues(v => ({ ...v, [f.name]: e.target.value }))}
              placeholder={f.hint || ''}
              rows={f.min_length && f.min_length > 50 ? 6 : 3}
              className="w-full px-3 py-1.5 rounded text-xs bg-dark-hover border border-dark-border text-gray-200 focus:outline-none focus:border-primary resize-y"
            />
          ) : (
            <Input
              type={f.type === 'password' ? 'password' : f.type === 'email' ? 'email' : f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'}
              value={values[f.name] || ''}
              onChange={e => setValues(v => ({ ...v, [f.name]: e.target.value }))}
              placeholder={f.hint || ''}
              className="text-xs"
            />
          )}
          {errors[f.name] && <p className="text-[10px] text-red-400 mt-0.5">{errors[f.name]}</p>}
          {f.hint && !errors[f.name] && <p className="text-[10px] text-gray-500 mt-0.5">{f.hint}</p>}
        </div>
      ))}
    </div>
  );

  const currentTab = config.tabs?.find(t => t.key === activeTab);

  return (
    <Card className="p-4 space-y-3">
      {config.tabs ? (
        <>
          <div className="flex gap-1 border-b border-dark-border pb-2">
            {config.tabs.map(t => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={`text-xs px-3 py-1 rounded-t ${activeTab === t.key ? 'bg-dark-hover text-gray-100' : 'text-gray-500 hover:text-gray-300'}`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {currentTab?.fields && renderFields(currentTab.fields)}
          <Button variant="primary" size="sm" onClick={() => handleSubmit(currentTab?.submit_label)} loading={submitting} icon={<Save className="w-3.5 h-3.5" />}>
            {currentTab?.submit_label || '提交'}
          </Button>
        </>
      ) : (
        <>
          {config.fields && renderFields(config.fields)}
          <Button variant="primary" size="sm" onClick={() => handleSubmit(config.submit_label)} loading={submitting} icon={<Save className="w-3.5 h-3.5" />}>
            {config.submit_label || '提交'}
          </Button>
        </>
      )}
    </Card>
  );
};
