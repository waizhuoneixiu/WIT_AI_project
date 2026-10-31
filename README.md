# 钢见 · SteelScan

钢材表面缺陷辅助质检原型：KMP Android 应用通过本机 FastAPI / SQLite 业务后端，调用魔搭的 YOLO26n@640 云检测和可选 DeepSeek 云问答。

- [开发路线图](docs/roadmap.md)与[共同接口](docs/plans/04-shared-contract.md)
- [Android 工程与构建](frontend/README.md)
- [轻量后端与云服务配置](backend/README.md)
- [联调验收计划](docs/plans/05-integration-acceptance.md)

本轮不安装本地模型推理库。密钥只放被 Git 忽略的 `backend/.env`，Android 仅配置业务 API 地址和访问口令。模型未检出目标不等同于产品合格；模型预测、人工复核和辅助建议分别展示。
