"""
AllwaysAlways Inc. - AgentKit Testnet Wallet, CROW Faucet & Pyth Price Oracle
Connected to Supabase (allways-social-ledger).
"""

import datetime
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from crow_fibonacci_librarian import (
    get_crow_fibonacci_librarian,
    run_fibonacci_block_stress_test,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
ENV_FILE = os.path.join(BASE_DIR, ".env")
AUCTIONS_FILE = os.path.join(BASE_DIR, "crow_auctions.json")
MANDALOZ_PLAYERS_FILE = os.path.join(BASE_DIR, "crow_mandaloz_players.json")
TREASURY_ADDRESS = "0xF21905EE23f7A8B66d4cda83C0Dec3EA8258B2Bd"


def load_mandaloz_players():
    if os.path.exists(MANDALOZ_PLAYERS_FILE):
        try:
            with open(MANDALOZ_PLAYERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_mandaloz_players(players):
    with open(MANDALOZ_PLAYERS_FILE, "w", encoding="utf-8") as f:
        json.dump(players, f, indent=2)


DAILY_REWARD_CAP_BY_LEVEL = {1: 25.0, 2: 45.0, 3: 80.0, 4: 130.0, 5: 200.0, 6: 300.0, 7: 450.0}


def get_daily_reward_cap(lv):
    lv = max(1, int(lv or 1))
    if lv in DAILY_REWARD_CAP_BY_LEVEL:
        return DAILY_REWARD_CAP_BY_LEVEL[lv]
    return float(450 + (lv - 7) * 35)


def check_and_record_daily_reward(addr, crow_amt):
    players = load_mandaloz_players()
    p = players.get(addr)
    if not p:
        return True, None, None
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if p.get("dailyRewardDate") != today:
        p["dailyRewardDate"] = today
        p["dailyRewardCrow"] = 0.0
    lv = int(p.get("level") or 1)
    cap = get_daily_reward_cap(lv)
    used = float(p.get("dailyRewardCrow") or 0.0)
    if used + crow_amt > cap:
        return False, f"Daily CROW reward cap reached for Lv.{lv} ({used:.1f}/{cap:.0f} CROW today). Level up to unlock higher daily payouts!", cap
    p["dailyRewardCrow"] = round(used + crow_amt, 2)
    players[addr] = p
    save_mandaloz_players(players)
    return True, None, cap


def default_mandaloz_player(address, username=""):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    return {
        "address": address,
        "username": username or f"Player-{address[2:8]}",
        "level": 1,
        "xp": 0,
        "fusionShards": 10,
        "wins": 0,
        "energy": 10,
        "energyDate": today,
        "dailyRewardDate": today,
        "dailyRewardCrow": 0.0,
        "pouch": {"id": "pouch_cloth_1", "name": "Cloth Starter Pouch", "tier": 1, "rarity": "common", "capacity": 6},
        "pouches": [],
        "materials": {"timber": 2, "ore": 0, "leather": 2, "herbs": 1, "essence": 0},
        "pendingMints": [],
        "abilities": [],
        "gear": [],
        "consumables": [],
        "mounts": [],
        "houses": [],
        "familiars": [],
        "eggs": [],
        "wildEncounter": None,
        "ringShards": 0,
        "trialsCleared": [],
        "rings": [{"id": "ring_starter_1", "name": "Cracked Starter Ring", "slots": 2, "brokenSlots": 1, "bound": [None, "BROKEN"]}],
        "petDen": None,
        "battleBoost": 0,
        "equipped": {
            "mandala": 1001,
            "pouch": "pouch_cloth_1",
            "ability": None,
            "head": None,
            "chest": None,
            "boots": None,
            "weapon": None,
            "quiver": None,
            "mount": None,
            "familiarRing": None,
            "familiar": None,
        },
        "collection": [
            {
                "id": 1001,
                "name": "Circle of Beginnings",
                "tier": 1,
                "rarity": "common",
                "pattern": "circular",
                "elements": ["earth"],
                "fusionPower": 65,
                "marketValue": 35,
            }
        ],
        "realmHarvests": {},
        "stats": {"mints": 0, "fuses": 0, "auctions": 0, "realms": 0, "dungeons": 0, "raids": 0, "shrineMints": 0},
        "claimedChallenges": [],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


MANDALOZ_BOT_FILE = os.path.join(BASE_DIR, "crow_mandaloz_bot.json")
MANDALOZ_BOT_LOCK = threading.Lock()
MANDALOZ_BOT_ROTATION = [
    {"slot": "morning", "name": "Solar Dawn Octagon",     "tier": 2, "rarity": "uncommon",  "pattern": "octagonal",  "elements": ["light", "fire"],    "fusionPower": 145, "marketValue": 150, "minBid": 90},
    {"slot": "midday",  "name": "Zenith Prism Hexagon",   "tier": 2, "rarity": "rare",      "pattern": "hexagonal",  "elements": ["fire", "air"],      "fusionPower": 190, "marketValue": 200, "minBid": 120},
    {"slot": "evening", "name": "Twilight Eclipse Lotus", "tier": 3, "rarity": "epic",      "pattern": "pentagonal", "elements": ["shadow", "spirit"], "fusionPower": 265, "marketValue": 300, "minBid": 180},
    {"slot": "morning", "name": "Dewdrop Triad",          "tier": 2, "rarity": "uncommon",  "pattern": "triangular", "elements": ["water", "earth"],   "fusionPower": 135, "marketValue": 150, "minBid": 85},
    {"slot": "midday",  "name": "High-Noon Bastion",      "tier": 3, "rarity": "rare",      "pattern": "square",     "elements": ["earth", "light"],   "fusionPower": 210, "marketValue": 220, "minBid": 130},
    {"slot": "evening", "name": "Astral Void Crown",      "tier": 3, "rarity": "legendary", "pattern": "circular",   "elements": ["spirit", "light"],  "fusionPower": 380, "marketValue": 500, "minBid": 300},
    {"slot": "morning", "name": "Zephyr Morning Star",    "tier": 2, "rarity": "uncommon",  "pattern": "pentagonal", "elements": ["air", "light"],     "fusionPower": 140, "marketValue": 150, "minBid": 90},
    {"slot": "midday",  "name": "Magma Forge Core",       "tier": 3, "rarity": "epic",      "pattern": "octagonal",  "elements": ["fire", "earth"],    "fusionPower": 280, "marketValue": 320, "minBid": 190},
    {"slot": "evening", "name": "Midnight Oracle Seal",   "tier": 3, "rarity": "epic",      "pattern": "hexagonal",  "elements": ["shadow", "water"],  "fusionPower": 270, "marketValue": 300, "minBid": 180},
    {"slot": "morning", "name": "Sunforged Plate Chest",  "tier": 2, "rarity": "rare",      "pattern": "square",     "elements": ["fire", "earth"],    "fusionPower": 45,  "marketValue": 140, "minBid": 75,  "category": "armor",  "slotType": "chest",  "powerBonus": 45},
    {"slot": "midday",  "name": "Phoenix Flame Bow",      "tier": 3, "rarity": "epic",      "pattern": "triangular", "elements": ["fire", "air"],      "fusionPower": 65,  "marketValue": 210, "minBid": 110, "category": "weapon", "slotType": "weapon", "weaponKind": "bow", "powerBonus": 65},
    {"slot": "evening", "name": "25x Void Arrow Quiver",  "tier": 2, "rarity": "rare",      "pattern": "pentagonal", "elements": ["shadow", "spirit"], "fusionPower": 30,  "marketValue": 95,  "minBid": 45,  "category": "arrows", "slotType": "quiver", "qty": 25, "maxQty": 25, "powerBonus": 30, "element": "shadow"},
    {"slot": "morning", "name": "Astral Warhorse",        "tier": 3, "rarity": "epic",      "pattern": "circular",   "elements": ["air", "light"],     "fusionPower": 0,   "marketValue": 320, "minBid": 180, "category": "mount",  "energyBonus": 6},
    {"slot": "evening", "name": "Obsidian Homestead",     "tier": 3, "rarity": "epic",      "pattern": "square",     "elements": ["earth", "shadow"],  "fusionPower": 0,   "marketValue": 400, "minBid": 220, "category": "house",  "vaultBonus": 10, "craftDiscount": 0.15, "energyRegen": 2},
    {"slot": "midday",  "name": "Ember Dragon Egg",       "tier": 3, "rarity": "epic",      "pattern": "circular",   "elements": ["fire", "air"],      "fusionPower": 0,   "marketValue": 180, "minBid": 95,  "category": "egg",    "species": "Dragon"},
    {"slot": "morning", "name": "5x Mystic Pet Treats",   "tier": 1, "rarity": "uncommon",  "pattern": "triangular", "elements": ["earth", "light"],   "fusionPower": 0,   "marketValue": 45,  "minBid": 20,  "category": "treats", "qty": 5, "maxQty": 5},
]


def load_mandaloz_bot():
    default_cfg = {
        "enabled": True,
        "rotationIndex": 0,
        "scheduleTimes": {"morning": "08:30", "midday": "13:30", "evening": "18:00"},
        "lastPostedSlots": {},
        "dropsCount": 0,
        "lastDropAt": None,
        "lastDropItem": None,
    }
    if os.path.exists(MANDALOZ_BOT_FILE):
        try:
            with open(MANDALOZ_BOT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    default_cfg.update(data)
        except Exception:
            pass
    return default_cfg


def save_mandaloz_bot(cfg):
    with open(MANDALOZ_BOT_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def execute_mandaloz_bot_drop(slot_name=None, manual=False):
    with MANDALOZ_BOT_LOCK:
        cfg = load_mandaloz_bot()
        idx = int(cfg.get("rotationIndex") or 0) % len(MANDALOZ_BOT_ROTATION)
        bp = MANDALOZ_BOT_ROTATION[idx]
        chosen_slot = slot_name or bp["slot"]
        nft_id = int(time.time() * 1000) % 100000000 + idx
        item_data = {
            "id": nft_id,
            "name": bp["name"],
            "tier": bp["tier"],
            "rarity": bp["rarity"],
            "pattern": bp["pattern"],
            "elements": list(bp["elements"]),
            "fusionPower": bp["fusionPower"],
            "marketValue": bp["marketValue"],
            "autoDropSlot": chosen_slot,
        }
        auctions = []
        if os.path.exists(AUCTIONS_FILE):
            try:
                with open(AUCTIONS_FILE, "r", encoding="utf-8") as f:
                    auctions = json.load(f)
            except Exception:
                auctions = []
        auction_id = f"auc_{int(time.time())}_{secrets.token_hex(3)}"
        tier_label = f"Tier {bp['tier']} • {bp['rarity'].upper()} • 3x/Day {chosen_slot.title()} Drop"
        min_bid = float(bp["minBid"])
        blk = mine_block_in_supabase(
            "MANDALOZ_AUCTION_LIST",
            TREASURY_ADDRESS,
            TREASURY_ADDRESS,
            amount_cents=0,
            crow_amount=min_bid,
            metadata={
                "auction_id": auction_id,
                "item_name": bp["name"],
                "tier": tier_label,
                "min_bid_crow": min_bid,
                "bot_slot": chosen_slot,
                "manual": manual,
            },
        )
        entry = {
            "auction_id": auction_id,
            "seller": TREASURY_ADDRESS,
            "item_name": bp["name"],
            "tier": tier_label,
            "item_data": item_data,
            "min_bid_crow": min_bid,
            "current_bid_crow": min_bid,
            "highest_bidder": None,
            "bid_count": 0,
            "status": "active",
            "auto_bot": True,
            "bot_slot": chosen_slot,
            "block_number": blk["block_number"],
            "tx_hash": blk["tx_hash"],
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        auctions.insert(0, entry)
        with open(AUCTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(auctions[:100], f, indent=2)

        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        cfg["rotationIndex"] = (idx + 1) % len(MANDALOZ_BOT_ROTATION)
        cfg["dropsCount"] = int(cfg.get("dropsCount") or 0) + 1
        cfg["lastDropAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cfg["lastDropItem"] = bp["name"]
        if not manual:
            cfg.setdefault("lastPostedSlots", {})[chosen_slot] = today_str
        save_mandaloz_bot(cfg)
        return {"ok": True, "auction": entry, "block": blk, "bot": cfg}


def mandaloz_bot_scheduler_loop():
    while True:
        try:
            cfg = load_mandaloz_bot()
            if cfg.get("enabled", True):
                now = datetime.datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                hhmm = now.strftime("%H:%M")
                last_slots = cfg.get("lastPostedSlots") or {}
                for slot_name, target_hhmm in (cfg.get("scheduleTimes") or {}).items():
                    if last_slots.get(slot_name) != today_str and hhmm >= target_hhmm:
                        execute_mandaloz_bot_drop(slot_name=slot_name, manual=False)
                        break
        except Exception:
            pass
        time.sleep(30)
CHAIN_LOCK = threading.Lock()
PRICE_CACHE = {"ts": 0.0, "prices": {}}
SIGNAL_CACHE = {"ts": 0.0, "signals": []}
ADMIN_SESSIONS = {}

# Pyth Hermes Mainnet Price Feed IDs
PYTH_FEEDS = {
    "ETH": "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "BTC": "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    "SOL": "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "POL": "0xffd11c5a1cfd42f80afb2df4d9c264c15f956d68153336374649f56509dc5720",
    "AVAX": "0x93da3352f9f1d105fdfe4971cfa80e9dd777bfc5d0f683ebb6e1294b92137bb7",
    "DOGE": "0xdcef50dd0a4cd2dcc17e45df1676dcb336a11a61c69df7a0299b0150c672d25c",
    "XRP": "0xec5d399846a9209f3fe5881d70aae9268c94339ff9817e8d18ff19fa05eea1c8",
    "LINK": "0x8ac0c70fff57e9aefdf5edf44b51d62c2d433653cbb2cf5cc06bb115af04d221",
}


def load_env():
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ and v:
                os.environ[k] = v


load_env()


def supa_headers(extra=None):
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def supa_rest(path, method="GET", body=None, extra_headers=None):
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    url = f"{base}/rest/v1/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=supa_headers(extra_headers), method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"message": raw}


def fetch_pyth_prices():
    now = time.time()
    if PRICE_CACHE["prices"] and (now - PRICE_CACHE["ts"]) < 15.0:
        return PRICE_CACHE["prices"]
    prices = {"USDC": 1.0, "CROW": 0.10}
    try:
        qs = "&".join(f"ids[]={fid}" for fid in PYTH_FEEDS.values())
        url = f"https://hermes.pyth.network/v2/updates/price/latest?{qs}"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AllwaysAlways-Oracle/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        id_to_sym = {fid.replace("0x", ""): sym for sym, fid in PYTH_FEEDS.items()}
        for item in data.get("parsed", []):
            fid = (item.get("id") or "").replace("0x", "")
            sym = id_to_sym.get(fid)
            p = item.get("price") or {}
            if sym and "price" in p and "expo" in p:
                prices[sym] = round(float(p["price"]) * (10 ** int(p["expo"])), 6)
    except Exception:
        # Fallback to Coinbase public spot API (no key required)
        for sym in ("ETH", "BTC", "SOL", "POL", "AVAX", "LINK", "DOGE", "XRP"):
            try:
                cb_url = f"https://api.coinbase.com/v2/prices/{sym}-USD/spot"
                req = urllib.request.Request(cb_url, headers={"Accept": "application/json", "User-Agent": "AllwaysAlways-Oracle/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    cb_data = json.loads(resp.read().decode("utf-8"))
                amt = (cb_data.get("data") or {}).get("amount")
                if amt:
                    prices[sym] = round(float(amt), 6)
            except Exception:
                pass
    if any(k in prices for k in ("ETH", "BTC", "SOL")):
        PRICE_CACHE["ts"] = now
        PRICE_CACHE["prices"] = prices
    return prices


def compute_wallstreet_signals():
    now = time.time()
    if SIGNAL_CACHE["signals"] and (now - SIGNAL_CACHE["ts"]) < 60.0:
        return SIGNAL_CACHE["signals"]
    signals = []
    for sym in ("ETH", "BTC", "SOL", "POL", "AVAX", "LINK", "DOGE", "XRP"):
        try:
            url = f"https://api.exchange.coinbase.com/products/{sym}-USD/candles?granularity=3600"
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AllwaysAlways-Oracle/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                candles = json.loads(resp.read().decode("utf-8"))
            # Coinbase returns newest first: [time, low, high, open, close, volume]
            closes = [float(c[4]) for c in candles[:30]][::-1]
            if len(closes) < 15:
                continue
            cur = closes[-1]
            prev24 = closes[-25] if len(closes) >= 25 else closes[0]
            chg24 = ((cur - prev24) / prev24) * 100.0
            sma7 = sum(closes[-7:]) / 7.0
            sma24 = sum(closes[-24:]) / min(24, len(closes))
            # RSI-14
            diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
            recent_diffs = diffs[-14:]
            gains = [d for d in recent_diffs if d > 0]
            losses = [-d for d in recent_diffs if d < 0]
            avg_gain = sum(gains) / 14.0
            avg_loss = sum(losses) / 14.0
            rsi = 100.0 if avg_loss == 0 else (100.0 - (100.0 / (1.0 + (avg_gain / avg_loss))))

            action = "HOLD"
            confidence = 55
            reasons = []
            # Smarter dip & trend rules: avoid catching deep falling knives and avoid shorting near the bottom
            if (chg24 <= -10.0 and rsi <= 26.0) or (chg24 > -10.0 and rsi <= 32.0):
                action = "BUY"
                confidence = 80 if rsi <= 28.0 else 75
                reasons.append(f"RSI-14 is {rsi:.1f} (oversold dip)")
            elif rsi >= 68:
                action = "SELL"
                confidence = 78
                reasons.append(f"RSI-14 is {rsi:.1f} (overbought zone)")
            elif sma7 > sma24 * 1.005 and rsi < 64:
                action = "BUY"
                confidence = 70
                reasons.append(f"7h avg (${sma7:,.2f}) crossed above 24h avg (${sma24:,.2f})")
            elif sma7 < sma24 * 0.995 and rsi >= 45.0:
                action = "SELL"
                confidence = 66
                reasons.append(f"7h avg (${sma7:,.2f}) slipped below 24h avg (${sma24:,.2f})")
            else:
                reasons.append(f"RSI-14 at {rsi:.1f} (waiting for cleaner setup); 7h avg (${sma7:,.2f}) vs 24h avg (${sma24:,.2f})")

            reasons.append(f"24h move {chg24:+.2f}%")
            signals.append({
                "asset": sym,
                "priceUsd": round(cur, 4),
                "change24hPct": round(chg24, 2),
                "sma7": round(sma7, 4),
                "sma24": round(sma24, 4),
                "rsi14": round(rsi, 1),
                "action": action,
                "confidence": confidence,
                "suggestedUsd": 15.0 if action != "HOLD" else 0.0,
                "rationale": " • ".join(reasons),
            })
        except Exception as e:
            signals.append({
                "asset": sym,
                "action": "HOLD",
                "confidence": 0,
                "rationale": f"Feed unavailable: {e}",
            })
    if signals:
        SIGNAL_CACHE["ts"] = now
        SIGNAL_CACHE["signals"] = signals
    return signals


def base_sepolia_rpc(method, params):
    rpc_url = os.environ.get("BASE_SEPOLIA_RPC", "https://sepolia.base.org")
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(
        rpc_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "AllwaysAlways-Oracle/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def mine_block_in_supabase(tx_type, from_addr, to_addr, amount_cents=0, crow_amount=0.0, metadata=None):
    with CHAIN_LOCK:
        st, latest_rows = supa_rest("blocks?select=block_number,block_hash&order=block_number.desc&limit=1")
        if st != 200 or not isinstance(latest_rows, list) or not latest_rows:
            raise RuntimeError(f"Failed to read latest block: {latest_rows}")
        latest = latest_rows[0]
        next_num = int(latest["block_number"]) + 1
        prev_hash = latest["block_hash"]
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tx_hash = hashlib.sha256(
            f"{tx_type}:{from_addr}:{to_addr}:{crow_amount}:{now_iso}:{time.time_ns()}".encode("utf-8")
        ).hexdigest()

        tx_payload = {
            "tx_hash": tx_hash,
            "tx_type": tx_type,
            "from_address": from_addr,
            "to_address": to_addr,
            "amount_cents": int(amount_cents),
            "crow_amount": float(crow_amount),
            "metadata": metadata or {},
            "timestamp": now_iso,
            "status": "completed",
        }
        nonce = 0
        while True:
            bstr = json.dumps(
                {
                    "block_number": next_num,
                    "nonce": nonce,
                    "previous_hash": prev_hash,
                    "transactions": [tx_payload],
                },
                sort_keys=True,
            )
            bhash = hashlib.sha256(bstr.encode("utf-8")).hexdigest()
            if bhash.startswith("0000"):
                break
            nonce += 1

        bst, bres = supa_rest(
            "blocks",
            method="POST",
            body={
                "block_number": next_num,
                "block_hash": bhash,
                "previous_hash": prev_hash,
                "nonce": nonce,
                "difficulty": 4,
                "miner": "agentkit_wallet",
                "transactions": [tx_payload],
                "created_at": now_iso,
            },
            extra_headers={"Prefer": "return=minimal"},
        )
        if bst not in (200, 201):
            raise RuntimeError(f"Block insert failed: {bres}")

        tst, tres = supa_rest(
            "transactions",
            method="POST",
            body={
                "tx_hash": tx_hash,
                "tx_type": tx_type,
                "from_address": from_addr,
                "to_address": to_addr,
                "amount_cents": int(amount_cents),
                "crow_amount": float(crow_amount),
                "metadata": metadata or {},
                "block_number": next_num,
                "block_hash": bhash,
                "status": "completed",
                "created_at": now_iso,
            },
            extra_headers={"Prefer": "return=minimal"},
        )
        if tst not in (200, 201):
            raise RuntimeError(f"Transaction insert failed: {tres}")

        get_crow_fibonacci_librarian().record_block("crow_main", next_num, bhash)
        return {"block_number": next_num, "block_hash": bhash, "nonce": nonce, "tx_hash": tx_hash}


def verify_chain_integrity():
    """Verify sequential block numbers, previous_hash links, and PoW prefixes across all Supabase blocks."""
    t0 = time.perf_counter()
    rows = []
    page_size = 1000
    offset = 0
    while True:
        st, batch = supa_rest(
            f"blocks?select=block_number,block_hash,previous_hash,nonce,difficulty&order=block_number.asc&limit={page_size}&offset={offset}"
        )
        if st != 200 or not isinstance(batch, list):
            return {"ok": False, "error": f"Failed to load blocks: {batch}"}
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    broken = []
    for i, blk in enumerate(rows):
        bnum = int(blk.get("block_number", -1))
        bhash = str(blk.get("block_hash") or "")
        phash = str(blk.get("previous_hash") or "")
        diff = int(blk.get("difficulty") or 4)
        if i > 0:
            prev = rows[i - 1]
            if bnum != int(prev["block_number"]) + 1:
                broken.append({"block_number": bnum, "reason": "non_sequential_block_number"})
            if phash != str(prev.get("block_hash") or ""):
                broken.append({"block_number": bnum, "reason": "previous_hash_mismatch"})
            if not bhash.startswith("0" * diff):
                broken.append({"block_number": bnum, "reason": "pow_prefix_invalid"})
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    latest = rows[-1] if rows else {}
    return {
        "ok": True,
        "valid": len(broken) == 0 and len(rows) > 0,
        "totalBlocks": len(rows),
        "brokenLinks": broken,
        "latestBlockNumber": latest.get("block_number"),
        "latestBlockHash": latest.get("block_hash"),
        "checkMs": elapsed_ms,
    }


def _merkle_root_and_proof(leaves):
    """Build a binary SHA-256 Merkle tree and return (root_hex, depth)."""
    if not leaves:
        return hashlib.sha256(b"").hexdigest(), 0
    layer = list(leaves)
    depth = 0
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        next_layer = []
        for idx in range(0, len(layer), 2):
            next_layer.append(hashlib.sha256((layer[idx] + layer[idx + 1]).encode("ascii")).hexdigest())
        layer = next_layer
        depth += 1
    return layer[0], depth


def run_chain_stress_test(tx_count=5000, anchor_block=True):
    """Simulate high-throughput signed/hashed transactions, build a Merkle root, and optionally anchor 1 PoW rollup block."""
    tx_count = max(100, min(100000, int(tx_count)))
    t0 = time.perf_counter()
    salt = f"{time.time_ns()}:{TREASURY_ADDRESS}"
    leaves = [
        hashlib.sha256(f"{salt}:{i}:{i % 97}".encode("ascii")).hexdigest()
        for i in range(tx_count)
    ]
    merkle_root, tree_depth = _merkle_root_and_proof(leaves)
    sim_ms = max(0.01, (time.perf_counter() - t0) * 1000.0)
    tx_per_sec = round(tx_count / (sim_ms / 1000.0))

    anchored = None
    if anchor_block:
        anchored = mine_block_in_supabase(
            "ROLLUP_BATCH_STRESS_TEST",
            TREASURY_ADDRESS,
            TREASURY_ADDRESS,
            amount_cents=0,
            crow_amount=0.0,
            metadata={
                "tx_count": tx_count,
                "tx_per_sec": tx_per_sec,
                "merkle_root": merkle_root,
                "tree_depth": tree_depth,
            },
        )
    integrity = verify_chain_integrity()
    return {
        "ok": True,
        "txCount": tx_count,
        "simMs": round(sim_ms, 2),
        "txPerSec": tx_per_sec,
        "merkleRoot": merkle_root,
        "treeDepth": tree_depth,
        "anchoredBlock": anchored,
        "integrity": integrity,
    }


def run_block_stress_test_with_anchor(block_count=10000, difficulty=2, anchor_block=True):
    """Run a 10k-100k sequential block-chaining stress test under Fibonacci Librarian scaling and optionally anchor 1 rollup block."""
    start_height = 0
    genesis_hash = None
    if anchor_block:
        st, latest_rows = supa_rest("blocks?select=block_number,block_hash&order=block_number.desc&limit=1")
        if st == 200 and isinstance(latest_rows, list) and latest_rows:
            start_height = int(latest_rows[0].get("block_number") or 0)
            genesis_hash = latest_rows[0].get("block_hash")

    res = run_fibonacci_block_stress_test(
        block_count=block_count,
        difficulty=difficulty,
        start_height=start_height,
        genesis_hash=genesis_hash,
    )
    anchored = None
    if anchor_block:
        anchored = mine_block_in_supabase(
            "FIBONACCI_BLOCK_STRESS_TEST",
            TREASURY_ADDRESS,
            TREASURY_ADDRESS,
            amount_cents=0,
            crow_amount=0.0,
            metadata={
                "block_count": res["blockCount"],
                "blocks_per_sec": res["blocksPerSec"],
                "merkle_root": res["merkleRoot"],
                "fibonacci": res["fibonacci"],
            },
        )
    res["anchoredBlock"] = anchored
    return res


class WalletHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def _send_json(self, data, status=200):
        raw = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _require_admin(self):
        expected_pass = os.environ.get("FOUNDER_ADMIN_PASSCODE", "").strip()
        if not expected_pass:
            return True
        tok = (self.headers.get("x-admin-token") or "").strip()
        exp = ADMIN_SESSIONS.get(tok)
        if not tok or not exp or time.time() > exp:
            self._send_json({"ok": False, "error": "Founder Admin unlock required"}, 403)
            return False
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            _, accounts = supa_rest("accounts?select=*&order=created_at.desc&limit=25")
            _, blocks = supa_rest("blocks?select=block_number,block_hash,previous_hash,nonce,difficulty,miner,created_at&order=block_number.desc&limit=10")
            _, trades = supa_rest("paper_trades?select=*&order=created_at.desc&limit=15")
            _, all_trades = supa_rest("paper_trades?select=wallet_address,side,asset,asset_qty&limit=500")
            _, policies = supa_rest("agent_policies?id=eq.default&limit=1")
            _, tokenomics = supa_rest("crow_tokenomics?select=*&order=pool_name.asc")
            holdings = {}
            for tr in (all_trades if isinstance(all_trades, list) else []):
                waddr = tr.get("wallet_address")
                sym = tr.get("asset")
                qty = float(tr.get("asset_qty") or 0.0)
                if not waddr or not sym:
                    continue
                bucket = holdings.setdefault(waddr, {})
                bucket[sym] = bucket.get(sym, 0.0) + (qty if tr.get("side") == "BUY" else -qty)
            cdp_ready = bool(os.environ.get("CDP_API_KEY_ID", "").strip() and os.environ.get("CDP_API_KEY_SECRET", "").strip())
            self._send_json({
                "ok": True,
                "treasuryAddress": os.environ.get("TREASURY_ADDRESS", TREASURY_ADDRESS),
                "cdpConfigured": cdp_ready,
                "prices": fetch_pyth_prices(),
                "signals": compute_wallstreet_signals(),
                "accounts": accounts or [],
                "blocks": blocks or [],
                "paperTrades": trades or [],
                "holdings": holdings,
                "policy": (policies[0] if isinstance(policies, list) and policies else {}),
                "tokenomics": tokenomics if isinstance(tokenomics, list) else [],
            })
            return

        if parsed.path == "/api/oracle/prices":
            self._send_json({"ok": True, "prices": fetch_pyth_prices()})
            return

        if parsed.path == "/api/signals":
            self._send_json({"ok": True, "signals": compute_wallstreet_signals()})
            return

        if parsed.path == "/api/chain/verify":
            self._send_json(verify_chain_integrity())
            return

        if parsed.path == "/api/chain/librarian":
            self._send_json({"ok": True, **get_crow_fibonacci_librarian().get_system_stats()})
            return

        if parsed.path == "/api/auction/list":
            auctions = []
            if os.path.exists(AUCTIONS_FILE):
                try:
                    with open(AUCTIONS_FILE, "r", encoding="utf-8") as f:
                        auctions = json.load(f)
                except Exception:
                    auctions = []
            self._send_json({"ok": True, "auctions": auctions})
            return

        if parsed.path == "/api/mandaloz/player":
            qs = urllib.parse.parse_qs(parsed.query)
            addr = (qs.get("address") or [""])[0].strip()
            uname = (qs.get("username") or [""])[0].strip()
            if not addr:
                self._send_json({"ok": False, "error": "address required"}, 400)
                return
            players = load_mandaloz_players()
            if addr not in players:
                p_new = default_mandaloz_player(addr, uname)
                try:
                    starter = p_new["collection"][0]
                    blk = mine_block_in_supabase(
                        "MANDALOZ_NFT_STARTER",
                        TREASURY_ADDRESS,
                        addr,
                        amount_cents=0,
                        crow_amount=0,
                        metadata={"nft_id": starter["id"], "name": starter["name"], "tier": starter["tier"], "rarity": starter["rarity"]},
                    )
                    starter["mintBlock"] = blk["block_number"]
                    starter["txHash"] = blk["tx_hash"]
                except Exception:
                    pass
                players[addr] = p_new
                save_mandaloz_players(players)
            else:
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                changed_p = False
                if uname and not players[addr].get("username"):
                    players[addr]["username"] = uname
                    changed_p = True
                if players[addr].get("energyDate") != today:
                    eq_mount_id = (players[addr].get("equipped") or {}).get("mount")
                    mount_obj = next((m for m in (players[addr].get("mounts") or []) if m.get("id") == eq_mount_id), None)
                    mount_bonus = int(mount_obj.get("energyBonus") or 0) if mount_obj else 0
                    house_bonus = max([int(h.get("energyRegen") or 0) for h in (players[addr].get("houses") or [])] or [0])
                    players[addr]["energyDate"] = today
                    players[addr]["energy"] = 10 + mount_bonus + house_bonus
                    changed_p = True
                if players[addr].get("dailyRewardDate") != today:
                    players[addr]["dailyRewardDate"] = today
                    players[addr]["dailyRewardCrow"] = 0.0
                    changed_p = True
                rpg_defaults = {
                    "pouch": {"id": "pouch_cloth_1", "name": "Cloth Starter Pouch", "tier": 1, "rarity": "common", "capacity": 6},
                    "pouches": [],
                    "materials": {"timber": 2, "ore": 0, "leather": 2, "herbs": 1, "essence": 0},
                    "pendingMints": [],
                    "abilities": [],
                    "gear": [],
                    "consumables": [],
                    "mounts": [],
                    "houses": [],
                    "familiars": [],
                    "eggs": [],
                    "wildEncounter": None,
                    "ringShards": 0,
                    "trialsCleared": [],
                    "rings": [{"id": "ring_starter_1", "name": "Cracked Starter Ring", "slots": 2, "brokenSlots": 1, "bound": [None, "BROKEN"]}],
                    "petDen": None,
                    "battleBoost": 0,
                    "equipped": {"mandala": 1001, "pouch": "pouch_cloth_1", "ability": None, "head": None, "chest": None, "boots": None, "weapon": None, "quiver": None, "mount": None, "familiarRing": None, "familiar": None},
                }
                for dk, dv in rpg_defaults.items():
                    if dk not in players[addr] or players[addr][dk] is None:
                        players[addr][dk] = dv
                        changed_p = True
                if changed_p:
                    save_mandaloz_players(players)
            self._send_json({"ok": True, "player": players[addr]})
            return

        if parsed.path == "/api/mandaloz/leaderboard":
            players = load_mandaloz_players()
            ranked = sorted(
                players.values(),
                key=lambda p: (int(p.get("level") or 1), int(p.get("xp") or 0), len(p.get("collection") or [])),
                reverse=True,
            )[:25]
            self._send_json({"ok": True, "leaderboard": ranked})
            return

        if parsed.path == "/api/mandaloz/bot/status":
            cfg = load_mandaloz_bot()
            idx = int(cfg.get("rotationIndex") or 0) % len(MANDALOZ_BOT_ROTATION)
            upcoming = [
                MANDALOZ_BOT_ROTATION[(idx + i) % len(MANDALOZ_BOT_ROTATION)]
                for i in range(3)
            ]
            self._send_json({"ok": True, "bot": cfg, "upcoming": upcoming})
            return

        if parsed.path == "/api/mandaloz/nft/history":
            _, txs = supa_rest("transactions?tx_type=like.MANDALOZ_*&order=created_at.desc&limit=25")
            self._send_json({"ok": True, "history": txs if isinstance(txs, list) else []})
            return

        if parsed.path == "/api/mandaloz/models":
            meshy_dir = os.path.join(PUBLIC_DIR, "models", "meshy")
            files = []
            if os.path.isdir(meshy_dir):
                for fn in sorted(os.listdir(meshy_dir)):
                    if fn.lower().endswith(".glb"):
                        low = fn.lower()
                        if any(k in low for k in ("tile", "island", "fire_base")):
                            cat = "floors"
                        elif any(k in low for k in ("bottle", "potion", "talisman", "leaf", "chest")):
                            cat = "potions_chests"
                        elif any(k in low for k in ("warlord", "guardian", "knight", "sentinel", "specter", "enchanter", "titan", "dragon_armo", "humanoid", "menace")):
                            cat = "characters"
                        else:
                            cat = "magic"
                        clean = fn.replace("Meshy_AI_", "").replace("_texture", "").replace(".glb", "").replace("_", " ")
                        files.append({"filename": fn, "label": clean, "category": cat, "url": f"/models/meshy/{urllib.parse.quote(fn)}"})
            self._send_json({"ok": True, "models": files})
            return

        if parsed.path == "/api/sepolia/balance":
            qs = urllib.parse.parse_qs(parsed.query)
            addr = (qs.get("address") or [""])[0].strip()
            if not addr.startswith("0x") or len(addr) != 42:
                self._send_json({"ok": False, "error": "Invalid EVM address"}, 400)
                return
            try:
                rpc_res = base_sepolia_rpc("eth_getBalance", [addr, "latest"])
                wei = int(rpc_res.get("result") or "0x0", 16)
                eth_val = wei / (10 ** 18)
                self._send_json({"ok": True, "address": addr, "eth": eth_val, "network": "base-sepolia (84532)"})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}

        if parsed == "/api/wallets/create":
            label = (payload.get("label") or "Test Wallet").strip()
            addr = (payload.get("address") or "").strip()
            if not addr:
                addr = "0x" + secrets.token_hex(20)
            st, res = supa_rest(
                "accounts?on_conflict=address",
                method="POST",
                body={
                    "address": addr,
                    "balance_cents": 10000,
                    "crow_balance": 500,
                    "nonce": 0,
                },
                extra_headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            )
            if st not in (200, 201):
                self._send_json({"ok": False, "error": res}, 400)
                return
            blk = mine_block_in_supabase(
                "TEST_WALLET_CREATED",
                TREASURY_ADDRESS,
                addr,
                amount_cents=10000,
                crow_amount=500.0,
                metadata={"label": label, "network": "base-sepolia"},
            )
            self._send_json({"ok": True, "address": addr, "block": blk})
            return

        if parsed == "/api/wallets/faucet":
            to_addr = (payload.get("address") or "").strip()
            crow_amt = float(payload.get("crowAmount") or 250)
            usd_cents = int(payload.get("usdCents") or 5000)
            if not to_addr:
                self._send_json({"ok": False, "error": "Wallet address required"}, 400)
                return
            _, rows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(to_addr)}&limit=1")
            if not rows:
                self._send_json({"ok": False, "error": "Wallet not found in Supabase"}, 404)
                return
            cur = rows[0]
            new_crow = float(cur.get("crow_balance") or 0) + crow_amt
            new_cents = int(cur.get("balance_cents") or 0) + usd_cents
            supa_rest(
                f"accounts?address=eq.{urllib.parse.quote(to_addr)}",
                method="PATCH",
                body={"crow_balance": new_crow, "balance_cents": new_cents},
            )
            blk = mine_block_in_supabase(
                "TEST_FAUCET_DRIP",
                TREASURY_ADDRESS,
                to_addr,
                amount_cents=usd_cents,
                crow_amount=crow_amt,
                metadata={"faucet": True},
            )
            self._send_json({"ok": True, "newCrowBalance": new_crow, "newBalanceCents": new_cents, "block": blk})
            return

        if parsed == "/api/wallets/transfer":
            from_addr = (payload.get("fromAddress") or "").strip()
            to_addr = (payload.get("toAddress") or "").strip()
            crow_amt = float(payload.get("crowAmount") or 0)
            if not from_addr or not to_addr or from_addr == to_addr or crow_amt <= 0:
                self._send_json({"ok": False, "error": "Valid distinct fromAddress, toAddress, and positive crowAmount required"}, 400)
                return
            _, frows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(from_addr)}&limit=1")
            _, trows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(to_addr)}&limit=1")
            if not frows or not trows:
                self._send_json({"ok": False, "error": "Sender or recipient wallet not found"}, 404)
                return
            sender_crow = float(frows[0].get("crow_balance") or 0)
            if sender_crow < crow_amt:
                self._send_json({"ok": False, "error": f"Insufficient CROW ({sender_crow} < {crow_amt})"}, 400)
                return
            recip_crow = float(trows[0].get("crow_balance") or 0)
            supa_rest(f"accounts?address=eq.{urllib.parse.quote(from_addr)}", method="PATCH", body={"crow_balance": sender_crow - crow_amt})
            supa_rest(f"accounts?address=eq.{urllib.parse.quote(to_addr)}", method="PATCH", body={"crow_balance": recip_crow + crow_amt})
            blk = mine_block_in_supabase("WALLET_CROW_TRANSFER", from_addr, to_addr, amount_cents=0, crow_amount=crow_amt, metadata={"network": "crow-chain"})
            self._send_json({"ok": True, "fromBalance": sender_crow - crow_amt, "toBalance": recip_crow + crow_amt, "block": blk})
            return

        if parsed == "/api/admin/login":
            email = (payload.get("email") or "").strip().lower()
            passcode = (payload.get("passcode") or "").strip()
            expected_email = os.environ.get("FOUNDER_ADMIN_EMAIL", "austin.hanshew24@gmail.com").strip().lower()
            expected_pass = os.environ.get("FOUNDER_ADMIN_PASSCODE", "").strip()
            if not expected_pass:
                self._send_json({"ok": False, "error": "Set FOUNDER_ADMIN_PASSCODE in .env to enable local Founder unlock."}, 400)
                return
            if email == expected_email and passcode == expected_pass:
                tok = secrets.token_hex(24)
                ADMIN_SESSIONS[tok] = time.time() + 12 * 3600
                self._send_json({"ok": True, "adminToken": tok, "email": email})
            else:
                self._send_json({"ok": False, "error": "Invalid Founder credentials"}, 401)
            return

        if parsed == "/api/agent/policy":
            if not self._require_admin():
                return
            kill = bool(payload.get("killSwitch", False))
            max_trade = float(payload.get("maxTradeUsd", 50.0))
            daily_lim = float(payload.get("dailyLimitUsd", 200.0))
            supa_rest(
                "agent_policies?id=eq.default",
                method="PATCH",
                body={
                    "kill_switch": kill,
                    "max_trade_usd": max_trade,
                    "daily_limit_usd": daily_lim,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
            )
            if kill:
                supa_rest(
                    "watchdog_alerts",
                    method="POST",
                    body={"level": "HIGH", "category": "agentkit", "message": "SentryGuard Kill-Switch ACTIVATED on AgentKit wallet"},
                )
            self._send_json({"ok": True})
            return

        if parsed == "/api/agent/paper_trade":
            wallet = (payload.get("address") or "").strip()
            side = (payload.get("side") or "BUY").upper()
            asset = (payload.get("asset") or "ETH").upper()
            usd_amount = float(payload.get("usdAmount") or 10.0)

            _, pols = supa_rest("agent_policies?id=eq.default&limit=1")
            pol = pols[0] if isinstance(pols, list) and pols else {}
            if pol.get("kill_switch"):
                self._send_json({"ok": False, "error": "Blocked by SentryGuard Kill-Switch!"}, 403)
                return
            max_trade = float(pol.get("max_trade_usd") or 50.0)
            if usd_amount <= 0 or usd_amount > max_trade:
                self._send_json({"ok": False, "error": f"Trade ${usd_amount:.2f} exceeds SentryGuard cap (${max_trade:.2f})"}, 400)
                return

            _, wrows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(wallet)}&limit=1")
            if not wrows:
                self._send_json({"ok": False, "error": "Select or create a test wallet first"}, 404)
                return
            w = wrows[0]
            cents_needed = int(round(usd_amount * 100))
            cur_cents = int(w.get("balance_cents") or 0)
            if side == "BUY" and cur_cents < cents_needed:
                self._send_json({"ok": False, "error": f"Insufficient test USD balance (${cur_cents/100:.2f})"}, 400)
                return

            prices = fetch_pyth_prices()
            price_usd = float(prices.get(asset) or 0)
            if price_usd <= 0:
                self._send_json({"ok": False, "error": f"No live Pyth price for {asset}"}, 400)
                return
            qty = usd_amount / price_usd
            new_cents = (cur_cents - cents_needed) if side == "BUY" else (cur_cents + cents_needed)
            supa_rest(
                f"accounts?address=eq.{urllib.parse.quote(wallet)}",
                method="PATCH",
                body={"balance_cents": new_cents, "nonce": int(w.get("nonce") or 0) + 1},
            )
            blk = mine_block_in_supabase(
                "AGENTKIT_PAPER_TRADE",
                wallet if side == "BUY" else TREASURY_ADDRESS,
                TREASURY_ADDRESS if side == "BUY" else wallet,
                amount_cents=cents_needed,
                crow_amount=0.0,
                metadata={"side": side, "asset": asset, "priceUsd": price_usd, "qty": round(qty, 8), "network": "base-sepolia"},
            )
            supa_rest(
                "paper_trades",
                method="POST",
                body={
                    "wallet_address": wallet,
                    "network": "base-sepolia",
                    "side": side,
                    "asset": asset,
                    "usd_amount": usd_amount,
                    "asset_price_usd": price_usd,
                    "asset_qty": qty,
                    "tx_hash": blk["tx_hash"],
                    "block_number": blk["block_number"],
                    "status": "executed",
                },
            )
            self._send_json({"ok": True, "qty": qty, "priceUsd": price_usd, "newBalanceCents": new_cents, "block": blk})
            return

        if parsed in ("/api/game/reward", "/api/game/spend"):
            is_reward = parsed.endswith("/reward")
            addr = (payload.get("address") or "").strip()
            crow_amt = float(payload.get("crowAmount") or 25.0)
            game_name = (payload.get("gameName") or "AtAA Web Game").strip()
            reason = (payload.get("reason") or ("Quest reward" if is_reward else "In-game item")).strip()
            if not addr or crow_amt <= 0:
                self._send_json({"ok": False, "error": "Wallet address and positive crowAmount required"}, 400)
                return
            _, rows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(addr)}&limit=1")
            if not rows:
                self._send_json({"ok": False, "error": "Player wallet not found in Supabase"}, 404)
                return
            cur_crow = float(rows[0].get("crow_balance") or 0)
            if is_reward and game_name == "MandalOz 3D" and not reason.startswith("Sold "):
                allowed, cap_err, _ = check_and_record_daily_reward(addr, crow_amt)
                if not allowed:
                    self._send_json({"ok": False, "error": cap_err}, 400)
                    return
            if not is_reward and cur_crow < crow_amt:
                self._send_json({"ok": False, "error": f"Insufficient CROW balance ({cur_crow} < {crow_amt})"}, 400)
                return
            new_crow = (cur_crow + crow_amt) if is_reward else (cur_crow - crow_amt)
            supa_rest(
                f"accounts?address=eq.{urllib.parse.quote(addr)}",
                method="PATCH",
                body={"crow_balance": new_crow},
            )
            blk = mine_block_in_supabase(
                "GAME_CROW_REWARD" if is_reward else "GAME_CROW_SPEND",
                TREASURY_ADDRESS if is_reward else addr,
                addr if is_reward else TREASURY_ADDRESS,
                amount_cents=0,
                crow_amount=crow_amt,
                metadata={"game": game_name, "reason": reason},
            )
            self._send_json({"ok": True, "newCrowBalance": new_crow, "block": blk})
            return

        if parsed == "/api/agent/auto_trade":
            wallet = (payload.get("address") or "").strip()
            target_pct = float(payload.get("targetPct") or 4.0)
            stop_pct = float(payload.get("stopPct") or 2.5)
            signals = [s for s in compute_wallstreet_signals() if s.get("action") in ("BUY", "SELL")]
            if not signals:
                self._send_json({"ok": True, "executed": False, "reason": "No high-conviction BUY/SELL setup right now (holding)."})
                return
            _, open_rows = supa_rest(
                f"paper_trades?select=asset,side,outcome&wallet_address=eq.{urllib.parse.quote(wallet)}&outcome=eq.WATCHING"
            )
            open_pairs = {(r.get("asset"), r.get("side")) for r in (open_rows or [])}
            fresh_signals = [s for s in signals if (s.get("asset"), s.get("action")) not in open_pairs]
            if not fresh_signals:
                self._send_json({"ok": True, "executed": False, "reason": "Already watching active setup(s); skipping duplicate entry."})
                return
            best = max(fresh_signals, key=lambda s: float(s.get("confidence") or 0))
            side = best["action"]
            asset = best["asset"]
            usd_amount = float(best.get("suggestedUsd") or 15.0)
            prices = fetch_pyth_prices()
            price_usd = float(prices.get(asset) or best.get("priceUsd") or 0)
            if not wallet or price_usd <= 0:
                self._send_json({"ok": False, "error": "Select an active wallet with live price feed"}, 400)
                return
            _, wrows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(wallet)}&limit=1")
            if not wrows:
                self._send_json({"ok": False, "error": "Active wallet not found"}, 404)
                return
            w = wrows[0]
            cents_needed = int(round(usd_amount * 100))
            cur_cents = int(w.get("balance_cents") or 0)
            if side == "BUY" and cur_cents < cents_needed:
                self._send_json({"ok": True, "executed": False, "reason": f"Insufficient test USD for {side} {asset}"})
                return
            qty = usd_amount / price_usd
            new_cents = (cur_cents - cents_needed) if side == "BUY" else (cur_cents + cents_needed)
            supa_rest(
                f"accounts?address=eq.{urllib.parse.quote(wallet)}",
                method="PATCH",
                body={"balance_cents": new_cents, "nonce": int(w.get("nonce") or 0) + 1},
            )
            blk = mine_block_in_supabase(
                "MAZ_AUTO_TRADE",
                wallet if side == "BUY" else TREASURY_ADDRESS,
                TREASURY_ADDRESS if side == "BUY" else wallet,
                amount_cents=cents_needed,
                crow_amount=0.0,
                metadata={"side": side, "asset": asset, "priceUsd": price_usd, "confidence": best.get("confidence"), "targetPct": target_pct, "stopPct": stop_pct},
            )
            target_px = price_usd * (1 + target_pct / 100.0) if side == "BUY" else price_usd * (1 - target_pct / 100.0)
            stop_px = price_usd * (1 - stop_pct / 100.0) if side == "BUY" else price_usd * (1 + stop_pct / 100.0)
            supa_rest(
                "paper_trades",
                method="POST",
                body={
                    "wallet_address": wallet,
                    "network": "base-sepolia",
                    "side": side,
                    "asset": asset,
                    "usd_amount": usd_amount,
                    "asset_price_usd": price_usd,
                    "asset_qty": qty,
                    "target_price_usd": round(target_px, 6),
                    "stop_price_usd": round(stop_px, 6),
                    "outcome": "WATCHING",
                    "tx_hash": blk["tx_hash"],
                    "block_number": blk["block_number"],
                    "status": "executed",
                },
            )
            self._send_json({"ok": True, "executed": True, "side": side, "asset": asset, "usdAmount": usd_amount, "priceUsd": price_usd, "confidence": best.get("confidence"), "block": blk})
            return

        if parsed == "/api/agent/chat":
            msg = (payload.get("message") or "").strip().lower()
            signals = compute_wallstreet_signals()
            fib = get_crow_fibonacci_librarian().get_system_stats()
            if "verify" in msg or "watchdog" in msg or "chain" in msg:
                integ = verify_chain_integrity()
                self._send_json({
                    "ok": True,
                    "reply": f"CROW Chain is {'VALID' if integ.get('valid') else 'CHECK NEEDED'} across {integ.get('totalBlocks')} blocks (latest #{integ.get('latestBlockNumber')}). Fibonacci Librarian has {fib['librarianCount']} active librarian(s) managing {fib['headCount']} head(s).",
                })
                return
            top = max(signals, key=lambda s: float(s.get("confidence") or 0)) if signals else None
            summary = f"Top setup right now: {top['asset']} {top['action']} ({top['confidence']}%) — {top.get('rationale', '')}." if top else "Scanning market feeds..."
            self._send_json({"ok": True, "reply": f"Maz here! {summary}"})
            return

        if parsed == "/api/chain/stress_test":
            if not self._require_admin():
                return
            tx_count = int(payload.get("txCount") or 5000)
            anchor_block = bool(payload.get("anchorBlock", True))
            try:
                res = run_chain_stress_test(tx_count=tx_count, anchor_block=anchor_block)
                self._send_json(res)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        if parsed == "/api/chain/block_stress_test":
            if not self._require_admin():
                return
            block_count = int(payload.get("blockCount") or 10000)
            difficulty = int(payload.get("difficulty") or 2)
            anchor_block = bool(payload.get("anchorBlock", True))
            try:
                res = run_block_stress_test_with_anchor(
                    block_count=block_count,
                    difficulty=difficulty,
                    anchor_block=anchor_block,
                )
                self._send_json(res)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        if parsed == "/api/auction/list":
            seller = (payload.get("seller") or "").strip()
            item_name = (payload.get("itemName") or "Aetheris Mandala").strip()
            tier = (payload.get("tier") or "Tier 3 • Rare").strip()
            min_bid = max(1.0, float(payload.get("minBidCrow") or 10.0))
            if not seller:
                self._send_json({"ok": False, "error": "Seller wallet address required"}, 400)
                return
            auctions = []
            if os.path.exists(AUCTIONS_FILE):
                try:
                    with open(AUCTIONS_FILE, "r", encoding="utf-8") as f:
                        auctions = json.load(f)
                except Exception:
                    auctions = []
            auction_id = f"auc_{int(time.time())}_{secrets.token_hex(3)}"
            blk = mine_block_in_supabase(
                "MANDALOZ_AUCTION_LIST",
                seller,
                TREASURY_ADDRESS,
                amount_cents=0,
                crow_amount=min_bid,
                metadata={"auction_id": auction_id, "item_name": item_name, "tier": tier, "min_bid_crow": min_bid},
            )
            entry = {
                "auction_id": auction_id,
                "seller": seller,
                "item_name": item_name,
                "tier": tier,
                "item_data": payload.get("itemData") or None,
                "min_bid_crow": min_bid,
                "current_bid_crow": min_bid,
                "highest_bidder": None,
                "bid_count": 0,
                "status": "active",
                "block_number": blk["block_number"],
                "tx_hash": blk["tx_hash"],
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            auctions.insert(0, entry)
            with open(AUCTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(auctions[:100], f, indent=2)
            self._send_json({"ok": True, "auction": entry, "block": blk})
            return

        if parsed == "/api/auction/bid":
            auction_id = (payload.get("auctionId") or "").strip()
            bidder = (payload.get("bidder") or "").strip()
            bid_crow = float(payload.get("bidCrow") or 0)
            if not auction_id or not bidder or bid_crow <= 0:
                self._send_json({"ok": False, "error": "auctionId, bidder, and positive bidCrow required"}, 400)
                return
            if not os.path.exists(AUCTIONS_FILE):
                self._send_json({"ok": False, "error": "Auction not found"}, 404)
                return
            with open(AUCTIONS_FILE, "r", encoding="utf-8") as f:
                auctions = json.load(f)
            target = next((a for a in auctions if a.get("auction_id") == auction_id), None)
            if not target or target.get("status") != "active":
                self._send_json({"ok": False, "error": "Active auction not found"}, 404)
                return
            min_required = float(target["current_bid_crow"]) + (1.0 if target.get("highest_bidder") else 0.0)
            if bid_crow < min_required:
                self._send_json({"ok": False, "error": f"Bid must be at least {min_required:.2f} CROW"}, 400)
                return
            _, b_rows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(bidder)}&limit=1")
            if not b_rows:
                self._send_json({"ok": False, "error": "Bidder wallet not found in Supabase"}, 404)
                return
            if float(b_rows[0].get("crow_balance") or 0) < bid_crow:
                self._send_json({"ok": False, "error": "Insufficient CROW balance for bid"}, 400)
                return
            blk = mine_block_in_supabase(
                "MANDALOZ_AUCTION_BID",
                bidder,
                target["seller"],
                amount_cents=0,
                crow_amount=bid_crow,
                metadata={"auction_id": auction_id, "item_name": target["item_name"], "bid_crow": bid_crow},
            )
            target["current_bid_crow"] = bid_crow
            target["highest_bidder"] = bidder
            target["bid_count"] = int(target.get("bid_count") or 0) + 1
            target["last_bid_block"] = blk["block_number"]
            with open(AUCTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(auctions, f, indent=2)
            self._send_json({"ok": True, "auction": target, "block": blk})
            return

        if parsed == "/api/auction/settle":
            auction_id = (payload.get("auctionId") or "").strip()
            if not os.path.exists(AUCTIONS_FILE):
                self._send_json({"ok": False, "error": "Auction not found"}, 404)
                return
            with open(AUCTIONS_FILE, "r", encoding="utf-8") as f:
                auctions = json.load(f)
            target = next((a for a in auctions if a.get("auction_id") == auction_id), None)
            if not target or target.get("status") != "active":
                self._send_json({"ok": False, "error": "Active auction not found"}, 404)
                return
            winner = target.get("highest_bidder")
            if not winner:
                target["status"] = "cancelled"
                if target.get("item_data"):
                    players = load_mandaloz_players()
                    seller_addr = target.get("seller")
                    if seller_addr in players:
                        players[seller_addr].setdefault("collection", []).append(target["item_data"])
                        save_mandaloz_players(players)
                with open(AUCTIONS_FILE, "w", encoding="utf-8") as f:
                    json.dump(auctions, f, indent=2)
                self._send_json({"ok": True, "auction": target, "message": "Auction closed with no bids (item returned to seller)."})
                return
            amt = float(target["current_bid_crow"])
            _, w_rows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(winner)}&limit=1")
            _, s_rows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(target['seller'])}&limit=1")
            if not w_rows or not s_rows:
                self._send_json({"ok": False, "error": "Winner or seller wallet missing"}, 404)
                return
            w_crow = float(w_rows[0].get("crow_balance") or 0)
            s_crow = float(s_rows[0].get("crow_balance") or 0)
            if w_crow < amt:
                self._send_json({"ok": False, "error": "Winner no longer has enough CROW"}, 400)
                return
            supa_rest(f"accounts?address=eq.{urllib.parse.quote(winner)}", method="PATCH", body={"crow_balance": w_crow - amt})
            supa_rest(f"accounts?address=eq.{urllib.parse.quote(target['seller'])}", method="PATCH", body={"crow_balance": s_crow + amt})
            blk = mine_block_in_supabase(
                "MANDALOZ_AUCTION_SETTLE",
                winner,
                target["seller"],
                amount_cents=0,
                crow_amount=amt,
                metadata={"auction_id": auction_id, "item_name": target["item_name"], "settled_crow": amt},
            )
            target["status"] = "settled"
            target["settled_block"] = blk["block_number"]
            if target.get("item_data"):
                players = load_mandaloz_players()
                if winner not in players:
                    players[winner] = default_mandaloz_player(winner)
                idata = target["item_data"]
                icat = (idata.get("category") or "mandala").lower()
                if icat == "pouch":
                    players[winner].setdefault("pouches", []).append(idata)
                elif icat == "ability":
                    players[winner].setdefault("abilities", []).append(idata)
                elif icat in ("armor", "weapon"):
                    players[winner].setdefault("gear", []).append(idata)
                elif icat in ("potion", "arrows", "treats", "ring"):
                    players[winner].setdefault("consumables", []).append(idata)
                elif icat == "familiar":
                    players[winner].setdefault("familiars", []).append(idata)
                elif icat == "egg":
                    players[winner].setdefault("eggs", []).append(idata)
                elif icat == "mount":
                    players[winner].setdefault("mounts", []).append(idata)
                elif icat == "house":
                    players[winner].setdefault("houses", []).append(idata)
                elif icat == "materials":
                    mats = players[winner].setdefault("materials", {})
                    for mk, mv in (idata.get("bundle") or {}).items():
                        mats[mk] = int(mats.get(mk, 0)) + int(mv)
                else:
                    players[winner].setdefault("collection", []).append(idata)
                players[winner]["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                save_mandaloz_players(players)
            with open(AUCTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(auctions, f, indent=2)
            self._send_json({"ok": True, "auction": target, "block": blk})
            return

        if parsed == "/api/mandaloz/player":
            addr = (payload.get("address") or "").strip()
            if not addr:
                self._send_json({"ok": False, "error": "address required"}, 400)
                return
            players = load_mandaloz_players()
            p = players.get(addr) or default_mandaloz_player(addr, payload.get("username", ""))
            for k in ("username", "level", "xp", "fusionShards", "wins", "energy", "energyDate", "dailyRewardDate", "dailyRewardCrow", "pouch", "pouches", "materials", "pendingMints", "abilities", "gear", "consumables", "mounts", "houses", "familiars", "eggs", "wildEncounter", "ringShards", "trialsCleared", "rings", "petDen", "battleBoost", "equipped", "collection", "realmHarvests", "stats", "claimedChallenges"):
                if k in payload and payload[k] is not None:
                    p[k] = payload[k]
            p["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            players[addr] = p
            save_mandaloz_players(players)
            self._send_json({"ok": True, "player": p})
            return

        if parsed == "/api/mandaloz/bot/toggle":
            cfg = load_mandaloz_bot()
            cfg["enabled"] = not bool(cfg.get("enabled", True))
            save_mandaloz_bot(cfg)
            self._send_json({"ok": True, "bot": cfg})
            return

        if parsed == "/api/mandaloz/bot/run_now":
            slot_name = (payload.get("slot") or "").strip() or None
            res = execute_mandaloz_bot_drop(slot_name=slot_name, manual=True)
            self._send_json(res)
            return

        if parsed == "/api/mandaloz/nft/mint":
            addr = (payload.get("address") or "").strip()
            action = (payload.get("action") or "MINT").strip().upper()
            nft = payload.get("nft") or {}
            cost_crow = float(payload.get("costCrow") or 0.0)
            reward_crow = float(payload.get("rewardCrow") or 0.0)
            parent_ids = payload.get("parentIds") or []
            if not addr or not nft.get("name"):
                self._send_json({"ok": False, "error": "address and nft required"}, 400)
                return
            _, rows = supa_rest(f"accounts?address=eq.{urllib.parse.quote(addr)}&limit=1")
            if not rows:
                self._send_json({"ok": False, "error": "Wallet not found in Supabase"}, 404)
                return
            cur_crow = float(rows[0].get("crow_balance") or 0)
            if cost_crow > 0:
                if cur_crow < cost_crow:
                    self._send_json({"ok": False, "error": f"Insufficient CROW balance (need {cost_crow} CROW)"}, 400)
                    return
                supa_rest(f"accounts?address=eq.{urllib.parse.quote(addr)}", method="PATCH", body={"crow_balance": cur_crow - cost_crow})
            elif reward_crow > 0:
                supa_rest(f"accounts?address=eq.{urllib.parse.quote(addr)}", method="PATCH", body={"crow_balance": cur_crow + reward_crow})
            tx_type = f"MANDALOZ_NFT_{action}"
            blk = mine_block_in_supabase(
                tx_type,
                addr if cost_crow > 0 else TREASURY_ADDRESS,
                TREASURY_ADDRESS if cost_crow > 0 else addr,
                amount_cents=0,
                crow_amount=cost_crow if cost_crow > 0 else reward_crow,
                metadata={
                    "nft_id": nft.get("id"),
                    "name": nft.get("name"),
                    "tier": nft.get("tier"),
                    "rarity": nft.get("rarity"),
                    "pattern": nft.get("pattern"),
                    "elements": nft.get("elements"),
                    "fusionPower": nft.get("fusionPower"),
                    "marketValue": nft.get("marketValue"),
                    "parentIds": parent_ids,
                    "action": action,
                },
            )
            nft["mintBlock"] = blk["block_number"]
            nft["txHash"] = blk["tx_hash"]
            self._send_json({"ok": True, "nft": nft, "block": blk})
            return

        self._send_json({"ok": False, "error": "Unknown endpoint"}, 404)


if __name__ == "__main__":
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    threading.Thread(target=mandaloz_bot_scheduler_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 8910))
    host = os.environ.get("HOST", "0.0.0.0")
    srv = ThreadingHTTPServer((host, port), WalletHandler)
    print(f"Maz MandalOz 3D & CROW Wallet running at http://{host}:{port}/")
    srv.serve_forever()
