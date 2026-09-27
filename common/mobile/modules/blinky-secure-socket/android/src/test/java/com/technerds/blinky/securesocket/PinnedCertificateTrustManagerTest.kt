package com.technerds.blinky.securesocket

import java.io.ByteArrayInputStream
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import org.junit.Assert.assertThrows
import org.junit.Test

class PinnedCertificateTrustManagerTest {
  private val certificate = CertificateFactory.getInstance("X.509")
    .generateCertificate(ByteArrayInputStream(TEST_CERTIFICATE.toByteArray())) as X509Certificate

  @Test
  fun acceptsCertificateWhosePublicKeyMatchesThePin() {
    PinnedCertificateTrustManager(CORRECT_PIN)
      .checkServerTrusted(arrayOf(certificate), "ECDHE_ECDSA")
  }

  @Test
  fun rejectsCertificateWhosePublicKeyDoesNotMatchThePin() {
    assertThrows(CertificateException::class.java) {
      PinnedCertificateTrustManager(WRONG_PIN)
        .checkServerTrusted(arrayOf(certificate), "ECDHE_ECDSA")
    }
  }

  @Test
  fun rejectsAnEmptyPeerCertificateChain() {
    assertThrows(CertificateException::class.java) {
      PinnedCertificateTrustManager(CORRECT_PIN)
        .checkServerTrusted(emptyArray(), "ECDHE_ECDSA")
    }
  }

  @Test
  fun rejectsMalformedSha256PinsBeforeConnecting() {
    assertThrows(IllegalArgumentException::class.java) {
      PinnedCertificateTrustManager("sha256/not-a-32-byte-digest")
    }
  }

  private companion object {
    const val CORRECT_PIN = "sha256/dXKyQvpI2cJVjwL1jQkUk7ZH4Oo7LC8ygHLeyBkb0RE="
    const val WRONG_PIN = "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    val TEST_CERTIFICATE = """
      -----BEGIN CERTIFICATE-----
      MIIBYzCCAQqgAwIBAgIUc0q0f+RUkkFLuTVUBj+GAOt6O3MwCgYIKoZIzj0EAwIw
      ITEfMB0GA1UEAwwWcmNnZW4gc2VsZiBzaWduZWQgY2VydDAgFw03NTAxMDEwMDAw
      MDBaGA80MDk2MDEwMTAwMDAwMFowITEfMB0GA1UEAwwWcmNnZW4gc2VsZiBzaWdu
      ZWQgY2VydDBZMBMGByqGSM49AgEGCCqGSM49AwEHA0IABO5Ii4hvQkVqirbFJ/iL
      a0VkvYL68xUP7YZRfOsE2/eQgjfbVbnYwAV1KBW3kUaw4LjQkFTy+IMuLBEIMHRV
      v+qjHjAcMBoGA1UdEQQTMBGCCWxvY2FsaG9zdIcEfwAAATAKBggqhkjOPQQDAgNH
      ADBEAiAYjqpPhyECxyE/Gwu04YRMWZDYRa+okd6Jm8GgBjozowIgOMdG6nIRHffO
      UZPkevO5zYv9UWsVoxNFtfSAY816pbA=
      -----END CERTIFICATE-----
    """.trimIndent()
  }
}
