from __future__ import annotations

import argparse
import json
import math
import random
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from shared import (
    ACCESSORY_DEFS,
    ARMOR_DEFS,
    ATTACK_ANIMATION_TIME,
    ATTACK_COOLDOWN,
    ATTACK_RANGE,
    BROADCAST_TICK,
    CHEST_SIZE,
    CRAFTING_RECIPES,
    DISCOVERY_PORT,
    DIFFICULTY_DEFS,
    DUNGEON_HEIGHT,
    DUNGEON_WIDTH,
    LOBBY_MAP,
    MAX_PLAYERS,
    MONSTER_ARCHETYPES,
    MONSTER_PROJECTILE_SPEED,
    MONSTER_SIZE,
    MOVE_SPEED,
    INVENTORY_SLOT_COUNT,
    PLAYER_COLORS,
    PLAYER_SIZE,
    PROJECTILE_SIZE,
    PROJECTILE_SPEED,
    RESOURCE_DEFS,
    ROUND_TIME_SECONDS,
    SERVER_PORT,
    SERVER_TICK,
    SHOP_AFTER_ESCAPES,
    SHOP_ITEM_SIZE,
    SHOP_MAPS,
    SHOP_SLOTS,
    TILE_SIZE,
    WEAPON_DEFS,
    circle_rect_collision,
    find_tiles,
    find_path,
    from_json,
    map_dimensions,
    tile_to_position,
    to_json,
    wall_rects,
)


@dataclass
class PlayerState:
    player_id: int
    name: str
    x: float
    y: float
    color_index: int = 0
    accessory_id: str = "none"
    hp: int = 100
    max_hp: int = 100
    gold: int = 0
    potions: int = 1
    bandages: int = 0
    arrows: int = 0
    armors: list[str] = field(default_factory=list)
    weapons: list[str] = field(default_factory=lambda: ["rusty_sword"])
    inventory_layout: list[str | None] = field(default_factory=list)
    equipped_index: int = 0
    ready: bool = False
    connected: bool = True
    attack_cooldown: float = 0.0
    interact_cooldown: float = 0.0
    craft_cooldown: float = 0.0
    input_state: dict[str, bool] = field(
        default_factory=lambda: {"up": False, "down": False, "left": False, "right": False}
    )
    resources: dict[str, int] = field(default_factory=lambda: {resource_id: 0 for resource_id in RESOURCE_DEFS})
    score: int = 0
    facing_x: float = 1.0
    facing_y: float = 0.0
    attack_animation: float = 0.0
    attack_style: str = "melee"
    attack_weapon_id: str = "rusty_sword"
    gamble_bet: int = 5

    @property
    def color(self) -> tuple[int, int, int]:
        return PLAYER_COLORS[self.color_index % len(PLAYER_COLORS)]

    @property
    def weapon_id(self) -> str:
        return self.weapons[self.equipped_index]


@dataclass
class MonsterState:
    monster_id: int
    kind: str
    x: float
    y: float
    hp: int
    max_hp: int
    damage: int
    speed: float
    attack_delay: float
    aggro_range: float
    alive: bool = True
    attack_cooldown: float = 0.0
    roam_target: tuple[float, float] | None = None
    roam_timer: float = 0.0
    path_tiles: list[tuple[int, int]] = field(default_factory=list)
    path_goal: tuple[int, int] | None = None
    path_refresh: float = 0.0
    attack_style: str = "melee"


@dataclass
class ProjectileState:
    owner_id: int | None
    x: float
    y: float
    dx: float
    dy: float
    speed: float
    damage: int
    from_monster: bool = False
    ttl: float = 1.0


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class GameServer:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.rng = random.Random()
        self.server_id = f"{socket.gethostname()}-{self.port}-{time.time_ns()}"
        self.players: dict[int, PlayerState] = {}
        self.connections: dict[int, socket.socket] = {}
        self.files: dict[int, object] = {}
        self.next_player_id = 1
        self.running = True
        self.lock = threading.RLock()
        self.server_socket: socket.socket | None = None
        self.discovery_socket: socket.socket | None = None

        self.phase = "lobby"
        self.difficulty_id = "normal"
        self.round_number = 0
        self.escapes_completed = 0
        self.status_message = "Waiting in the lobby. Choose your character before joining, then press R to ready up."
        self.paused = False
        self.paused_at: float | None = None
        self.paused_status_message: str | None = None
        self.round_ends_at: float | None = None
        self.active_map = [row[:] for row in LOBBY_MAP]
        self.width, self.height = map_dimensions(self.active_map)
        self.wall_rects = wall_rects(self.active_map)
        self.spawn_points = self._spawn_points(self.active_map)
        self.goal_tiles: list[tuple[float, float]] = []
        self.gamble_spots: list[tuple[float, float]] = []
        self.chests: list[dict] = []
        self.coins: list[dict] = []
        self.shop_items: list[dict] = []
        self.monsters: list[MonsterState] = []
        self.projectiles: list[ProjectileState] = []
        self.next_coin_id = 1
        self.no_players_since: float | None = None
        self.save_path = runtime_root() / "savegame.json"
        self._set_map(LOBBY_MAP, goal_tile="L")

    def _set_map(self, map_lines: list[str], goal_tile: str) -> None:
        self.active_map = map_lines
        self.width, self.height = map_dimensions(map_lines)
        self.wall_rects = wall_rects(map_lines)
        self.spawn_points = self._spawn_points(map_lines)
        self.gamble_spots = [
            tile_to_position(col, row, inset=10)
            for col, row in find_tiles(map_lines, "G")
        ]
        self.goal_tiles = [
            (col * TILE_SIZE + TILE_SIZE / 2, row * TILE_SIZE + TILE_SIZE / 2)
            for col, row in find_tiles(map_lines, goal_tile)
        ]

    def _spawn_points(self, map_lines: list[str]) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        for col, row in find_tiles(map_lines, "S"):
            points.append(tile_to_position(col, row))
            points.append(tile_to_position(col, row, inset=18))
            points.append(tile_to_position(col, row, inset=8))
        return points or [(TILE_SIZE * 2, TILE_SIZE * 2)]

    def _generate_dungeon_map(self) -> list[str]:
        while True:
            width = DUNGEON_WIDTH
            height = DUNGEON_HEIGHT
            grid = [["#" for _ in range(width)] for _ in range(height)]

            for row in range(1, height, 2):
                for col in range(1, width, 2):
                    grid[row][col] = "."

            stack = [(1, 1)]
            visited = {(1, 1)}
            directions = [(2, 0), (-2, 0), (0, 2), (0, -2)]
            while stack:
                col, row = stack[-1]
                neighbors = []
                for dc, dr in directions:
                    nc = col + dc
                    nr = row + dr
                    if 1 <= nc < width - 1 and 1 <= nr < height - 1 and (nc, nr) not in visited:
                        neighbors.append((nc, nr, dc, dr))
                if not neighbors:
                    stack.pop()
                    continue
                nc, nr, dc, dr = self.rng.choice(neighbors)
                visited.add((nc, nr))
                grid[row + dr // 2][col + dc // 2] = "."
                grid[nr][nc] = "."
                stack.append((nc, nr))

            floors = [(col, row) for row in range(1, height - 1) for col in range(1, width - 1) if grid[row][col] == "."]
            if len(floors) < 40:
                continue

            self.rng.shuffle(floors)
            for col, row in floors[:4]:
                grid[row][col] = "S"
            for col, row in floors[4:12]:
                grid[row][col] = "C"
            for col, row in floors[12:20]:
                grid[row][col] = "M"
            exit_col, exit_row = floors[-1]
            grid[exit_row][exit_col] = "E"
            return ["".join(row) for row in grid]

    def _connected_players(self) -> list[PlayerState]:
        return [player for player in self.players.values() if player.connected]

    def _living_players(self) -> list[PlayerState]:
        return [player for player in self._connected_players() if player.hp > 0]

    def _server_browser_name(self) -> str:
        players = self._connected_players()
        if players:
            host_name = players[0].name.strip() or "Adventurer"
            return f"{host_name}'s Game"
        return f"{socket.gethostname()} Server"

    def _discovery_payload(self) -> dict:
        return {
            "type": "server_info",
            "server_id": self.server_id,
            "name": self._server_browser_name(),
            "port": self.port,
            "players": len(self._connected_players()),
            "max_players": MAX_PLAYERS,
            "phase": self.phase,
            "difficulty_id": self.difficulty_id,
        }

    def _discovery_loop(self) -> None:
        try:
            self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except OSError:
                pass
            self.discovery_socket.bind(("", DISCOVERY_PORT))
            self.discovery_socket.settimeout(1.0)
        except OSError:
            self.discovery_socket = None
            return

        while self.running:
            try:
                packet, addr = self.discovery_socket.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                break

            try:
                payload = json.loads(packet.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if payload.get("type") != "discover_server":
                continue

            response = to_json(self._discovery_payload())
            try:
                self.discovery_socket.sendto(response, addr)
            except OSError:
                continue

    def start(self) -> None:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"Server listening on {self.host}:{self.port}")

        threading.Thread(target=self._game_loop, daemon=True).start()
        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        threading.Thread(target=self._discovery_loop, daemon=True).start()

        while self.running:
            try:
                conn, addr = self.server_socket.accept()
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _handle_client(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        player_id: int | None = None
        file = conn.makefile("rwb")
        try:
            join_message = from_json(file.readline())
            if join_message.get("type") != "join":
                file.write(to_json({"type": "error", "message": "Expected a join message first."}))
                file.flush()
                return

            with self.lock:
                if len(self._connected_players()) >= MAX_PLAYERS:
                    file.write(to_json({"type": "error", "message": "The lobby is full."}))
                    file.flush()
                    return

                player_id = self.next_player_id
                self.next_player_id += 1
                name = str(join_message.get("name", "Adventurer")).strip()[:18] or "Adventurer"
                try:
                    color_index = int(join_message.get("color_index", 0)) % len(PLAYER_COLORS)
                except (TypeError, ValueError):
                    color_index = 0
                accessory_id = str(join_message.get("accessory_id", "none"))
                if accessory_id not in ACCESSORY_DEFS:
                    accessory_id = "none"
                player = PlayerState(
                    player_id=player_id,
                    name=name,
                    x=0,
                    y=0,
                    color_index=color_index,
                    accessory_id=accessory_id,
                )
                self._spawn_player(player)
                self.players[player_id] = player
                self.connections[player_id] = conn
                self.files[player_id] = file

            file.write(to_json({"type": "welcome", "player_id": player_id}))
            file.flush()
            print(f"{name} joined from {addr[0]}:{addr[1]}")

            while self.running:
                line = file.readline()
                if not line:
                    break
                message = from_json(line)
                with self.lock:
                    player = self.players.get(player_id)
                    if player is None or not player.connected:
                        continue
                    if message.get("type") == "input":
                        player.input_state = {
                            "up": bool(message.get("up")),
                            "down": bool(message.get("down")),
                            "left": bool(message.get("left")),
                            "right": bool(message.get("right")),
                        }
                    elif message.get("type") == "action":
                        self._handle_action(player, str(message.get("action", "")))
        except (ConnectionError, OSError, ValueError):
            pass
        finally:
            with self.lock:
                if player_id is not None and player_id in self.players:
                    self.players[player_id].connected = False
                if player_id is not None:
                    self.connections.pop(player_id, None)
                    self.files.pop(player_id, None)
            try:
                file.close()
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
            if player_id is not None:
                print(f"Player {player_id} disconnected.")

    def _spawn_player(self, player: PlayerState) -> None:
        spawn_x, spawn_y = self.rng.choice(self.spawn_points)
        player.x = spawn_x
        player.y = spawn_y
        player.facing_x = 1.0
        player.facing_y = 0.0
        self._ensure_inventory_layout(player)

    def _handle_action(self, player: PlayerState, action: str) -> None:
        if action == "toggle_pause":
            if len(self._connected_players()) == 1 and self.phase in {"round", "shop"}:
                self._toggle_pause()
        elif action.startswith("save_game"):
            if len(self._connected_players()) == 1 and self.paused:
                filename = None
                if ":" in action:
                    filename = action.split(":", 1)[1]
                self._save_game(player, filename=filename)
        elif action.startswith("load_game"):
            if len(self._connected_players()) == 1 and self.paused:
                filename = None
                if ":" in action:
                    filename = action.split(":", 1)[1]
                self._load_game(player, filename=filename)
        elif self.paused:
            return
        elif action == "toggle_ready":
            if self.phase == "lobby":
                player.ready = not player.ready
        elif action == "difficulty_prev":
            if self.phase == "lobby":
                self._cycle_difficulty(-1)
        elif action == "difficulty_next":
            if self.phase == "lobby":
                self._cycle_difficulty(1)
        elif action == "cycle_color":
            player.color_index = (player.color_index + 1) % len(PLAYER_COLORS)
        elif action == "attack":
            self._player_attack(player)
        elif action == "interact":
            if self.phase == "round":
                self._open_chest(player)
            elif self.phase == "shop":
                self._buy_shop_item(player)
        elif action == "use_potion":
            self._use_potion(player)
        elif action == "use_bandage":
            self._use_bandage(player)
        elif action == "cycle_weapon_prev":
            if self.phase == "shop":
                player.gamble_bet = max(1, player.gamble_bet - 1)
                self.status_message = f"{player.name} sets the gamble bet to ${player.gamble_bet}."
            elif len(player.weapons) > 1:
                player.equipped_index = (player.equipped_index - 1) % len(player.weapons)
        elif action == "cycle_weapon_next":
            if self.phase == "shop":
                max_bet = max(1, player.gold)
                player.gamble_bet = min(max_bet, player.gamble_bet + 1)
                self.status_message = f"{player.name} sets the gamble bet to ${player.gamble_bet}."
            elif len(player.weapons) > 1:
                player.equipped_index = (player.equipped_index + 1) % len(player.weapons)
        elif action == "gamble":
            if self.phase == "shop":
                self._gamble_at_shop(player)
        elif action.startswith("craft:"):
            self._craft_recipe(player, action.split(":", 1)[1])
        elif action.startswith("move_slot:"):
            parts = action.split(":")
            if len(parts) == 3:
                try:
                    from_index = int(parts[1])
                    to_index = int(parts[2])
                except ValueError:
                    return
                self._move_inventory_slot(player, from_index, to_index)
        elif action.startswith("use_slot:"):
            try:
                slot_index = int(action.split(":", 1)[1])
            except ValueError:
                return
            self._use_inventory_slot(player, slot_index)

    def _game_loop(self) -> None:
        while self.running:
            start = time.time()
            with self.lock:
                self._update_world(SERVER_TICK)
            elapsed = time.time() - start
            time.sleep(max(0.0, SERVER_TICK - elapsed))

    def _broadcast_loop(self) -> None:
        while self.running:
            with self.lock:
                snapshots = {player_id: to_json(self._snapshot(player_id)) for player_id in self.files}
                files = dict(self.files)
            disconnected: list[int] = []
            for player_id, file in files.items():
                try:
                    file.write(snapshots[player_id])
                    file.flush()
                except OSError:
                    disconnected.append(player_id)
            if disconnected:
                with self.lock:
                    for player_id in disconnected:
                        player = self.players.get(player_id)
                        if player is not None:
                            player.connected = False
                        self.connections.pop(player_id, None)
                        self.files.pop(player_id, None)
            time.sleep(BROADCAST_TICK)

    def _update_world(self, dt: float) -> None:
        connected_players = self._connected_players()
        if connected_players:
            self.no_players_since = None
        elif self.phase in {"round", "shop"}:
            if self.no_players_since is None:
                self.no_players_since = time.time()
            elif time.time() - self.no_players_since >= 10.0:
                self._go_to_lobby("Everyone left. Waiting in the lobby for new players.")
                return

        if self.paused:
            return

        for player in connected_players:
            player.attack_cooldown = max(0.0, player.attack_cooldown - dt)
            player.interact_cooldown = max(0.0, player.interact_cooldown - dt)
            player.craft_cooldown = max(0.0, player.craft_cooldown - dt)
            player.attack_animation = max(0.0, player.attack_animation - dt)
            self._update_player_move(player, dt)
            self._collect_coins(player)

        self._update_projectiles(dt)
        self._update_monsters(dt)

        if self.phase == "lobby":
            if connected_players and all(player.ready for player in connected_players):
                self._start_round(1 if self.round_number == 0 else self.round_number + 1)
            elif connected_players:
                ready_count = sum(1 for player in connected_players if player.ready)
                difficulty_name = DIFFICULTY_DEFS[self.difficulty_id]["name"]
                self.status_message = f"Waiting in the lobby. {ready_count}/{len(connected_players)} players ready. Difficulty: {difficulty_name}."
        elif self.phase == "round":
            self._check_round_progress()
        elif self.phase == "shop":
            self._check_shop_progress()

    def _update_player_move(self, player: PlayerState, dt: float) -> None:
        dx = float(player.input_state["right"]) - float(player.input_state["left"])
        dy = float(player.input_state["down"]) - float(player.input_state["up"])
        if dx == 0 and dy == 0:
            return

        length = math.hypot(dx, dy)
        dx /= length
        dy /= length
        player.facing_x = dx
        player.facing_y = dy

        distance = MOVE_SPEED * dt
        next_x = player.x + dx * distance
        next_y = player.y + dy * distance
        player.x, player.y = self._slide_move(player.x, player.y, next_x, next_y, PLAYER_SIZE)

    def _update_projectiles(self, dt: float) -> None:
        remaining: list[ProjectileState] = []
        for projectile in self.projectiles:
            projectile.ttl -= dt
            if projectile.ttl <= 0:
                continue
            next_x = projectile.x + projectile.dx * projectile.speed * dt
            next_y = projectile.y + projectile.dy * projectile.speed * dt
            rect = (next_x, next_y, PROJECTILE_SIZE, PROJECTILE_SIZE)
            if any(self._rect_overlap(rect, wall) for wall in self.wall_rects):
                continue

            hit = False
            if projectile.from_monster:
                for player in self._living_players():
                    player_rect = (player.x, player.y, PLAYER_SIZE, PLAYER_SIZE)
                    if self._rect_overlap(rect, player_rect):
                        armor_reduction = sum(ARMOR_DEFS[armor_id]["bonus_hp"] for armor_id in player.armors) // 10
                        player.hp -= max(1, projectile.damage - armor_reduction)
                        self.status_message = f"{player.name} is hit by an arrow."
                        if player.hp <= 0:
                            player.hp = 0
                            self._handle_player_defeat(player)
                        hit = True
                        break
            else:
                for monster in self.monsters:
                    if not monster.alive:
                        continue
                    monster_rect = (monster.x, monster.y, MONSTER_SIZE, MONSTER_SIZE)
                    if self._rect_overlap(rect, monster_rect):
                        monster.hp -= projectile.damage
                        if monster.hp <= 0:
                            monster.alive = False
                            self._drop_coins(monster.x, monster.y, 5 + self.round_number * 2)
                            self._drop_resources(monster.x, monster.y, self._monster_resource_drop(monster.kind))
                            owner = self.players.get(projectile.owner_id) if projectile.owner_id is not None else None
                            if owner is not None:
                                owner.score += 10
                        hit = True
                        break
            if hit:
                continue

            projectile.x = next_x
            projectile.y = next_y
            remaining.append(projectile)
        self.projectiles = remaining

    def _update_monsters(self, dt: float) -> None:
        players = self._living_players()
        if not players:
            return

        for monster in self.monsters:
            if not monster.alive:
                continue
            monster.attack_cooldown = max(0.0, monster.attack_cooldown - dt)
            monster.path_refresh = max(0.0, monster.path_refresh - dt)
            monster.roam_timer = max(0.0, monster.roam_timer - dt)

            target = min(players, key=lambda player: math.hypot(player.x - monster.x, player.y - monster.y))
            distance = math.hypot(target.x - monster.x, target.y - monster.y)
            if distance <= monster.aggro_range:
                self._move_monster_with_path(monster, target.x, target.y, dt)
            else:
                self._roam_monster(monster, dt)

            if monster.attack_cooldown <= 0:
                if monster.attack_style == "ranged" and distance <= max(ATTACK_RANGE * 4, monster.aggro_range * 0.75):
                    monster.attack_cooldown = monster.attack_delay
                    self._monster_ranged_attack(monster, target)
                elif monster.attack_style != "ranged" and distance <= ATTACK_RANGE:
                    monster.attack_cooldown = monster.attack_delay
                    damage = monster.damage
                    armor_reduction = sum(ARMOR_DEFS[armor_id]["bonus_hp"] for armor_id in target.armors) // 10
                    target.hp -= max(1, damage - armor_reduction)
                    self.status_message = f"{target.name} is hit by a {monster.kind}."
                    if target.hp <= 0:
                        target.hp = 0
                        self._handle_player_defeat(target)

    def _monster_ranged_attack(self, monster: MonsterState, target: PlayerState) -> None:
        dx = (target.x + PLAYER_SIZE / 2) - (monster.x + MONSTER_SIZE / 2)
        dy = (target.y + PLAYER_SIZE / 2) - (monster.y + MONSTER_SIZE / 2)
        length = max(1.0, math.hypot(dx, dy))
        self.projectiles.append(
            ProjectileState(
                owner_id=None,
                from_monster=True,
                x=monster.x + MONSTER_SIZE / 2,
                y=monster.y + MONSTER_SIZE / 2,
                dx=dx / length,
                dy=dy / length,
                speed=MONSTER_PROJECTILE_SPEED,
                damage=monster.damage,
            )
        )
        self.status_message = f"{monster.kind.title()} fires a bow shot."

    def _entity_tile(self, x: float, y: float, size: int) -> tuple[int, int]:
        center_x = x + size / 2
        center_y = y + size / 2
        return int(center_x // TILE_SIZE), int(center_y // TILE_SIZE)

    def _tile_anchor(self, tile: tuple[int, int], size: int) -> tuple[float, float]:
        col, row = tile
        return (
            col * TILE_SIZE + (TILE_SIZE - size) / 2,
            row * TILE_SIZE + (TILE_SIZE - size) / 2,
        )

    def _refresh_monster_path(self, monster: MonsterState, goal_tile: tuple[int, int]) -> None:
        start_tile = self._entity_tile(monster.x, monster.y, MONSTER_SIZE)
        if monster.path_refresh > 0 and monster.path_goal == goal_tile and monster.path_tiles:
            return
        path = find_path(self.active_map, start_tile, goal_tile)
        monster.path_tiles = path[1:] if len(path) > 1 else []
        monster.path_goal = goal_tile
        monster.path_refresh = 0.35

    def _move_monster_toward_tile(self, monster: MonsterState, tile: tuple[int, int], dt: float) -> None:
        target_x, target_y = self._tile_anchor(tile, MONSTER_SIZE)
        dx = target_x - monster.x
        dy = target_y - monster.y
        distance = math.hypot(dx, dy)
        if distance < 2:
            return
        scale = max(1.0, distance)
        next_x = monster.x + dx / scale * monster.speed * dt
        next_y = monster.y + dy / scale * monster.speed * dt
        monster.x, monster.y = self._slide_move(monster.x, monster.y, next_x, next_y, MONSTER_SIZE)

    def _move_monster_with_path(self, monster: MonsterState, target_x: float, target_y: float, dt: float) -> None:
        goal_tile = self._entity_tile(target_x, target_y, PLAYER_SIZE)
        self._refresh_monster_path(monster, goal_tile)

        current_tile = self._entity_tile(monster.x, monster.y, MONSTER_SIZE)
        while monster.path_tiles and monster.path_tiles[0] == current_tile:
            monster.path_tiles.pop(0)

        if monster.path_tiles:
            self._move_monster_toward_tile(monster, monster.path_tiles[0], dt)
            return

        dx = target_x - monster.x
        dy = target_y - monster.y
        scale = max(1.0, math.hypot(dx, dy))
        next_x = monster.x + dx / scale * monster.speed * dt
        next_y = monster.y + dy / scale * monster.speed * dt
        monster.x, monster.y = self._slide_move(monster.x, monster.y, next_x, next_y, MONSTER_SIZE)

    def _roam_monster(self, monster: MonsterState, dt: float) -> None:
        if monster.roam_target is None or monster.roam_timer <= 0:
            floor_tiles = find_tiles(self.active_map, ".")
            if not floor_tiles:
                return
            roam_tile = self.rng.choice(floor_tiles)
            monster.roam_target = self._tile_anchor(roam_tile, MONSTER_SIZE)
            monster.path_tiles = []
            monster.path_goal = None
            monster.roam_timer = self.rng.uniform(1.5, 3.5)

        roam_x, roam_y = monster.roam_target
        roam_tile = self._entity_tile(roam_x, roam_y, MONSTER_SIZE)
        self._refresh_monster_path(monster, roam_tile)
        current_tile = self._entity_tile(monster.x, monster.y, MONSTER_SIZE)
        while monster.path_tiles and monster.path_tiles[0] == current_tile:
            monster.path_tiles.pop(0)

        if monster.path_tiles:
            self._move_monster_toward_tile(monster, monster.path_tiles[0], dt)
            return

        dx = roam_x - monster.x
        dy = roam_y - monster.y
        if math.hypot(dx, dy) < 6:
            monster.roam_timer = 0.0
            monster.roam_target = None

    def _handle_player_defeat(self, player: PlayerState) -> None:
        player.gold = max(0, player.gold - 6)
        self._go_to_lobby(f"{player.name} was defeated. Returning to the lobby.")

    def _slide_move(self, current_x: float, current_y: float, next_x: float, next_y: float, size: int) -> tuple[float, float]:
        x_only = (next_x, current_y, size, size)
        y_only = (current_x, next_y, size, size)
        both = (next_x, next_y, size, size)
        if not any(self._rect_overlap(both, wall) for wall in self.wall_rects):
            return next_x, next_y
        if not any(self._rect_overlap(x_only, wall) for wall in self.wall_rects):
            return next_x, current_y
        if not any(self._rect_overlap(y_only, wall) for wall in self.wall_rects):
            return current_x, next_y
        return current_x, current_y

    def _rect_overlap(self, a: tuple[float, float, int, int], b: tuple[float, float, int, int]) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by

    def _player_attack(self, player: PlayerState) -> None:
        if self.phase != "round" or player.attack_cooldown > 0:
            return

        weapon = WEAPON_DEFS[player.weapon_id]
        if weapon["style"] == "ranged" and player.arrows <= 0:
            self.status_message = f"{player.name} is out of arrows."
            return
        player.attack_cooldown = ATTACK_COOLDOWN
        player.attack_animation = ATTACK_ANIMATION_TIME
        player.attack_style = weapon["style"]
        player.attack_weapon_id = player.weapon_id
        self.status_message = f"{player.name} attacks with {weapon['name']}."

        if weapon["style"] == "ranged":
            player.arrows -= 1
            direction_x = player.facing_x
            direction_y = player.facing_y
            if direction_x == 0 and direction_y == 0:
                direction_x = 1.0
            self.projectiles.append(
                ProjectileState(
                    owner_id=player.player_id,
                    from_monster=False,
                    x=player.x + PLAYER_SIZE / 2,
                    y=player.y + PLAYER_SIZE / 2,
                    dx=direction_x,
                    dy=direction_y,
                    speed=PROJECTILE_SPEED,
                    damage=weapon["damage"],
                )
            )
            return

        center_x = player.x + PLAYER_SIZE / 2 + player.facing_x * ATTACK_RANGE / 2
        center_y = player.y + PLAYER_SIZE / 2 + player.facing_y * ATTACK_RANGE / 2
        hit_any = False
        for monster in self.monsters:
            if not monster.alive:
                continue
            rect = (monster.x, monster.y, MONSTER_SIZE, MONSTER_SIZE)
            if circle_rect_collision(center_x, center_y, ATTACK_RANGE, rect):
                monster.hp -= weapon["damage"]
                hit_any = True
                if monster.hp <= 0:
                    monster.alive = False
                    self._drop_coins(monster.x, monster.y, 5 + self.round_number * 2)
                    self._drop_resources(monster.x, monster.y, self._monster_resource_drop(monster.kind))
                    player.score += 10
        if not hit_any:
            self.status_message = f"{player.name} swings {weapon['name']}, but nothing is in range."

    def _open_chest(self, player: PlayerState) -> None:
        if player.interact_cooldown > 0:
            return
        player.interact_cooldown = 0.25
        for chest in self.chests:
            if chest["opened"]:
                continue
            rect = (chest["x"], chest["y"], CHEST_SIZE, CHEST_SIZE)
            if circle_rect_collision(player.x + PLAYER_SIZE / 2, player.y + PLAYER_SIZE / 2, ATTACK_RANGE, rect):
                chest["opened"] = True
                self._apply_loot(player, chest["x"], chest["y"])
                return

    def _apply_loot(self, player: PlayerState, source_x: float, source_y: float) -> None:
        gold = self.rng.randint(5, 12 + self.round_number * 2)
        self._drop_coins(source_x, source_y, gold)
        self._drop_resources(source_x, source_y, self._random_resource_bundle())

        if self.rng.random() < 0.34:
            arrows_found = self._roll_arrow_bundle()
            player.arrows += arrows_found
            self.status_message = f"{player.name} found {arrows_found} arrows."
            self._ensure_inventory_layout(player)
            return

        roll = self.rng.random()
        if roll < 0.22:
            max_tier = min(5, 1 + self.round_number // 2)
            weapon_choices = [
                weapon_id
                for weapon_id, info in WEAPON_DEFS.items()
                if 0 < info["tier"] <= max_tier
            ]
            weapon_id = self.rng.choice(weapon_choices or list(WEAPON_DEFS.keys())[1:])
            if weapon_id not in player.weapons:
                player.weapons.append(weapon_id)
                self.status_message = f"{player.name} found {WEAPON_DEFS[weapon_id]['name']}."
            else:
                player.gold += 8
            self._ensure_inventory_layout(player)
        elif roll < 0.38:
            player.potions += 1
            self.status_message = f"{player.name} found a potion."
            self._ensure_inventory_layout(player)
        elif roll < 0.5:
            armor_id = self.rng.choice(list(ARMOR_DEFS.keys()))
            if armor_id not in player.armors:
                player.armors.append(armor_id)
                bonus = ARMOR_DEFS[armor_id]["bonus_hp"]
                player.max_hp += bonus
                player.hp += bonus
                self.status_message = f"{player.name} found {ARMOR_DEFS[armor_id]['name']}."
            else:
                player.gold += 6
            self._ensure_inventory_layout(player)
        elif roll < 0.68:
            found_bandages = self.rng.randint(1, 3)
            player.bandages += found_bandages
            self.status_message = f"{player.name} found {found_bandages} bandages."
            self._ensure_inventory_layout(player)
        else:
            self.status_message = f"{player.name} opened a chest."

    def _buy_shop_item(self, player: PlayerState) -> None:
        if player.interact_cooldown > 0:
            return
        player.interact_cooldown = 0.25
        for item in self.shop_items:
            if item["sold"]:
                continue
            rect = (item["x"], item["y"], SHOP_ITEM_SIZE, SHOP_ITEM_SIZE)
            if not circle_rect_collision(player.x + PLAYER_SIZE / 2, player.y + PLAYER_SIZE / 2, ATTACK_RANGE, rect):
                continue
            if player.gold < item["price"]:
                self.status_message = f"{player.name} needs more gold for {item['name']}."
                return
            player.gold -= item["price"]
            item["sold"] = True
            if item["kind"] == "weapon":
                if item["item_id"] not in player.weapons:
                    player.weapons.append(item["item_id"])
            elif item["kind"] == "armor":
                if item["item_id"] not in player.armors:
                    player.armors.append(item["item_id"])
                    bonus = ARMOR_DEFS[item["item_id"]]["bonus_hp"]
                    player.max_hp += bonus
                    player.hp += bonus
            elif item["kind"] == "ammo":
                player.arrows += item["amount"]
            elif item["kind"] == "bandage":
                player.bandages += item["amount"]
            else:
                player.potions += item["amount"]
            self.status_message = f"{player.name} bought {item['name']}."
            self._ensure_inventory_layout(player)
            return

    def _craft_recipe(self, player: PlayerState, recipe_id: str) -> None:
        if player.craft_cooldown > 0:
            return
        recipe = CRAFTING_RECIPES.get(recipe_id)
        if recipe is None:
            return
        if any(player.resources.get(resource_id, 0) < amount for resource_id, amount in recipe["cost"].items()):
            self.status_message = f"{player.name} does not have enough materials."
            return

        for resource_id, amount in recipe["cost"].items():
            player.resources[resource_id] -= amount

        player.craft_cooldown = 0.35
        if recipe["kind"] == "weapon":
            item_id = recipe["item_id"]
            if item_id not in player.weapons:
                player.weapons.append(item_id)
            self.status_message = f"{player.name} crafted {WEAPON_DEFS[item_id]['name']}."
        elif recipe["kind"] == "armor":
            item_id = recipe["item_id"]
            if item_id not in player.armors:
                player.armors.append(item_id)
                bonus = ARMOR_DEFS[item_id]["bonus_hp"]
                player.max_hp += bonus
                player.hp += bonus
            self.status_message = f"{player.name} crafted {ARMOR_DEFS[item_id]['name']}."
        elif recipe["kind"] == "bandage":
            player.bandages += recipe["amount"]
            self.status_message = f"{player.name} crafted bandages."
        else:
            player.potions += recipe["amount"]
            self.status_message = f"{player.name} brewed potions."
        self._ensure_inventory_layout(player)

    def _gamble_at_shop(self, player: PlayerState) -> None:
        if player.interact_cooldown > 0:
            return
        player.interact_cooldown = 0.25
        if not self.gamble_spots:
            self.status_message = "No gambling table is set up in this shop."
            return

        player_center_x = player.x + PLAYER_SIZE / 2
        player_center_y = player.y + PLAYER_SIZE / 2
        near_table = any(
            circle_rect_collision(player_center_x, player_center_y, ATTACK_RANGE, (spot_x, spot_y, SHOP_ITEM_SIZE, SHOP_ITEM_SIZE))
            for spot_x, spot_y in self.gamble_spots
        )
        if not near_table:
            self.status_message = f"{player.name} needs to stand by the gambling table."
            return

        if player.gold <= 0:
            self.status_message = f"{player.name} has no gold to gamble."
            return

        bet = max(1, min(player.gamble_bet, player.gold))
        player.gamble_bet = bet
        if self.rng.random() < 0.45:
            winnings = bet
            player.gold += winnings
            self.status_message = f"{player.name} won ${winnings} at the gambling table."
        else:
            player.gold -= bet
            player.gamble_bet = max(1, min(player.gamble_bet, max(1, player.gold)))
            self.status_message = f"{player.name} lost ${bet} at the gambling table."

    def _drop_coins(self, x: float, y: float, amount: int) -> None:
        chunks = max(1, min(6, amount // 4 + 1))
        for _ in range(chunks):
            value = max(1, amount // chunks)
            self.coins.append(
                {
                    "id": self.next_coin_id,
                    "x": x + self.rng.randint(-10, 10),
                    "y": y + self.rng.randint(-10, 10),
                    "value": value,
                }
            )
            self.next_coin_id += 1

    def _drop_resources(self, x: float, y: float, drops: dict[str, int]) -> None:
        for resource_id, amount in drops.items():
            for _ in range(amount):
                self.coins.append(
                    {
                        "id": self.next_coin_id,
                        "x": x + self.rng.randint(-14, 14),
                        "y": y + self.rng.randint(-14, 14),
                        "value": 0,
                        "resource_id": resource_id,
                    }
                )
                self.next_coin_id += 1

    def _random_resource_bundle(self) -> dict[str, int]:
        return {
            "wood": self.rng.randint(0, 2),
            "iron": self.rng.randint(0, 2),
            "crystal": self.rng.randint(0, 1),
        }

    def _monster_resource_drop(self, monster_kind: str) -> dict[str, int]:
        if monster_kind == "brute":
            return {"wood": 1, "iron": 2}
        if monster_kind == "shade":
            return {"crystal": 2}
        return {"wood": 1, "iron": 1}

    def _cycle_difficulty(self, step: int) -> None:
        difficulty_ids = list(DIFFICULTY_DEFS.keys())
        index = difficulty_ids.index(self.difficulty_id)
        self.difficulty_id = difficulty_ids[(index + step) % len(difficulty_ids)]
        self.status_message = f"Lobby difficulty set to {DIFFICULTY_DEFS[self.difficulty_id]['name']}."

    def _roll_arrow_bundle(self) -> int:
        roll = self.rng.random()
        if roll < 0.7:
            return 10
        if roll < 0.9:
            return 50
        return 100

    def _inventory_tokens(self, player: PlayerState) -> list[str]:
        tokens = [f"weapon:{weapon_id}" for weapon_id in player.weapons]
        tokens.extend(f"armor:{armor_id}" for armor_id in player.armors)
        if player.potions > 0:
            tokens.append("stack:potion")
        if player.bandages > 0:
            tokens.append("stack:bandage")
        if player.arrows > 0:
            tokens.append("stack:arrow")
        for resource_id, amount in player.resources.items():
            if amount > 0:
                tokens.append(f"resource:{resource_id}")
        return tokens

    def _ensure_inventory_layout(self, player: PlayerState) -> None:
        remaining = self._inventory_tokens(player)
        layout: list[str | None] = []
        for token in player.inventory_layout[:INVENTORY_SLOT_COUNT]:
            if token in remaining:
                layout.append(token)
                remaining.remove(token)
            else:
                layout.append(None)
        while len(layout) < INVENTORY_SLOT_COUNT:
            layout.append(remaining.pop(0) if remaining else None)
        player.inventory_layout = layout[:INVENTORY_SLOT_COUNT]

    def _inventory_slot_payload(self, player: PlayerState, slot_index: int, token: str | None) -> dict:
        payload = {
            "slot": slot_index,
            "token": token,
            "empty": token is None,
            "label": "",
            "detail": "",
            "count": 0,
            "item_type": "empty",
            "usable": False,
            "equipped": False,
        }
        if token is None:
            return payload

        kind, item_id = token.split(":", 1)
        if kind == "weapon":
            info = WEAPON_DEFS[item_id]
            payload.update(
                {
                    "label": info["name"],
                    "detail": f"{info['damage']} dmg",
                    "item_type": "weapon",
                    "usable": True,
                    "equipped": item_id == player.weapon_id,
                }
            )
        elif kind == "armor":
            info = ARMOR_DEFS[item_id]
            payload.update(
                {
                    "label": info["name"],
                    "detail": f"+{info['bonus_hp']} hp",
                    "item_type": "armor",
                }
            )
        elif kind == "stack":
            if item_id == "potion":
                payload.update(
                    {
                        "label": "Potion",
                        "detail": "heal 35",
                        "count": player.potions,
                        "item_type": "consumable",
                        "usable": player.potions > 0,
                    }
                )
            elif item_id == "bandage":
                payload.update(
                    {
                        "label": "Bandage",
                        "detail": "heal 30%",
                        "count": player.bandages,
                        "item_type": "consumable",
                        "usable": player.bandages > 0,
                    }
                )
            elif item_id == "arrow":
                payload.update(
                    {
                        "label": "Arrows",
                        "detail": "bow ammo",
                        "count": player.arrows,
                        "item_type": "ammo",
                    }
                )
        elif kind == "resource":
            payload.update(
                {
                    "label": RESOURCE_DEFS[item_id]["name"],
                    "detail": "crafting",
                    "count": player.resources.get(item_id, 0),
                    "item_type": "resource",
                }
            )
        return payload

    def _move_inventory_slot(self, player: PlayerState, from_index: int, to_index: int) -> None:
        self._ensure_inventory_layout(player)
        if not (0 <= from_index < INVENTORY_SLOT_COUNT and 0 <= to_index < INVENTORY_SLOT_COUNT):
            return
        player.inventory_layout[from_index], player.inventory_layout[to_index] = (
            player.inventory_layout[to_index],
            player.inventory_layout[from_index],
        )

    def _use_potion(self, player: PlayerState) -> None:
        if player.potions <= 0:
            self.status_message = f"{player.name} has no potions."
            return
        if player.hp >= player.max_hp:
            self.status_message = f"{player.name} is already at full health."
            return
        player.potions -= 1
        player.hp = min(player.max_hp, player.hp + 35)
        self.status_message = f"{player.name} uses a potion."
        self._ensure_inventory_layout(player)

    def _use_bandage(self, player: PlayerState) -> None:
        if player.bandages <= 0:
            self.status_message = f"{player.name} has no bandages."
            return
        if player.hp >= player.max_hp:
            self.status_message = f"{player.name} is already at full health."
            return
        player.bandages -= 1
        heal_amount = max(1, int(round(player.max_hp * 0.3)))
        player.hp = min(player.max_hp, player.hp + heal_amount)
        self.status_message = f"{player.name} wraps a bandage."
        self._ensure_inventory_layout(player)

    def _use_inventory_slot(self, player: PlayerState, slot_index: int) -> None:
        self._ensure_inventory_layout(player)
        if not (0 <= slot_index < INVENTORY_SLOT_COUNT):
            return
        token = player.inventory_layout[slot_index]
        if token is None:
            return
        kind, item_id = token.split(":", 1)
        if kind == "weapon":
            if item_id in player.weapons:
                player.equipped_index = player.weapons.index(item_id)
                self.status_message = f"{player.name} equips {WEAPON_DEFS[item_id]['name']}."
            return
        if kind == "stack" and item_id == "potion":
            self._use_potion(player)
            return
        if kind == "stack" and item_id == "bandage":
            self._use_bandage(player)
            return
        if kind == "armor":
            self.status_message = f"{ARMOR_DEFS[item_id]['name']} is already equipped."
            return
        if kind == "stack" and item_id == "arrow":
            self.status_message = "Arrows are used automatically by bows."
            return
        if kind == "resource":
            self.status_message = f"{RESOURCE_DEFS[item_id]['name']} is used for crafting."

    def _safe_save_filename(self, filename: str | None) -> str | None:
        if filename is None:
            return None
        name = str(filename).strip()
        if not name:
            return None
        if "/" in name or "\\" in name:
            return None
        if len(name) > 64:
            return None
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- ")
        if any(ch not in allowed for ch in name):
            return None
        if not name.lower().endswith(".json"):
            name += ".json"
        return name

    def _list_save_files(self) -> list[str]:
        root = self.save_path.parent
        candidates: list[str] = []
        for path in root.glob("*.json"):
            if path.name.lower().startswith("save") and path.is_file():
                candidates.append(path.name)
        # Always include the default filename so the user can save even if it doesn't exist yet.
        if "savegame.json" not in {name.lower() for name in candidates}:
            candidates.append("savegame.json")
        # Prefer savegame.json first, then alphabetical.
        normalized = sorted({name for name in candidates}, key=lambda s: (s.lower() != "savegame.json", s.lower()))
        return normalized

    def _save_game(self, player: PlayerState, filename: str | None = None) -> None:
        safe_name = self._safe_save_filename(filename)
        if filename is not None and safe_name is None:
            self.status_message = "Invalid save filename."
            return
        save_path = self.save_path if safe_name is None else (self.save_path.parent / safe_name)
        save_data = {
            "difficulty_id": self.difficulty_id,
            "phase": self.phase,
            "round_number": self.round_number,
            "escapes_completed": self.escapes_completed,
            "status_message": self.paused_status_message or self.status_message,
            "map": self.active_map,
            "chests": self.chests,
            "coins": self.coins,
            "shop_items": self.shop_items,
            "goal_tiles": self.goal_tiles,
            "gamble_spots": self.gamble_spots,
            "next_coin_id": self.next_coin_id,
            "player": {
                "name": player.name,
                "x": player.x,
                "y": player.y,
                "color_index": player.color_index,
                "accessory_id": player.accessory_id,
                "hp": player.hp,
                "max_hp": player.max_hp,
                "gold": player.gold,
                "potions": player.potions,
                "bandages": player.bandages,
                "arrows": player.arrows,
                "armors": player.armors,
                "weapons": player.weapons,
                "inventory_layout": player.inventory_layout,
                "equipped_index": player.equipped_index,
                "resources": player.resources,
                "score": player.score,
                "facing_x": player.facing_x,
                "facing_y": player.facing_y,
                "attack_style": player.attack_style,
                "attack_weapon_id": player.attack_weapon_id,
                "gamble_bet": player.gamble_bet,
            },
            "monsters": [
                {
                    "monster_id": monster.monster_id,
                    "kind": monster.kind,
                    "x": monster.x,
                    "y": monster.y,
                    "hp": monster.hp,
                    "max_hp": monster.max_hp,
                    "damage": monster.damage,
                    "speed": monster.speed,
                    "attack_delay": monster.attack_delay,
                    "aggro_range": monster.aggro_range,
                    "alive": monster.alive,
                    "attack_cooldown": monster.attack_cooldown,
                    "roam_target": monster.roam_target,
                    "roam_timer": monster.roam_timer,
                    "path_tiles": monster.path_tiles,
                    "path_goal": monster.path_goal,
                    "path_refresh": monster.path_refresh,
                    "attack_style": monster.attack_style,
                }
                for monster in self.monsters
            ],
            "projectiles": [
                {
                    "owner_id": projectile.owner_id,
                    "x": projectile.x,
                    "y": projectile.y,
                    "dx": projectile.dx,
                    "dy": projectile.dy,
                    "speed": projectile.speed,
                    "damage": projectile.damage,
                    "from_monster": projectile.from_monster,
                    "ttl": projectile.ttl,
                }
                for projectile in self.projectiles
            ],
        }
        save_path.write_text(json.dumps(save_data, indent=2), encoding="utf-8")
        self.status_message = f"Game saved to {save_path.name}."

    def _load_game(self, player: PlayerState, filename: str | None = None) -> None:
        safe_name = self._safe_save_filename(filename)
        if filename is not None and safe_name is None:
            self.status_message = "Invalid save filename."
            return
        load_path = self.save_path if safe_name is None else (self.save_path.parent / safe_name)
        if not load_path.exists():
            self.status_message = f"No save file found ({load_path.name})."
            return

        try:
            save_data = json.loads(load_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.status_message = f"Could not read {load_path.name}."
            return

        phase = str(save_data.get("phase", "round"))
        if phase not in {"lobby", "round", "shop"}:
            phase = "round"

        goal_tile = "L" if phase == "lobby" else ("P" if phase == "shop" else "E")
        map_lines = save_data.get("map")
        if not isinstance(map_lines, list) or not map_lines or not all(isinstance(row, str) for row in map_lines):
            self.status_message = f"{load_path.name} is missing a valid map."
            return

        self.difficulty_id = str(save_data.get("difficulty_id", self.difficulty_id))
        if self.difficulty_id not in DIFFICULTY_DEFS:
            self.difficulty_id = "normal"

        self.phase = phase
        try:
            self.round_number = int(save_data.get("round_number", 0))
        except (TypeError, ValueError):
            self.round_number = 0
        try:
            self.escapes_completed = int(save_data.get("escapes_completed", 0))
        except (TypeError, ValueError):
            self.escapes_completed = 0

        self._set_map(map_lines, goal_tile=goal_tile)
        self.chests = list(save_data.get("chests", [])) if isinstance(save_data.get("chests"), list) else []
        self.coins = list(save_data.get("coins", [])) if isinstance(save_data.get("coins"), list) else []
        self.shop_items = list(save_data.get("shop_items", [])) if isinstance(save_data.get("shop_items"), list) else []

        goal_tiles = save_data.get("goal_tiles")
        if isinstance(goal_tiles, list):
            converted: list[tuple[float, float]] = []
            for entry in goal_tiles:
                if isinstance(entry, (list, tuple)) and len(entry) == 2:
                    try:
                        converted.append((float(entry[0]), float(entry[1])))
                    except (TypeError, ValueError):
                        continue
            if converted:
                self.goal_tiles = converted

        gamble_spots = save_data.get("gamble_spots")
        if isinstance(gamble_spots, list):
            converted: list[tuple[float, float]] = []
            for entry in gamble_spots:
                if isinstance(entry, (list, tuple)) and len(entry) == 2:
                    try:
                        converted.append((float(entry[0]), float(entry[1])))
                    except (TypeError, ValueError):
                        continue
            if converted:
                self.gamble_spots = converted

        try:
            self.next_coin_id = int(save_data.get("next_coin_id", self.next_coin_id))
        except (TypeError, ValueError):
            pass

        self.monsters = []
        monsters = save_data.get("monsters")
        if isinstance(monsters, list):
            for entry in monsters:
                if not isinstance(entry, dict):
                    continue
                try:
                    monster_id = int(entry.get("monster_id", 0))
                    kind = str(entry.get("kind", "fang"))
                    x = float(entry.get("x", 0.0))
                    y = float(entry.get("y", 0.0))
                    hp = int(entry.get("hp", 1))
                    max_hp = int(entry.get("max_hp", hp))
                    damage = int(entry.get("damage", 1))
                    speed = float(entry.get("speed", MONSTER_ARCHETYPES.get(kind, {}).get("speed", 90)))
                    attack_delay = float(entry.get("attack_delay", 1.0))
                    aggro_range = float(entry.get("aggro_range", 220))
                    alive = bool(entry.get("alive", True))
                except (TypeError, ValueError):
                    continue

                monster = MonsterState(
                    monster_id=monster_id,
                    kind=kind,
                    x=x,
                    y=y,
                    hp=hp,
                    max_hp=max_hp,
                    damage=damage,
                    speed=speed,
                    attack_delay=attack_delay,
                    aggro_range=aggro_range,
                    alive=alive,
                )
                monster.attack_cooldown = float(entry.get("attack_cooldown", 0.0) or 0.0)
                roam_target = entry.get("roam_target")
                if isinstance(roam_target, (list, tuple)) and len(roam_target) == 2:
                    try:
                        monster.roam_target = (float(roam_target[0]), float(roam_target[1]))
                    except (TypeError, ValueError):
                        monster.roam_target = None
                monster.roam_timer = float(entry.get("roam_timer", 0.0) or 0.0)
                monster.path_tiles = []
                path_tiles = entry.get("path_tiles")
                if isinstance(path_tiles, list):
                    for tile in path_tiles:
                        if isinstance(tile, (list, tuple)) and len(tile) == 2:
                            try:
                                monster.path_tiles.append((int(tile[0]), int(tile[1])))
                            except (TypeError, ValueError):
                                continue
                path_goal = entry.get("path_goal")
                if isinstance(path_goal, (list, tuple)) and len(path_goal) == 2:
                    try:
                        monster.path_goal = (int(path_goal[0]), int(path_goal[1]))
                    except (TypeError, ValueError):
                        monster.path_goal = None
                monster.path_refresh = float(entry.get("path_refresh", 0.0) or 0.0)
                monster.attack_style = str(entry.get("attack_style", "melee"))
                self.monsters.append(monster)

        self.projectiles = []
        projectiles = save_data.get("projectiles")
        if isinstance(projectiles, list):
            for entry in projectiles:
                if not isinstance(entry, dict):
                    continue
                try:
                    owner_id = entry.get("owner_id")
                    if owner_id is not None:
                        owner_id = int(owner_id)
                    projectile = ProjectileState(
                        owner_id=owner_id,
                        x=float(entry.get("x", 0.0)),
                        y=float(entry.get("y", 0.0)),
                        dx=float(entry.get("dx", 0.0)),
                        dy=float(entry.get("dy", 0.0)),
                        speed=float(entry.get("speed", PROJECTILE_SPEED)),
                        damage=int(entry.get("damage", 1)),
                        from_monster=bool(entry.get("from_monster", False)),
                        ttl=float(entry.get("ttl", 1.0)),
                    )
                except (TypeError, ValueError):
                    continue
                self.projectiles.append(projectile)

        player_data = save_data.get("player")
        if isinstance(player_data, dict):
            player.x = float(player_data.get("x", player.x))
            player.y = float(player_data.get("y", player.y))
            try:
                player.color_index = int(player_data.get("color_index", player.color_index)) % len(PLAYER_COLORS)
            except (TypeError, ValueError):
                pass
            accessory_id = str(player_data.get("accessory_id", player.accessory_id))
            player.accessory_id = accessory_id if accessory_id in ACCESSORY_DEFS else "none"
            player.hp = int(player_data.get("hp", player.hp))
            player.max_hp = int(player_data.get("max_hp", player.max_hp))
            player.gold = int(player_data.get("gold", player.gold))
            player.potions = int(player_data.get("potions", player.potions))
            player.bandages = int(player_data.get("bandages", player.bandages))
            player.arrows = int(player_data.get("arrows", player.arrows))
            player.armors = list(player_data.get("armors", player.armors)) if isinstance(player_data.get("armors"), list) else player.armors
            player.weapons = list(player_data.get("weapons", player.weapons)) if isinstance(player_data.get("weapons"), list) else player.weapons
            player.inventory_layout = (
                list(player_data.get("inventory_layout", player.inventory_layout))
                if isinstance(player_data.get("inventory_layout"), list)
                else player.inventory_layout
            )
            try:
                player.equipped_index = int(player_data.get("equipped_index", player.equipped_index))
            except (TypeError, ValueError):
                pass
            resources = player_data.get("resources")
            if isinstance(resources, dict):
                for resource_id in RESOURCE_DEFS:
                    try:
                        player.resources[resource_id] = int(resources.get(resource_id, 0))
                    except (TypeError, ValueError):
                        player.resources[resource_id] = 0
            try:
                player.score = int(player_data.get("score", player.score))
            except (TypeError, ValueError):
                pass
            player.facing_x = float(player_data.get("facing_x", player.facing_x))
            player.facing_y = float(player_data.get("facing_y", player.facing_y))
            player.attack_style = str(player_data.get("attack_style", player.attack_style))
            player.attack_weapon_id = str(player_data.get("attack_weapon_id", player.weapon_id))
            try:
                player.gamble_bet = int(player_data.get("gamble_bet", player.gamble_bet))
            except (TypeError, ValueError):
                pass

        if not player.weapons:
            player.weapons = ["rusty_sword"]
        player.equipped_index = max(0, min(player.equipped_index, len(player.weapons) - 1))
        if player.attack_weapon_id not in WEAPON_DEFS:
            player.attack_weapon_id = player.weapon_id
        self._ensure_inventory_layout(player)

        loaded_status = str(save_data.get("status_message", "Game loaded."))
        self.paused_status_message = loaded_status
        self.status_message = f"Loaded {load_path.name}. Press Esc to resume."
        self.paused = True
        self.paused_at = time.time()
        self.round_ends_at = None

    def _collect_coins(self, player: PlayerState) -> None:
        remaining = []
        center_x = player.x + PLAYER_SIZE / 2
        center_y = player.y + PLAYER_SIZE / 2
        for coin in self.coins:
            rect = (coin["x"], coin["y"], 14, 14)
            if circle_rect_collision(center_x, center_y, ATTACK_RANGE / 1.7, rect):
                resource_id = coin.get("resource_id")
                if resource_id:
                    player.resources[resource_id] += 1
                else:
                    player.gold += coin["value"]
            else:
                remaining.append(coin)
        self.coins = remaining

    def _check_round_progress(self) -> None:
        if any(not chest["opened"] for chest in self.chests):
            unopened = sum(1 for chest in self.chests if not chest["opened"])
            self.status_message = f"Open the remaining chests: {unopened} left."
            return

        players = self._connected_players()
        if not players:
            return
        count = sum(1 for player in players if self._player_in_goal(player))
        if count < len(players):
            self.status_message = f"All loot cleared. Gather the whole party at the exit: {count}/{len(players)} ready."
            return

        self.escapes_completed += 1
        for player in players:
            player.score += 20
            player.gold += 8
        if self.escapes_completed % SHOP_AFTER_ESCAPES == 0:
            self._start_shop()
        else:
            self._start_round(self.round_number + 1)

    def _check_shop_progress(self) -> None:
        players = self._connected_players()
        if not players:
            return
        count = sum(1 for player in players if self._player_in_goal(player))
        if count < len(players):
            self.status_message = f"Shop is open. Buy items and gather in the portal area: {count}/{len(players)} ready to leave."
            return
        self._start_round(self.round_number + 1)

    def _player_in_goal(self, player: PlayerState) -> bool:
        center_x = player.x + PLAYER_SIZE / 2
        center_y = player.y + PLAYER_SIZE / 2
        return any(
            math.hypot(center_x - goal_x, center_y - goal_y) <= TILE_SIZE / 1.7
            for goal_x, goal_y in self.goal_tiles
        )

    def _start_round(self, round_number: int) -> None:
        self.phase = "round"
        self.paused = False
        self.paused_at = None
        self.paused_status_message = None
        self.no_players_since = None
        self.round_number = round_number
        self._set_map(self._generate_dungeon_map(), goal_tile="E")
        self.round_ends_at = None
        self.chests = self._spawn_chests()
        self.coins = []
        self.projectiles = []
        self.monsters = self._spawn_monsters()
        self.shop_items = []
        self.status_message = f"Round {self.round_number} started. Open every chest, then get the whole party to the exit."
        for player in self._connected_players():
            self._spawn_player(player)
            player.hp = player.max_hp
            player.ready = False

    def _start_shop(self) -> None:
        self.phase = "shop"
        self.paused = False
        self.paused_at = None
        self.paused_status_message = None
        self.no_players_since = None
        shop_map = self.rng.choice(SHOP_MAPS)
        self._set_map(shop_map, goal_tile="P")
        self.round_ends_at = None
        self.chests = []
        self.coins = []
        self.projectiles = []
        self.monsters = []
        self.shop_items = self._spawn_shop_items(shop_map)
        self.status_message = "Shop round. Buy gear with F and gather everyone in the portal zone when you are done."
        for player in self._connected_players():
            self._spawn_player(player)
            player.hp = player.max_hp
            player.gamble_bet = max(1, min(player.gamble_bet, max(1, player.gold)))

    def _go_to_lobby(self, message: str) -> None:
        self.phase = "lobby"
        self.paused = False
        self.paused_at = None
        self.paused_status_message = None
        self.no_players_since = None
        self.round_ends_at = None
        self.shop_items = []
        self.chests = []
        self.coins = []
        self.projectiles = []
        self.monsters = []
        self._set_map([row[:] for row in LOBBY_MAP], goal_tile="L")
        self.status_message = message
        for player in self._connected_players():
            self._spawn_player(player)
            player.ready = False

    def _spawn_chests(self) -> list[dict]:
        chests = []
        for index, (col, row) in enumerate(find_tiles(self.active_map, "C"), start=1):
            x, y = tile_to_position(col, row, inset=13)
            chests.append({"id": index, "x": x, "y": y, "opened": False})
        return chests

    def _spawn_monsters(self) -> list[MonsterState]:
        monsters = []
        difficulty = DIFFICULTY_DEFS[self.difficulty_id]
        for index, (col, row) in enumerate(find_tiles(self.active_map, "M"), start=1):
            x, y = tile_to_position(col, row, inset=11)
            kind = self.rng.choice(list(MONSTER_ARCHETYPES.keys()))
            archetype = MONSTER_ARCHETYPES[kind]
            round_scale = max(0, self.round_number - 1)
            hp = int(round((archetype["base_hp"] + round_scale * archetype["hp_per_round"]) * difficulty["monster_hp_scale"]))
            damage = int(round((archetype["base_damage"] + round_scale * archetype["damage_per_round"]) * difficulty["monster_damage_scale"]))
            monsters.append(
                MonsterState(
                    monster_id=index,
                    kind=kind,
                    x=x,
                    y=y,
                    hp=hp,
                    max_hp=hp,
                    damage=damage,
                    speed=archetype["speed"],
                    attack_delay=archetype["attack_cooldown"],
                    aggro_range=archetype["aggro_range"],
                    attack_style=archetype.get("attack_style", "melee"),
                )
            )
        return monsters

    def _spawn_shop_items(self, shop_map: list[str]) -> list[dict]:
        items: list[dict] = []
        pads = find_tiles(shop_map, "B")
        self.rng.shuffle(pads)
        for slot, (col, row) in enumerate(pads[: len(SHOP_SLOTS)]):
            choice_roll = self.rng.random()
            if choice_roll < 0.58:
                amount = self._roll_arrow_bundle()
                price = max(8, amount // 2)
                item = {"kind": "ammo", "item_id": "arrow_bundle", "name": f"Arrows x{amount}", "price": price, "amount": amount}
            elif choice_roll < 0.78:
                max_tier = min(5, 1 + self.round_number // 2)
                weapon_choices = [
                    weapon_id
                    for weapon_id, info in WEAPON_DEFS.items()
                    if 0 < info["tier"] <= max_tier
                ]
                item_id = self.rng.choice(weapon_choices or list(WEAPON_DEFS.keys())[1:])
                info = WEAPON_DEFS[item_id]
                item = {"kind": "weapon", "item_id": item_id, "name": info["name"], "price": info["price"], "amount": 0}
            elif choice_roll < 0.92:
                item_id = self.rng.choice(list(ARMOR_DEFS.keys()))
                info = ARMOR_DEFS[item_id]
                item = {"kind": "armor", "item_id": item_id, "name": info["name"], "price": info["price"], "amount": 0}
            elif choice_roll < 0.96:
                amount = self.rng.randint(2, 4)
                item = {"kind": "bandage", "item_id": "bandage_bundle", "name": f"Bandage x{amount}", "price": 5 + amount * 2, "amount": amount}
            else:
                amount = self.rng.randint(1, 2)
                item = {"kind": "potion", "item_id": "potion_bundle", "name": f"Potion x{amount}", "price": 6 + 4 * amount, "amount": amount}
            x, y = tile_to_position(col, row, inset=10)
            item.update({"slot": slot, "x": x, "y": y, "sold": False})
            items.append(item)
        return items

    def _snapshot(self, player_id: int) -> dict:
        player = self.players.get(player_id)
        you = None
        if player is not None:
            self._ensure_inventory_layout(player)
            you = {
                "hp": player.hp,
                "max_hp": player.max_hp,
                "gold": player.gold,
                "potions": player.potions,
                "bandages": player.bandages,
                "arrows": player.arrows,
                "ready": player.ready,
                "weapon_id": player.weapon_id,
                "weapon_name": WEAPON_DEFS[player.weapon_id]["name"],
                "inventory": [WEAPON_DEFS[weapon_id]["name"] for weapon_id in player.weapons],
                "inventory_slots": [
                    self._inventory_slot_payload(player, slot_index, token)
                    for slot_index, token in enumerate(player.inventory_layout)
                ],
                "armors": [ARMOR_DEFS[armor_id]["name"] for armor_id in player.armors],
                "resources": player.resources,
                "recipes": [
                    {
                        "id": recipe_id,
                        "name": recipe["name"],
                        "description": recipe["description"],
                        "cost": recipe["cost"],
                    }
                    for recipe_id, recipe in CRAFTING_RECIPES.items()
                ],
                "equipped_index": player.equipped_index,
                "color_index": player.color_index,
                "accessory_id": player.accessory_id,
                "attack_weapon_id": player.attack_weapon_id,
                "attack_cooldown": round(player.attack_cooldown, 2),
                "gamble_bet": player.gamble_bet,
            }

        time_left = None
        if self.round_ends_at is not None:
            time_left = max(0, int(self.round_ends_at - time.time()))

        available_saves: list[str] = []
        if self.paused and len(self._connected_players()) == 1:
            available_saves = self._list_save_files()

        return {
            "type": "state",
            "phase": self.phase,
            "paused": self.paused,
            "available_saves": available_saves,
            "difficulty_id": self.difficulty_id,
            "round_number": self.round_number,
            "escapes_completed": self.escapes_completed,
            "status_message": self.status_message,
            "map": self.active_map,
            "world_width": self.width,
            "world_height": self.height,
            "time_left": time_left,
            "players": [
                {
                    "id": other.player_id,
                    "name": other.name,
                    "x": round(other.x, 2),
                    "y": round(other.y, 2),
                    "hp": other.hp,
                    "max_hp": other.max_hp,
                    "gold": other.gold,
                    "score": other.score,
                    "ready": other.ready,
                    "color": other.color,
                    "accessory_id": other.accessory_id,
                    "weapon_id": other.weapon_id,
                    "weapon_name": WEAPON_DEFS[other.weapon_id]["name"],
                    "attack_animation": round(other.attack_animation, 2),
                    "attack_style": other.attack_style,
                    "attack_weapon_id": other.attack_weapon_id,
                    "facing": [round(other.facing_x, 2), round(other.facing_y, 2)],
                }
                for other in self._connected_players()
            ],
            "coins": self.coins,
            "projectiles": [{"x": round(projectile.x, 2), "y": round(projectile.y, 2)} for projectile in self.projectiles],
            "monsters": [
                {
                    "id": monster.monster_id,
                    "kind": monster.kind,
                    "x": round(monster.x, 2),
                    "y": round(monster.y, 2),
                    "hp": monster.hp,
                    "max_hp": monster.max_hp,
                    "alive": monster.alive,
                    "damage": monster.damage,
                }
                for monster in self.monsters
            ],
            "chests": self.chests,
            "shop_items": self.shop_items,
            "goal_tiles": [{"x": x, "y": y} for x, y in self.goal_tiles],
            "you": you,
        }

    def _toggle_pause(self) -> None:
        if self.paused:
            paused_for = 0.0
            if self.paused_at is not None:
                paused_for = max(0.0, time.time() - self.paused_at)
            if self.round_ends_at is not None:
                self.round_ends_at += paused_for
            self.paused = False
            self.paused_at = None
            self.status_message = self.paused_status_message or "Game resumed."
            self.paused_status_message = None
            return

        self.paused = True
        self.paused_at = time.time()
        self.paused_status_message = self.status_message
        self.status_message = "Paused. Press Esc to resume."


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the multiplayer dungeon server.")
    parser.add_argument("--host", default="0.0.0.0", help="IP address to bind to.")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help="TCP port to listen on.")
    args = parser.parse_args()
    GameServer(args.host, args.port).start()


if __name__ == "__main__":
    main()
