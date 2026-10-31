package com.steelscan.app

import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class HistoryStateTest {
    private val headers = headersOf(HttpHeaders.ContentType, "application/json")
    private val emptyPage = """{"items":[],"total":0,"page":1,"page_size":20}"""
    private val detail = """{"inspection_id":"INSP-1","batch_no":"B1","image_width":20,"image_height":20,"model_version":"fixture","detections":[],"review_status":"pending"}"""

    @Test
    fun firstVisitReadsOnceAndReentryKeepsTheListUntilExplicitRefresh() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var reads = 0
        val client = mockClient { reads++; respond(emptyPage, headers = headers) }
        try {
            val state = AppState()
            state.bind(client, ConnectionSettings("https://api.test", ""))
            state.showPage(MainPage.History)
            state.ensureHistoryLoaded()
            advanceUntilIdle()
            assertNotNull(state.history)
            state.showPage(MainPage.Detect)
            state.showPage(MainPage.History)
            state.ensureHistoryLoaded()
            advanceUntilIdle()
            assertEquals(1, reads)
            state.loadHistory()
            advanceUntilIdle()
            assertEquals(2, reads)
        } finally { client.close(); Dispatchers.resetMain() }
    }

    @Test
    fun savingTheSameConnectionDoesNotInvalidateHistory() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var reads = 0
        val client = mockClient { reads++; respond(emptyPage, headers = headers) }
        try {
            val state = AppState()
            val connection = ConnectionSettings("https://api.test", "")
            state.bind(client, connection)
            state.ensureHistoryLoaded()
            advanceUntilIdle()
            val previous = state.history
            state.reconnect(client, connection)
            state.ensureHistoryLoaded()
            advanceUntilIdle()
            assertEquals(1, reads)
            assertEquals(previous, state.history)
        } finally { client.close(); Dispatchers.resetMain() }
    }

    @Test
    fun slowHistoryReadDoesNotBlockNavigationOrDuplicateRequests() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val release = CompletableDeferred<Unit>()
        var reads = 0
        val client = mockClient {
            reads++
            release.await()
            respond(emptyPage, headers = headers)
        }
        try {
            val state = AppState()
            state.bind(client, ConnectionSettings("https://api.test", ""))
            state.ensureHistoryLoaded()
            runCurrent()
            assertTrue(state.historyLoading)
            assertNull(state.busy)
            state.showPage(MainPage.Settings)
            assertEquals(MainPage.Settings, state.page)
            state.showPage(MainPage.Detect)
            assertEquals(MainPage.Detect, state.page)
            state.ensureHistoryLoaded()
            state.loadHistory()
            runCurrent()
            assertEquals(1, reads)
            release.complete(Unit)
            advanceUntilIdle()
            assertNotNull(state.history)
            assertEquals(MainPage.Detect, state.page)
            assertFalse(state.historyLoading)
        } finally { release.complete(Unit); client.close(); Dispatchers.resetMain() }
    }

    @Test
    fun failedFirstReadWaitsForManualRetryRatherThanRetryingOnEveryVisit() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var reads = 0
        val client = mockClient {
            reads++
            if (reads == 1) respond("{}", HttpStatusCode.ServiceUnavailable, headers)
            else respond(emptyPage, headers = headers)
        }
        try {
            val state = AppState()
            state.bind(client, ConnectionSettings("https://api.test", ""))
            state.ensureHistoryLoaded()
            advanceUntilIdle()
            assertNotNull(state.historyError)
            assertNull(state.busy)
            state.showPage(MainPage.Settings)
            state.showPage(MainPage.History)
            state.ensureHistoryLoaded()
            advanceUntilIdle()
            assertEquals(1, reads)
            state.loadHistory()
            advanceUntilIdle()
            assertEquals(2, reads)
            assertNull(state.historyError)
            assertNotNull(state.history)
        } finally { client.close(); Dispatchers.resetMain() }
    }

    @Test
    fun failedRefreshKeepsPreviouslyLoadedRecordsAndPage() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        var reads = 0
        val client = mockClient {
            reads++
            if (reads == 1) respond("""{"items":[{"inspection_id":"KEEP-1","batch_no":"B1"}],"total":21,"page":2,"page_size":20}""", headers = headers)
            else respond("{}", HttpStatusCode.ServiceUnavailable, headers)
        }
        try {
            val state = AppState()
            state.bind(client, ConnectionSettings("https://api.test", ""))
            state.loadHistory(2)
            advanceUntilIdle()
            val previous = state.history
            state.loadHistory()
            advanceUntilIdle()
            assertEquals(previous, state.history)
            assertEquals("KEEP-1", state.history?.items?.single()?.inspectionId)
            assertEquals(2, state.historyPage)
            assertNotNull(state.historyError)
            assertFalse(state.historyLoading)
        } finally { client.close(); Dispatchers.resetMain() }
    }

    @Test
    fun reconnectCancelsOldHistoryAndReadsNewServiceOnce() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val oldResponse = CompletableDeferred<Unit>()
        val oldClient = mockClient {
            oldResponse.await()
            respond(emptyPage.replace("\"total\":0", "\"total\":99"), headers = headers)
        }
        var newReads = 0
        val newClient = mockClient { newReads++; respond(emptyPage, headers = headers) }
        try {
            val state = AppState()
            state.bind(oldClient, ConnectionSettings("https://old.test", ""))
            state.ensureHistoryLoaded()
            runCurrent()
            state.reconnect(newClient, ConnectionSettings("https://new.test", ""))
            state.ensureHistoryLoaded()
            oldResponse.complete(Unit)
            advanceUntilIdle()
            assertEquals(1, newReads)
            assertEquals(0, state.history?.total)
            assertFalse(state.historyLoading)
        } finally { oldResponse.complete(Unit); oldClient.close(); newClient.close(); Dispatchers.resetMain() }
    }

    @Test
    fun leavingWhileRecordOpensCancelsReadWithoutReopeningTheDetail() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val release = CompletableDeferred<Unit>()
        val client = mockClient { release.await(); respond(detail, headers = headers) }
        try {
            val state = AppState()
            state.bind(client, ConnectionSettings("https://api.test", ""))
            state.showPage(MainPage.History)
            state.openRecord("INSP-1")
            runCurrent()
            assertTrue(state.recordLoading)
            assertNull(state.busy)
            state.showPage(MainPage.Settings)
            release.complete(Unit)
            advanceUntilIdle()
            assertEquals(MainPage.Settings, state.page)
            assertNull(state.inspection)
            assertFalse(state.recordLoading)
            assertNull(state.error)
        } finally { release.complete(Unit); client.close(); Dispatchers.resetMain() }
    }
}
