import Foundation

struct SendJob: Codable {
    let id: String
    let title: String
    let author: String
    let expectedFilename: String
    let archive: String
    let send: String
    let sha256: String

    func matches(fields: [String]) -> Bool {
        fields.count == 2 && fields[0] == expectedFilename && !title.isEmpty && !author.isEmpty
    }
    func verified(fields: [String]) -> Bool { fields == [title, author] }
    static func isSuccess(_ texts: [String]) -> Bool {
        texts.contains { $0.trimmingCharacters(in: .whitespacesAndNewlines) == "File sent" }
    }
}

struct Configuration: Codable {
    var destination = "~/Documents/Books"
    var mode = "auto"

    static func load(from url: URL) throws -> Configuration {
        guard FileManager.default.fileExists(atPath: url.path) else { return Configuration() }
        let config = try JSONDecoder().decode(Configuration.self, from: Data(contentsOf: url))
        guard ["auto", "review"].contains(config.mode), !config.destination.isEmpty,
              NSString(string: config.destination).expandingTildeInPath.hasPrefix("/") else {
            throw NSError(domain: "BookToKindle", code: 1, userInfo: [NSLocalizedDescriptionKey: "Invalid configuration. Reapply setup with an absolute destination and auto or review mode."])
        }
        return config
    }
}
