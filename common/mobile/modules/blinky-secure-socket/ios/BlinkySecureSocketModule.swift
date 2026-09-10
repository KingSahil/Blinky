import CryptoKit
import ExpoModulesCore
import Foundation
import Security

public final class BlinkySecureSocketModule: Module, URLSessionWebSocketDelegate {
  private lazy var session: URLSession = {
    URLSession(configuration: .ephemeral, delegate: self, delegateQueue: nil)
  }()
  private var sockets: [String: URLSessionWebSocketTask] = [:]
  private var pins: [String: String] = [:]

  public func definition() -> ModuleDefinition {
    Name("BlinkySecureSocket")
    Events("onOpen", "onMessage", "onClose", "onError")

    AsyncFunction("connect") { (id: String, urlString: String, pin: String) throws in
      guard let url = URL(string: urlString), url.scheme?.lowercased() == "wss" else {
        throw SecureSocketError("Secure socket requires a wss:// URL")
      }
      guard pin.hasPrefix("sha256/") else {
        throw SecureSocketError("Secure socket requires a sha256/ certificate pin")
      }
      self.closeSocket(id: id)
      let task = self.session.webSocketTask(with: url)
      self.sockets[id] = task
      self.pins[id] = pin
      task.resume()
    }

    AsyncFunction("sendText") { (id: String, data: String) throws in
      guard let socket = self.sockets[id] else { throw SecureSocketError("Secure socket is not connected: \(id)") }
      socket.send(.string(data)) { error in
        if let error { self.emitError(id: id, message: error.localizedDescription) }
      }
    }

    AsyncFunction("sendBinary") { (id: String, base64Data: String) throws in
      guard let socket = self.sockets[id], let data = Data(base64Encoded: base64Data) else {
        throw SecureSocketError("Secure socket binary payload is invalid or disconnected: \(id)")
      }
      socket.send(.data(data)) { error in
        if let error { self.emitError(id: id, message: error.localizedDescription) }
      }
    }

    AsyncFunction("close") { (id: String) in
      self.closeSocket(id: id)
    }
    AsyncFunction("getSecureValue") { (key: String) -> String? in
      self.getSecureValue(key: key)
    }
    AsyncFunction("setSecureValue") { (key: String, value: String) throws in
      try self.setSecureValue(key: key, value: value)
    }
    AsyncFunction("deleteSecureValue") { (key: String) throws in
      try self.deleteSecureValue(key: key)
    }

    OnDestroy {
      Array(self.sockets.keys).forEach { self.closeSocket(id: $0) }
    }
  }

  public func urlSession(
    _ session: URLSession,
    webSocketTask: URLSessionWebSocketTask,
    didOpenWithProtocol protocol: String?
  ) {
    guard let id = id(for: webSocketTask) else { return }
    sendEvent("onOpen", ["id": id])
    receiveNext(id: id, task: webSocketTask)
  }

  public func urlSession(
    _ session: URLSession,
    webSocketTask: URLSessionWebSocketTask,
    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
    reason: Data?
  ) {
    guard let id = id(for: webSocketTask) else { return }
    sockets.removeValue(forKey: id)
    pins.removeValue(forKey: id)
    sendEvent("onClose", ["id": id])
  }

  public func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    didReceive challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
  ) {
    guard let trust = challenge.protectionSpace.serverTrust,
          let task = task as? URLSessionWebSocketTask,
          let id = id(for: task),
          let expectedPin = pins[id],
          certificatePin(for: trust) == expectedPin else {
      completionHandler(.cancelAuthenticationChallenge, nil)
      return
    }
    // The pinned certificate is intentionally private/self-signed, so normal
    // system CA validation is not used after the public-key pin matches.
    completionHandler(.useCredential, URLCredential(trust: trust))
  }

  public func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
    guard let task = task as? URLSessionWebSocketTask, let id = id(for: task), let error else { return }
    emitError(id: id, message: error.localizedDescription)
  }

  private func receiveNext(id: String, task: URLSessionWebSocketTask) {
    task.receive { [weak self] result in
      guard let self else { return }
      DispatchQueue.main.async {
        guard self.sockets[id] === task else { return }
        switch result {
        case .success(let message):
          switch message {
          case .string(let text):
            self.sendEvent("onMessage", ["id": id, "data": text])
          case .data(let data):
            self.sendEvent("onMessage", ["id": id, "data": data.base64EncodedString()])
          @unknown default:
            break
          }
          self.receiveNext(id: id, task: task)
        case .failure(let error):
          self.emitError(id: id, message: error.localizedDescription)
        }
      }
    }
  }

  private func closeSocket(id: String) {
    sockets.removeValue(forKey: id)?.cancel(with: .normalClosure, reason: nil)
    pins.removeValue(forKey: id)
  }

  private func id(for task: URLSessionWebSocketTask) -> String? {
    sockets.first(where: { $0.value === task })?.key
  }

  private func emitError(id: String, message: String) {
    sendEvent("onError", ["id": id, "error": message])
  }

  private let keychainService = "app.blinky.tutor.remote"

  private func keychainQuery(key: String) -> [String: Any] {
    [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: keychainService,
      kSecAttrAccount as String: key,
    ]
  }

  private func getSecureValue(key: String) -> String? {
    var query = keychainQuery(key: key)
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
          let data = result as? Data else { return nil }
    return String(data: data, encoding: .utf8)
  }

  private func setSecureValue(key: String, value: String) throws {
    let data = Data(value.utf8)
    SecItemDelete(keychainQuery(key: key) as CFDictionary)
    var query = keychainQuery(key: key)
    query[kSecValueData as String] = data
    guard SecItemAdd(query as CFDictionary, nil) == errSecSuccess else {
      throw SecureSocketError("Unable to save secure value")
    }
  }

  private func deleteSecureValue(key: String) throws {
    let status = SecItemDelete(keychainQuery(key: key) as CFDictionary)
    guard status == errSecSuccess || status == errSecItemNotFound else {
      throw SecureSocketError("Unable to delete secure value")
    }
  }

  private func certificatePin(for trust: SecTrust) -> String? {
    guard let certificate = SecTrustGetCertificateAtIndex(trust, 0),
          let key = SecCertificateCopyKey(certificate),
          let rawKey = SecKeyCopyExternalRepresentation(key, nil) as Data?,
          rawKey.count == 65 else {
      return nil
    }

    // The desktop identity is P-256. This is the DER SubjectPublicKeyInfo
    // prefix for id-ecPublicKey + prime256v1 followed by the 65-byte key.
    let spkiPrefix = Data([
      0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2A, 0x86, 0x48, 0xCE, 0x3D,
      0x02, 0x01, 0x06, 0x08, 0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x03, 0x01,
      0x07, 0x03, 0x42, 0x00
    ])
    let digest = SHA256.hash(data: spkiPrefix + rawKey)
    return "sha256/" + Data(digest).base64EncodedString()
  }
}

private struct SecureSocketError: Error, LocalizedError {
  let message: String
  init(_ message: String) { self.message = message }
  var errorDescription: String? { message }
}
