# 测试文档导航（As-Is 对齐）

> 说明：本文件为测试文档导航页；测试真值以 `infra/tests/*` 的实际可运行性为准。

> 快速找到所需的测试文档

---

## 🎯 我是...

### 👨‍💻 开发者（快速开始）
→ [TESTING_QUICKSTART.md](TESTING_QUICKSTART.md) - 5分钟上手测试

### 👩‍🔬 测试工程师（详细指南）
→ [INFRA_DETAILED_TESTING_GUIDE.md](INFRA_DETAILED_TESTING_GUIDE.md) - 完整测试策略

### 🏗️ 架构师（系统设计）
→ [测试架构](INFRA_DETAILED_TESTING_GUIDE.md#系统架构概览)

### 👷 运维（CI/CD）
→ [CI/CD集成](INFRA_DETAILED_TESTING_GUIDE.md#cicd集成)

---

## 📊 测试状态

查看最新测试结果：[测试报告目录](reports/)

---

## 📚 文档结构

```
docs/testing/
├── index.md                          ← 你在这里
├── TESTING_QUICKSTART.md             ← 快速开始（推荐）
├── INFRA_DETAILED_TESTING_GUIDE.md   ← 完整指南
├── TESTING_GUIDE.md                  ← 最佳实践
├── TESTING_CHECKLIST.md              ← 检查清单
│
└── reports/                           ← 测试报告
    ├── DATABASE_INTEGRATION_REPORT.md
    ├── MESSAGING_INTEGRATION_REPORT.md
    ├── INTEGRATION_TESTS_SUMMARY.md
    └── TESTCONTAINERS_FINAL_REPORT.md
```

---

**返回**: [基础设施层文档](../index.md)
