package com.steelscan.app

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.header
import io.ktor.client.request.request
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.URLBuilder
import io.ktor.http.Url
import io.ktor.http.appendPathSegments
import io.ktor.http.contentType
import io.ktor.http.encodedPath
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class ApiException(val status: Int, val publicMessage: String) : Exception(publicMessage)

class SteelApi(private val httpClient: HttpClient, val connection: ConnectionSettings) {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }
    private val base = validatedBaseUrl(connection.baseUrl)

    suspend fun health(): Health = get(listOf("health"))

    suspend fun createInspection(image: PickedImage, batchNo: String, workpieceNo: String): CreatedInspection {
        requireInput(batchNo.isNotBlank(), "请填写批次号")
        requireInput(image.bytes.isNotEmpty() && image.bytes.size <= 10 * 1024 * 1024, "请选择不超过 10 MB 的图片")
        val extension = image.name.substringAfterLast('.', "").lowercase()
        requireInput(extension in listOf("jpg", "jpeg", "png", "bmp"), "仅支持 JPG、PNG 或 BMP 图片")
        val mimeType = when (extension) { "png" -> "image/png"; "bmp" -> "image/bmp"; else -> "image/jpeg" }
        // Use a fixed filename so user-provided names cannot become multipart header content.
        val body = MultiPartFormDataContent(formData {
            append("batch_no", batchNo.trim())
            if (workpieceNo.isNotBlank()) append("workpiece_no", workpieceNo.trim())
            append("image", image.bytes, Headers.build {
                append(HttpHeaders.ContentType, mimeType)
                append(HttpHeaders.ContentDisposition, "filename=\"inspection.$extension\"")
            })
        })
        return requestJson(HttpMethod.Post, listOf("api", "inspections")) { setBody(body) }
    }

    suspend fun inspection(id: String): Inspection = get(listOf("api", "inspections", id))

    suspend fun inspections(
        batchNo: String = "", classId: Int? = null, reviewStatus: String? = null, page: Int = 1,
    ): InspectionPage = get(listOf("api", "inspections"), buildMap {
        if (batchNo.isNotBlank()) put("batch_no", batchNo.trim())
        if (classId != null) put("class_id", classId.toString())
        if (!reviewStatus.isNullOrBlank()) put("review_status", reviewStatus)
        put("page", page.coerceAtLeast(1).toString())
        put("page_size", "20")
    })

    suspend fun analysis(id: String): Analysis =
        requestJson<AnalysisResponse>(HttpMethod.Post, listOf("api", "inspections", id, "analysis")).analysis

    suspend fun chat(id: String, question: String): ChatAnswer {
        requireInput(question.isNotBlank(), "请先输入问题")
        return requestJson(HttpMethod.Post, listOf("api", "chat", "messages")) {
            contentType(ContentType.Application.Json)
            setBody(json.encodeToString(ChatRequest(contextId = id, question = question.trim())))
        }
    }

    suspend fun review(
        id: String, version: Int, status: String, notes: String, corrections: List<Correction>,
    ): ReviewResult = requestJson(HttpMethod.Post, listOf("api", "inspections", id, "review")) {
        contentType(ContentType.Application.Json)
        setBody(json.encodeToString(ReviewRequest(version, status, notes, corrections)))
    }

    suspend fun batchSummary(batchNo: String): BatchSummary = get(listOf("api", "batches", batchNo, "summary"))

    suspend fun report(id: String): Report = get(listOf("api", "reports", id))

    suspend fun image(path: String): ByteArray {
        val imageUrl = sameOriginImageUrl(path)
        return guarded(30_000) {
            val response = httpClient.request(imageUrl) { authorize() }
            checkResponse(response)
            response.body<ByteArray>()
        }
    }

    private suspend inline fun <reified T> get(path: List<String>, query: Map<String, String> = emptyMap()): T =
        requestJson(HttpMethod.Get, path, query)

    private suspend inline fun <reified T> requestJson(
        method: HttpMethod,
        path: List<String>,
        query: Map<String, String> = emptyMap(),
        noinline block: HttpRequestBuilder.() -> Unit = {},
    ): T = guarded(if (method == HttpMethod.Post) 180_000 else 30_000) {
        val url = URLBuilder(base).apply {
            appendPathSegments(path, encodeSlash = true)
            query.forEach { (key, value) -> parameters.append(key, value) }
        }.build()
        val response = httpClient.request(url) {
            this.method = method
            authorize()
            block()
        }
        checkResponse(response)
        json.decodeFromString<T>(response.bodyAsText())
    }

    private fun HttpRequestBuilder.authorize() {
        if (connection.apiKey.isNotBlank()) header("X-API-Key", connection.apiKey.trim())
    }

    private fun sameOriginImageUrl(path: String): Url {
        val value = path.trim()
        requireInput(value.isNotEmpty() && !value.startsWith("//") && !value.contains('\\'), "图片地址无效")
        val url = try {
            if (value.startsWith('/')) {
                val origin = URLBuilder(base).apply { encodedPath = "" }.buildString().trimEnd('/')
                Url(origin + value)
            } else if (value.startsWith("http://") || value.startsWith("https://")) {
                Url(value)
            } else {
                throw ApiException(-1, "图片地址无效")
            }
        } catch (e: ApiException) { throw e } catch (_: Exception) { throw ApiException(-1, "图片地址无效") }
        requireInput(
            url.protocol == base.protocol && url.host == base.host && url.port == base.port &&
                url.user == null && url.password == null && url.fragment.isEmpty(),
            "服务返回了不同来源的图片地址，已停止加载",
        )
        return url
    }

    private fun checkResponse(response: HttpResponse) {
        val status = response.status.value
        if (status in 200..299) return
        val message = when (status) {
            401, 403 -> "连接凭据无效，请在设置中检查 API Key"
            404 -> "记录或服务地址不存在，请刷新后重试"
            409 -> "记录已被更新，请加载最新版本后重新复核；当前草稿已保留"
            400, 422 -> "提交内容无效，请检查图片、批次和标注内容"
            413 -> "图片超过服务允许的大小，请重新选择"
            429 -> "服务暂时繁忙，请稍后手动重试"
            502, 503 -> "云检测服务暂不可用，请稍后检查连接"
            504 -> "云服务等待超时，请先查询记录确认处理结果"
            in 300..399 -> "服务地址发生跳转，请在设置中填写最终业务 API 地址"
            else -> "服务处理失败，请稍后检查记录和服务状态"
        }
        throw ApiException(status, message)
    }

    private suspend fun <T> guarded(timeoutMs: Long, block: suspend () -> T): T = try {
        val result = withTimeoutOrNull(timeoutMs) { Result.success(block()) }
            ?: throw ApiException(0, "网络连接中断或等待超时，请检查连接")
        result.getOrThrow()
    } catch (e: CancellationException) {
        throw e
    } catch (e: ApiException) {
        throw e
    } catch (_: SerializationException) {
        throw ApiException(-1, "服务返回的数据格式无法识别，请检查前后端版本")
    } catch (_: Exception) {
        throw ApiException(0, "网络连接中断或等待超时，请检查连接")
    }

    private fun requireInput(valid: Boolean, message: String) {
        if (!valid) throw ApiException(-1, message)
    }
}

fun validatedBaseUrl(value: String): Url {
    val raw = value.trim()
    val invalid = ApiException(-1, "请输入有效的 HTTP 或 HTTPS 业务后端地址")
    if (!raw.startsWith("http://") && !raw.startsWith("https://")) throw invalid
    val url = try { Url(raw) } catch (_: Exception) { throw invalid }
    if (url.host.isBlank() || url.user != null || url.password != null ||
        raw.any { it == '?' || it == '#' || it == '\\' || it.isWhitespace() }) throw invalid
    return url
}

@Serializable
private data class AnalysisResponse(val analysis: Analysis)

@Serializable
private data class ChatRequest(
    @SerialName("context_type") val contextType: String = "inspection",
    @SerialName("context_id") val contextId: String,
    val question: String,
)

@Serializable
private data class ReviewRequest(
    @SerialName("base_version") val baseVersion: Int,
    @SerialName("review_status") val reviewStatus: String,
    val notes: String,
    val corrections: List<Correction>,
)
