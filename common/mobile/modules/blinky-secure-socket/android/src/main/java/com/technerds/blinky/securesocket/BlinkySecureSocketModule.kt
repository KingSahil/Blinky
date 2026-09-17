package com.technerds.blinky.securesocket

import android.util.Base64
import android.content.Context
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.net.URI
import java.security.SecureRandom
import java.util.concurrent.ConcurrentHashMap
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager

class BlinkySecureSocketModule : Module() {
  private val context: Context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()
  private val sockets = ConcurrentHashMap<String, WebSocket>()
  private val clients = ConcurrentHashMap<String, OkHttpClient>()
  private val secureKeyAlias = "blinky_remote_credentials"

  override fun definition() = ModuleDefinition {
    Name("BlinkySecureSocket")
    Events("onOpen", "onMessage", "onClose", "onError")

    AsyncFunction("connect") { id: String, url: String, pin: String ->
      connect(id, url, pin)
    }
    AsyncFunction("sendText") { id: String, data: String ->
      check(sockets[id]?.send(data) == true) { "Secure socket could not send the message: $id" }
    }
    AsyncFunction("sendBinary") { id: String, base64Data: String ->
      val bytes = Base64.decode(base64Data, Base64.DEFAULT)
      check(sockets[id]?.send(ByteString.of(*bytes)) == true) {
        "Secure socket could not send the binary message: $id"
      }
    }
    AsyncFunction("close") { id: String ->
      closeSocket(id)
    }
    AsyncFunction("getSecureValue") { key: String ->
      getSecureValue(key)
    }
    AsyncFunction("setSecureValue") { key: String, value: String ->
      setSecureValue(key, value)
    }
    AsyncFunction("deleteSecureValue") { key: String ->
      context.getSharedPreferences("blinky_secure", Context.MODE_PRIVATE)
        .edit().remove(key).apply()
    }
    OnDestroy {
      sockets.keys.toList().forEach { closeSocket(it) }
    }
  }

  @Synchronized
  private fun connect(id: String, url: String, pin: String) {
    val uri = URI(url)
    require(uri.scheme.equals("wss", ignoreCase = true)) { "Secure socket requires a wss:// URL" }
    require(uri.host != null) { "Secure socket URL must include a hostname" }
    require(pin.startsWith("sha256/")) { "Secure socket requires a sha256/ certificate pin" }

    closeSocket(id)
    val trustManager = PinnedCertificateTrustManager(pin)
    val sslContext = SSLContext.getInstance("TLS").apply {
      init(null, arrayOf<TrustManager>(trustManager), SecureRandom())
    }
    val client = OkHttpClient.Builder()
      // The desktop certificate uses stable localhost SANs while its LAN IP can
      // change. The pinned public key is therefore the server identity check.
      .sslSocketFactory(sslContext.socketFactory, trustManager)
      .hostnameVerifier { _, _ -> true }
      .build()
    val request = Request.Builder().url(url).build()
    clients[id] = client
    val webSocket = client.newWebSocket(request, object : WebSocketListener() {
      override fun onOpen(webSocket: WebSocket, response: Response) {
        synchronized(this@BlinkySecureSocketModule) {
          if (sockets[id] !== webSocket) {
            webSocket.cancel()
            return
          }
          sendEvent("onOpen", mapOf("id" to id))
        }
      }

      override fun onMessage(webSocket: WebSocket, text: String) {
        sendEvent("onMessage", mapOf("id" to id, "data" to text))
      }

      override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
        sendEvent(
          "onMessage",
          mapOf("id" to id, "data" to Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP))
        )
      }

      override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
        webSocket.close(code, reason)
      }

      override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
        if (removeSocketIfCurrent(id, webSocket)) {
          sendEvent("onClose", mapOf("id" to id))
        }
      }

      override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
        if (removeSocketIfCurrent(id, webSocket)) {
          sendEvent("onError", mapOf("id" to id, "error" to (t.message ?: "Secure socket failed")))
        }
      }
    })
    sockets[id] = webSocket
  }

  @Synchronized
  private fun removeSocketIfCurrent(id: String, webSocket: WebSocket): Boolean {
    if (sockets[id] === webSocket) {
      sockets.remove(id)
      clients.remove(id)?.dispatcher?.executorService?.shutdown()
      return true
    }
    return false
  }

  @Synchronized
  private fun closeSocket(id: String) {
    sockets.remove(id)?.cancel()
    clients.remove(id)?.dispatcher?.executorService?.shutdown()
  }

  private fun getSecureValue(key: String): String? {
    val encoded = context.getSharedPreferences("blinky_secure", Context.MODE_PRIVATE)
      .getString(key, null) ?: return null
    return try {
      val packed = Base64.decode(encoded, Base64.NO_WRAP)
      val iv = packed.copyOfRange(0, 12)
      val ciphertext = packed.copyOfRange(12, packed.size)
      val cipher = Cipher.getInstance("AES/GCM/NoPadding")
      cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, iv))
      String(cipher.doFinal(ciphertext), Charsets.UTF_8)
    } catch (_: Exception) {
      null
    }
  }

  private fun setSecureValue(key: String, value: String) {
    val cipher = Cipher.getInstance("AES/GCM/NoPadding")
    cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
    val packed = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
    context.getSharedPreferences("blinky_secure", Context.MODE_PRIVATE)
      .edit().putString(key, Base64.encodeToString(packed, Base64.NO_WRAP)).apply()
  }

  private fun getOrCreateKey(): SecretKey {
    val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    if (keyStore.containsAlias(secureKeyAlias)) {
      return keyStore.getKey(secureKeyAlias, null) as SecretKey
    }
    val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
    generator.init(
      KeyGenParameterSpec.Builder(
        secureKeyAlias,
        KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
      )
        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
        .build()
    )
    return generator.generateKey()
  }
}
