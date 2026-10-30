# backend（队员一：YOLO 模型与后端服务）

本目录是 WIT_AI_project 的**后端**：NEU-DET 六类钢材表面缺陷检测模型 + FastAPI 服务 + 团队共同接口（`/api`）+ 部署脚本。

> 依据：`docs/plans/01-model-backend.md`（队员一任务书）、`docs/plans/04-shared-contract.md`（共同接口约定）、`docs/plans/05-integration-acceptance.md`（联调验收）。

## 1. 当前状态（2026-10-30）

| 工作包 | 状态 | 说明 |
| --- | --- | --- |
| B-01 数据与环境核查 | ✅ | NEU-DET 官方检测版，1800 图/4189 框，逐类校验 0 异常；环境版本见 `docs/训练实验记录.md` |
| B-02 转换与冻结划分 | ✅ | VOC→YOLO；按类分层 70/15/15（1260/270/270），seed=0；清单 `docs/data_split_manifest.json` |
| B-03 YOLO 基线与选模 | ✅ | n320 / n320_pw / n640 三组实验；选 YOLO26n@640；权重 `models/best.pt`、`models/best.onnx` |
| B-04 合成接口与任务框架 | ✅ | 见下文 API 与 `docs/openapi.json`；任务状态 queued/running/completed/failed |
| B-05 真实检测 API | ✅ | `POST /api/inspections` 上传+检测+落库，原图像素坐标框、模型版本、任务查询 |
| B-06 记录与人工复核 | ✅（首版） | SQLite 保存记录/复核；复核 `base_version` 版本校验（409），原预测不被覆盖 |
| B-07 知识与大模型 | ⏳ 首版规则模板 | 分析/问答返回 facts/references/hypotheses/recheck_steps/missing_information；大模型接入预留（后续接 DeepSeek/OpenAI） |
| B-08 WebSocket | ⏳ 首版 | `/ws/tasks/{task_id}` 推送 accepted/completed；断线恢复走 `GET /api/tasks/{id}` |
| B-09 批次统计与报告 | ✅（首版） | `/api/batches/{no}/summary` 真实统计；`/api/reports/{id}` Markdown 报告 |
| B-10 部署与服务配置 | ✅ | 本地脚本 / Docker / 魔搭 Gradio 演示包（见 `deploy/`） |
| B-11 模型与流程评价 | ✅ | 测试集指标、时延、阈值、失败样例见 `docs/训练实验记录.md` |
| B-12 交付与演示恢复 | ⏳ | 启动/故障恢复说明见本 README 与 `deploy/`；演示前按需补充演练记录 |

## 2. 快速开始

```powershell
# 环境：conda env AIvision（Python 3.12 / torch 2.14.1+cu130 / ultralytics 8.4.193）
conda activate AIvision
cd backend
pip install -r requirements.txt                # 若尚未安装（GPU 环境）
python server.py --port 8000                   # 或 .\deploy\run_server.ps1
# Swagger: http://127.0.0.1:8000/docs
```

开启鉴权（公网/共享时必开）：

```powershell
$env:STEELSCAN_API_KEY = "换一个随机 Key"
python server.py --port 8000
# 调用时加请求头 X-API-Key: <key>
```

自检：

```powershell
python scripts/smoke_test_backend.py     # 环境/低层接口/文档
python scripts/test_auth.py              # API Key 401/200
python scripts/test_api_contract.py      # /api 端到端：检测→任务→详情→分析→问答→复核→统计→报告→WS
```

## 3. 模型与数据

| 项 | 值 |
| --- | --- |
| 模型 | **YOLO26n @ imgsz=640**（ultralytics 8.4.193，COCO 预训练迁移） |
| 规模 | 2.39M 参数 / 5.4 GFLOPs；best.pt 5.25MB，best.onnx 9.36MB |
| 数据 | NEU-DET 热轧带钢表面缺陷（1800 张 200×200，6 类，4189 框） |
| 划分 | 1260/270/270（按类分层，seed=0），清单 `docs/data_split_manifest.json` |
| 测试集指标 | mAP50 **0.8057** / mAP50-95 **0.4669** / Recall **0.7656** / 图片级漏检率 2.59% |
| 时延 | GPU 11.57ms / CPU 23.86ms（100 张均值；P95 14.11ms） |
| 弱项 | crazing 龟裂 AP50 0.49（细线状、类内差异大） |

### 类别映射（重要）

App/报告统一使用**契约 class_id**（`docs/plans/04-shared-contract.md`）：

| class_id | 名称 | 中文 |
| ---: | --- | --- |
| 0 | crazing | 龟裂 / 网状裂纹 |
| 1 | inclusion | 夹杂 |
| 2 | patches | 斑块 |
| 3 | pitted_surface | 麻点表面 |
| 4 | rolled-in_scale | 轧入氧化皮 |
| 5 | scratches | 划痕 |

模型训练原始顺序为 `rolled-in_scale, patches, crazing, pitted_surface, inclusion, scratches`，
后端输出时已自动映射；可用 `GET /api/class-map` 查看完整映射。

## 4. 接口

### 4.1 团队共同接口（App 主流程）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/inspections` | form: `image` + `batch_no` + `workpiece_no` → `inspection_id`/`task_id` |
| GET | `/api/inspections` | 历史（batch_no/class_id/review_status/page/page_size） |
| GET | `/api/inspections/{inspection_id}` | 详情（原图坐标框/timing/复核/annotated_url） |
| GET | `/api/tasks/{task_id}` | 任务状态与结果（断线恢复） |
| POST | `/api/inspections/{id}/analysis` | 复检建议（事实/引用/原因/步骤/待补信息） |
| POST | `/api/chat/messages` | 追问（context_type + context_id + question） |
| POST | `/api/inspections/{id}/review` | 人工复核；`base_version` 过期返回 409 |
| GET | `/api/batches/{batch_no}/summary` | 批次统计（图片数/模型框数/分类/复核状态） |
| GET | `/api/reports/{id}` | Markdown 报告 |
| WS | `/ws/tasks/{task_id}` | accepted/completed 事件 |
| GET | `/api/class-map` | 训练类别 ↔ 契约类别映射 |

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/inspections \
  -H "X-API-Key: 你的KEY" \
  -F "batch_no=BATCH-001" -F "workpiece_no=W-0001" \
  -F "image=@test.jpg"
```

### 4.2 低层检测接口（快速联调/演示）

`GET /health`、`GET /classes`、`GET /model/info`、`POST /detect`、`POST /detect/batch`、`POST /detect/base64`；
静态标注图：`/files/<inspection_id>_pred.jpg`。

完整字段见：**[docs/API接口文档.md](docs/API接口文档.md)**、**[docs/队友API调用文档.md](docs/队友API调用文档.md)**、OpenAPI：[docs/openapi.json](docs/openapi.json)。

## 5. 目录结构

```
backend/
├─ server.py              # FastAPI 入口（低层接口 + /api 路由 + /files 静态图）
├─ detector.py            # YOLO26n 检测封装（类别映射到契约 class_id）
├─ contract.py            # 类别契约与映射
├─ api_v1.py              # 团队共同接口（inspections/tasks/review/.../WS）
├─ storage.py             # SQLite 持久化（inspections/detections/tasks/reviews/reports/chats）
├─ runtime.py / security.py / config.py
├─ scripts/               # 数据转换/训练/评测/基准/阈值/自检/导出
├─ models/                # best.pt / best.onnx
├─ docs/                  # 接口文档、队友对接、内网穿透、训练记录、划分清单、模型卡、OpenAPI
└─ deploy/                # 本地启动脚本 + 魔搭创空间 Gradio 部署包
```

## 6. 部署

- **本地工位**：`python server.py --port 8000` 或 `.\deploy\run_server.ps1`（断外网仍可检测）。
- **Docker（云服务器）**：
  ```bash
  docker build -t steelscan-api:1.2 .
  docker run -d --name steelscan-api -p 8000:8000 \
    -e STEELSCAN_API_KEY=你的KEY steelscan-api:1.2
  ```
- **魔搭创空间（演示页）**：`deploy/modelscope_package/`（ONNX CPU 推理，无需 PyTorch），上传后自动运行得到公网链接；步骤见包内 `README_部署说明.md`。
- **队友临时联调**：`docs/内网穿透联调步骤.md`（cpolar / ngrok / 花生壳）。

## 7. 配置与安全

| 环境变量 | 说明 |
| --- | --- |
| `STEELSCAN_API_KEY` | 设置后 `/api*`、`/detect*`、`/model/info` 需要请求头 `X-API-Key` |
| `STEELSCAN_STORAGE_DIR` | SQLite 与图片存储目录（默认 `storage/`） |
| `STEELSCAN_DB` | SQLite 文件路径 |
| `PORT` | `deploy/run_server.sh` 使用的端口 |

- 密钥只放环境变量/`.env`，不要提交；`.gitignore` 已忽略 `.env`、`storage/`。
- 比赛材料/公开仓库不包含真实密钥、聊天凭据或私人联系方式。

## 8. 已知限制与下一步

1. 大模型分析/问答当前为**规则模板**（不伪称实时大模型结果）；接口结构已按契约定义，后续接入 DeepSeek/OpenAI 时替换 `api_v1.py` 中的 `_analysis_for` / `_answer_question`。
2. WebSocket 首版只推送最终事件，完整 progress/analysis_chunk 流式待补。
3. `crazing` 弱项：建议后续 960/1280 分辨率、切片推理（SAHI）或现场真实样本补充。
4. 批量检测（`/detect/batch`）为同步顺序处理，大文件量需改异步任务。
5. 模型训练原始类别顺序与契约不同，**已通过后端映射**；若后续重训，建议直接按契约顺序重排标签以消除映射层。

## 9. 引用与许可

- 数据：NEU surface defect database（东北大学），学术使用请引用 Song & Yan, Applied Surface Science 285 (2013) 858-864；He et al., IEEE TIM 69(4) (2020) 1493-1504。
- 框架：ultralytics YOLO26（AGPL-3.0）；比赛演示使用无碍，商业部署需评估授权。
