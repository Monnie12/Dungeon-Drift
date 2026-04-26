[app]
title = Dungeon Maze Online
package.name = dungeonmazeonline
package.domain = org.codex.dungeonmaze
source.dir = .
source.include_exts = py,md,png,jpg,jpeg,wav,ogg,ttf
version = 0.1

requirements = python3,pygame
orientation = landscape
fullscreen = 1

android.permissions = INTERNET
android.api = 31
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a

presplash.color = #1f1712

log_level = 2
warn_on_root = 0

[buildozer]
log_level = 2
