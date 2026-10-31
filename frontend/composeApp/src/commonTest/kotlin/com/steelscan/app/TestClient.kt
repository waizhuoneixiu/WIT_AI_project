package com.steelscan.app

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.MockRequestHandler
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope

fun TestScope.mockClient(handler: MockRequestHandler): HttpClient = HttpClient(
    MockEngine(MockEngineConfig().apply {
        // Keep the engine on virtual time so it runs before the request deadline advances.
        dispatcher = StandardTestDispatcher(testScheduler)
        addHandler(handler)
    }),
) {
    followRedirects = false
    expectSuccess = false
}
