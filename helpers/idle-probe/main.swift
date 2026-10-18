import AppKit
import CoreGraphics
import Foundation
let types:[CGEventType] = [.keyDown,.flagsChanged,.leftMouseDown,.rightMouseDown,.otherMouseDown,.mouseMoved,.leftMouseDragged,.rightMouseDragged,.otherMouseDragged,.scrollWheel]
let idle=types.map { CGEventSource.secondsSinceLastEventType(.combinedSessionState,eventType:$0) }.min() ?? 0
let point=CGEvent(source:nil)?.location ?? .zero
var counts:[String:UInt32]=[:]
for t in types {counts[String(t.rawValue)]=CGEventSource.counterForEventType(.combinedSessionState,eventType:t)}
let data:[String:Any] = ["idle":min(max(idle,0),1e9),"counts":counts,"x":point.x,"y":point.y]
print(String(data:try! JSONSerialization.data(withJSONObject:data,options:.sortedKeys),encoding:.utf8)!)
