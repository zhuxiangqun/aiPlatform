import { useState } from 'react';
import { MessageSquare } from 'lucide-react';
import ClarifyDialog from './ClarifyDialog';

interface FloatingFeedbackProps {
  currentStep: string;
  autoValues?: Record<string, string>;
}

const STEP_MAP: Record<string, string> = {
  customers: '① 业务认知', capability: '② 评估域', assess: '③ 问题重构',
  poc: '④ 验证价值', deploy: '⑤ 快速构建', canary: '⑥ 评测护栏',
  accept: '⑦ 验收移交', evolution: '⑧ 运营监控',
};

const FloatingFeedback: React.FC<FloatingFeedbackProps> = ({ currentStep, autoValues }) => {
  const [open, setOpen] = useState(false);

  const handleSubmit = async (result: { conversation: any[]; summary: string; structured: any }) => {
    await fetch('/api/platform/apps/fde/feedback/submit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        step: currentStep,
        step_label: STEP_MAP[currentStep],
        conversation: result.conversation,
        summary: result.summary,
        structured: result.structured,
        customer_name: autoValues?.customer || '',
        customer_namespace: autoValues?.customer_ns || '',
        customer_deploy: autoValues?.customer_deploy || '',
        customer_industry: autoValues?.customer_industry || '',
        domain_id: autoValues?.domain || '',
        pipeline_state: {
          customer_name: autoValues?.customer || '',
          customer_ns: autoValues?.customer_ns || '',
          customer_deploy: autoValues?.customer_deploy || '',
          customer_industry: autoValues?.customer_industry || '',
          domain_id: autoValues?.domain || '',
        },
      }),
    });
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-50 flex items-center gap-2 px-4 py-2.5 
                   bg-blue-600 hover:bg-blue-500 text-white rounded-full shadow-lg 
                   transition-all hover:scale-105"
      >
        <MessageSquare className="w-4 h-4" />
        <span className="text-sm font-medium hidden sm:inline">反馈</span>
      </button>

      <ClarifyDialog
        open={open}
        onClose={() => setOpen(false)}
        context="feedback"
        title={`现场反馈 — ${STEP_MAP[currentStep] || '未知'}`}
        placeholder="遇到了什么问题？"
        extra={{ ...autoValues, _step: currentStep, _step_label: STEP_MAP[currentStep] || '',
          _pipeline_state: JSON.stringify({
            customer_name: autoValues?.customer || '',
            customer_desc: autoValues?.customer_desc || '',
            customer_deploy: autoValues?.customer_deploy || '',
            customer_ns: autoValues?.customer_ns || '',
            customer_industry: autoValues?.customer_industry || '',
            domain_id: autoValues?.domain || '',
            diagnosis_deep_problem: autoValues?.diagnosis || '',
            poc_profile: autoValues?.template || '',
            deploy_version: autoValues?.version || '',
          }),
          _workflow_stages: autoValues?._workflow_stages || [],
          _agent_id: autoValues?._agent_id || currentStep,
        }}
        onSubmit={handleSubmit}
      />
    </>
  );
};

export default FloatingFeedback;
