# 钢见 Android App

Kotlin Multiplatform + Compose Android 客户端。界面使用 [Aboard-design.md](Aboard-design.md) 的浅色纸感、粉彩表面与圆角；系统相册、相机、文件保存和分享由 Android 提供。

## 本地构建

依赖版本：Kotlin / Compose compiler 2.4.0，Compose Multiplatform 1.12.2，Material3 1.9.0，AGP 9.1.1，Gradle 9.4.1，Ktor 3.6.1。最低 Android 8.0（API 26），compile SDK 37.0，target SDK 36。Gradle Wrapper 包含分发包 SHA-256 校验。

使用本机已有 Android Studio JBR 与 SDK，无需安装任何模型或推理库：

```powershell
$env:JAVA_HOME = 'D:\Program Files\Android Studio\jbr'
$env:ANDROID_HOME = 'D:\Android\Sdk'
cd frontend
.\gradlew.bat :androidApp:assembleDebug :composeApp:testAndroidHostTest
```

路径按实际安装位置调整，也可在 Android Studio 打开 `frontend`。SDK 需安装 Android 37.0 与 Build Tools 36.0.0。输出 APK：`androidApp/build/outputs/apk/debug/androidApp-debug.apk`。

本机 JBR 25 在默认 Windows 临时目录创建 NIO 管道时出现 `Unable to establish loopback connection`。遇到同一问题时，在上述命令前设置一个已有、可写的短路径：

```powershell
$env:JAVA_TOOL_OPTIONS = '-Djdk.net.unixdomain.tmpdir=D:\temp'
```

只改变当前终端进程的 Java 临时 socket 路径，不关闭 TLS 验证。依赖仓库使用官方 Google Maven、Maven Central 和 Gradle Plugin Portal。

## 连接与操作

先按 [backend README](../backend/README.md) 启动轻量 FastAPI 后端，配置魔搭令牌；令牌与 DeepSeek Key 只保存在后端。App 的连接设置填写业务 API 地址及可选 `X-API-Key`。App Key 使用 Android Keystore 加密存储，不写入源码或 APK。

- Android 模拟器默认：`http://10.0.2.2:8000`。
- 同一局域网真机：`http://电脑局域网IP:8000`；后端监听 `0.0.0.0`，Windows 防火墙允许该局域网连接。
- 当前调试版允许局域网 HTTP；公网服务应配置 HTTPS。

选图或拍照后输入批次号，提交单图检测。结果详情支持原图框展示、人工复核、上下文助手和 Markdown 报告；历史可按批次、模型类别和复核状态筛选。未检出仅表示未检出六类目标缺陷，不代表合格。

JPG、PNG、BMP 原文件最多 10 MB；不对上传图进行缩放。预览单独采样并应用 EXIF 旋转／镜像，框坐标始终依据服务端原图尺寸。超时后不会自动重发 POST，应先到历史按批次找回已保存记录。

## 验证

```powershell
.\gradlew.bat :androidApp:assembleDebug :composeApp:testAndroidHostTest
.\gradlew.bat :androidApp:connectedDebugAndroidTest
.\gradlew.bat :androidApp:lintDebug
```

Host tests 覆盖 API、状态恢复与框编辑计算；设备测试覆盖 EXIF 旋转／镜像、连接密钥存储与云调用 HTTP 配置。UI 验收需另检查系统选图／拍照、保存分享、断网、空结果和完整云检测流程，合成 fixture 不能替代真实云调用。

2026-10-31 本机构建记录：debug APK 构建成功；29 项 Host tests（含报告标题/表格的 3 项回归）、API 37 模拟器上的 3 项设备测试通过；`lintDebug` 通过（0 个错误，5 个非阻断警告）。日志位于忽略的 `build/shared-tests.log`、`build/report-preview-build.log`、`build/platform-build.log`，设备结果在 `androidApp/build/outputs/androidTest-results/connected/debug/`。这些检查不代表真机或魔搭云端调用已验收。

`composeApp` 保存共享 UI、状态与网络；`androidApp` 保存应用入口和平台桥。首版只有 Android target，未引入桌面、iOS、批量检测或本地推理。

已提交记录由后端恢复。旋转时保持 Activity 与在途系统操作；系统杀进程后的未提交选图／复核草稿恢复尚未实现。相机效果与系统分享目标需要真机验收。
