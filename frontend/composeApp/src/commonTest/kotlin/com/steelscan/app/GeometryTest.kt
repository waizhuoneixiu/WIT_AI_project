package com.steelscan.app

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class GeometryTest {
    @Test fun multiBoxHitUsesTopmostOverlapAndEmptySpaceClearsSelection() {
        val boxes = listOf(PixelBox(10f, 10f, 50f, 50f), PixelBox(30f, 30f, 70f, 70f))
        assertEquals(0, hitBox(boxes, PixelPoint(15f, 20f)))
        assertEquals(1, hitBox(boxes, PixelPoint(35f, 35f)))
        assertEquals(-1, hitBox(boxes, PixelPoint(100f, 80f)))
    }

    @Test fun coordinatesRoundTripWithLetterboxingZoomAndPan() {
        for ((vw, vh) in listOf(400f to 300f, 300f to 400f)) {
            val transform = ImageTransform.fit(800f, 200f, vw, vh, 3f, PixelPoint(45f, -20f))
            val point = PixelPoint(135.5f, 82.25f)
            val restored = transform.toImage(transform.toScreen(point))
            assertEquals(point.x, restored.x, 0.001f)
            assertEquals(point.y, restored.y, 0.001f)
        }
    }

    @Test fun panCannotLoseImageAndFitCentersLetterbox() {
        val fit = ImageTransform.fit(200f, 100f, 400f, 400f)
        assertEquals(2f, fit.scale)
        assertEquals(100f, fit.offsetY)
        val extreme = ImageTransform.fit(200f, 100f, 400f, 400f, 3f, PixelPoint(10000f, -10000f))
        assertEquals(0f, extreme.offsetX)
        assertEquals(-200f, extreme.offsetY)
    }

    @Test fun movingPreservesBoxSizeAtBothEdges() {
        val original = PixelBox(10f, 20f, 40f, 60f)
        val right = original.moved(1000f, 1000f, 200f, 100f)
        assertEquals(PixelBox(170f, 60f, 200f, 100f), right)
        assertEquals(original.width, right.width)
        assertEquals(original.height, right.height)
        assertEquals(PixelBox(0f, 0f, 30f, 40f), original.moved(-1000f, -1000f, 200f, 100f))
    }

    @Test fun resizingCannotCrossOppositeCornerOrImageEdge() {
        val box = PixelBox(10f, 20f, 40f, 60f)
        assertEquals(PixelBox(39f, 59f, 40f, 60f), box.resized(0, PixelPoint(90f, 90f), 200f, 100f))
        assertEquals(PixelBox(10f, 20f, 200f, 100f), box.resized(2, PixelPoint(900f, 900f), 200f, 100f))
        assertTrue(box.resized(1, PixelPoint(-10f, -10f), 200f, 100f).valid(200f, 100f))
        assertTrue(box.resized(3, PixelPoint(-10f, -10f), 200f, 100f).valid(200f, 100f))
        assertTrue(PixelBox(0f, 0f, 0.25f, 0.5f).resized(0, PixelPoint(2f, 2f), 200f, 100f).valid(200f, 100f))
        assertEquals(2, PixelBox(0f, 0f, 4f, 4f).cornerNear(PixelPoint(4f, 4f), 20f))
    }

    @Test fun additionsNormalizeDirectionAndRejectEmptyOrInvalidGeometry() {
        assertEquals(PixelBox(0f, 5f, 100f, 70f), PixelBox.between(PixelPoint(150f, 70f), PixelPoint(-2f, 5f), 100f, 100f))
        assertFalse(PixelBox(2f, 2f, 2f, 10f).valid(200f, 100f))
        assertFalse(PixelBox(Float.NaN, 2f, 10f, 10f).valid(200f, 100f))
        assertEquals(null, PixelBox.from(listOf(1.0, 2.0)))
        assertEquals(null, PixelBox.from(listOf(1e300, 2.0, 3.0, 4.0)))
        val original = PixelBox(10.25f, 20.5f, 40.75f, 60.125f)
        assertEquals(original, PixelBox.from(original.coordinates()))
    }
}
