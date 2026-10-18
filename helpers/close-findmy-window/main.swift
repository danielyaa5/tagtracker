import AppKit
import ApplicationServices
import Foundation
func fail(_ s:String)->Never {FileHandle.standardError.write(Data((s+"\n").utf8));exit(1)}
func attr(_ e:AXUIElement,_ key:String)->CFTypeRef? {var value:CFTypeRef?;let result=AXUIElementCopyAttributeValue(e,key as CFString,&value);return result == .success ? value:nil}
let args=CommandLine.arguments.dropFirst().compactMap(Double.init)
guard args.count==4 else {fail("Expected scanned window x y width height")}
guard let app=NSRunningApplication.runningApplications(withBundleIdentifier:"com.apple.findmy").first else {print("{\"closed\":true,\"already_closed\":true}");exit(0)}
let root=AXUIElementCreateApplication(app.processIdentifier)
guard let windows=attr(root,kAXWindowsAttribute) as? [AXUIElement] else {fail("Cannot read Find My windows")}
func matches(_ w:AXUIElement)->Bool {
 guard let pv=attr(w,kAXPositionAttribute),let sv=attr(w,kAXSizeAttribute),CFGetTypeID(pv)==AXValueGetTypeID(),CFGetTypeID(sv)==AXValueGetTypeID() else{return false}
 var p=CGPoint.zero;var s=CGSize.zero
 guard AXValueGetValue(pv as! AXValue,.cgPoint,&p),AXValueGetValue(sv as! AXValue,.cgSize,&s) else{return false}
 return zip([p.x,p.y,s.width,s.height],args).allSatisfy{abs($0-$1)<2}
}
let matchesList=windows.filter(matches)
guard matchesList.count==1 else {fail("Cannot uniquely identify the scanned Find My window")}
let window=matchesList[0]
guard let value=attr(window,kAXCloseButtonAttribute),CFGetTypeID(value)==AXUIElementGetTypeID() else {fail("Find My close button unavailable")}
let result=AXUIElementPerformAction(value as! AXUIElement,kAXPressAction as CFString)
guard result == .success else {fail("Find My close failed: \(result.rawValue)")}
for _ in 0..<20 {
 usleep(100_000)
 if app.isTerminated || NSRunningApplication.runningApplications(withBundleIdentifier:"com.apple.findmy").allSatisfy({$0.processIdentifier != app.processIdentifier}) || (attr(root,kAXWindowsAttribute) as? [AXUIElement]).map({!$0.contains(where:matches)}) == true {print("{\"closed\":true}");exit(0)}
}
fail("Find My window remained open after close action")
