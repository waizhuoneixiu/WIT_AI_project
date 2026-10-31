package com.steelscan.app

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.exifinterface.media.ExifInterface
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

internal const val MAX_IMAGE_BYTES = 10 * 1024 * 1024

internal fun readPickedImage(resolver: ContentResolver, uri: Uri): PickedImage {
    val bytes = resolver.openInputStream(uri)?.use { stream ->
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (output.size() <= MAX_IMAGE_BYTES) {
            val count = stream.read(buffer, 0, minOf(buffer.size, MAX_IMAGE_BYTES + 1 - output.size()))
            if (count == -1) break
            output.write(buffer, 0, count)
        }
        output.toByteArray()
    }
        ?: error("无法读取图片，请重新选择。")
    require(bytes.size <= MAX_IMAGE_BYTES) { "图片超过 10 MB，请选择较小的原图。" }
    val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
    require(options.outWidth > 0 && options.outHeight > 0) { "图片已损坏或格式不受支持。" }
    val extension = when (options.outMimeType) {
        "image/jpeg" -> "jpg"
        "image/png" -> "png"
        "image/bmp", "image/x-ms-bmp" -> "bmp"
        else -> error("请选择 JPG、PNG 或 BMP 图片。")
    }
    require(options.outWidth.toLong() * options.outHeight <= 100_000_000) {
        "图片分辨率过大，请选择不超过 1 亿像素的图片。"
    }
    val displayName = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
        if (it.moveToFirst()) it.getString(0) else null
    } ?: "image.$extension"
    val orientation = imageOrientation(bytes)
    val rotated = orientation in setOf(ExifInterface.ORIENTATION_TRANSPOSE, ExifInterface.ORIENTATION_ROTATE_90,
        ExifInterface.ORIENTATION_TRANSVERSE, ExifInterface.ORIENTATION_ROTATE_270)
    return PickedImage(
        name = displayName.substringBeforeLast('.', displayName).take(120) + ".$extension",
        mimeType = if (extension == "bmp") "image/bmp" else options.outMimeType,
        bytes = bytes,
        width = if (rotated) options.outHeight else options.outWidth,
        height = if (rotated) options.outWidth else options.outHeight,
    )
}

internal fun decodePreview(bytes: ByteArray): ImageBitmap {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    require(bounds.outWidth > 0 && bounds.outHeight > 0) { "无法显示图片。" }
    var sampleSize = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / sampleSize > 2048) sampleSize *= 2
    val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size,
        BitmapFactory.Options().apply { inSampleSize = sampleSize }) ?: error("无法显示图片。")
    val matrix = Matrix().apply {
        when (imageOrientation(bytes)) {
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> setScale(-1f, 1f)
            ExifInterface.ORIENTATION_ROTATE_180 -> setRotate(180f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> setScale(1f, -1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> { setRotate(90f); postScale(-1f, 1f) }
            ExifInterface.ORIENTATION_ROTATE_90 -> setRotate(90f)
            ExifInterface.ORIENTATION_TRANSVERSE -> { setRotate(-90f); postScale(-1f, 1f) }
            ExifInterface.ORIENTATION_ROTATE_270 -> setRotate(-90f)
        }
    }
    if (matrix.isIdentity) return bitmap.asImageBitmap()
    val oriented = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
    if (oriented !== bitmap) bitmap.recycle()
    return oriented.asImageBitmap()
}

private fun imageOrientation(bytes: ByteArray): Int = runCatching {
    ExifInterface(ByteArrayInputStream(bytes)).getAttributeInt(ExifInterface.TAG_ORIENTATION,
        ExifInterface.ORIENTATION_NORMAL)
}.getOrDefault(ExifInterface.ORIENTATION_NORMAL)
