package com.technerds.blinky.securesocket

import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.X509TrustManager
import okio.ByteString.Companion.decodeBase64

internal class PinnedCertificateTrustManager(pin: String) : X509TrustManager {
  private val expectedPublicKeyHash = parseSha256Pin(pin)

  override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {
    throw CertificateException("Client certificates are not supported")
  }

  override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
    val leaf = chain.firstOrNull()
      ?: throw CertificateException("Server did not provide a certificate")

    leaf.checkValidity()
    val actualPublicKeyHash = MessageDigest.getInstance("SHA-256")
      .digest(leaf.publicKey.encoded)

    if (!MessageDigest.isEqual(expectedPublicKeyHash, actualPublicKeyHash)) {
      throw CertificateException("Server certificate public key does not match the configured pin")
    }
  }

  override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()

  private companion object {
    private const val SHA256_PREFIX = "sha256/"
    private const val SHA256_BYTE_COUNT = 32

    fun parseSha256Pin(pin: String): ByteArray {
      require(pin.startsWith(SHA256_PREFIX)) {
        "Certificate pin must start with $SHA256_PREFIX"
      }
      val decoded = pin.removePrefix(SHA256_PREFIX).decodeBase64()
        ?: throw IllegalArgumentException("Certificate pin must contain valid base64")
      require(decoded.size == SHA256_BYTE_COUNT) {
        "Certificate pin must contain a 32-byte SHA-256 digest"
      }
      return decoded.toByteArray()
    }
  }
}
