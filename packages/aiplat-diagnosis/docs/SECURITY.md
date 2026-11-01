# Diagnosis — security (D2 cohost)

- Deploy: **central cohost**；Chart `a3_process_split_authorized=false`  
- 数据：诊断 case / evidence / report；只读上游 Artifact；不写 Eval/Ontology 源库  
- **不自动修复**：无 `remediate`；`auto_execute=false`；`accuracy_claim=false`  
- 密钥：不在本包内嵌生产凭据  
- 拆分：未授权前不得宣称独立服务安全边界  

See [`D2_COHOST.md`](./D2_COHOST.md) · [`a3/SPLIT_CHECKLIST.md`](./a3/SPLIT_CHECKLIST.md).
