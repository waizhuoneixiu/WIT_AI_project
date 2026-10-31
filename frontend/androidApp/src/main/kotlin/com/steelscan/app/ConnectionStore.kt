package com.steelscan.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.widget.Toast
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal class ConnectionStore(private val context: Context) {
    private val preferences = context.getSharedPreferences("connection", Context.MODE_PRIVATE)

    fun load(): ConnectionSettings {
        val encrypted = preferences.getString("api_key", null)
        val key = if (encrypted.isNullOrEmpty()) "" else runCatching {
            val data = Base64.decode(encrypted, Base64.NO_WRAP)
            require(data.size > 12)
            Cipher.getInstance("AES/GCM/NoPadding").run {
                init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, data.copyOfRange(0, 12)))
                String(doFinal(data.copyOfRange(12, data.size)), Charsets.UTF_8)
            }
        }.getOrElse {
            Toast.makeText(context, "已保存的 API Key 无法读取，请在连接设置中重新填写。", Toast.LENGTH_LONG).show()
            ""
        }
        return ConnectionSettings(preferences.getString("base_url", null) ?: "http://10.0.2.2:8000", key)
    }

    fun save(settings: ConnectionSettings) {
        val encrypted = if (settings.apiKey.isEmpty()) "" else Cipher.getInstance("AES/GCM/NoPadding").run {
            init(Cipher.ENCRYPT_MODE, secretKey())
            Base64.encodeToString(iv + doFinal(settings.apiKey.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)
        }
        check(preferences.edit().putString("base_url", settings.baseUrl).putString("api_key", encrypted).commit()) {
            "连接设置未能保存，请重试。"
        }
    }

    private fun secretKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("steelscan.connection", null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder("steelscan.connection", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build())
            generateKey()
        }
    }
}
