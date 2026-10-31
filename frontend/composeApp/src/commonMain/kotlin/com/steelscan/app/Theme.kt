package com.steelscan.app

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

val Ink = Color(0xFF262626)
val Graphite = Color(0xFF656568)
val CanvasColor = Color(0xFFFAFAFA)
val SignalBlue = Color(0xFF008AE8)
val SkyTint = Color(0xFFE0F2FE)
val Blush = Color(0xFFFBCFE8)
val Lavender = Color(0xFFE6DAFD)
val Mint = Color(0xFFB6EDEE)
val PowderBlue = Color(0xFFAFE4FF)
val Butter = Color(0xFFFFE77A)

val classNames = listOf("龟裂 / 网状裂纹", "夹杂", "斑块", "麻点表面", "轧入氧化皮", "划痕")
val classLabels = listOf("crazing", "inclusion", "patches", "pitted_surface", "rolled-in_scale", "scratches")
fun className(id: Int) = classNames.getOrElse(id) { "未知类别" }
fun reviewLabel(status: String) = when (status) {
    "confirmed" -> "已确认"
    "corrected" -> "已修正"
    "unresolved" -> "无法判断"
    else -> "待复核"
}

@Composable
fun SteelTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Ink, onPrimary = Color.White, primaryContainer = SkyTint,
            onPrimaryContainer = Ink, secondary = Color(0xFF006BAF),
            background = CanvasColor, onBackground = Ink, surface = Color.White,
            onSurface = Ink, surfaceVariant = Color(0xFFF0F0F2), onSurfaceVariant = Graphite,
            outline = Color(0xFF88888B), outlineVariant = Color(0xFFE0E0E3),
        ),
        typography = Typography(
            headlineLarge = TextStyle(fontSize = 36.sp, lineHeight = 40.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.4).sp),
            headlineMedium = TextStyle(fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.25).sp),
            titleLarge = TextStyle(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.14).sp),
            titleMedium = TextStyle(fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.Medium),
            bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 25.sp),
            bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 22.sp),
            labelLarge = TextStyle(fontSize = 15.sp, lineHeight = 22.sp, fontWeight = FontWeight.Medium),
        ),
        content = content,
    )
}

@Composable
fun PaperCard(color: Color = Color.White, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(modifier.fillMaxWidth(), color = color, shape = RoundedCornerShape(24.dp)) {
        Column(Modifier.padding(24.dp), content = content)
    }
}

@Composable
fun PrimaryAction(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    Button(onClick, modifier = modifier, enabled = enabled, shape = RoundedCornerShape(99.dp),
        contentPadding = PaddingValues(horizontal = 24.dp, vertical = 14.dp),
        colors = ButtonDefaults.buttonColors(containerColor = Ink)) { Text(text) }
}
