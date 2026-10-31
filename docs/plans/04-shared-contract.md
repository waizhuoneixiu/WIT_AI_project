# 共同接口与实现约定

更新日期：2026年10月30日。已有 FastAPI `/api` 业务接口、SQLite、DeepSeek/规则降级和魔搭 Gradio 检测；本轮先修订契约，再实现云适配和 Android App。**本轮补齐字段已有代码；2026-10-30无网络fixture验证了两轮完整复核、分析stale和报告历史，见[当前样例说明](../../backend/docs/api_samples/README.md)。这不代表真实云路径或Android已验收。**

## 1. 固定架构与类别

Android（KMP + Compose）通过同步 HTTP 访问本机轻量业务 API；业务 API 调用魔搭已部署的 YOLO26n@640（Ultralytics 8.4.193 导出 ONNX，云端运行）并在 SQLite 保存结果。分析/问答调用 DeepSeek 云 API，无 Key 或失败时明确降级规则模板。本机不安装 YOLO、PyTorch、ONNX Runtime 或本地大模型；云不可达时无离线检测。

魔搭仅提供 Gradio 检测：上传 → `/gradio_api/call/detect_ui` → SSE 取完成结果；它不提供业务 `/api`。前端不能直接使用魔搭地址替换业务 API 地址，魔搭和 DeepSeek 令牌只留后端。本轮默认 DETECTOR_PROVIDER=modelscope、LLM_PROVIDER=deepseek，魔搭云调用预算60秒，各阶段以剩余预算设置连接/读取超时；底层阻塞可能延至当前网络超时，并非强制取消的硬截止；模型标识为 yolo26n-640-onnx、imgsz固定640。部署事实见 [魔搭记录](../../backend/docs/魔搭部署记录.md)。

| class_id | class_name | 中文 |
|---:|---|---|
| 0 | crazing | 龟裂 / 网状裂纹 |
| 1 | inclusion | 夹杂 |
| 2 | patches | 斑块 |
| 3 | pitted_surface | 麻点表面 |
| 4 | rolled-in_scale | 轧入氧化皮 |
| 5 | scratches | 划痕 |

模型原始训练顺序不同，后端已映射为上表；前端不得再按训练编号重映射。`bbox_xyxy=[x1,y1,x2,y2]` 是统一方向后原图像素坐标、左上角原点。框不代表毫米尺寸或真实缺陷面积；空检出不是合格结论。

## 2. HTTP 主流程与状态

接口地址、类字段及基础响应以实际服务 OpenAPI 为准，现有响应样例见 [api_samples](../../backend/docs/api_samples/)。当前样例由明确标记的fixture生成，保留实际API响应形状；不能用于云服务可用性或模型精度证明。

| 方法与路径 | 本轮使用方式 |
|---|---|
| `GET /health`、`GET /model/info` | 业务与检测服务状态、部署和版本；健康响应不等于云推理已成功 |
| `POST /api/inspections` | multipart `image`、必填 `batch_no`、可选 `workpiece_no`；同步检测并保存，201 返回 inspection_id/task_id/status=completed |
| `GET /api/inspections` | batch_no/class_id/review_status/page/page_size 筛选分页；本轮修复 total 随筛选一致，不承诺时间筛选 |
| `GET /api/inspections/{id}` | 原预测、复核结果、原图、最新分析与版本；新增字段见下一节 |
| `GET /api/tasks/{task_id}` | 已知编号的最终任务快照；不保证未知上传的自动恢复 |
| `POST /api/inspections/{id}/analysis` | 同步返回 analysis 与 task_id，保留模型证据和对应复核版本 |
| `POST /api/chat/messages` | JSON context_type=inspection/batch、context_id、question；同步返回 answer/references/source/task_id/review_version/stale |
| `POST /api/inspections/{id}/review` | 保存完整复核差异与状态，必带 base_version；详见第4节 |
| `GET /api/batches/{batch_no}/summary` | image_count、model_box_count、per_class、review_stats、confirmed_count、unresolved_count |
| `GET /api/reports/{id}` | Markdown 报告 JSON：report_id、inspection_id、format、content_md、created_at；本轮补 review_version |
| `GET /api/class-map`、`GET /api/llm/info` | 类别映射、分析服务信息，不返回云令牌 |

批次号可包含斜杠，例如 `BATCH/2026-001`。客户端将完整批次号作为URL路径参数编码后请求汇总（如 `/api/batches/BATCH%2F2026-001/summary`）；服务端使用 `{batch_no:path}` 接收完整值。OpenAPI显示仍为 `{batch_no}`，不要据此截断或禁止斜杠；历史查询参数和聊天context_id保留同一完整批次号。

聊天回答和任务result的review_version是实际读取用于回答的图片复核版本，批次上下文为null；生成期间该图片复核版本变化时stale=true，前端提示依据已过时。

已有 WS `/ws/tasks/{task_id}` 在accept前校验X-API-Key；开启业务鉴权而Key缺失/错误时close 1008，正确时只回放 accepted/completed（无任务则 error），本轮 App 不依赖它；不实现 progress/analysis_chunk。UI 使用等待/成功/失败，不能把队列和流式状态写成已支持。

上传校验：jpg/jpeg/png/bmp，非空且不超过10MB，批次非空；解码或云调用失败不可生成成功记录。云模式请求非640输入尺寸返回422。开启业务鉴权时 /files 图片请求同样携带 X-API-Key。HTTP 400/422 表示输入问题，401 为业务鉴权错误，404 为不存在，409 为复核冲突；云503表示配置/魔搭鉴权问题，502表示上游网络或无效响应，504表示超时。上传结果未知时不自动重新 POST，先查询历史或由用户明确重试。

## 3. 详情、分析与统计

现有详情含 inspection_id、batch_no、workpiece_no、image_width/image_height、model_version、detections、timing、review_status、review、annotated_url、created_at。

本轮补齐：

- `original_url`：持久化、统一方向后的原图地址，前端用它与返回尺寸绘框。
- `review_version`：当前非负整数，未复核为0。
- `review_invalid`：历史复核差异损坏/非法时为true，详情回退原模型框以便人工修复；生成分析或报告返回409，提交合法完整差异或[]后恢复。
- `reviewed_detections`：对不可变 `detections` 应用最近一次完整差异后的有效框；无差异时与原预测相同。
- 有效框含 detection_id、class_id、class_name、bbox_xyxy、source；原框 source=model 且保留 score，人工新增/修改框 source=manual 且 score=null。
- `analysis`：最新分析对象或 null，保留 facts/references/hypotheses/recheck_steps/missing_information/source，附 review_version、stale、created_at。当前复核版本变化后旧分析 stale=true，不伪装成新结果。

复核状态独立于检测：pending/confirmed/corrected/unresolved。原模型 `detections` 永不覆盖。批次 `per_class` 和 `model_box_count` 仍统计原预测；`confirmed_count` 是 confirmed+corrected 的图片数，不是人工确认的缺陷框数。首轮不新增“复核后类别统计”。

报告必须明确区分原预测、人工结果与备注、复核版本、分析来源及其过时状态。`GET /api/reports/{inspection_id}` 按当前复核生成内容；已有 report_id 是对应版本的保存结果，不能把旧报告标成当前版本。

## 4. 完整框编辑与复核请求（本轮补齐）

`review_status`、`reviewer`、`notes` 保留；`base_version` 必填非负整数并与当前 review_version 匹配，否则422/409，不允许静默覆盖。

`corrections` 是**相对原始 detections 的完整差异集合**，不是相对上次复核的增量：

| op | 字段与含义 |
|---|---|
| add | 新 UUID detection_id、class_id、bbox_xyxy；增加人工框 |
| update | 原预测的 detection_id、class_id、bbox_xyxy；修改类别或位置 |
| delete | 原预测的 detection_id；移除该原框 |

示例（合成编号）：

```json
{
  "review_status": "corrected",
  "reviewer": "operator-1",
  "notes": "调整位置并补充漏检",
  "base_version": 0,
  "corrections": [
    {"op": "update", "detection_id": "DET-example", "class_id": 2, "bbox_xyxy": [20, 30, 80, 100]},
    {"op": "add", "detection_id": "e41c00b2-0ac6-4fd3-9932-6931b4d978ab", "class_id": 5, "bbox_xyxy": [110, 20, 130, 160]}
  ]
}
```

差异内 detection_id 唯一；update/delete 必须引用此图片原预测，add 不可占用原 ID。坐标必须为有限数且满足 `0 ≤ x1 < x2 ≤ image_width`、`0 ≤ y1 < y2 ≤ image_height`，class_id 必须0–5；后端验证，不能只信任界面。

再次编辑人工框时修改对应 add；删除人工框时从完整差异中移除该 add；恢复原框时移除对应 update/delete。兼容旧请求：无 op 的条目按 update；corrections 省略/null 保留最近差异，`[]` 显式恢复原预测。新 App 总是发送完整列表。

提交成功返回 inspection_id、review_status、review_version。保存后重新读取详情，验证 reviewed_detections 一致；409 保留草稿供比较，刷新后重新确认，不自动合并覆盖。

## 5. 协作与发布

先修文档，再实现云适配和 Android；不重新训练已有模型或下载本地模型。UI 编写前必须读取 [Aboard 设计参考](../../frontend/Aboard-design.md)。具体阶段见 [Roadmap](../roadmap.md)，检查见 [验收计划](05-integration-acceptance.md)。代码、接口样例和文档同步更新后才标记完成；历史模型/后端验证不能替代新路径验收。
