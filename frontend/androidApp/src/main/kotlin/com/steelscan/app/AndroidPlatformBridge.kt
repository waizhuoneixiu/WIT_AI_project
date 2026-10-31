package com.steelscan.app

import android.content.ClipData
import android.content.Intent
import android.net.Uri
import androidx.activity.ComponentActivity
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.graphics.ImageBitmap
import androidx.core.content.FileProvider
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

internal class AndroidPlatformBridge(private val activity: ComponentActivity) : PlatformBridge {
    private val connections by lazy { ConnectionStore(activity.applicationContext) }
    private var picked: CancellableContinuation<Uri?>? = null
    private var photographed: CancellableContinuation<Boolean>? = null
    private var saved: CancellableContinuation<Uri?>? = null
    private val picker = activity.registerForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        picked?.takeIf { it.isActive }?.resume(uri)
        picked = null
    }
    private val camera = activity.registerForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        photographed?.takeIf { it.isActive }?.resume(success)
        photographed = null
    }
    private val document = activity.registerForActivityResult(ActivityResultContracts.CreateDocument("text/markdown")) { uri ->
        saved?.takeIf { it.isActive }?.resume(uri)
        saved = null
    }

    override suspend fun pickImage(): PickedImage? {
        val uri = suspendCancellableCoroutine<Uri?> { continuation ->
            check(picked == null) { "选图窗口已打开。" }
            picked = continuation
            continuation.invokeOnCancellation { picked = null }
            try {
                picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            } catch (error: Exception) {
                picked = null
                continuation.resumeWithException(IllegalStateException("无法打开选图窗口，请稍后重试。", error))
            }
        } ?: return null
        return withContext(Dispatchers.IO) { readPickedImage(activity.contentResolver, uri) }
    }

    override suspend fun takePhoto(): PickedImage? {
        val directory = File(activity.cacheDir, "camera").apply { mkdirs() }
        val file = File.createTempFile("inspection-", ".jpg", directory)
        try {
            val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.files", file)
            val success = suspendCancellableCoroutine<Boolean> { continuation ->
                check(photographed == null) { "相机已打开。" }
                photographed = continuation
                continuation.invokeOnCancellation { photographed = null }
                try {
                    camera.launch(uri)
                } catch (error: Exception) {
                    photographed = null
                    continuation.resumeWithException(IllegalStateException("无法打开相机，请改用选择图片。", error))
                }
            }
            return if (success) withContext(Dispatchers.IO) { readPickedImage(activity.contentResolver, uri) } else null
        } finally {
            file.delete()
        }
    }

    override suspend fun decodeImage(bytes: ByteArray): ImageBitmap = withContext(Dispatchers.Default) {
        decodePreview(bytes)
    }

    override fun loadConnection(): ConnectionSettings = connections.load()
    override fun saveConnection(settings: ConnectionSettings) = connections.save(settings)

    override suspend fun saveReport(fileName: String, markdown: String): Boolean {
        val uri = suspendCancellableCoroutine<Uri?> { continuation ->
            check(saved == null) { "保存窗口已打开。" }
            saved = continuation
            continuation.invokeOnCancellation { saved = null }
            try {
                document.launch(reportName(fileName))
            } catch (error: Exception) {
                saved = null
                continuation.resumeWithException(IllegalStateException("无法打开保存窗口，请改用分享。", error))
            }
        } ?: return false
        withContext(Dispatchers.IO) {
            val output = activity.contentResolver.openOutputStream(uri, "wt") ?: error("无法写入报告文件。")
            output.use { it.write(markdown.toByteArray(Charsets.UTF_8)) }
        }
        return true
    }

    override fun shareReport(fileName: String, markdown: String) {
        val directory = File(activity.cacheDir, "reports").apply { mkdirs() }
        val file = File(directory, reportName(fileName))
        file.writeText(markdown, Charsets.UTF_8)
        val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.files", file)
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/markdown"
            putExtra(Intent.EXTRA_STREAM, uri)
            clipData = ClipData.newUri(activity.contentResolver, "质检报告", uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        activity.startActivity(Intent.createChooser(intent, "分享质检报告"))
    }

    private fun reportName(fileName: String): String =
        fileName.substringAfterLast('/').substringAfterLast('\\').replace(Regex("[^\\p{L}\\p{N}._-]"), "_")
            .take(100).removeSuffix(".md").ifBlank { "inspection" } + ".md"
}
