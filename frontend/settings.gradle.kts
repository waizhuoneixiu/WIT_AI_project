pluginManagement {
    repositories {
        google()
        maven("https://dl.google.com/android/maven2")
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        maven("https://dl.google.com/android/maven2")
        mavenCentral()
    }
}
rootProject.name = "SteelScan"
include(":composeApp", ":androidApp")
