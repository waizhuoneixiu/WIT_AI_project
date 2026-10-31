# API 响应样例

本次导出模式：**合成夹具（fixture-not-yolo）；没有调用魔搭、DeepSeek或本地模型**。所有响应JSON由当前业务API的TestClient实际返回，不是手写响应；`*_request.json`是对应复核请求。记录仅存在于临时SQLite，导出结束后删除。

运行：`python scripts/export_api_samples.py --fixture`。去掉`--fixture`会调用真实魔搭，默认图片为部署包公开样例；两种模式均禁用大模型调用。

流程：初始检测/详情/分析（v0）→ update+add复核（v1）→ 旧分析stale与新分析/报告 → delete原框并保留add（v2）→ 旧分析stale、新分析、最终详情/报告与旧报告回读。`batch_summary`仍统计原模型框。`chat`及`chat_task`包含实际上下文review_version/stale，`chat_batch`的review_version为null。脚本对版本、不可变原预测、人工框分数、stale和报告历史作断言。

图片URL和记录编号仅是本次临时样例，不对应可访问的持久服务。合成结果不能用于模型精度、云连通性或Android设备验收；source=rule_fallback不能称为真实大模型生成。
