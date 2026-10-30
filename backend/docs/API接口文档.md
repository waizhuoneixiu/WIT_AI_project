# SteelScan 缺陷检测后端 API 接口文档

| 文档信息 | 内容 |
| --- | --- |
| 版本 | v1.1.0 |
| 生成日期 | 2026-10-30 |
| 服务 | SteelScan 热轧带钢表面缺陷检测 API |
| 模型 | **YOLO26n @ imgsz=640**（ultralytics **8.4.193**，PyTorch 2.14.1+cu130） |
| 规范文件 | `docs/openapi.json`（OpenAPI 3.1，可导入 Postman/Swagger/自动生成客户端） |
| 在线调试 | 启动服务后打开 `http://127.0.0.1:8000/docs` |

> 本文档只描述后端接口；前端/第三方按本文档对接即可。

---

## 1. 启动服务

```powershell
conda activate AIvision
cd "D:\Users\何ch\source\repos  AI\AIvision1"
python server.py --port 8000          # 默认 0.0.0.0:8000
# 可选：--host 127.0.0.1  --reload
```

- Base URL：`http://<服务器IP>:8000`
- 首次请求会加载模型（约 2~4 秒），之后常驻显存；服务启动时已做 warmup。

## 1.1 鉴权（可选，公网部署强烈建议开启）

服务端环境变量 `STEELSCAN_API_KEY` 为空时**不鉴权**（仅本机/内网调试）；设置后，以下接口需要请求头：

```
X-API-Key: <你设置的 Key>
```

| 接口 | 是否需要 Key |
| --- | --- |
| `/health`、`/classes`、`/docs` | 否 |
| `/model/info`、`/detect`、`/detect/batch`、`/detect/base64` | **是** |

- 未带或错误 Key → `401 {"detail": "无效或缺失 API Key（请求头 X-API-Key）"}`
- 可通过 `GET /health` 的 `auth_required` 字段判断服务端是否开启鉴权。
- 设置方式：`$env:STEELSCAN_API_KEY="your-key"`（PowerShell）/ `export STEELSCAN_API_KEY=...`（Linux）/ Docker 环境变量。

---

## 2. 模型与类别

| 项 | 值 |
| --- | --- |
| 模型 | YOLO26n（Ultralytics YOLO26 系列，COCO 预训练迁移） |
| 框架 | ultralytics 8.4.193 / PyTorch 2.14.1+cu130 |
| 输入尺寸 | 640×640（内部自动 letterbox） |
| 参数量 / 计算量 | 2.39M / 5.4 GFLOPs |
| 权重文件 | `models/best.pt`（5.25MB）、`models/best.onnx`（9.36MB） |
| 默认阈值 | conf=0.25，iou=0.45 |
| 设备 | GPU（RTX 5060 Laptop 8GB）；可在 `config.py` 改 `DEFAULT_DEVICE='cpu'` |

**类别表（对外 API 统一契约 class_id，见 04-shared-contract）**：

| id | name | 中文 | 说明 |
| --- | --- | --- | --- |
| 0 | crazing | 龟裂 / 网状裂纹 | 细网状裂纹（当前弱项） |
| 1 | inclusion | 夹杂 | 非金属夹杂 |
| 2 | patches | 斑块 | 表面斑块/色差 |
| 3 | pitted_surface | 麻点表面 | 点状凹坑 |
| 4 | rolled-in_scale | 轧入氧化皮 | 轧制氧化皮压入 |
| 5 | scratches | 划痕 | 线状划伤 |

> 模型训练原始顺序为 `rolled-in_scale, patches, crazing, pitted_surface, inclusion, scratches`（见 `/api/class-map`），
> 后端输出时已统一转换为上表契约 class_id，App/报告请按上表处理。

---

## 3. 接口总览

| 序号 | 方法 | 路径 | 功能 | Content-Type |
| --- | --- | --- | --- | --- |
| 1 | GET | `/health` | 健康检查 | — |
| 2 | GET | `/model/info` | 当前模型信息 | — |
| 3 | GET | `/classes` | 类别列表 | — |
| 4 | POST | `/detect` | 单图检测 | multipart/form-data |
| 5 | POST | `/detect/batch` | 批量检测 | multipart/form-data |
| 6 | POST | `/detect/base64` | Base64 检测 | application/json |

---

## 4. 接口详情

### 4.1 GET /health

健康检查，可用于探活/负载均衡。

**响应示例**
```json
{"status": "ok", "service": "steelscan-defect-api", "version": "1.1.0", "model_loaded": true, "auth_required": true}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| status | string | 固定 `ok` |
| service | string | 服务名 |
| version | string | 服务版本 |
| model_loaded | bool | 模型是否已加载（首次调用 `/model/info` 或 `/detect` 后为 true） |
| auth_required | bool | 服务端是否启用了 API Key 鉴权 |

---

### 4.2 GET /model/info

返回当前生效权重与推理配置。

**响应示例**
```json
{
  "weights": "D:\\Users\\何ch\\source\\repos  AI\\AIvision1\\runs\\n640\\weights\\best.pt",
  "weights_file": "best.pt",
  "imgsz": 640,
  "conf_threshold": 0.25,
  "iou_threshold": 0.45,
  "device": "0",
  "classes": {"0": "rolled-in_scale", "1": "patches", "2": "crazing",
              "3": "pitted_surface", "4": "inclusion", "5": "scratches"},
  "weights_size_mb": 5.5
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| weights | string | 权重绝对路径（选择优先级：`runs/*/weights/best.pt` 最新 → `config.BEST_WEIGHTS` → COCO 预训练） |
| weights_file | string | 权重文件名 |
| imgsz | int | 推理输入尺寸（默认 640） |
| conf_threshold | float | 默认置信度阈值 |
| iou_threshold | float | 默认 NMS IoU 阈值 |
| device | string | `"0"`=GPU0，`"cpu"`=CPU |
| classes | object | id → 英文类别名 |
| weights_size_mb | float | 权重大小（MB） |

---

### 4.3 GET /classes

**响应示例**
```json
{
  "classes": [
    {"id": 0, "name": "rolled-in_scale", "name_cn": "氧化铁皮压入"},
    {"id": 1, "name": "patches", "name_cn": "斑块"},
    {"id": 2, "name": "crazing", "name_cn": "龟裂"},
    {"id": 3, "name": "pitted_surface", "name_cn": "麻点/凹坑"},
    {"id": 4, "name": "inclusion", "name_cn": "夹杂"},
    {"id": 5, "name": "scratches", "name_cn": "划伤"}
  ]
}
```

---

### 4.4 POST /detect（单图检测）

**请求**：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| image | file | 是 | 图片文件，支持 jpg/jpeg/png/bmp |

**响应（200）**
```json
{
  "image": "<array>",
  "width": 200,
  "height": 200,
  "defect_count": 2,
  "defects": [
    {
      "class_id": 1,
      "class_name": "patches",
      "class_cn": "斑块",
      "confidence": 0.8832,
      "bbox_xyxy": [62.23, 68.4, 136.18, 160.79],
      "area_ratio": 0.1708,
      "width": 73.95,
      "height": 92.39
    }
  ],
  "inference_ms": 11.15,
  "model": "best.pt",
  "imgsz": 640,
  "filename": "patches_110.jpg",
  "elapsed_ms": 11.75
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| image | string | 传路径时为文件名；直接传数组/文件流时为 `"<array>"` |
| width / height | int | 原图宽高（像素） |
| defect_count | int | 检出缺陷数（按 conf 过滤后） |
| defects[] | array | 缺陷列表，按 confidence 降序 |
| defects[].class_id | int | 类别 id（见类别表） |
| defects[].class_name | string | 英文类别名 |
| defects[].class_cn | string | 中文类别名 |
| defects[].confidence | float | 置信度 0~1 |
| defects[].bbox_xyxy | float[4] | 检测框左上/右下坐标（像素，原图坐标系） |
| defects[].area_ratio | float | 框面积 / 图片面积 |
| defects[].width / height | float | 框宽高（像素） |
| inference_ms | float | 模型推理耗时（ms，不含网络/解码） |
| model | string | 权重文件名 |
| imgsz | int | 本次推理输入尺寸 |
| filename | string | 上传文件名 |
| elapsed_ms | float | 服务端处理总耗时（ms） |

**curl 示例**
```bash
curl -X POST http://127.0.0.1:8000/detect \
  -F "image=@data/neu_det/images/test/patches_110.jpg"
```

**PowerShell 示例**
```powershell
curl.exe -s -X POST http://127.0.0.1:8000/detect -F "image=@data/neu_det/images/test/patches_110.jpg"
```

---

### 4.5 POST /detect/batch（批量检测）

**请求**：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| images | file[] | 是 | 多张图片（同名字段可重复） |

**响应（200）**
```json
{
  "count": 2,
  "elapsed_ms": 34.2,
  "results": [
    { "...": "同 /detect 响应，单张一张" },
    { "...": "同 /detect 响应，单张一张" }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| count | int | 成功处理图片数 |
| elapsed_ms | float | 批处理总耗时（ms） |
| results | array | 每张图的结果（结构同 `/detect`） |

**curl 示例**
```bash
curl -X POST http://127.0.0.1:8000/detect/batch \
  -F "images=@a.jpg" -F "images=@b.jpg"
```

---

### 4.6 POST /detect/base64（Base64 检测）

**请求**：`application/json`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| image_base64 | string | 是 | 图片 base64；可带 `data:image/jpeg;base64,` 前缀 |
| filename | string | 否 | 文件名，默认 `base64_image.jpg` |
| conf | float | 否 | 覆盖默认置信度阈值 |
| imgsz | int | 否 | 覆盖默认输入尺寸 |

**请求示例**
```json
{
  "image_base64": "/9j/4AAQSkZJRgABAQ...",
  "filename": "test.jpg",
  "conf": 0.15
}
```

**响应**：同 `/detect`。

---

## 4.10 团队共同接口 `/api`（按 docs/plans/04-shared-contract.md 实现）

App 主流程使用这组接口；`/detect` 仅用于快速联调。所有 `/api` 接口在开启鉴权时同样需要 `X-API-Key`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/inspections` | 上传图片+批次号（form: image, batch_no, workpiece_no），检测并落库 |
| GET | `/api/inspections` | 历史查询（batch_no/class_id/review_status/page/page_size） |
| GET | `/api/inspections/{inspection_id}` | 检测详情（原图坐标框、timing、复核、标注图 URL） |
| GET | `/api/tasks/{task_id}` | 任务状态与结果（断线恢复） |
| POST | `/api/inspections/{inspection_id}/analysis` | 生成复检建议（facts/references/hypotheses/recheck_steps/missing_information） |
| POST | `/api/chat/messages` | 追问（context_type=inspection/batch, context_id, question） |
| POST | `/api/inspections/{inspection_id}/review` | 人工复核（review_status/reviewer/corrections/notes/base_version，版本冲突返回 409） |
| GET | `/api/batches/{batch_no}/summary` | 批次真实统计（图片数/模型框数/分类/复核状态） |
| GET | `/api/reports/{report_id 或 inspection_id}` | 报告（Markdown） |
| WS | `/ws/tasks/{task_id}` | 任务事件（accepted/completed） |
| GET | `/api/class-map` | 原始训练类别 → 契约类别映射 |

**POST /api/inspections 示例**

```bash
curl -X POST http://127.0.0.1:8000/api/inspections \
  -H "X-API-Key: 你的KEY" \
  -F "batch_no=BATCH-20261030-01" \
  -F "workpiece_no=W-0001" \
  -F "image=@test.jpg"
```

响应（201）：
```json
{"inspection_id": "INSP-...", "task_id": "TASK-...", "status": "completed",
 "detection_count": 2, "image_width": 200, "image_height": 200,
 "model_version": "best.pt", "timing": {"inference_ms": 12.3, "total_ms": 15.8}}
```

**GET /api/inspections/{id} 关键字段**

```json
{"inspection_id": "...", "batch_no": "...", "image_width": 200, "image_height": 200,
 "model_version": "best.pt",
 "detections": [{"detection_id": "DET-...", "class_id": 2, "class_name": "patches",
                 "score": 0.8832, "bbox_xyxy": [62.2, 68.4, 136.2, 160.8]}],
 "timing": {"inference_ms": 12.3, "total_ms": 15.8},
 "review_status": "pending", "review": null,
 "annotated_url": "/files/INSP-..._pred.jpg"}
```

> 数据库默认位于 `storage/steelscan.db`，图片/标注图在 `storage/images/`，可通过 `/files/<文件名>` 访问；
> 环境变量 `STEELSCAN_STORAGE_DIR` / `STEELSCAN_DB` 可覆盖路径。

---

## 5. 错误码

| HTTP 状态码 | 场景 | 响应示例 |
| --- | --- | --- |
| 200 | 成功 | 见上文 |
| 401 | 未带/错误 API Key（服务端已开启鉴权） | `{"detail": "无效或缺失 API Key（请求头 X-API-Key）"}` |
| 400 | 图片无法解码 / base64 解析失败 | `{"detail": "无法解码图片（请上传 jpg/png/bmp）"}` |
| 404 | 路径不存在 | `{"detail": "Not Found"}` |
| 422 | 请求参数校验失败（缺字段/类型错误） | `{"detail": [{"loc": ["body", "image_base64"], "msg": "field required"}]}` |
| 500 | 模型加载失败（权重缺失/显存不足） | 服务日志可见，响应 500 |

---

## 6. 性能与阈值建议

**时延基准**（RTX 5060 Laptop 8GB，100 张测试图，n640）：

| 设备 | 平均 | P50 | P95 | 估算 FPS |
| --- | --- | --- | --- | --- |
| GPU（CUDA） | 11.57 ms | 11.64 ms | 14.11 ms | 86.4 |
| CPU | 23.86 ms | 23.65 ms | 26.57 ms | 41.9 |

> 端到端 `/detect` HTTP 时延 ≈ 模型时延 + 图片解码/网络开销（实测热身后 11~13ms）。

**业务阈值**（n640，test 集，F1 最大在 conf=0.35）：

| conf | Precision | Recall | F1 |
| --- | --- | --- | --- |
| 0.10 | 0.505 | 0.828 | 0.627 |
| 0.20 | 0.662 | 0.752 | 0.705 |
| **0.35** | **0.810** | **0.669** | **0.733** |
| 0.50 | 0.879 | 0.570 | 0.692 |

- 工业场景更怕漏检：建议 NG 判定阈值用 **0.10~0.15**（Recall≈0.83），NG 结果再人工复判；
- 追求准确率/减少过杀：用 **0.35~0.50**；
- `/detect/base64` 支持每次请求传 `conf` 覆盖，`/detect` 可通过修改 `config.DEFAULT_CONF` 统一调整。

---

## 7. 备注

1. 支持格式：jpg / jpeg / png / bmp（OpenCV 可解码的格式均可）。
2. 图片建议：单张 ≤ 10MB；超大图会先 letterbox 到 imgsz=640 再推理，小目标建议提高 `imgsz` 或裁剪后检测。
3. 模型权重选择优先级：`runs/*/weights/best.pt` 中 mtime 最新 → `config.BEST_WEIGHTS` → `models/yolo26n.pt` 预训练；重训后重启服务即可自动生效。
4. 部署到 CPU 服务器：修改 `config.py` 的 `DEFAULT_DEVICE = 'cpu'`，或安装 onnxruntime 使用 `models/best.onnx`。
5. 数据集：NEU-DET（东北大学表面缺陷数据库，学术使用请引用 Song & Yan 2013 / He et al. 2020）。
6. 框架许可：ultralytics 为 AGPL-3.0，比赛演示使用无碍；若商业部署需评估授权。

---

## 8. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.2.0 | 2026-10-30 | 新增团队共同接口 `/api`（inspections/tasks/review/summary/reports/chat/analysis/WS/class-map）、SQLite 持久化；类别按 04-shared-contract 统一映射 |
| v1.1.0 | 2026-10-30 | 新增 API Key 鉴权（`X-API-Key`，`STEELSCAN_API_KEY` 开启）；`/health` 增加 `auth_required` |
| v1.0.0 | 2026-10-30 | 首个后端版本；YOLO26n@640；6 个接口；GPU 11.6ms / CPU 23.9ms |
