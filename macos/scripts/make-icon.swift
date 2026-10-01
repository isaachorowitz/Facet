#!/usr/bin/env swift
// Draw the dashboard's five 270° arcs on a graphite macOS tile.
import AppKit

let size = 1024
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
                             bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                             isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
let context = NSGraphicsContext.current!.cgContext
context.setAllowsAntialiasing(true)

func color(_ hex: UInt32, alpha: CGFloat = 1) -> NSColor {
    NSColor(red: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: alpha)
}
let tile = NSBezierPath(roundedRect: NSRect(x: 100, y: 100, width: 824, height: 824), xRadius: 186, yRadius: 186)
color(0x151518).setFill(); tile.fill()
context.saveGState()
tile.addClip()
NSGradient(starting: color(0x35343b, alpha: 0.65), ending: color(0x09090a))!
    .draw(in: tile, angle: -90)
NSGradient(starting: color(0xf3b562, alpha: 0.09), ending: color(0xf3b562, alpha: 0))!
    .draw(fromCenter: NSPoint(x: 370, y: 660), radius: 10, toCenter: NSPoint(x: 370, y: 660), radius: 490, options: [])
context.restoreGState()

let colors: [UInt32] = [0xf3b562, 0xef8f72, 0xb9a6ff, 0x8fb8ff, 0x7fd6a4]
for (index, hex) in colors.enumerated() {
    let arc = NSBezierPath()
    arc.appendArc(withCenter: NSPoint(x: 512, y: 512), radius: CGFloat(300 - index * 47),
                  startAngle: 45, endAngle: 315, clockwise: false)
    arc.lineWidth = 25
    arc.lineCapStyle = .round
    let shadow = NSShadow()
    shadow.shadowColor = color(hex, alpha: 0.16)
    shadow.shadowBlurRadius = 16
    shadow.shadowOffset = .zero
    context.saveGState(); shadow.set()
    color(hex).setStroke(); arc.stroke()
    context.restoreGState()
}
NSGraphicsContext.restoreGraphicsState()
guard CommandLine.arguments.count == 2, let png = bitmap.representation(using: .png, properties: [:]) else {
    fatalError("Usage: swift scripts/make-icon.swift out.png")
}
try png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
