package com.steelscan.app

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.ImageBitmap

data class PickedImage(
    val name: String,
    val mimeType: String,
    val bytes: ByteArray,
    val width: Int,
    val height: Int,
)

data class ConnectionSettings(val baseUrl: String = "http://10.0.2.2:8000", val apiKey: String = "")

interface PlatformBridge {
    suspend fun pickImage(): PickedImage?
    suspend fun takePhoto(): PickedImage?
    suspend fun decodeImage(bytes: ByteArray): ImageBitmap
    fun loadConnection(): ConnectionSettings
    fun saveConnection(settings: ConnectionSettings)
    suspend fun saveReport(fileName: String, markdown: String): Boolean
    fun shareReport(fileName: String, markdown: String)
}

@Composable
expect fun PlatformBackHandler(enabled: Boolean, onBack: () -> Unit)
