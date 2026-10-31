package com.steelscan.app

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class ReportPreviewTest {
    @Test
    fun rendersThreeHeadingLevelsAndKeepsParagraphsAndListContent() {
        assertEquals(listOf(
            ReportBlock.Line("质检报告", 1), ReportBlock.Line("辅助分析", 2), ReportBlock.Line("依据", 3),
            ReportBlock.Line("• 待补充工艺信息"), ReportBlock.Line("空检出不等于合格"),
        ), reportBlocks("# 质检报告\n## 辅助分析\n### 依据\n- 待补充工艺信息\n空检出不等于合格"))
    }

    @Test
    fun groupsBackendTableWithoutDisplayingPipesOrSeparator() {
        val blocks = reportBlocks("| 类别 | 来源 | bbox |\n| --- | --- | --- |\n| 划痕 | 人工新增或修改 | [1, 2, 30, 40] |\n\n### 复检步骤")
        val table = assertIs<ReportBlock.Table>(blocks.first())
        assertEquals(listOf(listOf("类别", "来源", "bbox"), listOf("划痕", "人工新增或修改", "[1, 2, 30, 40]")), table.rows)
        assertEquals(ReportBlock.Line("复检步骤", 3), blocks.last())
    }

    @Test
    fun supportsEmptyResultTableAndDoesNotDropMalformedPipeText() {
        val blocks = reportBlocks("| 类别 | 来源 |\n| :--- | ---: |\n当前无框\n| 备注中的普通文本 |")
        assertEquals(1, assertIs<ReportBlock.Table>(blocks.first()).rows.size)
        assertEquals(ReportBlock.Line("当前无框"), blocks[1])
        assertEquals(ReportBlock.Line("| 备注中的普通文本 |"), blocks[2])
    }
}
