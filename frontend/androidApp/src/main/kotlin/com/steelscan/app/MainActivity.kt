package com.steelscan.app

import android.app.Application
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import java.util.concurrent.TimeUnit
import okhttp3.OkHttpClient

internal fun cloudHttpTransport() = OkHttpClient.Builder()
    .followRedirects(false)
    .followSslRedirects(false)
    .retryOnConnectionFailure(false)
    .connectTimeout(10, TimeUnit.SECONDS)
    .readTimeout(180, TimeUnit.SECONDS)
    .writeTimeout(60, TimeUnit.SECONDS)
    .callTimeout(180, TimeUnit.SECONDS)
    .build()

class SteelScanApplication : Application() {
    val httpClient by lazy {
        HttpClient(OkHttp) {
            followRedirects = false
            expectSuccess = false
            engine {
                preconfigured = cloudHttpTransport()
            }
        }
    }
}

class MainActivity : ComponentActivity() {
    private val platform = AndroidPlatformBridge(this)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val client = (application as SteelScanApplication).httpClient
        setContent { App(platform = platform, httpClient = client) }
    }
}
