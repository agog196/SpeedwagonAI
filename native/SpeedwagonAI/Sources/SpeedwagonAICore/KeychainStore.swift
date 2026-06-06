import Foundation
import Security

public final class KeychainStore {
    public static let shared = KeychainStore()

    private let service: String

    public init(service: String = "SpeedwagonAI.LocalBeta") {
        self.service = service
    }

    public func save(_ value: String, account: String) throws {
        let data = Data(value.utf8)
        let query = baseQuery(account: account)
        SecItemDelete(query as CFDictionary)
        var attributes = query
        attributes[kSecValueData as String] = data
        let status = SecItemAdd(attributes as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw KeychainError.status(status)
        }
    }

    public func load(account: String) throws -> String? {
        var query = baseQuery(account: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw KeychainError.status(status)
        }
        guard let data = result as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    public func delete(account: String) throws {
        let status = SecItemDelete(baseQuery(account: account) as CFDictionary)
        if status != errSecSuccess && status != errSecItemNotFound {
            throw KeychainError.status(status)
        }
    }

    public func ensureLocalAPIToken() throws -> String {
        if let existing = try load(account: KeychainAccount.localAPIToken), !existing.isEmpty {
            return existing
        }
        let token = randomToken()
        try save(token, account: KeychainAccount.localAPIToken)
        return token
    }

    private func baseQuery(account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }
}

public enum KeychainAccount {
    public static let openAIAPIKey = "openai_api_key"
    public static let localAPIToken = "local_api_token"
}

public enum KeychainError: Error, LocalizedError, Equatable {
    case status(OSStatus)

    public var errorDescription: String? {
        switch self {
        case let .status(status):
            return "Keychain operation failed with status \(status)."
        }
    }
}

public func randomToken() -> String {
    let bytes = (0..<32).map { _ in UInt8.random(in: 0...255) }
    return Data(bytes).base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
}
