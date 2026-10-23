# 验收标准（夹具场景）

1. 可从 scenario → bundle_id → run_id → report_id 追溯。  
2. 诊断缺 Pi 或 Bundle 证据不得 status=ok。  
3. fp- 场景 signoff 无 evidence_report_ids 必须拒绝。  
4. Bundle 导出失败不得伪装成功；仅 thin。  
5. 故障注入四条（见 DESIGN）全部记录后方可宣称路径 E3 完成。  
