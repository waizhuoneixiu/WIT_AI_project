package com.steelscan.app

import android.graphics.Bitmap
import android.graphics.Color
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.exifinterface.media.ExifInterface
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AndroidPlatformTest {
    @Test
    fun cloudTransportWaitsForInferenceWithoutRedirectOrRetry() {
        val client = cloudHttpTransport()
        assertEquals(180_000, client.readTimeoutMillis)
        assertEquals(60_000, client.writeTimeoutMillis)
        assertEquals(10_000, client.connectTimeoutMillis)
        assertTrue(!client.followRedirects && !client.followSslRedirects && !client.retryOnConnectionFailure)
    }

    @Test
    fun previewAppliesExifRotationAndMirror() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val image = Bitmap.createBitmap(40, 20, Bitmap.Config.ARGB_8888).apply {
            eraseColor(Color.BLUE)
            for (x in 0 until 20) for (y in 0 until 20) setPixel(x, y, Color.RED)
        }
        val file = File.createTempFile("orientation-", ".jpg", context.cacheDir)
        try {
            file.outputStream().use { image.compress(Bitmap.CompressFormat.JPEG, 100, it) }
            val exif = ExifInterface(file)
            exif.setAttribute(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_ROTATE_90.toString())
            exif.saveAttributes()
            val rotated = decodePreview(file.readBytes()).asAndroidBitmap()
            assertEquals(20, rotated.width)
            assertEquals(40, rotated.height)
            assertTrue(Color.red(rotated.getPixel(10, 5)) > Color.blue(rotated.getPixel(10, 5)))
            assertTrue(Color.blue(rotated.getPixel(10, 35)) > Color.red(rotated.getPixel(10, 35)))

            exif.setAttribute(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_FLIP_HORIZONTAL.toString())
            exif.saveAttributes()
            val mirrored = decodePreview(file.readBytes()).asAndroidBitmap()
            assertTrue(Color.blue(mirrored.getPixel(5, 10)) > Color.red(mirrored.getPixel(5, 10)))
            assertTrue(Color.red(mirrored.getPixel(35, 10)) > Color.blue(mirrored.getPixel(35, 10)))
        } finally {
            image.recycle()
            file.delete()
        }
    }

    @Test
    fun storedApiKeyIsEncryptedAndRoundTrips() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val store = ConnectionStore(context)
        val before = store.load()
        try {
            val value = ConnectionSettings("http://10.0.2.2:8011", "instrumentation-test-key")
            store.save(value)
            assertEquals(value, store.load())
            val stored = context.getSharedPreferences("connection", 0).getString("api_key", "")
            assertTrue(stored != value.apiKey)
        } finally {
            store.save(before)
        }
    }
}
