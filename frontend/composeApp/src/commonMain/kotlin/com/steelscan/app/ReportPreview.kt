package com.steelscan.app

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

sealed interface ReportBlock {
    data class Line(val text: String, val heading: Int = 0) : ReportBlock
    data class Table(val rows: List<List<String>>) : ReportBlock
}

// shortcut: parses only the backend report format; use a Markdown library if rich documents are introduced.
fun reportBlocks(markdown: String): List<ReportBlock> {
    fun cells(line: String): List<String>? = line.trim().takeIf { it.startsWith('|') && it.endsWith('|') }
        ?.removePrefix("|")?.removeSuffix("|")?.split('|')?.map(String::trim)
    val lines = markdown.lines()
    val separator = Regex(":?-{3,}:?")
    val heading = Regex("^(#{1,3}) (.+)$")
    return buildList {
        var index = 0
        while (index < lines.size) {
            val header = cells(lines[index])
            val rule = lines.getOrNull(index + 1)?.let(::cells)
            if (header != null && rule != null && rule.size == header.size && rule.all(separator::matches)) {
                val rows = mutableListOf(header)
                index += 2
                while (index < lines.size) {
                    val row = cells(lines[index])?.takeIf { it.size == header.size } ?: break
                    rows.add(row)
                    index++
                }
                add(ReportBlock.Table(rows))
            } else {
                val line = lines[index++].trim()
                val title = heading.matchEntire(line)
                add(if (title != null) ReportBlock.Line(title.groupValues[2], title.groupValues[1].length)
                    else ReportBlock.Line(if (line.startsWith("- ")) "• " + line.removePrefix("- ") else line))
            }
        }
    }
}

@Composable
fun MarkdownPreview(markdown: String) {
    val blocks = remember(markdown) { reportBlocks(markdown) }
    SelectionContainer {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            blocks.forEach { block ->
                when (block) {
                    is ReportBlock.Line -> if (block.text.isBlank()) Spacer(Modifier.height(3.dp)) else {
                        val style = when (block.heading) {
                            1 -> MaterialTheme.typography.titleLarge
                            2 -> MaterialTheme.typography.titleMedium
                            3 -> MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold)
                            else -> MaterialTheme.typography.bodyMedium
                        }
                        Text(block.text, style = style,
                            modifier = if (block.heading > 0) Modifier.semantics { heading() } else Modifier)
                    }
                    is ReportBlock.Table -> {
                        Text("横向滑动查看完整表格", color = Graphite, style = MaterialTheme.typography.bodySmall)
                        val tableWidth = block.rows[0].sumOf { if (it == "bbox") 250 else 140 }
                        Surface(shape = RoundedCornerShape(10.dp), border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
                            Column(Modifier.horizontalScroll(rememberScrollState()).width(tableWidth.dp)) {
                                block.rows.forEachIndexed { rowIndex, cells ->
                                    if (rowIndex > 0) HorizontalDivider()
                                    Row(Modifier.background(if (rowIndex == 0) SkyTint else Color.White)) {
                                        cells.forEachIndexed { column, value ->
                                            Text(value,
                                                modifier = Modifier.width(if (block.rows[0][column] == "bbox") 250.dp else 140.dp).padding(12.dp),
                                                style = MaterialTheme.typography.bodyMedium,
                                                fontWeight = if (rowIndex == 0) FontWeight.SemiBold else FontWeight.Normal)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
