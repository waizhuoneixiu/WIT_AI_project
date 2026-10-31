package com.steelscan.app

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun HistoryScreen(state: AppState, busy: Boolean, onExplicitRetry: () -> Unit) {
    ScreenColumn {
        SectionTitle("每一次，都有记录。", "按批次查看检测证据与人工判断。")
        PaperCard(Lavender) {
            OutlinedTextField(state.filterBatch, { state.filterBatch = it }, label = { Text("批次号") },
                placeholder = { Text("留空查看全部批次") }, modifier = Modifier.fillMaxWidth(), enabled = !busy, singleLine = true)
            ChoiceField("模型类别", state.filterClass?.let(::className) ?: "全部", listOf(null to "全部") + classNames.mapIndexed { i, label -> i to label }, !busy) {
                state.filterClass = it
            }
            ChoiceField("复核状态", state.filterStatus?.let(::reviewLabel) ?: "全部", listOf(null to "全部", "pending" to "待复核", "confirmed" to "已确认", "corrected" to "已修正", "unresolved" to "无法判断"), !busy) {
                state.filterStatus = it
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PrimaryAction("查询记录", { state.loadHistory() }, !busy, Modifier.weight(1f))
                OutlinedButton(state::loadBatchSummary, enabled = !busy && state.filterBatch.isNotBlank(),
                    modifier = Modifier.weight(1f), contentPadding = PaddingValues(vertical = 14.dp)) { Text("批次汇总") }
            }
            Spacer(Modifier.height(8.dp))
            Text("类别筛选基于原模型预测。", color = Graphite, style = MaterialTheme.typography.bodySmall)
        }
        state.summary?.let { summary ->
            PaperCard(Mint) {
                Text("${summary.batchNo} · 批次汇总", style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(14.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Stat("图片", summary.imageCount)
                    Stat("模型框", summary.modelBoxCount)
                    Stat("已复核图片", summary.confirmedCount)
                }
                Spacer(Modifier.height(14.dp))
                summary.perClass.forEach { (name, count) ->
                    InfoRow(className(classLabels.indexOf(name)), count.toString())
                }
                Text("框数和类别分布来自原预测；已复核图片数包含确认与修正，不代表人工确认缺陷数。", color = Graphite, style = MaterialTheme.typography.bodySmall)
            }
        }
        if (state.uncertainUpload) {
            PaperCard(Butter.copy(alpha = .5f)) {
                Text("请核对上次提交", style = MaterialTheme.typography.titleMedium)
                Text("找到对应记录后可打开继续复核；暂未找到可稍后刷新。", style = MaterialTheme.typography.bodyMedium)
                state.createdRecordId?.let { id ->
                    TextButton({ state.openRecord(id) }, enabled = !busy) { Text("打开已保存的记录") }
                } ?: TextButton(onExplicitRetry, enabled = !busy) { Text("确实没有记录，重新提交") }
            }
        }
        val history = state.history
        if (history == null) {
            Text("点击查询，读取服务端记录。", color = Graphite)
        } else {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("检测记录", style = MaterialTheme.typography.titleLarge)
                Text("共 ${history.total} 条", color = Graphite)
            }
            if (history.items.isEmpty()) {
                PaperCard(SkyTint) {
                    Text("还没有匹配的记录", style = MaterialTheme.typography.titleLarge)
                    Spacer(Modifier.height(8.dp))
                    Text("可调整筛选条件，或从检测页开始。", color = Graphite)
                }
            }
            history.items.forEach { item ->
                PaperCard(modifier = Modifier.clickable(enabled = !busy) { state.openRecord(item.inspectionId) }) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text(item.batchNo, style = MaterialTheme.typography.titleMedium)
                        StatusPill(reviewLabel(item.reviewStatus), if (item.reviewStatus == "pending") Butter else SkyTint)
                    }
                    Spacer(Modifier.height(10.dp))
                    Text(item.workpieceNo?.takeIf { it.isNotBlank() } ?: "未填写工件编号", color = Graphite, style = MaterialTheme.typography.bodyMedium)
                    Text(if (item.detectionCount == 0) "未检出六类目标缺陷" else "${item.detectionCount} 个模型框 · ${item.classes.joinToString("、") { className(classLabels.indexOf(it)) }}",
                        style = MaterialTheme.typography.bodyMedium)
                    Spacer(Modifier.height(8.dp))
                    Text(item.createdAt.replace('T', ' '), color = Graphite, style = MaterialTheme.typography.bodySmall)
                    Text(item.inspectionId, color = Graphite, style = MaterialTheme.typography.bodySmall)
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                TextButton({ state.loadHistory(state.historyPage - 1) }, enabled = !busy && state.historyPage > 1) { Text("上一页") }
                Text("第 ${state.historyPage} 页", color = Graphite)
                TextButton({ state.loadHistory(state.historyPage + 1) }, enabled = !busy && state.historyPage * history.pageSize < history.total) { Text("下一页") }
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: Int) {
    Column {
        Text(value.toString(), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
        Text(label, color = Graphite, style = MaterialTheme.typography.bodySmall)
    }
}
