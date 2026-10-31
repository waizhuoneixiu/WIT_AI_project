package com.steelscan.app

import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class AppStateTest {
    private val headers = headersOf(HttpHeaders.ContentType, "application/json")
    private val picked = PickedImage("test.png", "image/png", byteArrayOf(1, 2, 3), 20, 20)
    private val detail = """{"inspection_id":"INSP-1","batch_no":"B1","image_width":20,"image_height":20,"model_version":"fixture","detections":[],"reviewed_detections":[],"review_version":0,"review_status":"pending"}"""

    @Test
    fun createdRecordSurvivesDetailFailureWithoutAllowingAnotherPost() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var posts = 0
        val client = mockClient { request ->
            if (request.method.value == "POST") {
                posts++
                respond("""{"inspection_id":"INSP-1","task_id":"T1","status":"completed"}""", headers = headers)
            } else respond("{}", HttpStatusCode.NotFound, headers)
        }
        try {
            val state = AppState()
            state.bind(client, ConnectionSettings("https://api.test", ""))
            state.batchNo = "B1"
            state.acceptPicked(picked)
            state.submitImage()
            advanceUntilIdle()
            assertEquals("INSP-1", state.createdRecordId)
            assertTrue(state.uncertainUpload)
            state.submitImage()
            advanceUntilIdle()
            assertEquals(1, posts)
        } finally { client.close(); Dispatchers.resetMain() }
    }

    @Test
    fun malformedSuccessfulCreationIsStillAnUnknownSubmission() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val client = mockClient { respond("{}", headers = headers) }
        try {
            val state = AppState()
            state.bind(client, ConnectionSettings("https://api.test", ""))
            state.batchNo = "B1"
            state.acceptPicked(picked)
            state.submitImage()
            advanceUntilIdle()
            assertTrue(state.uncertainUpload)
            assertNotNull(state.error)
        } finally { client.close(); Dispatchers.resetMain() }
    }

    @Test
    fun savedReviewWithFailedRefreshKeepsDraftAndRequiresVersionCheck() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var gets = 0
        val client = mockClient { request ->
            if (request.method.value == "POST") {
                respond("""{"inspection_id":"INSP-1","review_status":"confirmed","review_version":1}""", headers = headers)
            } else {
                gets++
                if (gets == 1) respond(detail, headers = headers)
                else respond("{}", HttpStatusCode.ServiceUnavailable, headers)
            }
        }
        try {
            val state = AppState()
            state.bind(client, ConnectionSettings("https://api.test", ""))
            state.openRecord("INSP-1")
            advanceUntilIdle()
            state.notes = "人工备注"
            state.saveReview()
            advanceUntilIdle()
            assertEquals("人工备注", state.notes)
            assertTrue(state.conflictNeedsFetch)
            assertEquals(0, state.inspection?.reviewVersion)
        } finally { client.close(); Dispatchers.resetMain() }
    }

    @Test
    fun analysisRefreshDoesNotOverwriteDraftWhenServerReviewAdvances() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var gets = 0
        val client = mockClient { request ->
            if (request.method.value == "POST") {
                respond("""{"analysis":{"facts":["最新事实"],"review_version":2,"stale":false}}""", headers = headers)
            } else {
                gets++
                respond(if (gets == 1) detail else detail.replace("\"review_version\":0", "\"review_version\":2"), headers = headers)
            }
        }
        try {
            val state = AppState()
            state.bind(client, ConnectionSettings("https://api.test", ""))
            state.openRecord("INSP-1")
            advanceUntilIdle()
            state.notes = "未保存草稿"
            state.generateAnalysis()
            advanceUntilIdle()
            assertEquals("未保存草稿", state.notes)
            assertEquals(0, state.inspection?.reviewVersion)
            assertEquals(2, state.conflict?.reviewVersion)
            assertTrue(state.inspection?.analysis?.stale == true)
        } finally { client.close(); Dispatchers.resetMain() }
    }
}
