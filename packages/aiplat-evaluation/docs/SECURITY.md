# Evaluation — security (D2 cohost)

- Deploy: **central cohost**；Chart `a3_process_split_authorized=false`  
- 数据：评测任务/轨迹/报告；不读 FDE/Ontology 业务表（仅 API）  
- 报告 ≠ 客户签收（签收仍唯一在 FDE）  
- 密钥：不在本包内嵌生产凭据  
- 拆分：未授权前不得宣称独立服务安全边界  

See [`D2_COHOST.md`](./D2_COHOST.md) · [`../a3/SPLIT_CHECKLIST.md`](./a3/SPLIT_CHECKLIST.md).
