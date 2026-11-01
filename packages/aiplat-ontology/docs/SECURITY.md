# Ontology — security (D2 cohost)

- Deploy: **central cohost**（`hosted_by=aiplat`）；Chart `a3_process_split_authorized=false`  
- ACL：经 Identity / PolicyGate；禁止跨模块读表  
- 数据：`$AIPLAT_HOME/ontologies` + Graph/Wiki；无 Field 默认外传  
- 密钥：不在本包内嵌生产凭据  
- 拆分：未授权前不得宣称独立服务安全边界  

See [`D2_COHOST.md`](./D2_COHOST.md) · [`../a3/SPLIT_CHECKLIST.md`](./a3/SPLIT_CHECKLIST.md).
