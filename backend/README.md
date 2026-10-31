# SteelScan 业务后端

Android App 通过本机 FastAPI + SQLite 调用魔搭上的 **YOLO26n@640**，分析和问答使用 DeepSeek 云 API；无 DeepSeek Key 时明确返回规则模板。魔搭只有检测能力，不能把它的地址直接填成 App 的业务后端地址。

本轮默认运行方式不安装 PyTorch、Ultralytics、ONNX Runtime、Transformers，也不下载任何模型。OpenCV/NumPy 仅用于图片解码、编码及绘制标注。

## 启动

使用 Python 3.12+，在 backend 目录执行：

```powershell
python -m venv .venv-api
.\.venv-api\Scripts\python.exe -m pip install -r requirements-api.txt
Copy-Item .env.example .env   # 仅首次；已有 .env 时不要覆盖
# 在 .env 中填写 MODELSCOPE_API_TOKEN，可选 DEEPSEEK_API_KEY，设置业务 STEELSCAN_API_KEY
.\.venv-api\Scripts\python.exe server.py --host 0.0.0.0 --port 8000
```

`.env` 在读取配置前加载，显式环境变量优先；私有 `.env`、SQLite、上传图片和虚拟环境不进 Git。

- API 文档：`http://127.0.0.1:8000/docs`
- Android 模拟器：`http://10.0.2.2:8000`
- 同一局域网手机：`http://<电脑局域网地址>:8000`，App 填业务 Key；调试包允许该明文连接。
- 原图与标注图 `/files/{filename}` 使用同样的 `X-API-Key` 鉴权，不把 Key 放在 URL。

## 配置

| 环境变量 | 默认值／用途 |
|---|---|
| `DETECTOR_PROVIDER` | `modelscope`；默认只调用云端。已有离线环境可显式设 `local`，云错误不自动回退 |
| `MODELSCOPE_BASE_URL` | `https://studio-waizhuoneixiu-steelscan-demo.api-inference.modelscope.net` |
| `MODELSCOPE_API_TOKEN` | 魔搭调用令牌，只留后端 |
| `MODELSCOPE_TIMEOUT` | `60` 秒，云调用预算；各阶段使用剩余预算作为网络超时并检查 SSE 心跳 |
| `STEELSCAN_API_KEY` | 业务 API 和图片鉴权；留空仅本机调试 |
| `LLM_PROVIDER` | `deepseek`；默认不选择本地大模型 |
| `DEEPSEEK_API_KEY` | 可选，留空或调用失败明确标记 `source=rule_fallback` |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | `https://api.deepseek.com` / `deepseek-chat` |
| `LLM_TIMEOUT` / `LLM_MAX_RETRIES` | `40` 秒 / `2` 次 |
| `STEELSCAN_STORAGE_DIR` / `STEELSCAN_DB` | 默认 `storage/` 和其中的 `steelscan.db` |

`GET /health` 表示业务进程存活；`detector_configured` 只表示后端配置了令牌，不保证令牌有效或云端此时可推理。`GET /model/info` 返回部署位置、固定模型版本和阈值，不触发模型加载。调用期间配置错误/上游鉴权失败返回503，网络或非法云响应返回502，超时返回504。

## 模型与云调用

模型训练版本为 YOLO26n@640、Ultralytics 8.4.193；当前云端运行 `best.onnx` CPU 推理。业务返回 `model_version=yolo26n-640-onnx`，它标识此已部署模型方案，不是权重文件哈希。

调用链：`/gradio_api/upload` → `/gradio_api/call/detect_ui` → SSE 完成结果。适配器只向 HTTPS 魔搭 API 域名发送令牌，拒绝重定向，验证返回尺寸、类别编号、分数及框边界。不会把服务失败变成“未检出”。

网络读写使用有限超时。底层连接正在阻塞时，预算到期需等待当前网络操作返回后处理；它不是精确到秒的强制取消任务。客户端超时后先查询历史，避免重复提交。

云模型固定 `imgsz=640`、`iou=0.45`；低层接口可调整 `conf`，其他尺寸或 IoU 返回422。六类对外编号为 **0 龟裂、1 夹杂、2 斑块、3 麻点、4 轧入氧化皮、5 划痕**；云端已从训练顺序转换，App 不再重映射。

魔搭地址与既往部署验证见 [魔搭部署记录](docs/魔搭部署记录.md)。既往模型卡和训练记录属于历史实验证据，不能作为本轮网络、App 或真实云调用已验收的证明。

## App 主接口

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/inspections` | image + batch_no + 可选 workpiece_no，同步检测并持久化 |
| GET | `/api/inspections` | 按批次、原模型类别、复核状态分页 |
| GET | `/api/inspections/{id}` | 原图、原预测、最新人工结果、复核版本和分析 |
| POST | `/api/inspections/{id}/review` | 完整复核差异；base_version 冲突返回409 |
| POST | `/api/inspections/{id}/analysis` | 复检建议，区分模型、人工与规则来源 |
| POST | `/api/chat/messages` | 当前图片／批次的上下文追问 |
| GET | `/api/tasks/{id}` | 已知编号的最终任务快照 |
| GET | `/api/batches/{batch_no}/summary` | 图片、原模型框及复核状态统计 |
| GET | `/api/reports/{id}` | 由当前记录生成或读取已保存的 Markdown 报告 |

完整契约见 [共同接口约定](../docs/plans/04-shared-contract.md)、[API 文档](docs/API接口文档.md) 和 [OpenAPI](docs/openapi.json)。低层 `/detect`、`/detect/batch`、`/detect/base64` 保留用于调试，App 使用持久化 `/api`。

当前检测、分析、问答同步完成才返回。WebSocket 仅回放 accepted/completed，App 不依赖流式进度。上传断网后先查历史，不能盲目重新 POST；可能已提交的复核先刷新版本。空结果显示“未检出六类目标缺陷”，不直接判合格。

## 验证

轻量自检不调用真实模型：

```powershell
.\.venv-api\Scripts\python.exe -m pip install pytest httpx
.\.venv-api\Scripts\python.exe scripts/test_cloud_adapter.py
.\.venv-api\Scripts\python.exe scripts/test_auth.py
.\.venv-api\Scripts\python.exe -m pytest scripts/test_review_workflow.py -q
```

真实联调需在后端私有配置填令牌，再从 App 上传明确标识的测试图片；DeepSeek 缺配置时仅验证规则降级。验收记录须区分模拟响应和真实云调用。

保留的 `requirements.txt`、`requirements-docker.txt`、训练脚本和旧模型验收脚本供原有模型开发环境使用，**本轮不要运行其安装命令**。旧交付 ZIP 为历史快照，不代表当前源码。

## 范围与来源

首版面向 NEU-DET 六类热轧带钢缺陷辅助质检。公开数据实验不能代替真实工位评价；边界框不是毫米尺寸或真实缺陷面积。

不实现批量 App、视频、完整 WebSocket 流、离线待上传队列或多端交付。保留已有显式 local 代码，但本轮不验证本地模型运行。

数据与权重来源见 [模型卡](docs/模型卡_n640.md)、[训练实验记录](docs/训练实验记录.md)。YOLO 实现采用 Ultralytics，需分别遵守代码、模型与数据的适用许可；FastAPI、Compose 等第三方来源见总计划。
