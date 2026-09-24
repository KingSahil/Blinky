package com.technerds.blinky.securesocket

import android.util.Base64
import android.content.Context
import android.net.Uri
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
import java.net.HttpURLConnection
import java.net.URL
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
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
  private val transferChunkSize = 16 * 1024 * 1024

  override fun definition() = ModuleDefinition {
    Name("BlinkySecureSocket")
    Events("onOpen", "onMessage", "onClose", "onError", "onTransferProgress")

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
    AsyncFunction("hashFile") { uri: String -> hashFile(uri) }
    AsyncFunction("uploadFile") { options: Map<String, Any?> -> uploadFile(options) }
    AsyncFunction("downloadFile") { options: Map<String, Any?> -> downloadFile(options) }
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

  private fun hashFile(uri: String): Map<String, Any> {
    val digest = MessageDigest.getInstance("SHA-256")
    var size = 0L
    context.contentResolver.openInputStream(Uri.parse(uri))?.use { input ->
      val buffer = ByteArray(1024 * 1024)
      while (true) {
        val count = input.read(buffer)
        if (count < 0) break
        digest.update(buffer, 0, count)
        size += count
      }
    } ?: throw IllegalArgumentException("Unable to open the selected file")
    return mapOf("size" to size, "sha256" to digest.digest().toHex())
  }

  private fun uploadFile(options: Map<String, Any?>): Map<String, Any> {
    val sourceUri = options.string("sourceUri")
    val transferId = options.string("transferId")
    val url = options.string("url")
    val token = options.string("token")
    val pin = options["pin"] as? String
    val totalSize = options.long("size")
    val chunkSize = options.long("chunkSize", transferChunkSize.toLong()).coerceIn(1, transferChunkSize.toLong()).toInt()
    var offset = options.long("offset")
    require(totalSize > 0 && offset in 0..totalSize) { "Invalid upload size or offset" }

    var input = openSourceAtOffset(sourceUri, offset)
    try {
      while (offset < totalSize) {
        val chunk = readStreamChunk(input, minOf(chunkSize.toLong(), totalSize - offset).toInt())
        if (chunk.isEmpty()) throw IllegalStateException("Selected file ended before its reported size")
        val connection = transferConnection(url, pin)
        try {
          connection.requestMethod = "POST"
          connection.doOutput = true
          connection.connectTimeout = 30_000
          connection.readTimeout = 300_000
          connection.setRequestProperty("Authorization", "Bearer $token")
          connection.setRequestProperty("Upload-Offset", offset.toString())
          connection.setRequestProperty("Content-Type", "application/octet-stream")
          connection.setFixedLengthStreamingMode(chunk.size)
          connection.outputStream.use { it.write(chunk) }
          val status = connection.responseCode
          val nextOffset = connection.getHeaderField("Upload-Offset")?.toLongOrNull()
          if (status == 409 && nextOffset != null && nextOffset in 0..totalSize) {
            offset = nextOffset
            input.close()
            input = openSourceAtOffset(sourceUri, offset)
            continue
          }
          if (status != 200 && status != 201) {
            val detail = runCatching { connection.errorStream?.bufferedReader()?.use { it.readText() } }.getOrNull()
            throw IllegalStateException("Upload failed ($status)${if (detail.isNullOrBlank()) "" else ": $detail"}")
          }
          val updated = nextOffset ?: (offset + chunk.size)
          require(updated > offset && updated <= totalSize) { "PC returned an invalid upload offset" }
          offset = updated
          sendEvent("onTransferProgress", mapOf("id" to transferId, "direction" to "upload", "bytes" to offset, "total" to totalSize))
        } finally {
          connection.disconnect()
        }
      }
    } finally {
      input.close()
    }
    return mapOf("transferId" to transferId, "uploadOffset" to offset, "complete" to true)
  }

  private fun openSourceAtOffset(uri: String, offset: Long): java.io.InputStream {
    val input = context.contentResolver.openInputStream(Uri.parse(uri))
      ?: throw IllegalArgumentException("Unable to open the selected file")
    try {
      var remaining = offset
      while (remaining > 0) {
        val skipped = input.skip(remaining)
        if (skipped <= 0) {
          if (input.read() < 0) throw IllegalStateException("Selected file ended before the resume offset")
          remaining -= 1
        } else remaining -= skipped
      }
      return input
    } catch (error: Throwable) {
      input.close()
      throw error
    }
  }

  private fun readStreamChunk(input: java.io.InputStream, maxBytes: Int): ByteArray {
    val buffer = ByteArray(maxBytes)
    var count = 0
    while (count < maxBytes) {
      val read = input.read(buffer, count, maxBytes - count)
      if (read < 0) break
      count += read
    }
    return if (count == buffer.size) buffer else buffer.copyOf(count)
  }

  private fun downloadFile(options: Map<String, Any?>): String {
    val transferId = options.string("transferId")
    val url = options.string("url")
    val token = options.string("token")
    val pin = options["pin"] as? String
    val expectedSize = options.long("size")
    val expectedSha256 = options.string("sha256").lowercase()
    val filename = safeName(options.string("filename"))
    require(expectedSize > 0) { "Invalid download size" }

    val directory = File(context.filesDir, "BlinkyTransfers").apply { mkdirs() }
    val partial = File(directory, "$transferId.part")
    var offset = partial.length()
    if (offset > expectedSize) {
      partial.delete()
      offset = 0
    }
    while (offset < expectedSize) {
      val end = minOf(expectedSize - 1, offset + transferChunkSize - 1)
      val connection = transferConnection(url, pin)
      try {
        connection.requestMethod = "GET"
        connection.connectTimeout = 30_000
        connection.readTimeout = 300_000
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.setRequestProperty("Range", "bytes=$offset-$end")
        val status = connection.responseCode
        if (status != 206) throw IllegalStateException("Download failed ($status)")
        require(connection.getHeaderField("X-File-Size")?.toLongOrNull() == expectedSize) { "PC returned a different file size" }
        require(connection.getHeaderField("X-File-Sha256")?.equals(expectedSha256, ignoreCase = true) == true) { "PC returned a different file digest" }
        val expectedChunk = end - offset + 1
        var received = 0L
        FileOutputStream(partial, true).use { output ->
          connection.inputStream.use { input ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
              val count = input.read(buffer)
              if (count < 0) break
              output.write(buffer, 0, count)
              received += count
            }
          }
          output.fd.sync()
        }
        require(received == expectedChunk) { "Download chunk was incomplete" }
        offset += received
        sendEvent("onTransferProgress", mapOf("id" to transferId, "direction" to "download", "bytes" to offset, "total" to expectedSize))
      } finally {
        connection.disconnect()
      }
    }

    val actualHash = hashFile(Uri.fromFile(partial).toString())["sha256"] as String
    require(actualHash.equals(expectedSha256, ignoreCase = true)) { "Downloaded file SHA-256 did not match the PC" }
    val destination = uniqueTransferFile(directory, filename)
    if (!partial.renameTo(destination)) throw IllegalStateException("Could not save the downloaded file")
    return Uri.fromFile(destination).toString()
  }

  private fun transferConnection(url: String, pin: String?): HttpURLConnection {
    val parsed = URI(url)
    require(parsed.scheme.equals("http", true) || parsed.scheme.equals("https", true)) { "Transfer URL must use HTTP or HTTPS" }
    val connection = URL(url).openConnection() as HttpURLConnection
    if (connection is javax.net.ssl.HttpsURLConnection) {
      require(!pin.isNullOrBlank()) { "HTTPS transfers require the saved certificate pin" }
      val trustManager = PinnedCertificateTrustManager(pin)
      val sslContext = SSLContext.getInstance("TLS").apply { init(null, arrayOf<TrustManager>(trustManager), SecureRandom()) }
      connection.sslSocketFactory = sslContext.socketFactory
      connection.hostnameVerifier = javax.net.ssl.HostnameVerifier { _, _ -> true }
    } else {
      require(pin.isNullOrBlank()) { "Pinned release transfers must use HTTPS" }
    }
    return connection
  }

  private fun safeName(value: String): String {
    val cleaned = value.replace(Regex("[\\\\/:*?\"<>|\\p{Cntrl}]"), "_").trim().trim('.')
    return cleaned.takeIf { it.isNotEmpty() && it != ".." } ?: "blinky-download.bin"
  }

  private fun uniqueTransferFile(directory: File, filename: String): File {
    val original = File(directory, filename)
    if (!original.exists()) return original
    val stem = original.nameWithoutExtension
    val extension = original.extension
    for (index in 1..99999) {
      val suffix = if (extension.isEmpty()) " ($index)" else " ($index).$extension"
      val candidate = File(directory, "$stem$suffix")
      if (!candidate.exists()) return candidate
    }
    throw IllegalStateException("Could not find a free file name")
  }

  private fun Map<String, Any?>.string(key: String): String = this[key] as? String
    ?: throw IllegalArgumentException("Missing $key")

  private fun Map<String, Any?>.long(key: String, default: Long = 0): Long = when (val value = this[key]) {
    is Number -> value.toLong()
    null -> default
    else -> throw IllegalArgumentException("Invalid $key")
  }

  private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

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
