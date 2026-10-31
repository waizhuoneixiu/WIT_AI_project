package com.steelscan.app

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class Detection(
    @SerialName("detection_id") val detectionId: String,
    @SerialName("class_id") val classId: Int,
    @SerialName("class_name") val className: String = "",
    val score: Double? = null,
    @SerialName("bbox_xyxy") val bbox: List<Double>,
    val source: String = "model",
)

@Serializable
data class Correction(
    val op: String = "update",
    @SerialName("detection_id") val detectionId: String,
    @SerialName("class_id") val classId: Int? = null,
    @SerialName("bbox_xyxy") val bbox: List<Double>? = null,
)

@Serializable
data class Inspection(
    @SerialName("inspection_id") val inspectionId: String,
    @SerialName("batch_no") val batchNo: String,
    @SerialName("workpiece_no") val workpieceNo: String? = null,
    @SerialName("image_width") val imageWidth: Int,
    @SerialName("image_height") val imageHeight: Int,
    @SerialName("model_version") val modelVersion: String,
    val detections: List<Detection>,
    @SerialName("reviewed_detections") val reviewedDetections: List<Detection> = emptyList(),
    @SerialName("review_version") val reviewVersion: Int = 0,
    @SerialName("review_status") val reviewStatus: String = "pending",
    @SerialName("review_invalid") val reviewInvalid: Boolean = false,
    @SerialName("original_url") val originalUrl: String? = null,
    @SerialName("annotated_url") val annotatedUrl: String? = null,
    val analysis: Analysis? = null,
    val review: Review? = null,
    @SerialName("created_at") val createdAt: String = "",
    val timing: Map<String, Double?> = emptyMap(),
)

@Serializable
data class Review(
    val payload: ReviewPayload = ReviewPayload(),
    val reviewer: String? = null,
    @SerialName("review_status") val reviewStatus: String = "",
    @SerialName("base_version") val baseVersion: Int = 0,
)

@Serializable
data class ReviewPayload(
    val notes: String? = null,
)

@Serializable
data class Analysis(
    val facts: List<String> = emptyList(),
    val references: List<String> = emptyList(),
    val hypotheses: List<String> = emptyList(),
    @SerialName("recheck_steps") val recheckSteps: List<String> = emptyList(),
    @SerialName("missing_information") val missingInformation: List<String> = emptyList(),
    val source: String = "rule_fallback",
    val model: String? = null,
    @SerialName("review_version") val reviewVersion: Int? = null,
    val stale: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class CreatedInspection(
    @SerialName("inspection_id") val inspectionId: String,
    @SerialName("task_id") val taskId: String,
    val status: String,
    @SerialName("detection_count") val detectionCount: Int = 0,
    @SerialName("image_width") val imageWidth: Int = 0,
    @SerialName("image_height") val imageHeight: Int = 0,
    @SerialName("model_version") val modelVersion: String = "",
)

@Serializable
data class InspectionSummary(
    @SerialName("inspection_id") val inspectionId: String,
    @SerialName("batch_no") val batchNo: String,
    @SerialName("workpiece_no") val workpieceNo: String? = null,
    @SerialName("review_status") val reviewStatus: String = "pending",
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("detection_count") val detectionCount: Int = 0,
    val classes: List<String> = emptyList(),
    @SerialName("annotated_url") val annotatedUrl: String? = null,
)

@Serializable
data class InspectionPage(
    val total: Int = 0,
    val page: Int = 1,
    @SerialName("page_size") val pageSize: Int = 20,
    val items: List<InspectionSummary> = emptyList(),
)

@Serializable
data class Health(
    val status: String = "",
    @SerialName("api_version") val apiVersion: String = "",
    @SerialName("auth_required") val authRequired: Boolean = false,
    val llm: LlmInfo = LlmInfo(),
    @SerialName("detector_provider") val detectorProvider: String = "",
    @SerialName("model_version") val modelVersion: String = "",
    @SerialName("detector_configured") val detectorConfigured: Boolean = false,
)

@Serializable
data class LlmInfo(
    val provider: String = "none",
    val mode: String = "",
    val model: String = "",
    val source: String = "rule_fallback",
    val configured: Boolean = false,
)

@Serializable
data class ChatAnswer(
    val answer: String,
    val references: List<String> = emptyList(),
    val source: String = "rule_fallback",
    @SerialName("task_id") val taskId: String = "",
    val status: String = "completed",
    @SerialName("review_version") val reviewVersion: Int? = null,
    val stale: Boolean = false,
)

@Serializable
data class ReviewResult(
    @SerialName("inspection_id") val inspectionId: String,
    @SerialName("review_status") val reviewStatus: String,
    @SerialName("review_version") val reviewVersion: Int,
)

@Serializable
data class BatchSummary(
    @SerialName("batch_no") val batchNo: String,
    @SerialName("image_count") val imageCount: Int,
    @SerialName("model_box_count") val modelBoxCount: Int,
    @SerialName("per_class") val perClass: Map<String, Int> = emptyMap(),
    @SerialName("review_stats") val reviewStats: Map<String, Int> = emptyMap(),
    @SerialName("confirmed_count") val confirmedCount: Int = 0,
    @SerialName("unresolved_count") val unresolvedCount: Int = 0,
)

@Serializable
data class Report(
    @SerialName("report_id") val reportId: String,
    @SerialName("inspection_id") val inspectionId: String,
    @SerialName("content_md") val contentMd: String,
    @SerialName("review_version") val reviewVersion: Int? = null,
    @SerialName("created_at") val createdAt: String = "",
    val format: String = "md",
)
