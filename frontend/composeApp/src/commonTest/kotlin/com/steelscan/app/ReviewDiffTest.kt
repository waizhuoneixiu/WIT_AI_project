package com.steelscan.app

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ReviewDiffTest {
    private val original = Detection("DET-1", 2, "patches", .88, listOf(10.0, 20.0, 50.0, 80.0))

    @Test
    fun unchangedResultDoesNotInventCorrections() {
        assertTrue(reviewDiff(listOf(original), listOf(original)).isEmpty())
    }

    @Test
    fun updatedBoxKeepsItsOriginalIdentityAndCoordinates() {
        val edited = original.copy(classId = 5, bbox = listOf(12.0, 20.0, 60.0, 70.0), source = "manual", score = null)
        assertEquals(listOf(Correction("update", "DET-1", 5, edited.bbox)), reviewDiff(listOf(original), listOf(edited)))
        assertEquals(.88, original.score)
    }

    @Test
    fun deletingOriginalAndAddingManualBoxProducesCompleteDifference() {
        val manual = Detection("98959c9e-5c32-40c7-a5bc-46423cbfe25e", 1, "inclusion", null, listOf(1.0, 2.0, 9.0, 10.0), "manual")
        assertEquals(listOf(Correction("delete", "DET-1"), Correction("add", manual.detectionId, 1, manual.bbox)),
            reviewDiff(listOf(original), listOf(manual)))
        assertEquals(listOf(Correction("delete", "DET-1")), reviewDiff(listOf(original), emptyList()))
    }

    @Test
    fun editingPreviouslyAddedBoxStillUsesAddAndRevertingOriginalDropsUpdate() {
        val manual = Detection("98959c9e-5c32-40c7-a5bc-46423cbfe25e", 1, "inclusion", null, listOf(1.0, 2.0, 9.0, 10.0), "manual")
        val changed = manual.copy(classId = 4)
        assertEquals(listOf(Correction("add", manual.detectionId, 4, manual.bbox)),
            reviewDiff(listOf(original), listOf(original, changed)))
    }
}
