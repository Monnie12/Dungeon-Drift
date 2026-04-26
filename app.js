const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");

const connectPanel = document.getElementById("connectPanel");
const joinButton = document.getElementById("joinButton");
const playPublicButton = document.getElementById("playPublicButton");
const connectStatus = document.getElementById("connectStatus");
const nameInput = document.getElementById("nameInput");
const hostInput = document.getElementById("hostInput");
const portInput = document.getElementById("portInput");
const roomNameInput = document.getElementById("roomNameInput");
const roomCodeInput = document.getElementById("roomCodeInput");
const colorPreview = document.getElementById("colorPreview");
const colorPreviewPlayer = document.getElementById("colorPreviewPlayer");
const colorPreviewName = document.getElementById("colorPreviewName");
const colorSwatches = document.getElementById("colorSwatches");

const phaseValue = document.getElementById("phaseValue");
const roundValue = document.getElementById("roundValue");
const escapesValue = document.getElementById("escapesValue");
const timerValue = document.getElementById("timerValue");
const statusMessage = document.getElementById("statusMessage");
const statsMessage = document.getElementById("statsMessage");
const partyList = document.getElementById("partyList");
const inventoryPanel = document.getElementById("inventoryPanel");
const inventoryContent = document.getElementById("inventoryContent");
const closeInventoryButton = document.getElementById("closeInventoryButton");

const hudHeight = 170;
const tileSize = 48;
const playerSize = 26;
const monsterSize = 26;
const chestSize = 22;
const coinSize = 14;
const projectileSize = 10;
const shopItemSize = 26;
const attackRange = 42;
const attackAnimationTime = 0.22;
const roomCodeAlphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

const colors = {
  wall: "#585268",
  floor: "#ece2c8",
  accent: "#d5974e",
  hud: "#2a2d38",
  text: "#faf6ee",
  subtle: "#e9e0d0",
  exit: "#5eaa7b",
  shop: "#5e7ec4",
  gamble: "#c95252",
  chest: "#bf7d40",
  monster: "#a94760",
  coin: "#f4cb48",
};

const playerColors = [
  [64, 145, 255],
  [242, 95, 92],
  [52, 191, 115],
  [255, 193, 59],
  [181, 110, 255],
  [255, 125, 196],
  [42, 197, 214],
  [255, 146, 71],
];

const resourceColors = {
  wood: "#8b6542",
  iron: "#929aa0",
  crystal: "#7cc2ff",
};

const state = {
  socket: null,
  playerId: null,
  phase: "lobby",
  paused: false,
  round_number: 0,
  escapes_completed: 0,
  status_message: "Waiting to connect...",
  map: [],
  world_width: 1280,
  world_height: 820,
  time_left: null,
  players: [],
  monsters: [],
  chests: [],
  coins: [],
  projectiles: [],
  shop_items: [],
  goal_tiles: [],
  you: null,
  inventoryOpen: false,
  input: { up: false, down: false, left: false, right: false },
  selectedColorIndex: 0,
  publicRoom: {
    host: "shortline.proxy.rlwy.net",
    port: 55839,
    room_name: "Dungeon Drift Public",
    room_code: "",
    auto_connect: false,
    lock_settings: false,
  },
};

function normalizeRoomCode(value) {
  return String(value || "")
    .toUpperCase()
    .split("")
    .filter((char) => roomCodeAlphabet.includes(char))
    .join("")
    .slice(0, 6);
}

function resizeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(window.innerWidth * ratio);
  canvas.height = Math.floor(window.innerHeight * ratio);
  canvas.style.width = `${window.innerWidth}px`;
  canvas.style.height = `${window.innerHeight}px`;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function websocketUrl() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws`;
}

function setConnectStatus(message, error = false) {
  connectStatus.textContent = message;
  connectStatus.style.color = error ? "#ffb5aa" : "";
}

async function loadPublicConfig() {
  try {
    const response = await fetch("/config", { cache: "no-store" });
    if (!response.ok) return;
    const config = await response.json();
    state.publicRoom = {
      ...state.publicRoom,
      ...config,
    };
    if (!hostInput.value.trim()) {
      hostInput.value = state.publicRoom.host;
    }
    if (!portInput.value.trim()) {
      portInput.value = String(state.publicRoom.port);
    }
    if (!roomNameInput.value.trim()) {
      roomNameInput.value = state.publicRoom.room_name || "";
    }
    if (!roomCodeInput.value.trim()) {
      roomCodeInput.value = normalizeRoomCode(state.publicRoom.room_code || "");
    }
    if (state.publicRoom.lock_settings) {
      hostInput.readOnly = true;
      portInput.readOnly = true;
      roomNameInput.readOnly = true;
    }
    setConnectStatus(`Open this page and press Play Public Room, or enter 127.0.0.1 to create your own room.`);
  } catch (_error) {
    // Keep the baked-in defaults if the config endpoint is unavailable.
  }
}

function applyPublicRoom() {
  hostInput.value = state.publicRoom.host || "shortline.proxy.rlwy.net";
  portInput.value = String(state.publicRoom.port || 55839);
  roomNameInput.value = state.publicRoom.room_name || "Dungeon Drift Public";
  roomCodeInput.value = normalizeRoomCode(state.publicRoom.room_code || "");
  updateRoomFields();
}

function isLocalHost(value) {
  const host = String(value || "").trim().toLowerCase();
  return host === "127.0.0.1" || host === "localhost" || host === "0.0.0.0";
}

function connect() {
  if (state.socket && state.socket.readyState <= 1) {
    state.socket.close();
  }

  const socket = new WebSocket(websocketUrl());
  state.socket = socket;
  setConnectStatus("Connecting...");

  socket.addEventListener("open", () => {
    const host = hostInput.value.trim() || "shortline.proxy.rlwy.net";
    const port = Number(portInput.value) || 55839;
    const name = nameInput.value.trim() || "Adventurer";
    const roomCode = normalizeRoomCode(roomCodeInput.value);
    const roomName = roomNameInput.value.trim().slice(0, 32);

    socket.send(JSON.stringify({
      type: "connect",
      name,
      host,
      port,
      color_index: state.selectedColorIndex,
      server_name: roomName,
      password: roomCode,
    }));
  });

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "welcome") {
      state.playerId = payload.player_id;
      connectPanel.style.display = "none";
      if (isLocalHost(hostInput.value)) {
        const hostRoomCode = normalizeRoomCode(roomCodeInput.value);
        const hostRoomName = roomNameInput.value.trim() || `${nameInput.value.trim() || "Adventurer"}'s Room`;
        setConnectStatus(`Room ready: ${hostRoomName}${hostRoomCode ? ` | Code ${hostRoomCode}` : ""}`);
      } else {
        setConnectStatus("Connected.");
      }
      return;
    }
    if (payload.type === "error") {
      connectPanel.style.display = "";
      setConnectStatus(payload.message || "Connection failed.", true);
      return;
    }
    if (payload.type === "disconnected") {
      connectPanel.style.display = "";
      setConnectStatus(payload.message || "Disconnected.", true);
      return;
    }
    if (payload.type === "state") {
      Object.assign(state, payload);
      renderHud();
      renderInventory();
    }
  });

  socket.addEventListener("close", () => {
    connectPanel.style.display = "";
    setConnectStatus("Socket closed.", true);
  });
}

function connectPublicRoom() {
  applyPublicRoom();
  connect();
}

function sendMessage(payload) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) return;
  state.socket.send(JSON.stringify(payload));
}

function sendInput() {
  sendMessage({ type: "input", ...state.input });
}

function triggerAction(action) {
  if (action === "inventory") {
    state.inventoryOpen = !state.inventoryOpen;
    renderInventory();
    return;
  }
  const mapped = {
    attack: state.inventoryOpen ? null : (state.phase === "lobby" ? "toggle_ready" : (state.phase === "shop" ? "gamble" : "attack")),
    interact: state.inventoryOpen ? null : (state.phase === "shop" ? "interact" : (state.phase === "lobby" ? null : "interact")),
    potion: "use_potion",
    weapon_prev: "cycle_weapon_prev",
    weapon_next: "cycle_weapon_next",
  }[action];
  if (mapped) {
    sendMessage({ type: "action", action: mapped });
  }
}

function controlsLabel() {
  if (state.phase === "lobby") return "Choose your color before joining, then ready up in the lobby.";
  if (state.phase === "shop") return "Buy with F, gamble with G, and change the bet with Q or Tab.";
  return "Move, fight, open chests, and keep the whole party alive.";
}

function renderHud() {
  phaseValue.textContent = state.phase[0].toUpperCase() + state.phase.slice(1);
  roundValue.textContent = String(state.round_number);
  escapesValue.textContent = String(state.escapes_completed);
  timerValue.textContent = state.time_left == null ? "--" : `${String(state.time_left).padStart(2, "0")}s`;
  statusMessage.textContent = state.status_message || controlsLabel();

  if (state.you) {
    const gambleBet = state.phase === "shop" ? ` | Gamble Bet $${state.you.gamble_bet ?? 1}` : "";
    statsMessage.textContent = `HP ${state.you.hp}/${state.you.max_hp} | Gold ${state.you.gold} | Potions ${state.you.potions} | Weapon ${state.you.weapon_name}${gambleBet}`;
  } else {
    statsMessage.textContent = "Waiting for player state...";
  }

  partyList.innerHTML = "";
  state.players
    .slice()
    .sort((a, b) => (b.score - a.score) || a.name.localeCompare(b.name))
    .forEach((player) => {
      const card = document.createElement("div");
      card.className = "party-card";
      card.style.borderLeft = `4px solid rgb(${player.color.join(",")})`;
      card.innerHTML = `<strong>${player.name}</strong><div>Score ${player.score} | HP ${player.hp} | ${player.weapon_name}</div>`;
      partyList.appendChild(card);
    });
}

function renderInventory() {
  inventoryPanel.classList.toggle("hidden", !state.inventoryOpen);
  if (!state.you) {
    inventoryContent.innerHTML = "";
    return;
  }
  const resources = Object.entries(state.you.resources || {})
    .map(([key, value]) => `${key} ${value}`)
    .join(" | ");
  const weapons = (state.you.inventory || []).join(", ");
  const armor = (state.you.armors || []).length ? state.you.armors.join(", ") : "None";

  inventoryContent.innerHTML = "";

  const summary = document.createElement("div");
  summary.className = "recipe-card";
  summary.innerHTML = `<strong>Loadout</strong><p>Weapons: ${weapons || "None"}</p><p>Armor: ${armor}</p><p>Resources: ${resources || "None"}</p>`;
  inventoryContent.appendChild(summary);

  (state.you.recipes || []).forEach((recipe) => {
    const item = document.createElement("button");
    item.className = "recipe-card";
    item.type = "button";
    item.innerHTML = `<strong>${recipe.name}</strong><p>${recipe.description}</p><p>${Object.entries(recipe.cost).map(([key, value]) => `${key}:${value}`).join(", ")}</p>`;
    item.addEventListener("click", () => sendMessage({ type: "action", action: `craft:${recipe.id}` }));
    inventoryContent.appendChild(item);
  });
}

function camera() {
  const you = state.players.find((player) => player.id === state.playerId);
  const screenWidth = window.innerWidth;
  const visibleHeight = window.innerHeight - hudHeight;
  let drawX = 0;
  let drawY = 0;
  if (you) {
    const centerX = you.x + playerSize / 2;
    const centerY = you.y + playerSize / 2;
    drawX = screenWidth / 2 - centerX;
    drawY = visibleHeight / 2 - centerY;
    if (state.world_width >= screenWidth) {
      drawX = Math.min(0, Math.max(screenWidth - state.world_width, drawX));
    }
    if (state.world_height >= visibleHeight) {
      drawY = Math.min(0, Math.max(visibleHeight - state.world_height, drawY));
    }
  }
  return { drawX, drawY, visibleHeight };
}

function drawRoundedRect(x, y, width, height, radius, fill, stroke, context = ctx) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.arcTo(x + width, y, x + width, y + height, radius);
  context.arcTo(x + width, y + height, x, y + height, radius);
  context.arcTo(x, y + height, x, y, radius);
  context.arcTo(x, y, x + width, y, radius);
  if (fill) {
    context.fillStyle = fill;
    context.fill();
  }
  if (stroke) {
    context.strokeStyle = stroke;
    context.lineWidth = 2;
    context.stroke();
  }
}

const tileVariantCount = 8;
let tileArt = null;

function clampByte(value) {
  return Math.max(0, Math.min(255, value | 0));
}

function hexToRgb(hex) {
  const cleaned = hex.replace("#", "").trim();
  if (cleaned.length !== 6) return [255, 255, 255];
  return [
    parseInt(cleaned.slice(0, 2), 16),
    parseInt(cleaned.slice(2, 4), 16),
    parseInt(cleaned.slice(4, 6), 16),
  ];
}

function shadeRgb(rgb, delta) {
  return [clampByte(rgb[0] + delta), clampByte(rgb[1] + delta), clampByte(rgb[2] + delta)];
}

function rgbCss(rgb, alpha = 1) {
  return alpha === 1 ? `rgb(${rgb[0]},${rgb[1]},${rgb[2]})` : `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${alpha})`;
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function tileVariant(col, row, seed = 0) {
  const value = (col * 73856093) ^ (row * 19349663) ^ (seed * 83492791);
  return value & (tileVariantCount - 1);
}

function makeTileCanvas(drawFn) {
  const c = document.createElement("canvas");
  c.width = tileSize;
  c.height = tileSize;
  const g = c.getContext("2d");
  drawFn(g);
  return c;
}

function buildFloorTile(variant) {
  const base = hexToRgb(colors.floor);
  const rng = mulberry32(19007 + variant * 911);
  return makeTileCanvas((g) => {
    g.fillStyle = colors.floor;
    g.fillRect(0, 0, tileSize, tileSize);
    for (let i = 0; i < 70; i += 1) {
      const x = Math.floor(rng() * tileSize);
      const y = Math.floor(rng() * tileSize);
      const delta = Math.floor(rng() * 32) - 18;
      g.fillStyle = rgbCss(shadeRgb(base, delta));
      g.fillRect(x, y, 1, 1);
    }
    g.strokeStyle = "rgba(246,238,220,0.8)";
    g.beginPath();
    g.moveTo(0, 0);
    g.lineTo(tileSize, 0);
    g.moveTo(0, 0);
    g.lineTo(0, tileSize);
    g.stroke();
    g.strokeStyle = "rgba(208,197,171,0.8)";
    g.beginPath();
    g.moveTo(0, tileSize - 1);
    g.lineTo(tileSize, tileSize - 1);
    g.moveTo(tileSize - 1, 0);
    g.lineTo(tileSize - 1, tileSize);
    g.stroke();
  });
}

function buildWallTile(variant) {
  const base = hexToRgb(colors.wall);
  const rng = mulberry32(42013 + variant * 733);
  const mortar = rgbCss(shadeRgb(base, -24));
  return makeTileCanvas((g) => {
    g.fillStyle = rgbCss(shadeRgb(base, -6));
    g.fillRect(0, 0, tileSize, tileSize);

    const brickH = 12;
    const brickW = 16;
    for (let y = 0; y < tileSize; y += brickH) {
      const offset = ((y / brickH) | 0) % 2 ? brickW / 2 : 0;
      for (let x = -offset; x < tileSize; x += brickW) {
        const delta = Math.floor(rng() * 22) - 12;
        g.fillStyle = rgbCss(shadeRgb(base, delta));
        g.fillRect(x + 1, y + 1, brickW - 2, brickH - 2);
        g.strokeStyle = mortar;
        g.strokeRect(x + 1, y + 1, brickW - 2, brickH - 2);
      }
    }

    g.fillStyle = rgbCss(shadeRgb(base, 24));
    g.fillRect(0, 0, tileSize, 4);
    g.fillRect(0, 0, 4, tileSize);
    g.fillStyle = rgbCss(shadeRgb(base, -28));
    g.fillRect(0, tileSize - 4, tileSize, 4);
    g.fillRect(tileSize - 4, 0, 4, tileSize);
  });
}

function buildPortalOverlay(hexColor, ringHex) {
  const base = hexToRgb(hexColor);
  const ring = hexToRgb(ringHex);
  return makeTileCanvas((g) => {
    g.clearRect(0, 0, tileSize, tileSize);
    drawRoundedRect(5, 5, tileSize - 10, tileSize - 10, 14, rgbCss(shadeRgb(base, -8), 0.92), null, g);
    g.strokeStyle = rgbCss(ring, 0.82);
    g.lineWidth = 3;
    g.strokeRect(8, 8, tileSize - 16, tileSize - 16);
    const cx = tileSize / 2;
    const cy = tileSize / 2;
    const glow = shadeRgb(base, 50);
    [18, 14, 10, 6].forEach((r, index) => {
      g.fillStyle = rgbCss(glow, 0.12 + index * 0.05);
      g.beginPath();
      g.arc(cx, cy, r, 0, Math.PI * 2);
      g.fill();
    });
  });
}

function buildPadOverlay() {
  return makeTileCanvas((g) => {
    g.clearRect(0, 0, tileSize, tileSize);
    drawRoundedRect(7, 7, tileSize - 14, tileSize - 14, 10, "rgba(145,123,79,0.92)", "rgba(72,56,34,0.82)", g);
    g.strokeStyle = "rgba(170,146,102,0.7)";
    g.lineWidth = 2;
    g.beginPath();
    g.moveTo(16, 18);
    g.lineTo(tileSize - 16, 18);
    g.moveTo(16, tileSize / 2);
    g.lineTo(tileSize - 16, tileSize / 2);
    g.stroke();
  });
}

function ensureTileArt() {
  if (tileArt) return tileArt;
  const floor = [];
  const wall = [];
  for (let i = 0; i < tileVariantCount; i += 1) {
    floor.push(buildFloorTile(i));
    wall.push(buildWallTile(i));
  }
  tileArt = {
    floor,
    wall,
    overlays: {
      exit: buildPortalOverlay(colors.exit, "#fff6e0"),
      shop: buildPortalOverlay(colors.shop, "#e6f4ff"),
      gamble: buildPortalOverlay(colors.gamble, "#ffecc7"),
      pad: buildPadOverlay(),
    },
  };
  return tileArt;
}

function drawShadow(cx, cy, rx, ry, alpha = 0.28) {
  ctx.fillStyle = `rgba(0,0,0,${alpha})`;
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();
}

function drawAttackEffect(cx, cy, fx, fy, progress, style) {
  const len = Math.hypot(fx, fy) || 1;
  const dx = fx / len;
  const dy = fy / len;
  const px = -dy;
  const py = dx;
  const t = Math.max(0, Math.min(1, progress));

  if (style === "ranged") {
    const reach = 26 + 10 * t;
    const sx = cx + dx * 8;
    const sy = cy + dy * 8;
    const ex = cx + dx * reach;
    const ey = cy + dy * reach;
    ctx.lineCap = "round";
    ctx.strokeStyle = "rgba(120,68,25,0.95)";
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(ex, ey);
    ctx.stroke();
    ctx.strokeStyle = "rgba(248,218,151,0.9)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(sx + dx * 5, sy + dy * 5);
    ctx.lineTo(ex, ey);
    ctx.stroke();
    ctx.fillStyle = "rgba(248,218,151,0.95)";
    ctx.beginPath();
    ctx.moveTo(ex, ey);
    ctx.lineTo(ex - dx * 10 + px * 4, ey - dy * 10 + py * 4);
    ctx.lineTo(ex - dx * 10 - px * 4, ey - dy * 10 - py * 4);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "rgba(255,244,224,0.18)";
    ctx.beginPath();
    ctx.arc(cx - dx * 8, cy - dy * 8, 16, 0, Math.PI * 2);
    ctx.fill();
    return;
  }

  const reach = 22 + 14 * t;
  const mx = cx + dx * reach;
  const my = cy + dy * reach;
  const arcR = 18 + 10 * t;
  const start = Math.atan2(dy, dx) + 2.7;
  const end = start + 1.1;
  ctx.strokeStyle = "rgba(255,235,180,0.25)";
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.arc(mx, my, arcR, start, end);
  ctx.stroke();
  ctx.strokeStyle = "rgba(255,235,180,0.55)";
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.arc(mx, my, arcR, start, end);
  ctx.stroke();
  ctx.strokeStyle = "rgba(255,235,180,0.95)";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(mx, my, arcR, start, end);
  ctx.stroke();

  const tipAng = end;
  const tipX = mx + Math.cos(tipAng) * arcR;
  const tipY = my + Math.sin(tipAng) * arcR;
  ctx.strokeStyle = "rgba(255,244,224,0.7)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(tipX, tipY, 9, 0, Math.PI * 2);
  ctx.stroke();
}

function drawMap(drawX, drawY) {
  const art = ensureTileArt();
  state.map.forEach((line, row) => {
    [...line].forEach((cell, col) => {
      const x = col * tileSize + drawX;
      const y = row * tileSize + drawY + hudHeight;
      if (cell === "#") {
        const v = tileVariant(col, row, 3);
        ctx.drawImage(art.wall[v], x, y);
        return;
      }
      const v = tileVariant(col, row, 7);
      ctx.drawImage(art.floor[v], x, y);
      if (cell === "E" || cell === "L") ctx.drawImage(art.overlays.exit, x, y);
      else if (cell === "P") ctx.drawImage(art.overlays.shop, x, y);
      else if (cell === "G") ctx.drawImage(art.overlays.gamble, x, y);
      else if (cell === "B") ctx.drawImage(art.overlays.pad, x, y);
    });
  });
}

function drawWorld() {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
  ctx.fillStyle = "#0d1016";
  ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);

  const { drawX, drawY } = camera();
  drawMap(drawX, drawY);

  state.chests.forEach((chest) => {
    const x = chest.x + drawX;
    const y = chest.y + drawY + hudHeight;
    drawShadow(x + chestSize / 2, y + chestSize + 2, chestSize * 0.75, chestSize * 0.28, 0.28);
    if (chest.opened) {
      const lidH = Math.max(8, (chestSize / 2) | 0);
      const baseY = y + lidH - 2;
      drawRoundedRect(x, baseY, chestSize, chestSize - lidH + 2, 4, "rgba(106,82,63,0.95)", "#371c0c");
      drawRoundedRect(x + 3, baseY + 2, chestSize - 6, 6, 3, "rgba(34,24,18,0.9)", "rgba(10,10,12,0.65)");
      ctx.strokeStyle = "rgba(110,82,52,0.9)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x + 5, baseY + 4);
      ctx.lineTo(x + chestSize - 5, baseY + 4);
      ctx.stroke();

      const hingeY = baseY + 1;
      const topY = baseY - 10;
      ctx.fillStyle = "rgba(165,112,70,0.95)";
      ctx.strokeStyle = "rgba(55,28,12,0.95)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x + 2, hingeY);
      ctx.lineTo(x + chestSize - 2, hingeY);
      ctx.lineTo(x + chestSize - 6, topY);
      ctx.lineTo(x + 6, topY);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.strokeStyle = "rgba(240,211,166,0.75)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x + 7, topY + 2);
      ctx.lineTo(x + chestSize - 7, topY + 2);
      ctx.stroke();
    } else {
      drawRoundedRect(x, y, chestSize, chestSize, 4, colors.chest, "#371c0c");
      ctx.fillStyle = "rgba(210,186,124,0.95)";
      drawRoundedRect(x + chestSize / 2 - 3, y + chestSize / 2 - 1, 6, 8, 2, ctx.fillStyle, "rgba(76,52,24,0.9)");
    }
  });

  state.coins.forEach((coin) => {
    const x = coin.x + drawX;
    const y = coin.y + drawY + hudHeight;
    drawShadow(x + coinSize / 2, y + coinSize + 1, coinSize * 0.6, coinSize * 0.22, 0.22);
    if (coin.resource_id) {
      const fill = resourceColors[coin.resource_id] || colors.coin;
      ctx.fillStyle = fill;
      ctx.beginPath();
      ctx.moveTo(x + coinSize / 2, y);
      ctx.lineTo(x + coinSize, y + coinSize / 2);
      ctx.lineTo(x + coinSize / 2, y + coinSize);
      ctx.lineTo(x, y + coinSize / 2);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = "rgba(50,42,34,0.9)";
      ctx.stroke();
    } else {
      ctx.fillStyle = colors.coin;
      ctx.beginPath();
      ctx.ellipse(x + coinSize / 2, y + coinSize / 2, coinSize / 2, coinSize / 2, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(136,95,21,0.95)";
      ctx.stroke();
      ctx.fillStyle = "rgba(255,244,210,0.75)";
      ctx.beginPath();
      ctx.ellipse(x + coinSize * 0.38, y + coinSize * 0.35, coinSize * 0.2, coinSize * 0.2, 0, 0, Math.PI * 2);
      ctx.fill();
    }
  });

  state.shop_items.forEach((item) => {
    const x = item.x + drawX;
    const y = item.y + drawY + hudHeight;
    drawShadow(x + shopItemSize / 2, y + shopItemSize + 1, shopItemSize * 0.7, shopItemSize * 0.25, 0.25);
    drawRoundedRect(x, y, shopItemSize, shopItemSize, 6, item.sold ? "#5b5b5b" : colors.shop, "#11161d");
    drawRoundedRect(x + 5, y + 5, shopItemSize - 10, shopItemSize - 10, 6, item.sold ? "#6a6a6a" : "rgba(230,244,255,0.35)");
    ctx.fillStyle = colors.text;
    ctx.font = "14px Trebuchet MS";
    ctx.fillText(String(item.slot + 1), x + 8, y + 18);
    ctx.fillStyle = "rgba(28,24,18,0.9)";
    ctx.font = "bold 14px Trebuchet MS";
    const icon = ({ weapon: "W", armor: "A", potion: "H", ammo: "R", bandage: "B" })[item.kind] || "?";
    ctx.fillText(icon, x + 9, y + shopItemSize - 6);
  });

  state.monsters.forEach((monster) => {
    if (!monster.alive) return;
    const x = monster.x + drawX;
    const y = monster.y + drawY + hudHeight;
    drawShadow(x + monsterSize / 2, y + monsterSize + 2, monsterSize * 0.72, monsterSize * 0.28, 0.28);
    ctx.fillStyle = ({ fang: "#c4595e", brute: "#814e34", shade: "#6359a2" })[monster.kind] || colors.monster;
    ctx.beginPath();
    ctx.ellipse(x + monsterSize / 2, y + monsterSize / 2, monsterSize / 2, monsterSize / 2, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#f0967a";
    ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,0.22)";
    ctx.beginPath();
    ctx.arc(x + monsterSize * 0.35, y + monsterSize * 0.35, monsterSize * 0.18, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#1c1812";
    ctx.beginPath();
    ctx.arc(x + 9, y + 10, 2.3, 0, Math.PI * 2);
    ctx.arc(x + monsterSize - 9, y + 10, 2.3, 0, Math.PI * 2);
    ctx.fill();
    const ratio = monster.max_hp ? Math.max(0, Math.min(1, monster.hp / monster.max_hp)) : 1;
    drawRoundedRect(x - 2, y - 10, monsterSize + 4, 6, 3, "rgba(18,18,22,0.9)");
    drawRoundedRect(x - 1, y - 9, (monsterSize + 2) * ratio, 4, 3, "rgba(216,78,78,0.95)");
    ctx.fillStyle = colors.text;
    ctx.font = "14px Trebuchet MS";
    ctx.fillText(String(monster.hp), x - 2, y - 4);
  });

  state.projectiles.forEach((projectile) => {
    const x = projectile.x + drawX;
    const y = projectile.y + drawY + hudHeight;
    drawShadow(x + projectileSize / 2, y + projectileSize + 1, projectileSize * 0.7, projectileSize * 0.25, 0.18);
    ctx.fillStyle = "#7c481e";
    ctx.beginPath();
    ctx.moveTo(x + projectileSize / 2, y);
    ctx.lineTo(x + projectileSize, y + projectileSize / 2);
    ctx.lineTo(x + projectileSize / 2, y + projectileSize);
    ctx.lineTo(x, y + projectileSize / 2);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = "rgba(248,218,151,0.9)";
    ctx.stroke();
  });

  state.players.forEach((player) => {
    const x = player.x + drawX;
    const y = player.y + drawY + hudHeight;
    drawShadow(x + playerSize / 2, y + playerSize + 2, playerSize * 0.76, playerSize * 0.28, 0.28);
    ctx.fillStyle = `rgb(${player.color.join(",")})`;
    drawRoundedRect(x, y, playerSize, playerSize, 6, ctx.fillStyle, "#141418");
    ctx.fillStyle = "rgba(255,255,255,0.22)";
    ctx.beginPath();
    ctx.arc(x + playerSize * 0.35, y + playerSize * 0.35, playerSize * 0.18, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#1c1812";
    ctx.beginPath();
    ctx.arc(x + 9, y + 11, 2.1, 0, Math.PI * 2);
    ctx.arc(x + playerSize - 9, y + 11, 2.1, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = colors.text;
    ctx.font = "14px Trebuchet MS";
    ctx.fillText(`${player.name} $${player.gold}`, x - 8, y - 6);

    if (player.id === state.playerId) {
      ctx.strokeStyle = "rgba(255,255,255,0.45)";
      ctx.beginPath();
      ctx.arc(x + playerSize / 2, y + playerSize / 2, attackRange, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (player.attack_animation > 0) {
      const progress = player.attack_animation / attackAnimationTime;
      const [fx, fy] = player.facing || [1, 0];
      const cx = x + playerSize / 2;
      const cy = y + playerSize / 2;
      drawAttackEffect(cx, cy, fx, fy, progress, player.attack_style === "ranged" ? "ranged" : "melee");
    }
  });

  drawHudOverlay();
}

function drawHudOverlay() {
  drawRoundedRect(0, 0, window.innerWidth, hudHeight, 0, "rgba(42,45,56,0.88)");
  ctx.strokeStyle = colors.accent;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(0, hudHeight);
  ctx.lineTo(window.innerWidth, hudHeight);
  ctx.stroke();

  if (state.paused || state.phase === "lobby" || !state.players.length) {
    drawRoundedRect(18, hudHeight + 18, Math.min(560, window.innerWidth - 36), 88, 14, "rgba(255,249,239,0.95)", colors.accent);
    ctx.fillStyle = "#423830";
    ctx.font = "bold 28px Georgia";
    ctx.fillText(state.paused ? "Paused" : (state.phase === "lobby" ? "Lobby" : "Waiting for server"), 36, hudHeight + 54);
    ctx.fillStyle = "#585046";
    ctx.font = "18px Trebuchet MS";
    ctx.fillText(
      state.paused
        ? "Press Esc to resume your single-player run."
        : (state.phase === "lobby" ? "Walk around and press R when everyone is ready." : "Connecting..."),
      36,
      hudHeight + 84,
    );
  }
}

function updateColorPreview() {
  const color = `rgb(${playerColors[state.selectedColorIndex].join(",")})`;
  colorPreview.style.background = color;
  colorPreviewPlayer.style.background = color;
  colorPreviewName.textContent = nameInput.value.trim() || "Adventurer";
  [...colorSwatches.children].forEach((button, index) => {
    button.classList.toggle("active", index === state.selectedColorIndex);
  });
}

function updateRoomFields() {
  roomCodeInput.value = normalizeRoomCode(roomCodeInput.value);
  if (isLocalHost(hostInput.value) && !roomNameInput.value.trim()) {
    const hostName = nameInput.value.trim() || "Adventurer";
    roomNameInput.placeholder = `${hostName}'s Room`;
  } else {
    roomNameInput.placeholder = "Friends Only";
  }
}

function buildColorSwatches() {
  colorSwatches.innerHTML = "";
  playerColors.forEach((color, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "color-swatch";
    button.style.background = `rgb(${color.join(",")})`;
    button.addEventListener("click", () => {
      state.selectedColorIndex = index;
      updateColorPreview();
    });
    colorSwatches.appendChild(button);
  });
  updateColorPreview();
}

function animationLoop() {
  drawWorld();
  requestAnimationFrame(animationLoop);
}

function setMovement(direction, active) {
  state.input[direction] = active;
  sendInput();
  document.querySelector(`[data-move="${direction}"]`)?.classList.toggle("active", active);
}

function bindHoldButton(button, onStart, onEnd) {
  const start = (event) => {
    event.preventDefault();
    button.classList.add("active");
    onStart();
  };
  const end = (event) => {
    event.preventDefault();
    button.classList.remove("active");
    onEnd();
  };
  button.addEventListener("pointerdown", start);
  button.addEventListener("pointerup", end);
  button.addEventListener("pointercancel", end);
  button.addEventListener("pointerleave", end);
}

document.querySelectorAll("[data-move]").forEach((button) => {
  const direction = button.dataset.move;
  bindHoldButton(button, () => setMovement(direction, true), () => setMovement(direction, false));
});

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => triggerAction(button.dataset.action));
});

window.addEventListener("keydown", (event) => {
  if (event.target.tagName === "INPUT") return;
  const map = {
    w: "up",
    ArrowUp: "up",
    s: "down",
    ArrowDown: "down",
    a: "left",
    ArrowLeft: "left",
    d: "right",
    ArrowRight: "right",
  };
  const direction = map[event.key];
  if (direction) {
    if (!state.input[direction]) setMovement(direction, true);
    return;
  }
  const actions = {
    r: () => sendMessage({ type: "action", action: "toggle_ready" }),
    g: () => sendMessage({ type: "action", action: "gamble" }),
    " ": () => sendMessage({ type: "action", action: "attack" }),
    f: () => sendMessage({ type: "action", action: "interact" }),
    h: () => sendMessage({ type: "action", action: "use_potion" }),
    b: () => sendMessage({ type: "action", action: "use_bandage" }),
    q: () => sendMessage({ type: "action", action: "cycle_weapon_prev" }),
    Escape: () => {
      if (state.players.length === 1 && (state.phase === "round" || state.phase === "shop")) {
        sendMessage({ type: "action", action: "toggle_pause" });
      }
    },
    e: () => {
      state.inventoryOpen = !state.inventoryOpen;
      renderInventory();
    },
    Tab: () => sendMessage({ type: "action", action: "cycle_weapon_next" }),
  };
  if (actions[event.key]) {
    event.preventDefault();
    actions[event.key]();
  }
});

window.addEventListener("keyup", (event) => {
  const map = {
    w: "up",
    ArrowUp: "up",
    s: "down",
    ArrowDown: "down",
    a: "left",
    ArrowLeft: "left",
    d: "right",
    ArrowRight: "right",
  };
  const direction = map[event.key];
  if (direction) setMovement(direction, false);
});

joinButton.addEventListener("click", connect);
playPublicButton.addEventListener("click", connectPublicRoom);
nameInput.addEventListener("input", updateColorPreview);
nameInput.addEventListener("input", updateRoomFields);
hostInput.addEventListener("input", updateRoomFields);
roomCodeInput.addEventListener("input", () => {
  roomCodeInput.value = normalizeRoomCode(roomCodeInput.value);
});
closeInventoryButton.addEventListener("click", () => {
  state.inventoryOpen = false;
  renderInventory();
});

window.addEventListener("resize", resizeCanvas);
buildColorSwatches();
updateRoomFields();
resizeCanvas();
renderHud();
renderInventory();
animationLoop();
loadPublicConfig().then(() => {
  if (state.publicRoom.auto_connect) {
    connectPublicRoom();
  }
});
