package com.steelscan.app

import kotlin.math.max
import kotlin.math.min
import kotlin.math.round

data class PixelPoint(val x: Float, val y: Float)

fun hitBox(boxes: List<PixelBox>, point: PixelPoint): Int = boxes.indexOfLast { it.contains(point) }

data class PixelBox(val left: Float, val top: Float, val right: Float, val bottom: Float) {
    val width get() = right - left
    val height get() = bottom - top
    fun contains(point: PixelPoint) = point.x in left..right && point.y in top..bottom
    fun coordinates() = listOf(left, top, right, bottom).map { round(it.toDouble() * 10000) / 10000 }
    fun valid(width: Float, height: Float) =
        listOf(left, top, right, bottom).all { it.isFinite() } &&
            left >= 0f && top >= 0f && right <= width && bottom <= height &&
            right > left && bottom > top

    fun moved(dx: Float, dy: Float, imageWidth: Float, imageHeight: Float): PixelBox {
        val x = (left + dx).coerceIn(0f, max(0f, imageWidth - width))
        val y = (top + dy).coerceIn(0f, max(0f, imageHeight - height))
        return PixelBox(x, y, x + width, y + height)
    }

    fun resized(corner: Int, point: PixelPoint, imageWidth: Float, imageHeight: Float): PixelBox {
        val minWidth = min(1f, width)
        val minHeight = min(1f, height)
        return when (corner) {
            0 -> copy(left = point.x.coerceIn(0f, right - minWidth), top = point.y.coerceIn(0f, bottom - minHeight))
            1 -> copy(right = point.x.coerceIn(left + minWidth, imageWidth), top = point.y.coerceIn(0f, bottom - minHeight))
            2 -> copy(right = point.x.coerceIn(left + minWidth, imageWidth), bottom = point.y.coerceIn(top + minHeight, imageHeight))
            3 -> copy(left = point.x.coerceIn(0f, right - minWidth), bottom = point.y.coerceIn(top + minHeight, imageHeight))
            else -> this
        }
    }

    fun cornerNear(point: PixelPoint, radius: Float): Int {
        val distances = corners().map { (point.x - it.x) * (point.x - it.x) + (point.y - it.y) * (point.y - it.y) }
        val nearest = distances.indices.minBy { distances[it] }
        return nearest.takeIf { distances[it] <= radius * radius } ?: -1
    }

    fun corners() = listOf(PixelPoint(left, top), PixelPoint(right, top), PixelPoint(right, bottom), PixelPoint(left, bottom))

    companion object {
        fun from(coordinates: List<Double>): PixelBox? = if (coordinates.size == 4 && coordinates.all { it.isFinite() }) {
            PixelBox(coordinates[0].toFloat(), coordinates[1].toFloat(), coordinates[2].toFloat(), coordinates[3].toFloat())
                .takeIf { listOf(it.left, it.top, it.right, it.bottom).all(Float::isFinite) }
        } else null

        fun between(start: PixelPoint, end: PixelPoint, width: Float, height: Float) = PixelBox(
            min(start.x, end.x).coerceIn(0f, width), min(start.y, end.y).coerceIn(0f, height),
            max(start.x, end.x).coerceIn(0f, width), max(start.y, end.y).coerceIn(0f, height),
        )
    }
}

data class ImageTransform(val scale: Float, val offsetX: Float, val offsetY: Float) {
    fun toScreen(point: PixelPoint) = PixelPoint(point.x * scale + offsetX, point.y * scale + offsetY)
    fun toImage(point: PixelPoint) = PixelPoint((point.x - offsetX) / scale, (point.y - offsetY) / scale)

    companion object {
        fun fit(imageWidth: Float, imageHeight: Float, viewportWidth: Float, viewportHeight: Float,
                zoom: Float = 1f, pan: PixelPoint = PixelPoint(0f, 0f)): ImageTransform {
            require(imageWidth > 0f && imageHeight > 0f && viewportWidth > 0f && viewportHeight > 0f)
            val scale = min(viewportWidth / imageWidth, viewportHeight / imageHeight) * zoom.coerceIn(1f, 6f)
            val limitX = max(0f, (imageWidth * scale - viewportWidth) / 2f)
            val limitY = max(0f, (imageHeight * scale - viewportHeight) / 2f)
            return ImageTransform(
                scale,
                (viewportWidth - imageWidth * scale) / 2f + pan.x.coerceIn(-limitX, limitX),
                (viewportHeight - imageHeight * scale) / 2f + pan.y.coerceIn(-limitY, limitY),
            )
        }
    }
}
