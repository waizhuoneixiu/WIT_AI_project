package com.steelscan.app

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import io.ktor.client.HttpClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
fun App(platform: PlatformBridge, httpClient: HttpClient) {
    val state = viewModel { AppState() }
    val scope = rememberCoroutineScope()
    var platformBusy by remember { mutableStateOf(false) }
    var pendingDiscard by remember { mutableStateOf<(() -> Unit)?>(null) }
    var retryConfirmation by remember { mutableStateOf(false) }
    var savedRecordId by rememberSaveable { mutableStateOf<String?>(null) }
    var savedPage by rememberSaveable { mutableStateOf(MainPage.Detect.name) }
    LaunchedEffect(Unit) {
        val restoring = !state.initialized
        try { state.bind(httpClient, platform.loadConnection()) }
        catch (_: Exception) {
            state.bind(httpClient, ConnectionSettings())
            state.error = "无法读取已保存的连接设置，请重新配置服务地址和访问密钥。"
        }
        if (restoring) {
            state.page = MainPage.valueOf(savedPage)
            if (state.inspection == null) savedRecordId?.let { state.openRecord(it) }
        }
    }
    LaunchedEffect(state.inspection?.inspectionId) {
        state.inspection?.inspectionId?.let { savedRecordId = it }
    }
    LaunchedEffect(state.page) { savedPage = state.page.name }
    val busy = state.busy != null || platformBusy
    fun navigate(action: () -> Unit) {
        if (busy) return
        if (state.inspection != null && state.dirty) pendingDiscard = action else action()
    }
    fun platformAction(action: suspend () -> Unit) {
        if (busy) return
        platformBusy = true
        scope.launch {
            try { action() }
            catch (cancel: CancellationException) { throw cancel }
            catch (e: Exception) { state.error = e.message?.take(160) ?: "未能完成操作，请重试。" }
            finally { platformBusy = false }
        }
    }

    PlatformBackHandler(state.inspection != null || busy) {
        navigate { state.closeRecord(); savedRecordId = null }
    }
    SteelTheme {
        Scaffold(
            containerColor = CanvasColor,
            topBar = {
                Column(Modifier.statusBarsPadding().background(CanvasColor)) {
                    Row(Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 14.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        BrandMark()
                        Spacer(Modifier.width(10.dp))
                        Column {
                            Text("钢见", fontSize = 22.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.2).sp)
                            Text("STEELSCAN", color = Graphite, fontSize = 10.sp, letterSpacing = 2.sp)
                        }
                        Spacer(Modifier.weight(1f))
                        Surface(shape = RoundedCornerShape(99.dp), color = SkyTint) {
                            Text("质检工作台", Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                                color = Ink, style = MaterialTheme.typography.labelMedium)
                        }
                    }
                    if (busy) {
                        LinearProgressIndicator(Modifier.fillMaxWidth(), color = SignalBlue, trackColor = SkyTint)
                        Text(state.busy ?: "正在处理图片", Modifier.padding(horizontal = 24.dp, vertical = 5.dp),
                            color = Graphite, style = MaterialTheme.typography.bodySmall)
                    }
                }
            },
            bottomBar = {
                NavigationBar(containerColor = Color.White, tonalElevation = 0.dp) {
                    listOf(MainPage.Detect to "检测", MainPage.History to "记录", MainPage.Settings to "设置").forEach { (page, label) ->
                        NavigationBarItem(selected = state.page == page, enabled = !busy,
                            onClick = { navigate { state.closeRecord(); savedRecordId = null; state.page = page
                                if (page == MainPage.History) state.loadHistory() } },
                            icon = { NavGlyph(page, state.page == page) }, label = { Text(label) },
                            colors = NavigationBarItemDefaults.colors(indicatorColor = SkyTint, selectedIconColor = Ink, selectedTextColor = Ink))
                    }
                }
            },
        ) { padding ->
            Column(Modifier.padding(padding).fillMaxSize()) {
                state.error?.let { message ->
                    MessageBanner(message, true) { state.error = null }
                }
                state.notice?.let { message ->
                    MessageBanner(message, false) { state.notice = null }
                }
                val detail = state.inspection
                if (detail != null) {
                    key(detail.inspectionId, state.tab) {
                        DetailScreen(state, platform, busy,
                            onBack = { navigate { state.closeRecord(); savedRecordId = null } },
                            onRefresh = { navigate { state.refreshRecord() } },
                            onPlatformAction = { action -> platformAction(action) })
                    }
                } else when (state.page) {
                    MainPage.Detect -> DetectScreen(state, platform, busy,
                        onPick = { camera -> platformAction {
                            val picked = if (camera) platform.takePhoto() else platform.pickImage()
                            picked?.let(state::acceptPicked)
                        } }, onExplicitRetry = { retryConfirmation = true })
                    MainPage.History -> HistoryScreen(state, busy,
                        onExplicitRetry = { retryConfirmation = true })
                    MainPage.Settings -> SettingsScreen(state, busy) {
                        platformAction {
                            val settings = ConnectionSettings(state.baseUrl.trim().trimEnd('/'), state.apiKey.trim())
                            SteelApi(httpClient, settings)
                            platform.saveConnection(settings)
                            state.reconnect(httpClient, settings)
                            savedRecordId = null
                            state.checkConnection()
                        }
                    }
                }
            }
        }
        pendingDiscard?.let { action ->
            AlertDialog(onDismissRequest = { pendingDiscard = null }, title = { Text("保留这次复核？") },
                text = { Text("当前有未保存的框或复核内容。离开会放弃这些修改。") },
                confirmButton = { TextButton(onClick = { state.resetDraft(); pendingDiscard = null; action() }) { Text("放弃修改并继续") } },
                dismissButton = { TextButton(onClick = { pendingDiscard = null }) { Text("继续复核") } })
        }
        if (retryConfirmation) {
            AlertDialog(onDismissRequest = { retryConfirmation = false }, title = { Text("重新提交这张图片？") },
                text = { Text("请先检查该批次历史记录。上次请求可能已保存，重新提交可能生成重复记录。") },
                confirmButton = { TextButton(onClick = { retryConfirmation = false; state.allowExplicitRetry() }) { Text("已检查，允许重新提交") } },
                dismissButton = { TextButton(onClick = { retryConfirmation = false; state.findUncertainUpload() }) { Text("查看历史") } })
        }
    }
}

@Composable
private fun BrandMark() {
    Canvas(Modifier.size(34.dp)) {
        drawRoundRect(Ink, cornerRadius = androidx.compose.ui.geometry.CornerRadius(9.dp.toPx()))
        val line = 2.dp.toPx()
        drawLine(Color.White, Offset(size.width * .28f, size.height * .3f), Offset(size.width * .28f, size.height * .7f), line)
        drawLine(Color.White, Offset(size.width * .28f, size.height * .3f), Offset(size.width * .58f, size.height * .3f), line)
        drawLine(Color.White, Offset(size.width * .72f, size.height * .7f), Offset(size.width * .42f, size.height * .7f), line)
        drawLine(Color.White, Offset(size.width * .72f, size.height * .3f), Offset(size.width * .72f, size.height * .7f), line)
        drawCircle(PowderBlue, 2.dp.toPx(), Offset(size.width / 2, size.height / 2))
    }
}

@Composable
private fun NavGlyph(page: MainPage, selected: Boolean) {
    Canvas(Modifier.size(23.dp)) {
        val c = if (selected) Ink else Graphite
        val stroke = 1.7.dp.toPx()
        when (page) {
            MainPage.Detect -> {
                drawRoundRect(c, Offset(2.dp.toPx(), 2.dp.toPx()), Size(size.width - 4.dp.toPx(), size.height - 4.dp.toPx()),
                    androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()), style = Stroke(stroke))
                drawLine(c, Offset(0f, size.height / 2), Offset(size.width, size.height / 2), stroke)
            }
            MainPage.History -> repeat(3) { n ->
                drawLine(c, Offset(6.dp.toPx(), (5 + 7 * n).dp.toPx()), Offset(size.width - 1.dp.toPx(), (5 + 7 * n).dp.toPx()), stroke)
                drawCircle(c, stroke / 2, Offset(1.dp.toPx(), (5 + 7 * n).dp.toPx()))
            }
            MainPage.Settings -> repeat(3) { n ->
                val y = (5 + 7 * n).dp.toPx()
                drawLine(c, Offset(0f, y), Offset(size.width, y), stroke)
                drawCircle(CanvasColor, 3.dp.toPx(), Offset((if (n == 1) 16 else 7).dp.toPx(), y))
                drawCircle(c, 3.dp.toPx(), Offset((if (n == 1) 16 else 7).dp.toPx(), y), style = Stroke(stroke))
            }
        }
    }
}

@Composable
fun ScreenColumn(content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).padding(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp), content = content)
}

@Composable
private fun MessageBanner(message: String, error: Boolean, onDismiss: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(if (error) Color(0xFFFFEEE7) else SkyTint).padding(start = 20.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(message, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
        TextButton(onClick = onDismiss) { Text("关闭") }
    }
}

@Composable
fun SectionTitle(title: String, subtitle: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Text(title, style = MaterialTheme.typography.headlineMedium)
        subtitle?.let { Text(it, color = Graphite, style = MaterialTheme.typography.bodyMedium) }
    }
}

@Composable
fun DecodedImage(bytes: ByteArray?, platform: PlatformBridge): ImageBitmap? {
    var image by remember(bytes) { mutableStateOf<ImageBitmap?>(null) }
    LaunchedEffect(bytes) {
        if (bytes != null) {
            try { image = platform.decodeImage(bytes) }
            catch (cancel: CancellationException) { throw cancel }
            catch (_: Exception) { image = null }
        }
    }
    return image
}

@Composable
private fun DetectScreen(state: AppState, platform: PlatformBridge, busy: Boolean, onPick: (Boolean) -> Unit, onExplicitRetry: () -> Unit) {
    val bitmap = DecodedImage(state.picked?.bytes, platform)
    ScreenColumn {
        Spacer(Modifier.height(2.dp))
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("每一次复核，都有据可循。", color = Graphite, style = MaterialTheme.typography.bodyMedium)
            Text("看见细节，\n留住判断。", style = MaterialTheme.typography.headlineLarge)
        }
        PaperCard(Mint) {
            Text("01  /  添加待检图片", style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(18.dp))
            if (bitmap != null) {
                Surface(shape = RoundedCornerShape(14.dp), color = Color.White) {
                    Image(bitmap, "待检图片预览", Modifier.fillMaxWidth().height(210.dp), contentScale = ContentScale.Fit)
                }
                Spacer(Modifier.height(10.dp))
                Text(state.picked?.name ?: "", style = MaterialTheme.typography.bodyMedium)
                Text("${state.picked?.width} × ${state.picked?.height} 像素", color = Graphite, style = MaterialTheme.typography.bodySmall)
            } else {
                Surface(color = Color.White.copy(alpha = .65f), shape = RoundedCornerShape(16.dp)) {
                    Column(Modifier.fillMaxWidth().padding(26.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Canvas(Modifier.size(48.dp)) {
                            drawRoundRect(Ink, cornerRadius = androidx.compose.ui.geometry.CornerRadius(8.dp.toPx()), style = Stroke(1.7.dp.toPx()))
                            drawLine(Ink, Offset(size.width * .22f, size.height * .7f), Offset(size.width * .45f, size.height * .42f), 2.dp.toPx())
                            drawLine(Ink, Offset(size.width * .45f, size.height * .42f), Offset(size.width * .78f, size.height * .7f), 2.dp.toPx())
                            drawCircle(Ink, 3.dp.toPx(), Offset(size.width * .7f, size.height * .28f))
                        }
                        Spacer(Modifier.height(14.dp))
                        Text("从一张清晰的图片开始", fontWeight = FontWeight.Medium)
                        Text("支持 JPG、PNG、BMP · 最大 10 MB", color = Graphite, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                PrimaryAction(if (state.picked == null) "选择图片" else "更换图片", { onPick(false) }, !busy, Modifier.weight(1f))
                OutlinedButton({ onPick(true) }, enabled = !busy, modifier = Modifier.weight(1f), contentPadding = PaddingValues(vertical = 14.dp)) { Text("拍照") }
            }
        }
        PaperCard {
            Text("02  /  补充检测信息", style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(16.dp))
            OutlinedTextField(state.batchNo, { state.batchNo = it }, modifier = Modifier.fillMaxWidth(),
                label = { Text("批次号 *") }, placeholder = { Text("例如 BATCH-001") }, singleLine = true, enabled = !busy,
                shape = RoundedCornerShape(10.dp))
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(state.workpieceNo, { state.workpieceNo = it }, modifier = Modifier.fillMaxWidth(),
                label = { Text("工件编号（选填）") }, singleLine = true, enabled = !busy, shape = RoundedCornerShape(10.dp))
            Spacer(Modifier.height(18.dp))
            PrimaryAction("开始检测", state::submitImage, !busy && state.picked != null && state.batchNo.isNotBlank() && !state.uncertainUpload, Modifier.fillMaxWidth())
            Spacer(Modifier.height(12.dp))
            Text("图片将上传到检测服务。结果用于辅助复核，不直接判定产品合格。", color = Graphite, style = MaterialTheme.typography.bodySmall)
        }
        if (state.uncertainUpload) {
            PaperCard(Butter.copy(alpha = .5f)) {
                Text("上次提交结果尚未确认", fontWeight = FontWeight.Medium)
                Text("先在当前批次中查找记录，避免重复提交。", style = MaterialTheme.typography.bodyMedium)
                TextButton(state::findUncertainUpload, enabled = !busy) { Text("查看该批次记录") }
                state.createdRecordId?.let { id ->
                    TextButton({ state.openRecord(id) }, enabled = !busy) { Text("打开已保存的记录") }
                } ?: TextButton(onExplicitRetry, enabled = !busy) { Text("已核对，重新提交") }
            }
        }
        Text("热轧带钢 · 六类表面缺陷", color = Graphite, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun SettingsScreen(state: AppState, busy: Boolean, onSave: () -> Unit) {
    ScreenColumn {
        SectionTitle("连接与设置", "连接你的质检服务，保持数据在同一个工作台。")
        PaperCard(Lavender) {
            Text("业务服务", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(14.dp))
            OutlinedTextField(state.baseUrl, { state.baseUrl = it }, label = { Text("服务地址") },
                singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !busy,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), shape = RoundedCornerShape(10.dp))
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(state.apiKey, { state.apiKey = it }, label = { Text("业务访问密钥（如启用）") },
                singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !busy,
                visualTransformation = PasswordVisualTransformation(), shape = RoundedCornerShape(10.dp))
            Spacer(Modifier.height(16.dp))
            PrimaryAction("保存并检查连接", onSave, !busy, Modifier.fillMaxWidth())
            TextButton(state::checkConnection, enabled = !busy) { Text("检查已保存的连接") }
        }
        PaperCard {
            Text("服务状态", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(12.dp))
            val health = state.health
            if (health == null) Text("尚未检查连接", color = Graphite)
            else {
                InfoRow("业务服务", if (health.detectorProvider == "test-fixture") "合成验收服务" else if (health.status == "ok") "可达" else health.status)
                InfoRow("API 版本", health.apiVersion)
                InfoRow("模型", health.modelVersion.ifBlank { "YOLO26n@640" })
                InfoRow("云检测配置", if (health.detectorConfigured) "已配置，待实际检测验证" else "尚未配置")
                InfoRow("助手来源", if (health.llm.source == "rule_fallback") "规则模板" else "云端助手")
            }
        }
        PaperCard(SkyTint) {
            Text("连接说明", fontWeight = FontWeight.Medium)
            Text("手机与业务服务电脑连接同一局域网，填入电脑的服务地址。模拟器使用 10.0.2.2:8000。", style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(8.dp))
            Text("这里只填写业务访问密钥，魔搭和 DeepSeek 凭据由后端配置。云服务不可达时无法检测。", color = Graphite, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
fun InfoRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(label, Modifier.width(100.dp), color = Graphite, style = MaterialTheme.typography.bodyMedium)
        Text(value, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
    }
}
