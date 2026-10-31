package com.steelscan.app

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.ktor.client.HttpClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

enum class MainPage { Detect, History, Settings }
enum class DetailTab { Result, Review, Assistant, Report }
data class ConversationTurn(val question: String, val response: ChatAnswer, val reviewVersion: Int?)

fun reviewDiff(original: List<Detection>, edited: List<Detection>): List<Correction> {
    val byId = edited.associateBy { it.detectionId }
    val originalIds = original.map { it.detectionId }.toSet()
    return buildList {
        original.forEach { before ->
            val after = byId[before.detectionId]
            when {
                after == null -> add(Correction("delete", before.detectionId))
                before.classId != after.classId || before.bbox != after.bbox ->
                    add(Correction("update", after.detectionId, after.classId, after.bbox))
            }
        }
        edited.filter { it.detectionId !in originalIds }.forEach {
            add(Correction("add", it.detectionId, it.classId, it.bbox))
        }
    }
}

class AppState : ViewModel() {
    private var api: SteelApi? = null
    var connection by mutableStateOf(ConnectionSettings()); private set
    var baseUrl by mutableStateOf("")
    var apiKey by mutableStateOf("")
    var page by mutableStateOf(MainPage.Detect)
    var tab by mutableStateOf(DetailTab.Result)
    var busy by mutableStateOf<String?>(null); private set
    var error by mutableStateOf<String?>(null)
    var notice by mutableStateOf<String?>(null)
    var health by mutableStateOf<Health?>(null); private set
    var picked by mutableStateOf<PickedImage?>(null); private set
    var batchNo by mutableStateOf("")
    var workpieceNo by mutableStateOf("")
    var inspection by mutableStateOf<Inspection?>(null); private set
    var originalBytes by mutableStateOf<ByteArray?>(null); private set
    var selectedId by mutableStateOf<String?>(null)
    var draftBoxes by mutableStateOf<List<Detection>>(emptyList())
    var notes by mutableStateOf("")
    var reviewStatus by mutableStateOf("confirmed")
    var conflict by mutableStateOf<Inspection?>(null); private set
    var conflictNeedsFetch by mutableStateOf(false); private set
    var question by mutableStateOf("")
    var conversation by mutableStateOf<List<ConversationTurn>>(emptyList()); private set
    var report by mutableStateOf<Report?>(null); private set
    var history by mutableStateOf<InspectionPage?>(null); private set
    var filterBatch by mutableStateOf("")
    var filterClass by mutableStateOf<Int?>(null)
    var filterStatus by mutableStateOf<String?>(null)
    var historyPage by mutableStateOf(1); private set
    var summary by mutableStateOf<BatchSummary?>(null); private set
    var uncertainUpload by mutableStateOf(false); private set
    var createdRecordId by mutableStateOf<String?>(null); private set
    var initialized by mutableStateOf(false); private set

    val dirty: Boolean get() {
        val item = inspection ?: return false
        return draftBoxes != item.reviewedDetections || notes != (item.review?.payload?.notes ?: "") ||
            reviewStatus != initialReviewStatus(item)
    }

    fun bind(client: HttpClient, settings: ConnectionSettings) {
        if (api != null) return
        connection = settings
        baseUrl = settings.baseUrl
        apiKey = settings.apiKey
        api = SteelApi(client, settings)
        initialized = true
    }

    fun reconnect(client: HttpClient, settings: ConnectionSettings) {
        api = SteelApi(client, settings)
        connection = settings
        inspection = null
        originalBytes = null
        report = null
        history = null
        summary = null
        health = null
        conversation = emptyList()
        uncertainUpload = false
        createdRecordId = null
        conflict = null
        conflictNeedsFetch = false
        notice = "连接设置已保存"
    }

    private fun task(label: String, mutation: Boolean = false, block: suspend SteelApi.() -> Unit) {
        if (busy != null) return
        val client = api ?: return
        busy = label
        error = null
        notice = null
        viewModelScope.launch {
            try {
                block(client)
            } catch (cancel: CancellationException) {
                throw cancel
            } catch (e: ApiException) {
                error = if (mutation && e.status == 0) "请求结果未确认。请先刷新记录或复核版本，再决定是否重新提交。" else e.publicMessage
            } catch (_: Exception) {
                error = "操作未完成，请检查连接后重试。"
            } finally {
                busy = null
            }
        }
    }

    fun checkConnection() = task("正在检查业务服务") {
        health = health()
        notice = "业务服务可达；云检测是否成功以实际检测为准。"
    }

    fun acceptPicked(image: PickedImage) {
        if (image.bytes.size > 10 * 1024 * 1024) {
            error = "图片超过 10 MB，请选择较小的图片。"
            return
        }
        picked = image
        uncertainUpload = false
        createdRecordId = null
        error = null
    }

    fun submitImage() {
        val image = picked ?: return
        if (batchNo.isBlank()) { error = "请填写批次号"; return }
        if (uncertainUpload) { error = "上次提交结果尚未确认，请先查看历史记录。"; return }
        task("正在上传并等待云检测", mutation = true) {
            uncertainUpload = true
            try {
                val created = createInspection(image, batchNo.trim(), workpieceNo.trim())
                createdRecordId = created.inspectionId
                openInspection(created.inspectionId)
                uncertainUpload = false
                picked = null
                notice = "检测完成，请查看结果并人工复核。"
            } catch (e: ApiException) {
                if (createdRecordId == null && e.status in listOf(400, 401, 403, 413, 422)) uncertainUpload = false
                createdRecordId?.let { notice = "检测已保存：$it。可重新打开该记录，不必再次上传。" }
                throw e
            }
        }
    }

    private suspend fun SteelApi.openInspection(id: String) {
        val item = inspection(id)
        if (item.inspectionId != id) throw ApiException(-1, "服务返回了不同的检测记录，请检查服务。")
        if (id == createdRecordId) { uncertainUpload = false; picked = null }
        this@AppState.inspection = item
        tab = DetailTab.Result
        originalBytes = null
        selectedId = null
        conversation = emptyList()
        question = ""
        report = null
        resetDraft()
        item.originalUrl?.let { path ->
            try { originalBytes = image(path) }
            catch (cancel: CancellationException) { throw cancel }
            catch (_: Exception) { notice = "记录已加载，原图加载失败；可刷新重试。" }
        }
    }

    fun openRecord(id: String) = task("正在读取记录") { openInspection(id) }

    fun refreshRecord() {
        val id = inspection?.inspectionId ?: return
        task("正在刷新记录") { openInspection(id) }
    }

    private fun initialReviewStatus(item: Inspection): String =
        item.reviewStatus.takeIf { it != "pending" } ?: "confirmed"

    fun resetDraft() {
        val item = inspection ?: return
        draftBoxes = item.reviewedDetections
        notes = item.review?.payload?.notes ?: ""
        reviewStatus = initialReviewStatus(item)
        conflict = null
        conflictNeedsFetch = false
    }

    fun updateDraft(boxes: List<Detection>) {
        draftBoxes = boxes
        if (boxes != inspection?.reviewedDetections) reviewStatus = "corrected"
    }

    fun changeClass(id: String, classId: Int) = updateDraft(draftBoxes.map {
        if (it.detectionId == id) it.copy(classId = classId, className = classLabels[classId], score = null, source = "manual") else it
    })

    fun saveReview() {
        val item = inspection ?: return
        if (conflict != null || conflictNeedsFetch) return
        val differences = reviewDiff(item.detections, draftBoxes)
        val status = if (reviewStatus == "confirmed" && differences.isNotEmpty()) "corrected" else reviewStatus
        task("正在保存人工复核", mutation = true) {
            var saved = false
            try {
                review(item.inspectionId, item.reviewVersion, status, notes.trim(), differences)
                saved = true
                this@AppState.inspection = inspection(item.inspectionId)
                resetDraft()
                report = null
                notice = "人工复核已保存，原模型预测保留。"
            } catch (e: ApiException) {
                if (saved || e.status !in listOf(400, 401, 403, 404, 413, 422)) {
                    conflictNeedsFetch = true
                    try {
                        conflict = inspection(item.inspectionId)
                        conflictNeedsFetch = false
                    } catch (cancel: CancellationException) { throw cancel }
                    catch (_: Exception) { /* The draft stays available while the server is unreachable. */ }
                }
                throw e
            }
        }
    }

    fun fetchConflict() {
        val id = inspection?.inspectionId ?: return
        task("正在确认服务器版本") {
            conflict = inspection(id)
            conflictNeedsFetch = false
        }
    }

    fun resolveConflict(keepDraft: Boolean) {
        val latest = conflict ?: return
        inspection = latest
        report = null
        conflict = null
        conflictNeedsFetch = false
        if (!keepDraft) resetDraft()
        notice = if (keepDraft) "已载入服务器版本 ${latest.reviewVersion}；草稿保留，请逐项核对后手动保存。" else "已采用服务器上的最新复核。"
        error = null
    }

    fun generateAnalysis() {
        val item = inspection ?: return
        val hadDraft = dirty
        task("正在生成复检建议", mutation = true) {
            val result = analysis(item.inspectionId)
            val latest = inspection(item.inspectionId)
            val checked = result.copy(stale = result.stale || result.reviewVersion != latest.reviewVersion)
            if (hadDraft && latest.reviewVersion != item.reviewVersion) {
                this@AppState.inspection = item.copy(analysis = checked.copy(stale = true))
                conflict = latest.copy(analysis = checked)
                notice = "服务器复核已更新。当前草稿保留，请在人工复核中核对新版本。"
            } else {
                this@AppState.inspection = latest.copy(analysis = checked)
                if (!hadDraft) resetDraft()
            }
            report = null
        }
    }

    fun askQuestion() {
        val item = inspection ?: return
        val text = question.trim()
        if (text.isEmpty()) return
        task("助手正在整理回答", mutation = true) {
            val reply = chat(item.inspectionId, text)
            conversation = conversation + ConversationTurn(text, reply, reply.reviewVersion)
            question = ""
        }
    }

    fun loadReport() {
        val item = inspection ?: return
        task("正在生成当前版本报告") { report = report(item.inspectionId) }
    }

    fun loadHistory(page: Int = 1) = task("正在读取历史记录") {
        history = inspections(filterBatch.trim(), filterClass, filterStatus, page)
        historyPage = page
        summary = null
    }

    fun loadBatchSummary() {
        if (filterBatch.isBlank()) { error = "先输入一个批次号"; return }
        task("正在读取批次统计") { summary = batchSummary(filterBatch.trim()) }
    }

    fun findUncertainUpload() {
        page = MainPage.History
        inspection = null
        filterBatch = batchNo.trim()
        loadHistory()
    }

    fun allowExplicitRetry() { uncertainUpload = false; page = MainPage.Detect }

    fun closeRecord() {
        inspection = null
        originalBytes = null
        conversation = emptyList()
        report = null
        error = null
    }
}
