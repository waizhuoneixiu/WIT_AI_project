# SteelScan 智检 Agent — 魔搭创空间部署说明

## 包内容

```
modelscope_package/
├─ app.py                  # Gradio 页面入口（平台自动运行）
├─ inference_onnx.py       # ONNX Runtime 推理（CPU，无需 PyTorch）
├─ requirements.txt        # 依赖（gradio + onnxruntime + opencv-headless）
├─ models/best.onnx        # YOLO26n@640 权重（9.4MB）
└─ samples/                # 12 张样例缺陷图（6 类 × 2）
```

模型：YOLO26n @640，测试集 mAP50 0.806 / Recall 0.766 / 图片级漏检率 2.59%；CPU 单张约 20~60ms。

## 部署步骤（约 10 分钟）

1. **注册/登录魔搭**：https://modelscope.cn/ （手机号/支付宝均可）。
2. **创建创空间**：进入「创空间 Studio」→「创建创空间」→
   - 名称：如 `steelscan-demo`
   - SDK 类型：**Gradio**
   - 可见性：**公开**
   - 硬件：**CPU**（免费即可，本模型 CPU 推理足够）
3. **上传文件**（两种方式任选）：
   - 方式 A（网页）：进入创空间 →「文件」→ 上传本目录全部文件（保持目录结构：`app.py` 在根目录，`models/`、`samples/` 子目录）。
   - 方式 B（Git）：
     ```bash
     git clone https://www.modelscope.cn/studios/<你的用户名>/steelscan-demo.git
     # 把本目录全部文件复制进该仓库根目录
     git add .
     git commit -m "SteelScan 缺陷检测 demo"
     git push
     ```
4. **等待构建**：平台自动安装 requirements 并运行 `app.py`（首次约 2~5 分钟）。
5. **获取链接**：构建完成后，公网地址形如
   `https://modelscope.cn/studios/<你的用户名>/steelscan-demo`
   该链接可直接作为作品演示链接，也可贴给队友/评委。

## 验收（部署后自测）

- 打开链接 → 点样例图或上传图片 → 点「开始检测」→ 右侧出现标注框、JSON、缺陷表格；
- 调整 conf（0.05~0.9）观察检出变化；
- 若报错，查看创空间「构建日志」，常见问题：`models/best.onnx` 未上传、目录层级不对。

## 常见问题

| 问题 | 处理 |
| --- | --- |
| 构建失败提示缺少 onnxruntime | 确认 `requirements.txt` 未被改动 |
| 页面打开 404 / 构建中 | 等 2~5 分钟，或看构建日志 |
| 上传图片无结果 | 换 `samples/` 里的图先验证；或调低 conf |
| 想换成自己的模型 | 替换 `models/best.onnx`（同输入 640×640、6 类）后重新提交 |
