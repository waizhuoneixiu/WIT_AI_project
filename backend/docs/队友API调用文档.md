# SteelScan Android 对接速查

更新日期：2026年10月30日。主契约见[API接口文档](API接口文档.md)和[共同契约](../../docs/plans/04-shared-contract.md)。本轮云适配和复核字段已落地，当前样例来自无网络fixture；真实云与Android仍须分别验收，不能仅凭样例假定部署服务已更新。

## 1. 连接对象

App连接本机轻量FastAPI业务地址，业务API再调用魔搭YOLO26n@640并保存SQLite记录。魔搭地址只提供Gradio检测，不能直接当业务BASE_URL。App只配置业务地址和必要的`X-API-Key`；魔搭/DeepSeek令牌留后端。本轮不安装任何本地模型运行库。

模拟器访问宿主一般用`http://10.0.2.2:8000`；真机使用同一网络下电脑实际IP。启动步骤见[后端README](../README.md)。先请求`GET /health`；它能证明业务可达，但不能代替真实云检测验证。开启鉴权时图片`/files/*`也带业务Key。

## 2. 正式单图流程

1. `POST /api/inspections`：multipart `image`、`batch_no`、可选`workpiece_no`；同步201返回inspection_id/task_id。
2. `GET /api/inspections/{id}`：原图、detections、reviewed_detections、review_version和最新analysis。
3. 编辑后`POST /api/inspections/{id}/review`：必填base_version，完整add/update/delete差异；成功重新拉详情。
4. `POST /api/inspections/{id}/analysis`生成复检建议；`POST /api/chat/messages`携带当前inspection/batch上下文追问。
5. `GET /api/inspections`查询分页历史；`GET /api/batches/{batch_no}/summary`看原模型统计和图片复核状态。
6. `GET /api/reports/{inspection_id}`读取当前版本Markdown，保存/分享content_md。

检测、分析、问答均同步HTTP；不要等待不存在的流式片段。已有WS需同HTTP的X-API-Key，开启鉴权而缺失/错误Key时accept前close 1008；正确Key只回放accepted/completed，App不依赖。上传等待中禁用按钮；结果未知时先查历史，不自动重复创建。

```python
import requests

BASE = 'http://127.0.0.1:8000'
HEADERS = {'X-API-Key': '<业务KEY>'}  # 未启用业务鉴权时使用空dict

with open('test.jpg', 'rb') as image:
    response = requests.post(
        BASE + '/api/inspections', headers=HEADERS,
        data={'batch_no': 'BATCH-001'},
        files={'image': ('test.jpg', image, 'image/jpeg')}, timeout=90)
response.raise_for_status()
inspection_id = response.json()['inspection_id']
response = requests.get(BASE + '/api/inspections/' + inspection_id,
                        headers=HEADERS, timeout=15)
response.raise_for_status()
detail = response.json()
for detection in detail['detections']:
    print(detection['class_name'], detection['score'], detection['bbox_xyxy'])
```

## 3. 容易抄错的约定

- 对外class_id固定：0龟裂、1夹杂、2斑块、3麻点、4轧入氧化皮、5划痕；原模型训练顺序不同但后端已转换。
- 原图坐标使用`image_width/image_height`和`original_url`；不是640画布坐标。灰度、方向和留白缩放须联调。
- `detections`不可变；有效人工结果在`reviewed_detections`。新增/修改框source=manual、score=null，不能编造置信度。
- 空检出只表示“未检出六类目标缺陷”，不表示OK或产品合格。
- 业务模型标识为`yolo26n-640-onnx`；魔搭云总请求时延包含上传/排队/网络，不能引用本地GPU毫秒数作为App体验。

## 4. 完整复核（本轮补齐）

请求带review_status（pending/confirmed/corrected/unresolved）、reviewer、notes、**必填非负base_version**和corrections。每次提交相对原detections的完整差异：add用新UUID，update/delete引用原框ID；add/update带class_id和bbox_xyxy，delete只需op/id。

再次编辑人工框更新add；删除人工框移除add。原框恢复时移除update/delete。坐标必须有限、图内且有面积，ID不得重复或跨记录。无op旧条目按update；corrections省略/null保留，`[]`重置。新App总是发送完整列表。

409后保留草稿供参考，刷新最新review_version再人工确认，不能自动覆盖。字段与JSON样例见[共同契约](../../docs/plans/04-shared-contract.md)。

## 5. 分析、历史与报告

- analysis含facts/references/hypotheses/recheck_steps/missing_information/source，最新对象附review_version/stale/created_at。复核后旧分析stale=true，界面提示重新生成。
- source=deepseek是云生成，rule_fallback是规则降级，不能冒充实时大模型；历史local-deepseek仅作旧记录兼容。
- chat请求为context_type=inspection/batch、context_id、question，切换记录必须切换上下文。回答和任务result包含实际用于回答的review_version（图片为整数，批次为null）及stale；生成期间图片版本变化则stale=true，提示依据已过时。
- 历史支持batch_no/class_id/review_status/page/page_size，没有时间筛选承诺。total与筛选一致。
- summary的per_class/model_box_count是原预测，confirmed_count是图片数，不是人工确认框数。
- report返回content_md和review_version；inspection_id生成当前版本，report_id读取保存版本。报告包含原预测、有效复核、备注及分析来源，实际保存`.md`验收。

## 6. 故障与资料

输入错误400/422应修正，401检查业务Key，404刷新列表，409处理版本冲突；魔搭503为配置/鉴权、502为上游网络/非法响应、504为超时，均显示检测失败，不当成空检出。默认60秒是分阶段使用剩余时间的调用预算，底层阻塞可能延至当前网络超时。本机业务API可达时可读已有记录，但断外网不能新检测，不承诺离线队列。

详细资料：[API说明](API接口文档.md)、[魔搭部署记录](魔搭部署记录.md)、[现有样例](api_samples/)、[本轮验收计划](../../docs/plans/05-integration-acceptance.md)。样例与OpenAPI已按本轮代码导出，见样例目录README的合成标记；这不等于Android或真实云端到端通过。
