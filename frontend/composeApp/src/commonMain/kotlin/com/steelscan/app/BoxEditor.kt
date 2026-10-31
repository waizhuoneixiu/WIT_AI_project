@file:OptIn(kotlin.uuid.ExperimentalUuidApi::class)

package com.steelscan.app

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.roundToInt
import kotlin.uuid.Uuid

private enum class EditorTool { Select, Draw, Pan }

@Composable
fun BoxEditor(
    bitmap: ImageBitmap?,
    imageWidth: Int,
    imageHeight: Int,
    boxes: List<Detection>,
    selectedId: String?,
    editable: Boolean,
    onSelect: (String?) -> Unit,
    onBoxesChange: (List<Detection>) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (imageWidth <= 0 || imageHeight <= 0) return
    val iw = imageWidth.toFloat()
    val ih = imageHeight.toFloat()
    var zoom by remember(bitmap) { mutableStateOf(1f) }
    var pan by remember(bitmap) { mutableStateOf(PixelPoint(0f, 0f)) }
    var viewport by remember { mutableStateOf(IntSize(1, 1)) }
    var tool by remember(editable) { mutableStateOf(EditorTool.Select) }
    var preview by remember { mutableStateOf<PixelBox?>(null) }
    val currentBoxes by rememberUpdatedState(boxes)
    val currentSelected by rememberUpdatedState(selectedId)
    val select by rememberUpdatedState(onSelect)
    val changeBoxes by rememberUpdatedState(onBoxesChange)
    val transform = ImageTransform.fit(iw, ih, viewport.width.toFloat(), viewport.height.toFloat(), zoom, pan)
    val currentTransform by rememberUpdatedState(transform)
    val touchRadius = with(LocalDensity.current) { 20.dp.toPx() }
    val textMeasurer = rememberTextMeasurer()
    val blue = SignalBlue
    val ink = Ink

    fun addBox(box: PixelBox) {
        if (!box.valid(iw, ih)) return
        val id = Uuid.random().toString()
        changeBoxes(currentBoxes + Detection(id, 0, "crazing", null, box.coordinates(), "manual"))
        select(id)
        tool = EditorTool.Select
    }

    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("${imageWidth} × $imageHeight px", style = MaterialTheme.typography.labelMedium)
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = { zoom = (zoom / 1.5f).coerceAtLeast(1f); pan = PixelPoint(0f, 0f) }, enabled = zoom > 1f) { Text("缩小") }
                TextButton(onClick = { zoom = (zoom * 1.5f).coerceAtMost(6f); pan = PixelPoint(0f, 0f) }, enabled = zoom < 6f) { Text("放大") }
                TextButton(onClick = { zoom = 1f; pan = PixelPoint(0f, 0f) }) { Text("复位") }
            }
        }
        if (editable) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(EditorTool.Select to "选框", EditorTool.Draw to "画新框", EditorTool.Pan to "平移").forEach { (value, label) ->
                    FilterChip(selected = tool == value, onClick = { tool = value }, label = { Text(label) })
                }
            }
        }

        var gestures = Modifier.pointerInput(bitmap, editable, tool) {
            detectTapGestures { offset ->
                if (tool == EditorTool.Select) {
                    val point = currentTransform.toImage(PixelPoint(offset.x, offset.y))
                    val validBoxes = currentBoxes.mapNotNull { item -> PixelBox.from(item.bbox)?.let { item to it } }
                    select(validBoxes.getOrNull(hitBox(validBoxes.map { it.second }, point))?.first?.detectionId)
                }
            }
        }
        if (editable || zoom > 1f) {
            gestures = gestures.pointerInput(bitmap, editable, tool, viewport) {
                var start = PixelPoint(0f, 0f)
                var initialPan = PixelPoint(0f, 0f)
                var origin = currentTransform
                var dragged: Detection? = null
                var corner = -1
                var total = PixelPoint(0f, 0f)
                detectDragGestures(
                    onDragStart = { offset ->
                        origin = currentTransform
                        start = origin.toImage(PixelPoint(offset.x, offset.y))
                        initialPan = pan
                        total = PixelPoint(0f, 0f)
                        dragged = null
                        corner = -1
                        if (editable && tool == EditorTool.Select) {
                            val selected = currentBoxes.find { it.detectionId == currentSelected }
                            corner = selected?.let { PixelBox.from(it.bbox)?.cornerNear(start, touchRadius / origin.scale) } ?: -1
                            dragged = if (corner >= 0) selected else currentBoxes.lastOrNull { PixelBox.from(it.bbox)?.contains(start) == true }
                            select(dragged?.detectionId)
                        }
                        if (editable && tool == EditorTool.Draw && start.x in 0f..iw && start.y in 0f..ih) {
                            preview = PixelBox.between(start, start, iw, ih)
                        }
                    },
                    onDrag = { pointer, amount ->
                        pointer.consume()
                        total = PixelPoint(total.x + amount.x, total.y + amount.y)
                        if (!editable || tool == EditorTool.Pan) {
                            val rawPan = PixelPoint(initialPan.x + total.x, initialPan.y + total.y)
                            val bounded = ImageTransform.fit(iw, ih, viewport.width.toFloat(), viewport.height.toFloat(), zoom, rawPan)
                            pan = PixelPoint(bounded.offsetX - (viewport.width - iw * bounded.scale) / 2f,
                                bounded.offsetY - (viewport.height - ih * bounded.scale) / 2f)
                        } else {
                            val position = origin.toImage(PixelPoint(pointer.position.x, pointer.position.y))
                            when (tool) {
                                EditorTool.Draw -> if (preview != null) preview = PixelBox.between(start, position, iw, ih)
                                EditorTool.Select -> dragged?.let { original ->
                                    PixelBox.from(original.bbox)?.let { box ->
                                        val next = if (corner >= 0) box.resized(corner, position, iw, ih)
                                        else box.moved(total.x / origin.scale, total.y / origin.scale, iw, ih)
                                        changeBoxes(currentBoxes.map {
                                            if (it.detectionId == original.detectionId) it.copy(bbox = next.coordinates(), score = null, source = "manual") else it
                                        })
                                    }
                                }
                                EditorTool.Pan -> Unit
                            }
                        }
                    },
                    onDragEnd = {
                        preview?.takeIf { it.width >= 1f && it.height >= 1f }?.let { addBox(it) }
                        preview = null
                    },
                    onDragCancel = {
                        dragged?.let { original -> changeBoxes(currentBoxes.map { if (it.detectionId == original.detectionId) original else it }) }
                        preview = null
                    },
                )
            }
        }

        Box(
            Modifier.fillMaxWidth().height(320.dp).clip(RoundedCornerShape(16.dp))
                .background(SkyTint).onSizeChanged { viewport = it },
            contentAlignment = Alignment.Center,
        ) {
            if (bitmap == null) CircularProgressIndicator(color = ink)
            Canvas(Modifier.matchParentSize().then(gestures).semantics {
                contentDescription = "缺陷图像，${boxes.size} 个框。${if (editable) "可使用下方坐标输入精确编辑。" else "点击缺陷列表选择对应框。"}"
            }) {
                if (bitmap != null) {
                    drawImage(bitmap,
                        dstOffset = IntOffset(transform.offsetX.roundToInt(), transform.offsetY.roundToInt()),
                        dstSize = IntSize((iw * transform.scale).roundToInt().coerceAtLeast(1), (ih * transform.scale).roundToInt().coerceAtLeast(1)))
                }
                boxes.forEachIndexed { index, detection ->
                    val box = PixelBox.from(detection.bbox) ?: return@forEachIndexed
                    val point = transform.toScreen(PixelPoint(box.left, box.top))
                    val selected = detection.detectionId == selectedId
                    val color = if (selected) blue else ink
                    drawRect(Color.White.copy(alpha = 0.8f), Offset(point.x, point.y), Size(box.width * transform.scale, box.height * transform.scale), style = Stroke(5.dp.toPx()))
                    drawRect(color, Offset(point.x, point.y), Size(box.width * transform.scale, box.height * transform.scale), style = Stroke(if (selected) 3.dp.toPx() else 1.5.dp.toPx()))
                    val label = textMeasurer.measure("${index + 1}", TextStyle(color = Color.White, fontSize = 12.sp))
                    val labelY = (point.y - label.size.height - 4.dp.toPx()).coerceAtLeast(0f)
                    drawRect(color, Offset(point.x, labelY), Size(label.size.width + 8.dp.toPx(), label.size.height + 4.dp.toPx()))
                    drawText(label, topLeft = Offset(point.x + 4.dp.toPx(), labelY + 2.dp.toPx()))
                    if (selected && editable) box.corners().forEach {
                        val screen = transform.toScreen(it)
                        drawCircle(Color.White, 6.dp.toPx(), Offset(screen.x, screen.y))
                        drawCircle(blue, 6.dp.toPx(), Offset(screen.x, screen.y), style = Stroke(2.dp.toPx()))
                    }
                }
                preview?.let {
                    val p = transform.toScreen(PixelPoint(it.left, it.top))
                    drawRect(blue, Offset(p.x, p.y), Size(it.width * transform.scale, it.height * transform.scale), style = Stroke(2.dp.toPx()))
                }
            }
        }
        Text(
            if (editable) when (tool) {
                EditorTool.Select -> "拖动框移动位置，拖动四角调整大小；下方也可输入精确坐标。"
                EditorTool.Draw -> "在图像上拖出一个新框，再在缺陷列表中选择类别。"
                EditorTool.Pan -> "放大后拖动图像查看细节。"
            } else "点击缺陷列表或框查看对应区域；放大后可拖动图像。",
            style = MaterialTheme.typography.bodySmall,
            color = Graphite,
        )
        if (editable) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { addBox(PixelBox(iw * 0.35f, ih * 0.35f, iw * 0.65f, ih * 0.65f)) }) { Text("添加中央框") }
                OutlinedButton(onClick = {
                    changeBoxes(currentBoxes.filterNot { it.detectionId == selectedId })
                    select(null)
                }, enabled = selectedId != null, colors = ButtonDefaults.outlinedButtonColors(contentColor = ink)) { Text("删除选中框") }
            }
            boxes.find { it.detectionId == selectedId }?.let { selected ->
                CoordinateInputs(selected, iw, ih) { updated ->
                    changeBoxes(currentBoxes.map { if (it.detectionId == updated.detectionId) updated else it })
                }
            }
        }
    }
}

@Composable
private fun CoordinateInputs(detection: Detection, imageWidth: Float, imageHeight: Float, onChange: (Detection) -> Unit) {
    var values by remember(detection.detectionId, detection.bbox) { mutableStateOf(detection.bbox.map { it.toString() }) }
    var error by remember(detection.detectionId) { mutableStateOf<String?>(null) }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(Color.White).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("选中框的原图坐标", style = MaterialTheme.typography.labelLarge)
        for (row in 0..1) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (column in 0..1) {
                    val index = row * 2 + column
                    OutlinedTextField(values.getOrElse(index) { "" }, onValueChange = { value ->
                        values = values.mapIndexed { i, old -> if (i == index) value else old }
                        error = null
                    }, label = { Text(listOf("左 x1", "上 y1", "右 x2", "下 y2")[index]) },
                        singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f))
                }
            }
        }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        TextButton(onClick = {
            val parsed = values.map { it.toDoubleOrNull() }
            val box = if (parsed.all { it != null }) PixelBox.from(parsed.filterNotNull()) else null
            if (box == null || !box.valid(imageWidth, imageHeight)) {
                error = "坐标须在图像内，且左小于右、上小于下。"
            } else {
                error = null
                onChange(detection.copy(bbox = box.coordinates(), score = null, source = "manual"))
            }
        }) { Text("应用坐标") }
    }
}
