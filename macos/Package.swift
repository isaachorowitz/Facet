// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Facet",
    platforms: [.macOS(.v15)],
    products: [
        .library(name: "FacetCore", targets: ["FacetCore"]),
        .executable(name: "FacetApp", targets: ["Facet"]),
    ],
    targets: [
        .target(name: "FacetCore"),
        .executableTarget(name: "Facet", dependencies: ["FacetCore"]),
        .testTarget(name: "FacetCoreTests", dependencies: ["FacetCore"], resources: [.copy("Fixtures")]),
    ],
    swiftLanguageModes: [.v5]
)
