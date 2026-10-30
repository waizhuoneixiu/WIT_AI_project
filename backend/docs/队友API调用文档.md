# SteelScan 缺陷检测 API —— 队友对接文档

> 版本：v1.1.0（2026-10-30）  
> 适用：负责前端页面 / 智能体 / 演示视频的同学  
> 详细字段定义见：`docs/API接口文档.md`；交互式调试见：服务地址 + `/docs`

---

## 1. 你会拿到什么

找队长要两样东西：

1. **服务地址**（`BASE_URL`）：例如
   - 本机：`http://127.0.0.1:8000`
   - 内网穿透：`https://xxxx.cpolar.cn` 或 `https://xxxx.ngrok-free.app`
   - 云服务器：`http://服务器公网IP:8000`
2. **API Key**（如果服务端启用了鉴权）：放在请求头 `X-API-Key: <key>`。
   - Key 只用于联调，不要写进公开文档/PPT/视频；不要提交到 Git。

---

## 2. 快速自测（30 秒）

```bash
# 1) 健康检查（不需要 Key）
curl https://你的地址/health
# 期望: {"status":"ok",...,"auth_required":true}

# 2) 检测一张图（需要 Key；没有启用鉴权则去掉 -H）
curl -X POST "https://你的地址/detect" \
  -H "X-API-Key: 你的KEY" \
  -F "image=@本地图片.jpg"
```

返回里能看到 `defect_count`、`defects` 即成功。

---

## 3. 接口清单

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/health` | 否 | 健康检查（`auth_required` 告诉你是否需要 Key） |
| GET | `/classes` | 否 | 6 类缺陷 id/英文/中文 |
| GET | `/model/info` | 是 | 当前模型信息（imgsz / 阈值 / 权重） |
| POST | `/detect` | 是 | 单图检测（multipart 字段 `image`） |
| POST | `/detect/batch` | 是 | 批量（multipart 字段 `images` 多文件） |
| POST | `/detect/base64` | 是 | Base64 检测，可覆盖 `conf` / `imgsz` |

**鉴权方式**：请求头 `X-API-Key: <key>`；服务端未配置 Key 时无需该头（仅限本机/内网）。

---

## 4. Python 示例（推荐直接复制）

```python
import base64
import requests

BASE = "https://你的地址"          # 注意不要带末尾斜杠
KEY = "你的API_KEY"                # 服务端未启用鉴权则留空
HEADERS = {"X-API-Key": KEY} if KEY else {}


def health():
    return requests.get(f"{BASE}/health", timeout=10).json()


def detect(image_path):
    """单图检测。"""
    with open(image_path, "rb") as f:
        files = {"image": (image_path.split("/")[-1], f, "image/jpeg")}
        r = requests.post(f"{BASE}/detect", files=files, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def detect_base64(image_path, conf=0.25):
    """Base64 检测，可覆盖阈值。"""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = {"image_base64": b64, "conf": conf, "filename": "test.jpg"}
    r = requests.post(f"{BASE}/detect/base64", json=payload, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    print(health())
    result = detect("test.jpg")
    print("缺陷数:", result["defect_count"])
    for d in result["defects"]:
        print(d["class_cn"], d["confidence"], d["bbox_xyxy"])
```

**批量检测**：

```python
files = [("images", ("a.jpg", open("a.jpg", "rb"), "image/jpeg")),
         ("images", ("b.jpg", open("b.jpg", "rb"), "image/jpeg"))]
r = requests.post(f"{BASE}/detect/batch", files=files, headers=HEADERS, timeout=120)
print(r.json()["count"])
```

---

## 5. 返回结构（单图）

```json
{
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
  "inference_ms": 12.9,
  "model": "best.pt",
  "imgsz": 640,
  "filename": "patches_110.jpg",
  "elapsed_ms": 13.59
}
```

| 字段 | 说明 |
| --- | --- |
| `defect_count` | 检出缺陷数；0 表示 OK |
| `defects[].class_id` / `class_name` / `class_cn` | 类别 id / 英文 / 中文 |
| `defects[].confidence` | 置信度 0~1 |
| `defects[].bbox_xyxy` | 像素坐标 [x1,y1,x2,y2]，原点左上 |
| `defects[].area_ratio` | 框面积/图片面积 |
| `inference_ms` / `elapsed_ms` | 模型推理 / 请求总耗时（ms） |

类别 id：0 氧化铁皮压入、1 斑块、2 龟裂、3 麻点、4 夹杂、5 划伤。

---

## 6. 错误码与排查

| 状态码 | 含义 | 处理 |
| --- | --- | --- |
| 401 | 缺 Key / Key 错误 | 检查请求头 `X-API-Key` 是否与队长给的一致 |
| 400 | 图片无法解码 | 换 jpg/png/bmp；确认文件不是 0 字节 |
| 422 | 参数缺失/类型错误 | 检查 form 字段名（单图必须是 `image`） |
| 500 | 服务端模型加载失败 | 联系队长重启服务 |
| 连接超时/域名打不开 | 内网穿透断开 | 免费隧道会断/换域名，找队长确认新地址 |

---

## 7. 联调注意事项

- 图片建议 jpg/png/bmp，单张 ≤10MB；手机拍照原图也可以（会内部缩放到 640）。
- `conf` 默认 0.25；**漏检敏感场景**可传 0.10~0.15（尤其是 crazing 龟裂类），**减少误报**可用 0.35~0.5。
- 单张耗时：GPU 约 12ms、CPU 约 25~60ms；批量接口按顺序处理，图片多时耐心等。
- 服务默认**无 CORS 限制**（允许跨域），浏览器/前端可直接 fetch。
- 返回坐标为原图像素坐标，前端按原图尺寸等比缩放即可。
- 不要高频压测共享的穿透地址；需要稳定性找队长用云服务器/正式部署。
- 演示前用 `samples/` 里的图先跑通（斑块、划伤类检出效果较好；龟裂类偏弱，答辩时注意说明）。

---

## 8. 我要联调什么？

| 队友任务 | 怎么用 API |
| --- | --- |
| 前端检测页 | 上传图片 → `POST /detect` → 用 `bbox_xyxy` 在原图画框 + 展示 defects 表格 |
| 智能体/大模型 | 把 `/detect` 的 JSON 作为工具返回，再让 LLM 总结/出报告 |
| 演示视频 | 录屏「上传→检测→结果」即可；也可用批量接口演示产线多图 |
| 需要示例图 | 找队长要 `deploy/modelscope_package/samples/`（6 类各 2 张） |

有问题先看 `/docs`（Swagger 可直接在线试接口）。

---

## 9. 团队共同接口（App 主流程，优先用这个）

按仓库 `docs/plans/04-shared-contract.md` 实现；`/detect` 仅用于快速联调。所有 `/api` 接口同样带 `X-API-Key`。

```python
BASE = "https://你的地址"
KEY = "你的KEY"
H = {"X-API-Key": KEY}

# 1) 上传图片 + 批次号 -> 检测并落库
with open("test.jpg", "rb") as f:
    r = requests.post(f"{BASE}/api/inspections", headers=H,
                      data={"batch_no": "BATCH-001", "workpiece_no": "W-0001"},
                      files={"image": ("test.jpg", f, "image/jpeg")})
created = r.json()          # {inspection_id, task_id, status, detection_count, timing...}

# 2) 查询详情（原图坐标框）
detail = requests.get(f"{BASE}/api/inspections/{created['inspection_id']}", headers=H).json()
for d in detail["detections"]:
    print(d["class_id"], d["class_name"], d["score"], d["bbox_xyxy"])   # 契约 class_id

# 3) 任务状态（断线恢复）
task = requests.get(f"{BASE}/api/tasks/{created['task_id']}", headers=H).json()

# 4) 复检建议（事实/引用/原因/步骤/待补信息）
analysis = requests.post(f"{BASE}/api/inspections/{created['inspection_id']}/analysis", headers=H).json()

# 5) 追问
chat = requests.post(f"{BASE}/api/chat/messages", headers=H,
                     json={"context_type": "inspection", "context_id": created["inspection_id"],
                           "question": "这类缺陷可能原因是什么？怎么复检？"}).json()

# 6) 人工复核（base_version 用当前 review_version，防旧页面覆盖）
review = requests.post(f"{BASE}/api/inspections/{created['inspection_id']}/review", headers=H,
                       json={"review_status": "confirmed", "reviewer": "operator-1",
                             "notes": "复判确认", "base_version": 0}).json()

# 7) 批次统计 / 报告
summary = requests.get(f"{BASE}/api/batches/BATCH-001/summary", headers=H).json()
report = requests.get(f"{BASE}/api/reports/{created['inspection_id']}", headers=H).json()

# 8) WebSocket 任务事件：/ws/tasks/{task_id}（accepted → completed）
```

**类别注意**：App 一律使用契约 class_id（0 龟裂、1 夹杂、2 斑块、3 麻点、4 轧入氧化皮、5 划痕）。
后端已做映射；原始训练顺序可通过 `GET /api/class-map` 查看。

**列表查询**：`GET /api/inspections?batch_no=BATCH-001&class_id=2&review_status=pending&page=1&page_size=20`。

**复核状态**：`pending / confirmed / corrected / unresolved`；检测完成 ≠ 人工确认。
`POST review` 若 `base_version` 落后会返回 **409**，重新拉详情再提交。

**标注图/原图**：详情里的 `annotated_url`（如 `/files/INSP-..._pred.jpg`）直接拼 `BASE` 即可打开。

---

## 10. 大模型分析与追问（DeepSeek）

- 服务端配置 `DEEPSEEK_API_KEY` 后，`analysis` 和 `chat` 会自动调用 DeepSeek；未配置/断网时自动降级规则模板。
- 返回结果带 `source` 字段：`deepseek` 表示真实大模型，`rule_fallback` 表示离线模板（会有 `reason`）。前端可据此提示用户。
- 查看服务端是否已开启：`GET /api/llm/info`（不返回 Key）。
- 可把 `analysis` 的 `facts/references/hypotheses/recheck_steps/missing_information` 直接展示给用户；
  `chat` 返回 `answer` 与 `references`。
- 大模型内容是**辅助建议**，不能替代人工复核；演示/报告中注意标注。


