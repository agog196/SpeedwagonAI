// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "SpeedwagonAI",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "SpeedwagonAICore", targets: ["SpeedwagonAICore"]),
        .executable(name: "SpeedwagonAI", targets: ["SpeedwagonAI"])
    ],
    targets: [
        .target(name: "SpeedwagonAICore"),
        .executableTarget(
            name: "SpeedwagonAI",
            dependencies: ["SpeedwagonAICore"]
        ),
        .testTarget(
            name: "SpeedwagonAICoreTests",
            dependencies: ["SpeedwagonAICore"]
        )
    ]
)
