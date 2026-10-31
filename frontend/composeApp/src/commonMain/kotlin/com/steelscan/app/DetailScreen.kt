package com.steelscan.app

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

@Composable
fun DetailScreen(state: AppState, platform: PlatformBridge, busy: Boolean, onBack: () -> Unit,
    onRefresh: () -> Unit, onPlatformAction: (suspend () -> Unit) -> Unit) {
    val item = state.inspection ?: return
    val bitmap = DecodedImage(state.originalBytes, platform)
    ScreenColumn {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            TextButton(onBack, enabled = !busy) { Text("‹ 返回") }
            TextButton(onRefresh, enabled = !busy) { Text("刷新记录") }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(item.batchNo, style = MaterialTheme.typography.headlineMedium)
            Text(item.workpieceNo?.takeIf { it.isNotBlank() } ?: "单图检测记录", color = Graphite)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                StatusPill(reviewLabel(item.reviewStatus), if (item.reviewStatus == "pending") Butter else SkyTint)
                Text("复核版本 ${item.reviewVersion}", color = Graphite, style = MaterialTheme.typography.bodySmall)
            }
            Text(item.inspectionId, color = Graphite, style = MaterialTheme.typography.bodySmall)
            if (item.modelVersion.contains("fixture", ignoreCase = true)) {
                StatusPill("合成验收结果 · 非真实模型推理", Butter)
            }
            if (item.reviewInvalid) {
                Text("旧复核数据无法完整还原。当前显示原模型框，请重新复核并保存，之后再生成建议和报告。", color = Color(0xFF825700), style = MaterialTheme.typography.bodyMedium)
            }
        }
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(DetailTab.Result to "检测结果", DetailTab.Review to "人工复核", DetailTab.Assistant to "助手", DetailTab.Report to "报告").forEach { (tab, label) ->
                FilterChip(selected = state.tab == tab, onClick = { state.tab = tab }, label = { Text(label) }, enabled = !busy)
            }
        }
        when (state.tab) {
            DetailTab.Result -> {
                PaperCard(Mint) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("原模型预测", style = MaterialTheme.typography.titleMedium)
                        Text("${item.detections.size} 处", style = MaterialTheme.typography.titleMedium)
                    }
                    Spacer(Modifier.height(12.dp))
                    if (bitmap != null) {
                        BoxEditor(bitmap, item.imageWidth, item.imageHeight, item.detections,
                            state.selectedId, false, { state.selectedId = it }, {})
                    } else {
                        Text("原图尚未加载，点击刷新记录重试。", color = Graphite)
                    }
                }
                if (item.detections.isEmpty()) EmptyResult()
                else DetectionCards(item.detections, state.selectedId, onSelect = { state.selectedId = it })
                PaperCard {
                    Text("检测信息", style = MaterialTheme.typography.titleMedium)
                    InfoRow("模型版本", item.modelVersion)
                    InfoRow("原图尺寸", "${item.imageWidth} × ${item.imageHeight}")
                    InfoRow("检测时间", item.createdAt.replace('T', ' '))
                    item.timing["inference_ms"]?.let { InfoRow("云推理耗时", "${it.roundToInt()} ms") }
                    Text("分数是模型置信度，不是合格概率。边界框不代表真实尺寸。", color = Graphite, style = MaterialTheme.typography.bodySmall)
                }
                PrimaryAction("查看并复核", { state.tab = DetailTab.Review }, !busy, Modifier.fillMaxWidth())
            }
            DetailTab.Review -> {
                PaperCard(Lavender) {
                    Text("修正位置，补充判断。", style = MaterialTheme.typography.titleLarge)
                    Spacer(Modifier.height(8.dp))
                    Text("在原图上编辑；原模型预测始终保留。", style = MaterialTheme.typography.bodyMedium, color = Graphite)
                    Spacer(Modifier.height(14.dp))
                    if (bitmap != null) {
                        BoxEditor(bitmap, item.imageWidth, item.imageHeight, state.draftBoxes,
                            state.selectedId, !busy, { state.selectedId = it }, state::updateDraft)
                    } else Text("请先刷新加载原图，再编辑标注框。", color = Graphite)
                }
                val selected = state.draftBoxes.firstOrNull { it.detectionId == state.selectedId }
                if (selected != null) {
                    PaperCard {
                        Text("选中框的类别", style = MaterialTheme.typography.titleMedium)
                        ChoiceField("类别", className(selected.classId), classNames.mapIndexed { i, label -> i to label }, !busy) {
                            state.changeClass(selected.detectionId, it)
                        }
                    }
                }
                if (state.draftBoxes.isNotEmpty()) DetectionCards(state.draftBoxes, state.selectedId, { state.selectedId = it })
                else Text("当前人工结果无标注框。可补充漏检，或在备注中记录判断依据。", color = Graphite)
                PaperCard {
                    Text("复核结论", style = MaterialTheme.typography.titleLarge)
                    ChoiceField("状态", reviewLabel(state.reviewStatus), listOf("confirmed" to "确认结果", "corrected" to "已修正", "unresolved" to "无法判断"), !busy) {
                        state.reviewStatus = it
                    }
                    OutlinedTextField(state.notes, { state.notes = it }, label = { Text("复核备注") },
                        placeholder = { Text("记录依据、现场观察或待补充信息") }, modifier = Modifier.fillMaxWidth(),
                        minLines = 3, enabled = !busy, shape = RoundedCornerShape(10.dp))
                    Spacer(Modifier.height(12.dp))
                    Text("${state.draftBoxes.size} 个有效框 · ${if (state.dirty) "有未保存修改" else "已与记录同步"}", color = Graphite, style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.height(14.dp))
                    PrimaryAction("保存人工复核", state::saveReview, !busy && state.conflict == null && !state.conflictNeedsFetch, Modifier.fillMaxWidth())
                    TextButton(state::resetDraft, enabled = !busy && state.dirty) { Text("取消修改，恢复已保存结果") }
                }
                if (state.conflictNeedsFetch) {
                    PaperCard(Butter.copy(alpha = .5f)) {
                        Text("保存结果待确认，草稿已保留", fontWeight = FontWeight.Medium)
                        Text("连接恢复后读取服务器版本，再决定下一步。", style = MaterialTheme.typography.bodyMedium)
                        TextButton(state::fetchConflict, enabled = !busy) { Text("读取服务器版本") }
                    }
                }
                state.conflict?.let { latest ->
                    PaperCard(Butter.copy(alpha = .5f)) {
                        Text("发现服务器版本 ${latest.reviewVersion}", style = MaterialTheme.typography.titleMedium)
                        Text("服务器状态：${reviewLabel(latest.reviewStatus)}，${latest.reviewedDetections.size} 个有效框。当前草稿未被覆盖。", style = MaterialTheme.typography.bodyMedium)
                        latest.review?.payload?.notes?.let { Text("服务器备注：$it", style = MaterialTheme.typography.bodyMedium) }
                        TextButton({ state.resolveConflict(false) }, enabled = !busy) { Text("采用服务器结果") }
                        TextButton({ state.resolveConflict(true) }, enabled = !busy) { Text("保留草稿，按新版本重新核对") }
                    }
                }
            }
            DetailTab.Assistant -> {
                PaperCard(PowderBlue) {
                    Text("围绕这次检测，继续追问。", style = MaterialTheme.typography.titleLarge)
                    Spacer(Modifier.height(10.dp))
                    Text("当前上下文：${item.batchNo} · 复核版本 ${item.reviewVersion}", style = MaterialTheme.typography.bodyMedium)
                    Text("助手只读取已保存内容。未保存的标注和备注不会进入建议。", color = Graphite, style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.height(14.dp))
                    PrimaryAction(if (item.analysis == null) "生成复检建议" else "重新生成建议", state::generateAnalysis, !busy && !item.reviewInvalid, Modifier.fillMaxWidth())
                }
                item.analysis?.let { analysis ->
                    PaperCard {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("复检建议", style = MaterialTheme.typography.titleLarge)
                            SourcePill(analysis.source)
                        }
                        if (analysis.stale) {
                            Spacer(Modifier.height(8.dp))
                            Text("这份建议基于较早的复核版本，请重新生成。", color = Color(0xFF825700), style = MaterialTheme.typography.bodyMedium)
                        }
                        AnalysisSection("检测事实", analysis.facts)
                        AnalysisSection("知识依据", analysis.references)
                        AnalysisSection("参考原因", analysis.hypotheses)
                        AnalysisSection("复检步骤", analysis.recheckSteps)
                        AnalysisSection("待补信息", analysis.missingInformation)
                    }
                }
                state.conversation.forEach { turn ->
                    PaperCard(SkyTint) { Text(turn.question) }
                    PaperCard {
                        SourcePill(turn.response.source)
                        Spacer(Modifier.height(10.dp))
                        SelectionContainer { Text(turn.response.answer, style = MaterialTheme.typography.bodyLarge) }
                        Text(if (turn.reviewVersion == null) "回答的复核依据版本未知" else "回答基于复核版本 ${turn.reviewVersion}", color = Graphite, style = MaterialTheme.typography.bodySmall)
                        if (turn.response.stale || (turn.reviewVersion != null && turn.reviewVersion != item.reviewVersion)) {
                            Text("复核依据已变化，请刷新记录并重新提问。", color = Color(0xFF825700), style = MaterialTheme.typography.bodySmall)
                        }
                        AnalysisSection("引用依据", turn.response.references)
                    }
                }
                PaperCard {
                    OutlinedTextField(state.question, { state.question = it }, label = { Text("询问这次检测") },
                        placeholder = { Text("例如：这类缺陷需要怎样复检？") }, modifier = Modifier.fillMaxWidth(), minLines = 2,
                        enabled = !busy, shape = RoundedCornerShape(10.dp))
                    Spacer(Modifier.height(12.dp))
                    PrimaryAction("发送问题", state::askQuestion, !busy && !item.reviewInvalid && state.question.isNotBlank(), Modifier.fillMaxWidth())
                }
            }
            DetailTab.Report -> {
                PaperCard(Blush) {
                    Text("留存这次判断", style = MaterialTheme.typography.titleLarge)
                    Spacer(Modifier.height(8.dp))
                    Text("报告包含原预测、人工复核、备注及建议来源。未保存的编辑不进入报告。", style = MaterialTheme.typography.bodyMedium)
                    Spacer(Modifier.height(14.dp))
                    PrimaryAction("生成当前版本报告", state::loadReport, !busy && !item.reviewInvalid, Modifier.fillMaxWidth())
                }
                state.report?.let { report ->
                    PaperCard {
                        Text("报告预览", style = MaterialTheme.typography.titleLarge)
                        Text("复核版本 ${report.reviewVersion ?: item.reviewVersion} · Markdown", color = Graphite, style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.height(14.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            PrimaryAction("保存文件", { onPlatformAction {
                                if (platform.saveReport("${report.reportId}.md", report.contentMd)) state.notice = "报告已保存"
                            } }, !busy, Modifier.weight(1f))
                            OutlinedButton({ onPlatformAction { platform.shareReport("${report.reportId}.md", report.contentMd) } },
                                enabled = !busy, modifier = Modifier.weight(1f), contentPadding = PaddingValues(vertical = 14.dp)) { Text("分享") }
                        }
                        Spacer(Modifier.height(20.dp))
                        MarkdownPreview(report.contentMd)
                    }
                }
            }
        }
    }
}

@Composable
fun StatusPill(text: String, color: Color = SkyTint) {
    Surface(color = color, shape = RoundedCornerShape(99.dp)) {
        Text(text, Modifier.padding(horizontal = 10.dp, vertical = 5.dp), style = MaterialTheme.typography.labelSmall, color = Ink)
    }
}

@Composable
fun SourcePill(source: String) = StatusPill(if (source == "rule_fallback") "规则模板建议" else "云端 AI 建议", if (source == "rule_fallback") Butter.copy(alpha = .55f) else SkyTint)

@Composable
private fun AnalysisSection(title: String, values: List<String>) {
    if (values.isEmpty()) return
    Spacer(Modifier.height(18.dp))
    Text(title, style = MaterialTheme.typography.titleMedium)
    Spacer(Modifier.height(7.dp))
    values.forEachIndexed { index, value ->
        Row(Modifier.padding(vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
            Text("${index + 1}.", color = Graphite, style = MaterialTheme.typography.bodyMedium)
            Text(value, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
fun DetectionCards(boxes: List<Detection>, selectedId: String?, onSelect: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        boxes.forEachIndexed { index, box ->
            Surface(color = Color.White, shape = RoundedCornerShape(16.dp),
                border = if (box.detectionId == selectedId) BorderStroke(1.5.dp, SignalBlue) else null,
                modifier = Modifier.fillMaxWidth().clickable { onSelect(box.detectionId) }) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Surface(color = if (box.detectionId == selectedId) SkyTint else CanvasColor, shape = RoundedCornerShape(10.dp)) {
                        Text("${index + 1}", Modifier.padding(12.dp), fontWeight = FontWeight.Medium)
                    }
                    Column(Modifier.weight(1f)) {
                        Text(className(box.classId), style = MaterialTheme.typography.titleMedium)
                        Text(box.bbox.joinToString(" · ") { "${(it * 10).roundToInt() / 10.0}" }, color = Graphite, style = MaterialTheme.typography.bodySmall)
                    }
                    Text(if (box.source == "manual" || box.score == null) "人工" else "${(box.score * 100).roundToInt()}%",
                        color = if (box.source == "manual") Graphite else Ink, style = MaterialTheme.typography.labelLarge)
                }
            }
        }
    }
}

@Composable
private fun EmptyResult() {
    PaperCard(SkyTint) {
        Text("未检出六类目标缺陷", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(8.dp))
        Text("这不等同于产品合格。请检查图像质量并进行人工复核，可补充漏检框。", style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
fun <T> ChoiceField(label: String, selected: String, options: List<Pair<T, String>>, enabled: Boolean = true, onSelect: (T) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        OutlinedButton({ expanded = true }, enabled = enabled, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(10.dp)) {
            Text("$label：$selected", Modifier.weight(1f))
            Text("⌄")
        }
        DropdownMenu(expanded, { expanded = false }) {
            options.forEach { (value, title) ->
                DropdownMenuItem(text = { Text(title) }, onClick = { expanded = false; onSelect(value) })
            }
        }
    }
}
