# Dungeon Maze Online

A co-op `pygame` dungeon maze with:

- a pre-game lobby with ready-up
- player color selection
- a larger maze map
- shared online multiplayer over Python sockets
- chest loot, weapons, potions, and armor
- 60-second dungeon rounds
- a random shop phase every 5 successful escapes
- group-only progression where everyone has to stand in the same exit or portal area to continue

## Install

```bash
pip install -r requirements.txt
```

## Host From The Game

Host computer:

```bash
python game.py --host 127.0.0.1 --port 5000 --name Host
```

If no local server is already running, the game starts one inside the same app and listens on TCP port `5000`.
The host can play immediately, and the game now tries to open the router automatically with UPnP for internet play.
If UPnP works, the host gets a shareable public IP and port in-game.
If UPnP is unavailable, friends on the same network can still join with the LAN IP and internet play still works with manual port forwarding.
Players on the same LAN can also use the new `Find Servers` button from the join screen to discover hosts automatically.

Another computer:

```bash
python game.py --host YOUR_PUBLIC_IP --port 5000 --name Rogue
```

If people are joining from outside your home network, the host still needs to:

- share their public IP address
- allow TCP port `5000` through the firewall
- forward TCP port `5000` from the router to the host computer if the automatic UPnP step does not succeed

## Run a dedicated server (optional)

```bash
python server.py --host 0.0.0.0 --port 5000
```

## Deploy To Railway Without The CLI

If your Windows machine blocks `npm` or the Railway CLI, you can still deploy this project from the Railway website.

1. Put this folder on GitHub.
2. In Railway, create a new project and choose the GitHub repo.
3. Railway will detect the included `Dockerfile` and build the dedicated server service.
4. After deploy, open the service settings and enable `TCP Proxy` for internal port `5000`.
5. Share the generated Railway TCP address with players.

This Docker setup deploys only the dedicated Python socket server, not the local desktop client.

## Run in a Web Browser

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the web app:

```bash
python web_server.py --host 0.0.0.0 --port 8080
```

Then open:

```text
http://YOUR_COMPUTER_IP:8080
```

The web server includes a WebSocket proxy for the browser client.
If you enter `127.0.0.1` or `localhost` in the join form, it can also start an embedded local game server automatically.
If you want the browser client to connect to a separate host, run `server.py` on that host and enter its IP and port in the web UI.

## Controls

- `WASD` or arrow keys: move
- `R`: ready up in the lobby
- `Space`: attack
- `F`: open nearby chests or buy nearby shop items
- `G`: gamble at the shop
- `H`: use a potion
- `Q` / `Tab`: switch equipped weapon or change gamble bet in the shop
- `E`: inventory/crafting
- `Esc`: pause in single-player runs

## Mobile Controls

- on-screen movement pad in the lower-left corner
- on-screen action buttons in the lower-right corner for ready/attack, buy/use, potion, inventory, and weapon or gamble-bet cycling
- tappable join button on the connection screen
- tappable character color picker on the connection screen
- tappable inventory recipes plus touch buttons for closing inventory and cycling weapons

## Browser Controls

- desktop: `WASD` or arrow keys to move, `R` ready, `Space` attack, `F` interact, `G` gamble, `H` potion, `Q` / `Tab` weapon swap or gamble bet, `E` inventory, `Esc` pause in single-player
- mobile: touch controls on-screen plus tappable inventory crafting

## Android Packaging Note

This project is now more mobile-friendly at the input layer, but it is still a `pygame` project rather than a native Android project.
Building a real `.apk` still requires an Android packaging toolchain such as Java, Android SDK, Gradle, and a supported Python-to-Android workflow, which is not installed in this workspace right now.

## APK Converter Prep

This folder now includes:

- `main.py` as a package-friendly entrypoint for Android-oriented Python packagers
- `buildozer.spec` as a starter config for `Buildozer` / `python-for-android`

If you move this project into an APK packaging environment, start from `main.py` instead of `game.py`.
If your converter supports custom arguments, pass `--host`, `--port`, and `--name`.

## Game Flow

1. Everyone joins the lobby and presses `R` when ready.
2. A 60-second round starts in the dungeon.
3. Open all chests to find gold, weapons, potions, and armor.
4. Once the loot is cleared, every connected player has to stand in the exit zone together.
5. After every 5 successful escapes, everyone is sent to a random shop.
6. In the shop, players can spend gold and then must all gather in the portal area to start the next round.
