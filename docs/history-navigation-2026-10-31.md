# Android 记录读取与滑动导航

## 行为

- 首次进入记录页自动读取历史；同一应用会话内再次进入、点击当前记录导航或旋转屏幕均保留列表，不重复请求。
- 记录页沿用浅蓝与淡紫卡片，提供“重新读取”、页内进度和错误提示；筛选通过“应用筛选”明确提交，分页仍为手动读取。
- 列表和批次统计使用独立读取状态。请求未结束时底部检测、记录和设置可切换，页面也可横向滑动；后台完成只更新缓存，不跳回记录页。
- 刷新失败保留上次列表和页码。首次失败不会因为离开再进入自动重试，可手动重新读取。
- 打开单条记录的读取不锁底部导航；离开时取消该次读取，避免迟到响应重新打开详情。修改中的复核仍保留离开确认。
- 三个主页面按“检测—记录—设置”顺序使用原生 HorizontalPager。手势跟随拖动，松手吸附；点击底部导航使用约 280ms 的横向切页。详情中的框编辑不参与主页面滑动。
- 保存新的服务连接后取消旧读取并清空旧缓存；首次进入新服务的记录页重新读取。
- 去除全局品牌横栏、“质检工作台”和检测页的两句宣传文案，检测页直接进入图片操作；将原黑底白色取景框、浅蓝圆点标志复用为 APK 应用图标。

## 实现与来源

复用工程已有的 Compose Foundation、Material 3、ViewModel 和协程，不增加运行依赖。导航使用 Foundation 自带的 HorizontalPager / PagerState；未复制第三方应用源码。

实施前核对了 Android 官方 Compose 示例仓库及 Apache-2.0 许可，并检查 AndroidX 的原生 Pager 示例。参考的是已有组件调用方式；本次业务状态、缓存与取消逻辑为针对本工程的修改。

- [Compose 官方示例](https://github.com/android/compose-samples)，[许可](https://github.com/android/compose-samples/blob/main/LICENSE)。
- [AndroidX PagerSamples.kt](https://github.com/androidx/androidx/blob/androidx-main/compose/foundation/foundation/samples/src/main/java/androidx/compose/foundation/samples/PagerSamples.kt)，文件头为 Apache-2.0。
- [Compose Pager 官方说明](https://developer.android.com/develop/ui/compose/layouts/pager)。

## 回归检查

新增 7 项 HistoryStateTest，覆盖首次读取/重入/手动刷新、重复保存相同连接、慢请求与重复点击、首次失败后的手动恢复、刷新失败保留旧结果、切换服务取消旧请求、离开记录取消详情请求。

2026-10-31 验证结果：

| 检查 | 实际结果与范围 |
| --- | --- |
| APK 构建 | assembleDebug 成功；0.1.0 / versionCode 1 / com.steelscan.app |
| Host tests | 36 项通过，0 失败、0 错误，含新增 7 项历史读取回归 |
| Android 设备测试 | Android 17 / API 37.0 模拟器 3 项通过 |
| 实际安装与启动 | 安装成功，MainActivity 冷启动 Status: ok；新版直接显示图片操作与检测信息 |
| 慢读取导航 | 测试服务延迟 20 秒；读取期间实际点击检测、设置均可切页 |
| 首次读取与重入 | 检测/记录/设置间反复点击和左右滑动后，历史 GET 仍只有 1 次；手动重新读取后增至 2 次 |
| 刷新失败 | 注入 HTTP 503，显示页内失败提示；上次记录与页码保留 |
| 取消详情读取 | 单条记录延迟 15 秒；切到设置后保持设置页，迟到响应未重新打开详情 |
| 动画与布局 | 捕获拖动中的双页面滑入画面；上下滚动正常，1.3 倍字体下重新读取入口与底部导航可见，无文字重叠 |
| APK 完整性 | apksigner 验证通过，v2 签名有效 |

本次导航测试使用隔离的 HTTP 测试服务与 `fixture-not-yolo` 合成记录；没有调用真实魔搭/DeepSeek，也没有进行真机验收。

### 本机静态检查限制

`lintDebug` 在本机报告 1 error / 3 warnings，错误为 MainActivity 的 `Instantiatable`。在未修改的 `95b2f90` 独立副本中执行同一检查，得到相同错误与警告数量；MainActivity 和 Manifest 本次未修改，最终 APK 已实际冷启动成功。未屏蔽或降低该项检查，不能把本轮写成 lint 全部通过。

### 交付包校验

调试 APK SHA-256：`56af6a2a931e08e9395b7c4085296aba3706ee75fbe2cfe0803680e2f3f1a392`。APK、实际界面截图、请求日志与测试报告随本次交付保留。
