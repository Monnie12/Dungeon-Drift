from __future__ import annotations

import json
from collections import deque


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 820
HUD_HEIGHT = 170
TILE_SIZE = 48
PLAYER_SIZE = 26
MONSTER_SIZE = 26
CHEST_SIZE = 22
SHOP_ITEM_SIZE = 26
COIN_SIZE = 14
PROJECTILE_SIZE = 10
INVENTORY_COLUMNS = 6
INVENTORY_ROWS = 3
INVENTORY_SLOT_COUNT = INVENTORY_COLUMNS * INVENTORY_ROWS

MOVE_SPEED = 190.0
MONSTER_SPEED = 90.0
ATTACK_RANGE = 42
ATTACK_COOLDOWN = 0.3
ATTACK_ANIMATION_TIME = 0.22
PROJECTILE_SPEED = 360.0
PROJECTILE_TTL = 1.0
MONSTER_PROJECTILE_SPEED = 280.0
SERVER_TICK = 1 / 30
BROADCAST_TICK = 1 / 20
MAX_PLAYERS = 4
SERVER_PORT = 5000
DISCOVERY_PORT = 5001
ROUND_TIME_SECONDS = 60
SHOP_AFTER_ESCAPES = 5

WALL_COLOR = (88, 82, 104)
FLOOR_COLOR = (236, 226, 200)
HUD_COLOR = (42, 45, 56)
ACCENT_COLOR = (213, 151, 78)
TEXT_COLOR = (250, 246, 238)
SUBTLE_TEXT = (233, 224, 208)
CHEST_COLOR = (191, 125, 64)
EXIT_COLOR = (94, 170, 123)
SHOP_COLOR = (94, 126, 196)
GAMBLE_COLOR = (201, 82, 82)
MONSTER_COLOR = (169, 71, 96)
COIN_COLOR = (244, 203, 72)

PLAYER_COLORS = [
    (64, 145, 255),
    (242, 95, 92),
    (52, 191, 115),
    (255, 193, 59),
    (181, 110, 255),
    (255, 125, 196),
    (42, 197, 214),
    (255, 146, 71),
]

ACCESSORY_DEFS = {
    "none": {"name": "None"},
    "cap": {"name": "Cap"},
    "cape": {"name": "Cape"},
    "horns": {"name": "Red Horns"},
    "crown": {"name": "Crown"},
    "wolf_ears": {"name": "Wolf Ears"},
    "fox_ears": {"name": "Fox Ears"},
    "dog_ears": {"name": "Dog Ears"},
}

DIFFICULTY_DEFS = {
    "easy": {"name": "Easy", "monster_hp_scale": 0.8, "monster_damage_scale": 0.75},
    "normal": {"name": "Normal", "monster_hp_scale": 1.0, "monster_damage_scale": 1.0},
    "hard": {"name": "Hard", "monster_hp_scale": 1.3, "monster_damage_scale": 1.35},
}

WEAPON_DEFS = {
    "broken_dagger": {"name": "Broken Dagger", "damage": 7, "price": 4, "tier": 0, "style": "melee"},
    "rusty_sword": {"name": "Rusty Sword", "damage": 11, "price": 0, "tier": 1, "style": "melee"},
    "oak_bow": {"name": "Oak Bow", "damage": 14, "price": 12, "tier": 1, "style": "ranged"},
    "iron_axe": {"name": "Iron Axe", "damage": 20, "price": 18, "tier": 2, "style": "melee"},
    "hunter_bow": {"name": "Hunter Bow", "damage": 23, "price": 24, "tier": 2, "style": "ranged"},
    "crystal_blade": {"name": "Crystal Blade", "damage": 29, "price": 30, "tier": 3, "style": "melee"},
    "storm_spear": {"name": "Storm Spear", "damage": 36, "price": 40, "tier": 4, "style": "melee"},
    "sun_hammer": {"name": "Sun Hammer", "damage": 46, "price": 54, "tier": 5, "style": "melee"},
}

ARMOR_DEFS = {
    "leather_coat": {"name": "Leather Coat", "bonus_hp": 12, "price": 10},
    "iron_mail": {"name": "Iron Mail", "bonus_hp": 20, "price": 18},
    "dragon_guard": {"name": "Dragon Guard", "bonus_hp": 28, "price": 30},
}

RESOURCE_DEFS = {
    "wood": {"name": "Wood Shard", "color": (139, 101, 66)},
    "iron": {"name": "Iron Scrap", "color": (146, 154, 160)},
    "crystal": {"name": "Crystal Dust", "color": (124, 194, 255)},
}

CRAFTING_RECIPES = {
    "recipe_blade": {
        "name": "Crystal Blade",
        "description": "Forge a Crystal Blade",
        "kind": "weapon",
        "item_id": "crystal_blade",
        "cost": {"wood": 2, "iron": 3, "crystal": 2},
    },
    "recipe_spear": {
        "name": "Storm Spear",
        "description": "Forge a Storm Spear",
        "kind": "weapon",
        "item_id": "storm_spear",
        "cost": {"wood": 1, "iron": 4, "crystal": 4},
    },
    "recipe_potions": {
        "name": "Potion Bundle",
        "description": "Brew 2 healing potions",
        "kind": "potion",
        "amount": 2,
        "cost": {"wood": 1, "crystal": 2},
    },
    "recipe_bandages": {
        "name": "Bandage Wrap",
        "description": "Craft 3 bandages",
        "kind": "bandage",
        "amount": 3,
        "cost": {"wood": 2, "iron": 1},
    },
    "recipe_mail": {
        "name": "Iron Mail",
        "description": "Craft Iron Mail armor",
        "kind": "armor",
        "item_id": "iron_mail",
        "cost": {"wood": 1, "iron": 4},
    },
}

MONSTER_ARCHETYPES = {
    "fang": {
        "name": "Fang",
        "speed": 122,
        "base_hp": 16,
        "hp_per_round": 4,
        "base_damage": 4,
        "damage_per_round": 1,
        "attack_cooldown": 0.65,
        "aggro_range": 240,
        "attack_style": "ranged",
    },
    "brute": {
        "name": "Brute",
        "speed": 88,
        "base_hp": 28,
        "hp_per_round": 6,
        "base_damage": 8,
        "damage_per_round": 2,
        "attack_cooldown": 1.05,
        "aggro_range": 210,
        "attack_style": "melee",
    },
    "shade": {
        "name": "Shade",
        "speed": 108,
        "base_hp": 18,
        "hp_per_round": 5,
        "base_damage": 5,
        "damage_per_round": 2,
        "attack_cooldown": 0.8,
        "aggro_range": 300,
        "attack_style": "ranged",
    },
}

SHOP_SLOTS = [
    {"slot": 0, "label": "A"},
    {"slot": 1, "label": "B"},
    {"slot": 2, "label": "C"},
    {"slot": 3, "label": "D"},
    {"slot": 4, "label": "E"},
    {"slot": 5, "label": "F"},
]

PHASE_LABELS = {
    "lobby": "Lobby",
    "round": "Dungeon",
    "shop": "Shop",
}


def _normalize_map(map_lines: list[str]) -> list[str]:
    width = max(len(row) for row in map_lines)
    return [row.ljust(width, "#") for row in map_lines]


LOBBY_MAP = _normalize_map(
    [
        "########################",
        "#..........L..........#",
        "#..S................S.#",
        "#.....................#",
        "#.....................#",
        "#..........R..........#",
        "#.....................#",
        "#..S................S.#",
        "#..........L..........#",
        "########################",
    ]
)

DUNGEON_WIDTH = 31
DUNGEON_HEIGHT = 23

SHOP_MAPS = [
    _normalize_map(
        [
            "########################",
            "#..........P..........#",
            "#..S................S.#",
            "#.....................#",
            "#....B....B....B......#",
            "#..........G..........#",
            "#.....................#",
            "#....B....B....B......#",
            "#..........S..........#",
            "########################",
        ]
    ),
    _normalize_map(
        [
            "########################",
            "#....P.................#",
            "#..S................S..#",
            "#......................#",
            "#..B....B....B....B....#",
            "#...........G..........#",
            "#......................#",
            "#....B....B....B.......#",
            "#..........S...........#",
            "########################",
        ]
    ),
]


def map_dimensions(map_lines: list[str]) -> tuple[int, int]:
    return len(map_lines[0]) * TILE_SIZE, len(map_lines) * TILE_SIZE


def to_json(message: dict) -> bytes:
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


def from_json(line: bytes) -> dict:
    return json.loads(line.decode("utf-8"))


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def circle_rect_collision(cx: float, cy: float, radius: float, rect: tuple[float, float, int, int]) -> bool:
    rx, ry, rw, rh = rect
    nearest_x = clamp(cx, rx, rx + rw)
    nearest_y = clamp(cy, ry, ry + rh)
    dx = cx - nearest_x
    dy = cy - nearest_y
    return dx * dx + dy * dy <= radius * radius


def wall_rects(map_lines: list[str]) -> list[tuple[int, int, int, int]]:
    rects: list[tuple[int, int, int, int]] = []
    for row, line in enumerate(map_lines):
        for col, cell in enumerate(line):
            if cell == "#":
                rects.append((col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE))
    return rects


def find_tiles(map_lines: list[str], tile: str) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    for row, line in enumerate(map_lines):
        for col, cell in enumerate(line):
            if cell == tile:
                matches.append((col, row))
    return matches


def tile_to_position(col: int, row: int, inset: int = 11) -> tuple[float, float]:
    return (col * TILE_SIZE + inset, row * TILE_SIZE + inset)


def connected_floor_regions(map_lines: list[str], walkable: set[str] | None = None) -> set[tuple[int, int]]:
    if walkable is None:
        walkable = {".", "S", "C", "M", "E", "L", "P", "B", "R", "G"}

    start: tuple[int, int] | None = None
    for row, line in enumerate(map_lines):
        for col, cell in enumerate(line):
            if cell in walkable:
                start = (col, row)
                break
        if start is not None:
            break

    if start is None:
        return set()

    seen = {start}
    queue = deque([start])
    while queue:
        col, row = queue.popleft()
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nc = col + dc
            nr = row + dr
            if nr < 0 or nr >= len(map_lines) or nc < 0 or nc >= len(map_lines[0]):
                continue
            if (nc, nr) in seen or map_lines[nr][nc] not in walkable:
                continue
            seen.add((nc, nr))
            queue.append((nc, nr))
    return seen


def find_path(
    map_lines: list[str],
    start: tuple[int, int],
    goal: tuple[int, int],
    walkable: set[str] | None = None,
) -> list[tuple[int, int]]:
    if walkable is None:
        walkable = {".", "S", "C", "M", "E", "L", "P", "B", "R", "G"}

    if start == goal:
        return [start]

    width = len(map_lines[0])
    height = len(map_lines)

    def in_bounds(tile: tuple[int, int]) -> bool:
        col, row = tile
        return 0 <= col < width and 0 <= row < height

    def is_walkable(tile: tuple[int, int]) -> bool:
        col, row = tile
        return map_lines[row][col] in walkable

    if not in_bounds(start) or not in_bounds(goal):
        return []
    if not is_walkable(start) or not is_walkable(goal):
        return []

    queue = deque([start])
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    while queue:
        col, row = queue.popleft()
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (col + dc, row + dr)
            if neighbor in came_from or not in_bounds(neighbor) or not is_walkable(neighbor):
                continue
            came_from[neighbor] = (col, row)
            if neighbor == goal:
                path = [goal]
                current = (col, row)
                while current is not None:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                return path
            queue.append(neighbor)

    return []
