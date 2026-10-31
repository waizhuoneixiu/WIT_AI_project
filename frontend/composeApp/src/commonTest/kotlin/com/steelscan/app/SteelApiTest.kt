package com.steelscan.app

import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class SteelApiTest {
    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    @Test
    fun inspectionReadsManualBoxesAndNullableMetadata() = runTest {
        val client = mockClient {
            assertEquals("local-key", it.headers["X-API-Key"])
            respond(
                """{"inspection_id":"I-1","batch_no":"B-1","image_width":200,"image_height":100,"model_version":"yolo26n-640-onnx","detections":[],"reviewed_detections":[{"detection_id":"manual-1","class_id":2,"class_name":"patches","score":null,"bbox_xyxy":[1,2,30,40],"source":"manual"}],"review_version":2,"review_invalid":true,"review":{"base_version":1,"payload":{"corrections":{"legacy":"invalid"},"notes":"保留备注"}},"analysis":{"facts":["人工复核"],"source":"rule_fallback","review_version":null,"created_at":null,"stale":true},"server_extra":true}""",
                headers = jsonHeaders,
            )
        }
        try {
            val detail = SteelApi(client, ConnectionSettings("https://example.test", "local-key")).inspection("I-1")
            assertEquals(2, detail.reviewVersion)
            assertEquals(null, detail.reviewedDetections.single().score)
            assertEquals("manual", detail.reviewedDetections.single().source)
            assertTrue(detail.analysis!!.stale)
            assertEquals(null, detail.analysis!!.reviewVersion)
            assertTrue(detail.reviewInvalid)
            assertEquals("保留备注", detail.review?.payload?.notes)
        } finally { client.close() }
    }

    @Test
    fun multipartDoesNotTrustImageFilenameForHeaders() = runTest {
        val client = mockClient {
            assertTrue(it.body.contentType.toString().startsWith("multipart/form-data"))
            val body = it.body.toByteArray().decodeToString()
            assertFalse(body.contains("Injected"))
            assertTrue(body.contains("filename=\"inspection.jpg\""))
            assertTrue(body.contains("name=batch_no") || body.contains("name=\"batch_no\""))
            assertTrue(body.contains("batch"))
            assertEquals("/api/inspections", it.url.encodedPath)
            respond("""{"inspection_id":"I-1","task_id":"T-1","status":"completed"}""", HttpStatusCode.Created, jsonHeaders)
        }
        try {
            val result = SteelApi(client, ConnectionSettings("https://example.test", "")).createInspection(
                PickedImage("name\"\r\nInjected.jpg", "incorrect/type", byteArrayOf(1, 2), 2, 1), " batch ", "",
            )
            assertEquals("I-1", result.inspectionId)
        } finally { client.close() }
    }

    @Test
    fun reviewsIncludeVersionAndFullCorrectionsWithoutScores() = runTest {
        val client = mockClient {
            val payload = Json.parseToJsonElement((it.body as TextContent).text).jsonObject
            assertEquals("3", payload.getValue("base_version").jsonPrimitive.content)
            val update = payload.getValue("corrections").jsonArray.single().jsonObject
            assertEquals("update", update.getValue("op").jsonPrimitive.content)
            assertEquals("2", update.getValue("class_id").jsonPrimitive.content)
            assertFalse("score" in update)
            respond("""{"inspection_id":"I-1","review_status":"corrected","review_version":4}""", headers = jsonHeaders)
        }
        try {
            val result = SteelApi(client, ConnectionSettings("https://example.test", "")).review(
                "I-1", 3, "corrected", "人工改类", listOf(Correction(detectionId = "D-1", classId = 2)),
            )
            assertEquals(4, result.reviewVersion)
        } finally { client.close() }
    }

    @Test
    fun batchIdsAndFiltersRemainData() = runTest {
        val client = mockClient {
            assertTrue("B%2F1%3F" in it.url.encodedPath)
            assertTrue(it.url.encodedPath.endsWith("/summary"))
            assertTrue(it.url.parameters.names().isEmpty())
            respond("""{"batch_no":"B/1?","image_count":1,"model_box_count":2}""", headers = jsonHeaders)
        }
        try {
            assertEquals(2, SteelApi(client, ConnectionSettings("https://example.test", "")).batchSummary("B/1?").modelBoxCount)
        } finally { client.close() }
    }

    @Test
    fun errorResponseDoesNotExposeServerBodyOrAutomaticallyRetry() = runTest {
        var requests = 0
        val client = mockClient {
            requests++
            respond("secret-token-in-error", HttpStatusCode.Conflict, jsonHeaders)
        }
        try {
            val error = assertFailsWith<ApiException> {
                SteelApi(client, ConnectionSettings("https://example.test", "")).review("I", 0, "confirmed", "", emptyList())
            }
            assertEquals(409, error.status)
            assertFalse(error.publicMessage.contains("secret"))
            assertEquals(1, requests)
        } finally { client.close() }
    }

    @Test
    fun imageCredentialsCannotLeaveConfiguredOrigin() = runTest {
        var requests = 0
        val client = mockClient {
            requests++
            assertEquals("local-key", it.headers["X-API-Key"])
            assertEquals("example.test", it.url.host)
            respond(byteArrayOf(1, 2), headers = headersOf(HttpHeaders.ContentType, "image/png"))
        }
        try {
            val api = SteelApi(client, ConnectionSettings("https://example.test", "local-key"))
            assertFailsWith<ApiException> { api.image("https://other.test/image.png") }
            assertFailsWith<ApiException> { api.image("//other.test/image.png") }
            assertFailsWith<ApiException> { api.image("http://example.test/image.png") }
            assertEquals(2, api.image("/files/image.png").size)
            assertEquals(1, requests)
        } finally { client.close() }
    }

    @Test
    fun networkFailureIsUncertainAndDoesNotRetry() = runTest {
        var requests = 0
        val client = mockClient { requests++; throw IllegalStateException("socket closed") }
        try {
            val failure = assertFailsWith<ApiException> {
                SteelApi(client, ConnectionSettings("https://example.test", "")).chat("I", "检查缺陷")
            }
            assertEquals(0, failure.status)
            assertEquals(1, requests)
        } finally { client.close() }
    }

    @Test
    fun historyFiltersAreEscapedQueryValues() = runTest {
        val client = mockClient {
            assertEquals("B & other=1", it.url.parameters["batch_no"])
            assertEquals("2", it.url.parameters["class_id"])
            assertEquals("pending", it.url.parameters["review_status"])
            assertEquals(null, it.url.parameters["other"])
            respond("""{"total":0,"page":1,"page_size":20,"items":[]}""", headers = jsonHeaders)
        }
        try {
            assertEquals(0, SteelApi(client, ConnectionSettings("https://example.test", "")).inspections("B & other=1", 2, "pending").total)
        } finally { client.close() }
    }

    @Test
    fun malformedResponseIsNotTreatedAsEmptyDetection() = runTest {
        val client = mockClient { respond("{\"unexpected\":true}", headers = jsonHeaders) }
        try {
            val error = assertFailsWith<ApiException> {
                SteelApi(client, ConnectionSettings("https://example.test", "")).inspection("I")
            }
            assertEquals(-1, error.status)
        } finally { client.close() }
    }

    @Test
    fun callerCancellationIsPreserved() = runTest {
        val client = mockClient { awaitCancellation() }
        try {
            var cancellation = false
            val job = launch {
                try {
                    SteelApi(client, ConnectionSettings("https://example.test", "")).health()
                } catch (_: CancellationException) { cancellation = true }
            }
            testScheduler.runCurrent()
            job.cancel()
            job.join()
            assertTrue(cancellation)
        } finally { client.close() }
    }

    @Test
    fun requestDeadlineBecomesUncertainAfterEngineActuallyStarts() = runTest {
        var requests = 0
        val client = mockClient { requests++; awaitCancellation() }
        try {
            val failure = assertFailsWith<ApiException> {
                SteelApi(client, ConnectionSettings("https://example.test", "")).health()
            }
            assertEquals(0, failure.status)
            assertEquals(1, requests)
            assertEquals(30_000L, testScheduler.currentTime)
        } finally { client.close() }
    }

    @Test
    fun addressValidationRejectsEmbeddedCredentialsAndQuery() {
        listOf("file:///secret", "https://user:password@example.test", "https://example.test?key=x", "https://example.test#x").forEach {
            assertFailsWith<ApiException> { validatedBaseUrl(it) }
        }
        assertEquals("127.0.0.1", validatedBaseUrl(" http://127.0.0.1:8000 ").host)
    }
}
