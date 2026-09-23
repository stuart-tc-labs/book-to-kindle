import AppKit
import ApplicationServices

func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    var result: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name as CFString, &result) == .success else { return nil }
    return result
}
func string(_ element: AXUIElement, _ name: String) -> String { attribute(element, name) as? String ?? "" }
func texts(_ element: AXUIElement) -> [String] {
    [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute].map { string(element, $0) }.filter { !$0.isEmpty }
}
func walk(_ root: AXUIElement) -> [AXUIElement] {
    var queue = [root], result: [AXUIElement] = [], index = 0
    // CFEqual, not CFHash alone: two distinct AX elements can share a hash.
    while index < queue.count && result.count < 1000 {
        let element = queue[index]; index += 1
        if result.contains(where: { CFEqual($0, element) }) { continue }
        result.append(element)
        for key in [kAXChildrenAttribute, kAXWindowsAttribute, "AXSheets"] {
            queue += attribute(element, key) as? [AXUIElement] ?? []
        }
    }
    return result
}
func press(_ element: AXUIElement) -> Bool {
    AXUIElementPerformAction(element, kAXPressAction as CFString) == .success
}
