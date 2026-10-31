# SteelScan 业务 API 对接说明

更新日期：2026年10月30日。后端现有基础接口已实现；**本轮云适配、完整框复核和详情/报告新增字段按[共同契约](../../docs/plans/04-shared-contract.md)实施，已落地代码并通过本轮fixture业务流程，真实云与Android仍须分别验收。** 本文不是新增功能已上线的证明。

## 1. 连接与运行

Android 使用本机轻量 FastAPI 业务地址 `http://<电脑局域网IP>:8000`；模拟器访问宿主通常使用 `http://10.0.2.2:8000`。具体启动和依赖以[后端README](../README.md)为准。不要使用其他开发者的绝对路径或虚构 Conda 环境。

业务 API 调用魔搭云推理，并在本机 SQLite 保存原图、结果与复核；魔搭本身只提供 Gradio 检测，不承载 `/api/inspections` 等业务接口。本轮不安装本地 YOLO、PyTorch、ONNX Runtime 或本地大模型依赖。

| 后端配置 | 本轮默认/用途 |
|---|---|
| `DETECTOR_PROVIDER` | `modelscope` |
| `MODELSCOPE_BASE_URL` | `https://studio-waizhuoneixiu-steelscan-demo.api-inference.modelscope.net` |
| `MODELSCOPE_API_TOKEN` | 魔搭访问令牌，仅后端私有配置 |
| `MODELSCOPE_TIMEOUT` | 60秒云调用预算；各阶段用剩余预算设置连接/读取超时，底层阻塞可能延至当前网络超时，并非强制取消硬截止 |
| `LLM_PROVIDER` | `deepseek`；无Key或失败返回规则模板 |
| `DEEPSEEK_API_KEY` | DeepSeek令牌，仅后端私有配置 |
| `STEELSCAN_API_KEY` | 可选业务访问Key，客户端通过 `X-API-Key` 发送 |
| `STEELSCAN_STORAGE_DIR` / `STEELSCAN_DB` | 本机图片/SQLite位置 |

开启业务鉴权时 `/api*`、`/detect*`、`/model/info` 以及本轮补齐保护的 `/files/*` 都带 `X-API-Key`。`/health`、`/classes` 可用于连接诊断。图片加载与报告请求同样使用业务Key；云令牌不能进入App、URL、日志或公开示例。

## 2. 模型、类别与坐标

当前模型 **YOLO26n@640**，训练框架 Ultralytics 8.4.193；魔搭运行 `best.onnx`，业务响应模型标识本轮固定为 `yolo26n-640-onnx`。输入尺寸固定640、默认conf=0.25；本地GPU基准不是云端请求时延。

| class_id | class_name | 中文 |
|---:|---|---|
| 0 | crazing | 龟裂 / 网状裂纹 |
| 1 | inclusion | 夹杂 |
| 2 | patches | 斑块 |
| 3 | pitted_surface | 麻点表面 |
| 4 | rolled-in_scale | 轧入氧化皮 |
| 5 | scratches | 划痕 |

原训练类别顺序不同，后端已映射；包括低层 `/detect` 在内的对外结果都使用上表，不再映射一次。`bbox_xyxy` 是统一方向后原图像素坐标，不是640画布坐标或毫米尺寸。零框显示“未检出六类目标缺陷”，不表示合格。

## 3. Android 主流程

| 方法与路径 | 请求/响应要点 |
|---|---|
| `POST /api/inspections` | multipart `image`、必填非空 `batch_no`、可选 `workpiece_no`；201返回 inspection_id/task_id/status=completed |
| `GET /api/inspections` | batch_no/class_id/review_status/page/page_size；返回total/page/page_size/items，total按相同条件过滤 |
| `GET /api/inspections/{id}` | 原预测、有效复核框、图像URL、复核版本及最新分析 |
| `GET /api/tasks/{task_id}` | 已返回编号的任务最终状态/结果 |
| `POST /api/inspections/{id}/analysis` | 可选note；同步返回analysis/task_id/status |
| `POST /api/chat/messages` | context_type=inspection/batch、context_id、question；同步返回answer/references/source/task_id/review_version/stale |
| `POST /api/inspections/{id}/review` | review_status、reviewer、notes、必填base_version、完整corrections；成功返回新review_version |
| `GET /api/batches/{batch_no}/summary` | 图片、原模型框、原预测类别和图片复核状态统计 |
| `GET /api/reports/{inspection_id或report_id}` | format=md、content_md、report_id、inspection_id、review_version、created_at |
| `GET /api/class-map`、`GET /api/llm/info` | 类别映射、分析服务来源和状态 |

批次号允许含斜杠；汇总路径中的完整值需URL编码，例如 `BATCH/2026-001` 请求 `/api/batches/BATCH%2F2026-001/summary`。服务端使用 `{batch_no:path}`，但OpenAPI路径仍显示 `{batch_no}`；历史筛选和chat context_id使用相同完整批次号。

这些接口同步等待完成，不返回真实进度流。已有 `/ws/tasks/{task_id}` 在accept前校验X-API-Key，开启业务鉴权时缺失/错误Key以1008关闭；正确Key仅回放 accepted/completed，App无需连接；不依赖不存在的 progress/analysis_chunk。

```bash
curl -X POST http://127.0.0.1:8000/api/inspections \
  -H "X-API-Key: <业务KEY>" \
  -F "batch_no=BATCH-001" -F "workpiece_no=W-001" -F "image=@test.jpg"
```

成功上传后保存inspection_id，查询详情绘图。上传响应丢失且没有编号时不盲目自动重发，先查询历史或用户明确重试，避免重复记录。

### 详情新增字段（本轮补齐）

`detections` 是不可变原预测，每项包含detection_id/class_id/class_name/score/bbox_xyxy；现有尺寸、批次、timing、annotated_url、created_at等字段保留。

| 字段 | 语义 |
|---|---|
| `original_url` | 统一方向后原图地址，与image_width/image_height一致 |
| `review_version` | 当前复核版本，初始0 |
| `review_invalid` | 历史非法复核返回true并回退原预测；分析/报告409，重新合法复核后恢复 |
| `reviewed_detections` | 原预测应用最近完整差异后的有效框 |
| `reviewed_detections[].source` | model/manual；新增或修改为manual且score=null |
| `analysis` | 最新分析对象或null，含review_version/stale/created_at及分析内容 |

复核状态为pending/confirmed/corrected/unresolved。分析内容包含facts/references/hypotheses/recheck_steps/missing_information，source区分deepseek或rule_fallback（历史local-deepseek可读取）。复核版本变化后旧分析stale=true；前端允许重新生成，不能把它标为当前结果。

### 完整复核差异（本轮补齐）

`base_version` 必填非负整数，必须等于当前review_version；不匹配返回409。每次发送相对**原始detections**的完整差异，详细校验和样例见[共同契约第4节](../../docs/plans/04-shared-contract.md#4-完整框编辑与复核请求本轮补齐)。

- add：新UUID detection_id、class_id、bbox_xyxy。
- update：原预测detection_id、class_id、bbox_xyxy。
- delete：原预测detection_id。
- 坐标为有限数、在图内且面积大于0，类别0–5，ID不能重复或引用其他记录。
- 再次编辑人工框修改add；删除人工框移除add；恢复原框移除对应update/delete。
- 兼容旧无op条目为update；corrections省略/null保留最近差异，`[]`恢复原预测。新App总是发送完整列表。

409后保留草稿供比较并刷新详情，由人工重新确认；不要跳过版本号强制覆盖。

聊天回答及其任务result附带实际用于回答的review_version；图片上下文为整数，批次上下文为null。若回答生成期间图片已被复核，stale=true；前端应提示依据已过时，不把旧版本回答标为最新。

### 统计与报告

`image_count`为图片数，`model_box_count`和`per_class`为原模型预测，`confirmed_count`为confirmed+corrected图片数；不把它们当作人工确认框数量或产线合格率。

以inspection_id获取当前版本Markdown；以已有report_id获取其保存版本。报告区分原预测、有效复核、备注、review_version和分析来源/过时状态。Android保存`.md`或系统分享，不另造PDF/Excel导出。

## 4. 保留的低层检测接口

| 接口 | 用途 |
|---|---|
| `GET /health` | 业务服务状态与配置；成功不证明云推理实时可用 |
| `GET /classes` | 契约类别列表 |
| `GET /model/info` | 检测provider、模型和640输入信息，不泄露本机私有路径 |
| `POST /detect` | multipart image，返回width/height/defect_count/defects/inference_ms/model/imgsz等 |
| `POST /detect/batch` | multipart images，多图顺序处理；不是首期App主流程 |
| `POST /detect/base64` | image_base64、可选filename/conf/imgsz；云模式imgsz非640返回422 |

低层结果使用confidence，业务详情转换为score；不要混用两种DTO。上传仅jpg/jpeg/png/bmp、非空、单图≤10MB，必须可解码。低层接口不提供业务复核与历史闭环，正式App使用`/api/inspections`。

## 5. 错误与验证

| 状态 | 处理 |
|---|---|
| 400/422 | 图片或字段错误，修正后再提交 |
| 401 | 业务Key错误；云令牌错误由后端处理，不索要给App |
| 404 | 记录/报告不存在，返回列表刷新 |
| 409 | 复核版本冲突，刷新并人工重新确认 |
| 503 | 云配置或魔搭鉴权问题，由后端修正配置 |
| 502 | 上游网络或无效响应，显示失败与重试 |
| 504 | 云调用超时，先查历史；不能用空框表示失败 |

错误信息只说明处理方式，不返回云凭据。验证清单见[联调验收](../../docs/plans/05-integration-acceptance.md)。[当前样例](api_samples/README.md)已用明确fixture模式导出，[OpenAPI](openapi.json)已更新；本轮合成验证见联调验收，既有[验收记录](验收记录.md)不代表Android或新云路径已经通过。

模型离线指标见[模型卡](模型卡_n640.md)，云部署记录见[魔搭部署记录](魔搭部署记录.md)。默认阈值保持0.25；不同阈值实验不能直接转为自动合格/判废规则，也不能用测试集结果反复调参。
