# 钢见项目文档

当前基线：后端已有 YOLO26n@640 模型、FastAPI/SQLite 业务接口、DeepSeek 与规则降级，以及魔搭云推理部署记录。本轮先修正文档，再实施轻量云调用适配和 KMP Android 单图闭环；新增能力和设备验收不能由旧记录推定完成。

| 文档 | 用途 |
|---|---|
| [项目计划书](project-plan.md) | 场景、范围、实际技术路线、预算与参赛表达 |
| [Roadmap](roadmap.md) | 当前基线、里程碑与完成门槛 |
| [Plans索引](plans/README.md) | 工作包与执行顺序 |
| [模型与后端](plans/01-model-backend.md) | 沿用模型、云适配、复核与报告 |
| [KMP Android](plans/02-kmp-app.md) | 设计参考、采集、框编辑、网络和记录 |
| [文档、测试与答辩](plans/03-docs-validation-presentation.md) | 知识、模板、实验与参赛证据 |
| [共同接口约定](plans/04-shared-contract.md) | 同步HTTP、类别、复核差异和版本 |
| [联调与验收](plans/05-integration-acceptance.md) | 核心用例、证据与发布检查 |
| [2026-10-31验收记录](验收记录-2026-10-31.md) | 实际测试、模拟器操作与真实云验证边界 |
| [后端模型卡](../backend/docs/模型卡_n640.md) | 已有离线模型指标 |
| [魔搭部署记录](../backend/docs/魔搭部署记录.md) | 已有云服务地址和调用过程 |
| [UI设计参考](../frontend/Aboard-design.md) | UI代码编写前必须读取 |

技术规则以共同契约集中维护，运行字段以实际服务及其OpenAPI核对；本轮补齐字段已有代码，合成验证范围见验收计划；真实云和Android仍以独立证据确认。示例使用合成编号，旧样例的验证身份需保留，不能冒充当前App真实云调用。

密钥、私人配置和聊天凭据不进入公开文档；依赖、模型和数据来源分别登记。本轮不安装本地模型运行库，不重做已有模型训练。
