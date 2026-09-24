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
  private let socketStateLock = NSRecursiveLock()
  private var transferPins: [Int: String] = [:]
  private let transferPinsLock = NSLock()
  private let transferChunkSize = 16 * 1024 * 1024

  public func definition() -> ModuleDefinition {
    Name("BlinkySecureSocket")
    Events("onOpen", "onMessage", "onClose", "onError", "onTransferProgress")

    AsyncFunction("connect") { (id: String, urlString: String, pin: String) throws in
      guard let url = URL(string: urlString), url.scheme?.lowercased() == "wss" else {
        throw SecureSocketError("Secure socket requires a wss:// URL")
      }
      guard pin.hasPrefix("sha256/") else {
        throw SecureSocketError("Secure socket requires a sha256/ certificate pin")
      }
      self.socketStateLock.lock()
      defer { self.socketStateLock.unlock() }
      self.closeSocket(id: id)
      let task = self.session.webSocketTask(with: url)
      self.sockets[id] = task
      self.pins[id] = pin
      task.resume()
    }

    AsyncFunction("sendText") { (id: String, data: String) throws in
      guard let socket = self.socket(for: id) else { throw SecureSocketError("Secure socket is not connected: \(id)") }
      socket.send(.string(data)) { error in
        if let error { self.emitError(id: id, message: error.localizedDescription) }
      }
    }

    AsyncFunction("sendBinary") { (id: String, base64Data: String) throws in
      guard let socket = self.socket(for: id), let data = Data(base64Encoded: base64Data) else {
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
    AsyncFunction("hashFile") { (uri: String) async throws -> [String: Any] in
      try self.hashFile(uri: uri)
    }
    AsyncFunction("uploadFile") { (options: [String: Any]) async throws -> [String: Any] in
      try await self.uploadFile(options: options)
    }
    AsyncFunction("downloadFile") { (options: [String: Any]) async throws -> String in
      try await self.downloadFile(options: options)
    }

    OnDestroy {
      self.socketIDs().forEach { self.closeSocket(id: $0) }
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
    guard let id = id(for: webSocketTask), removeSocket(id: id, ifCurrent: webSocketTask) else { return }
    sendEvent("onClose", ["id": id])
  }

  public func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    didReceive challenge: URLAuthenticationChallenge,
    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
  ) {
    let expectedPin: String?
    if let socket = task as? URLSessionWebSocketTask, let id = id(for: socket) {
      expectedPin = pin(for: id)
    } else {
      expectedPin = transferPin(for: task.taskIdentifier)
    }
    guard let trust = challenge.protectionSpace.serverTrust,
          let expectedPin,
          certificatePin(for: trust) == expectedPin else {
      completionHandler(.cancelAuthenticationChallenge, nil)
      return
    }
    // The pinned certificate is intentionally private/self-signed, so normal
    // system CA validation is not used after the public-key pin matches.
    completionHandler(.useCredential, URLCredential(trust: trust))
  }

  public func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
    removeTransferPin(for: task.taskIdentifier)
    guard let socket = task as? URLSessionWebSocketTask, let id = id(for: socket), let error else { return }
    emitError(id: id, message: error.localizedDescription)
  }

  private func hashFile(uri: String) throws -> [String: Any] {
    let url = try fileURL(uri)
    let hasSecurityScope = url.startAccessingSecurityScopedResource()
    defer { if hasSecurityScope { url.stopAccessingSecurityScopedResource() } }
    let handle = try FileHandle(forReadingFrom: url)
    defer { try? handle.close() }
    var hasher = SHA256()
    var size: UInt64 = 0
    while true {
      guard let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty else { break }
      hasher.update(data: data)
      size += UInt64(data.count)
    }
    let digest = hasher.finalize().map { String(format: "%02x", $0) }.joined()
    return ["size": size, "sha256": digest]
  }

  private func uploadFile(options: [String: Any]) async throws -> [String: Any] {
    let source = try fileURL(options.string("sourceUri"))
    let transferId = try options.string("transferId")
    let endpoint = try transferURL(options.string("url"))
    let token = try options.string("token")
    let pin = options["pin"] as? String
    let size = try options.uint64("size")
    let chunkSize = min(max(1, options.int("chunkSize", default: transferChunkSize)), transferChunkSize)
    var offset = try options.uint64("offset", default: 0)
    guard size > 0 && offset <= size else { throw SecureSocketError("Invalid upload size or offset") }

    let hasSecurityScope = source.startAccessingSecurityScopedResource()
    defer { if hasSecurityScope { source.stopAccessingSecurityScopedResource() } }
    while offset < size {
      let handle = try FileHandle(forReadingFrom: source)
      defer { try? handle.close() }
      try handle.seek(toOffset: offset)
      let requestBytes = min(UInt64(chunkSize), size - offset)
      guard let data = try handle.read(upToCount: Int(requestBytes)), !data.isEmpty else {
        throw SecureSocketError("Selected file ended before its reported size")
      }
      var request = URLRequest(url: endpoint, timeoutInterval: 300)
      request.httpMethod = "POST"
      request.httpBody = data
      request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
      request.setValue(String(offset), forHTTPHeaderField: "Upload-Offset")
      request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
      request.setValue(String(data.count), forHTTPHeaderField: "Content-Length")
      let (_, response) = try await send(request, pin: pin)
      let next = response.value(forHTTPHeaderField: "Upload-Offset").flatMap(UInt64.init)
      if response.statusCode == 409, let next, next <= size {
        offset = next
        continue
      }
      guard response.statusCode == 200 || response.statusCode == 201 else {
        throw SecureSocketError("Upload failed (HTTP \(response.statusCode))")
      }
      let updated = next ?? offset + UInt64(data.count)
      guard updated > offset && updated <= size else { throw SecureSocketError("PC returned an invalid upload offset") }
      offset = updated
      sendEvent("onTransferProgress", ["id": transferId, "direction": "upload", "bytes": offset, "total": size])
    }
    return ["transferId": transferId, "uploadOffset": offset, "complete": true]
  }

  private func downloadFile(options: [String: Any]) async throws -> String {
    let transferId = try options.string("transferId")
    let baseURL = try transferURL(options.string("url"))
    let token = try options.string("token")
    let pin = options["pin"] as? String
    let size = try options.uint64("size")
    let expectedHash = try options.string("sha256").lowercased()
    let filename = safeName(try options.string("filename"))
    guard size > 0 else { throw SecureSocketError("Invalid download size") }

    let directory = try FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
      .appendingPathComponent("BlinkyTransfers", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let partial = directory.appendingPathComponent("\(transferId).part")
    var offset = (try? partial.resourceValues(forKeys: [.fileSizeKey]).fileSize).map(UInt64.init) ?? 0
    if offset > size {
      try FileManager.default.removeItem(at: partial)
      offset = 0
    }

    while offset < size {
      let end = min(size - 1, offset + UInt64(transferChunkSize) - 1)
      var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)!
      components.path = "/download/\(transferId)"
      guard let url = components.url else { throw SecureSocketError("Invalid file download URL") }
      var request = URLRequest(url: url, timeoutInterval: 300)
      request.httpMethod = "GET"
      request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
      request.setValue("bytes=\(offset)-\(end)", forHTTPHeaderField: "Range")
      let (data, response) = try await send(request, pin: pin)
      guard response.statusCode == 206 else { throw SecureSocketError("Download failed (HTTP \(response.statusCode))") }
      guard UInt64(response.value(forHTTPHeaderField: "X-File-Size") ?? "") == size,
            response.value(forHTTPHeaderField: "X-File-Sha256")?.lowercased() == expectedHash else {
        throw SecureSocketError("PC returned different file metadata")
      }
      let expectedChunk = Int(end - offset + 1)
      guard data.count == expectedChunk else { throw SecureSocketError("Download chunk was incomplete") }
      if !FileManager.default.fileExists(atPath: partial.path) {
        FileManager.default.createFile(atPath: partial.path, contents: nil)
      }
      let output = try FileHandle(forWritingTo: partial)
      try output.seekToEnd()
      try output.write(contentsOf: data)
      try output.synchronize()
      try output.close()
      offset += UInt64(data.count)
      sendEvent("onTransferProgress", ["id": transferId, "direction": "download", "bytes": offset, "total": size])
    }

    let localHash = try hashFile(uri: partial.absoluteString)["sha256"] as? String
    guard localHash?.lowercased() == expectedHash else { throw SecureSocketError("Downloaded file SHA-256 did not match the PC") }
    let destination = uniqueTransferURL(directory: directory, filename: filename)
    try FileManager.default.moveItem(at: partial, to: destination)
    return destination.absoluteString
  }

  private func send(_ request: URLRequest, pin: String?) async throws -> (Data, HTTPURLResponse) {
    guard let scheme = request.url?.scheme?.lowercased(), scheme == "http" || scheme == "https" else {
      throw SecureSocketError("Transfer URL must use HTTP or HTTPS")
    }
    if scheme == "https" && (pin?.hasPrefix("sha256/") != true) {
      throw SecureSocketError("HTTPS transfers require the saved certificate pin")
    }
    if scheme == "http" && pin != nil {
      throw SecureSocketError("Pinned release transfers must use HTTPS")
    }
    return try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<(Data, HTTPURLResponse), Error>) in
      let task = session.dataTask(with: request) { data, response, error in
        if let error { continuation.resume(throwing: error); return }
        guard let response = response as? HTTPURLResponse else {
          continuation.resume(throwing: SecureSocketError("PC returned an invalid HTTP response")); return
        }
        continuation.resume(returning: (data ?? Data(), response))
      }
      if scheme == "https", let pin { self.setTransferPin(pin, for: task.taskIdentifier) }
      task.resume()
    }
  }

  private func transferPin(for taskIdentifier: Int) -> String? {
    transferPinsLock.lock()
    defer { transferPinsLock.unlock() }
    return transferPins[taskIdentifier]
  }

  private func setTransferPin(_ pin: String, for taskIdentifier: Int) {
    transferPinsLock.lock()
    defer { transferPinsLock.unlock() }
    transferPins[taskIdentifier] = pin
  }

  private func removeTransferPin(for taskIdentifier: Int) {
    transferPinsLock.lock()
    defer { transferPinsLock.unlock() }
    transferPins.removeValue(forKey: taskIdentifier)
  }

  private func fileURL(_ uri: String) throws -> URL {
    guard let url = URL(string: uri), url.isFileURL else { throw SecureSocketError("Selected file URI is invalid") }
    return url
  }

  private func transferURL(_ value: String) throws -> URL {
    guard let url = URL(string: value), let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https" else {
      throw SecureSocketError("Transfer URL must use HTTP or HTTPS")
    }
    return url
  }

  private func safeName(_ value: String) -> String {
    let cleaned = value.unicodeScalars.map { scalar -> Character in
      if CharacterSet(charactersIn: "/\\:*?\"<>|").contains(scalar) || CharacterSet.controlCharacters.contains(scalar) { return "_" }
      return Character(scalar)
    }.reduce(into: "") { $0.append($1) }.trimmingCharacters(in: CharacterSet(charactersIn: ". "))
    return cleaned.isEmpty || cleaned == ".." ? "blinky-download.bin" : String(cleaned.prefix(240))
  }

  private func uniqueTransferURL(directory: URL, filename: String) -> URL {
    let original = directory.appendingPathComponent(filename)
    if !FileManager.default.fileExists(atPath: original.path) { return original }
    let stem = original.deletingPathExtension().lastPathComponent
    let ext = original.pathExtension
    for index in 1...99999 {
      let candidateName = ext.isEmpty ? "\(stem) (\(index))" : "\(stem) (\(index)).\(ext)"
      let candidate = directory.appendingPathComponent(candidateName)
      if !FileManager.default.fileExists(atPath: candidate.path) { return candidate }
    }
    return directory.appendingPathComponent("blinky-\(UUID().uuidString)-\(filename)")
  }


  private func receiveNext(id: String, task: URLSessionWebSocketTask) {
    task.receive { [weak self] result in
      guard let self else { return }
      DispatchQueue.main.async {
        guard self.isCurrentSocket(task, for: id) else { return }
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
    socketStateLock.lock()
    let socket = sockets.removeValue(forKey: id)
    pins.removeValue(forKey: id)
    socketStateLock.unlock()
    socket?.cancel(with: .normalClosure, reason: nil)
  }

  private func id(for task: URLSessionWebSocketTask) -> String? {
    socketStateLock.lock()
    defer { socketStateLock.unlock() }
    return sockets.first(where: { $0.value === task })?.key
  }

  private func socket(for id: String) -> URLSessionWebSocketTask? {
    socketStateLock.lock()
    defer { socketStateLock.unlock() }
    return sockets[id]
  }

  private func pin(for id: String) -> String? {
    socketStateLock.lock()
    defer { socketStateLock.unlock() }
    return pins[id]
  }

  private func socketIDs() -> [String] {
    socketStateLock.lock()
    defer { socketStateLock.unlock() }
    return Array(sockets.keys)
  }

  private func isCurrentSocket(_ task: URLSessionWebSocketTask, for id: String) -> Bool {
    socketStateLock.lock()
    defer { socketStateLock.unlock() }
    return sockets[id] === task
  }

  private func removeSocket(id: String, ifCurrent task: URLSessionWebSocketTask) -> Bool {
    socketStateLock.lock()
    defer { socketStateLock.unlock() }
    guard sockets[id] === task else { return false }
    sockets.removeValue(forKey: id)
    pins.removeValue(forKey: id)
    return true
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

private extension Dictionary where Key == String, Value == Any {
  func string(_ key: String) throws -> String {
    guard let value = self[key] as? String else { throw SecureSocketError("Missing \(key)") }
    return value
  }

  func uint64(_ key: String, default fallback: UInt64? = nil) throws -> UInt64 {
    guard let value = self[key] else {
      if let fallback { return fallback }
      throw SecureSocketError("Missing \(key)")
    }
    guard let number = value as? NSNumber, number.doubleValue >= 0, number.doubleValue <= Double(UInt64.max) else {
      throw SecureSocketError("Invalid \(key)")
    }
    return number.uint64Value
  }

  func int(_ key: String, default fallback: Int) -> Int {
    (self[key] as? NSNumber)?.intValue ?? fallback
  }
}
