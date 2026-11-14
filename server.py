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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
ENV_FILE = os.path.join(BASE_DIR, ".env")
TREASURY_ADDRESS = "0xF21905EE23f7A8B66d4cda83C0Dec3EA8258B2Bd"
CHAIN_LOCK = threading.Lock()
PRICE_CACHE = {"ts": 0.0, "prices": {}}
SIGNAL_CACHE = {"ts": 0.0, "signals": []}

# Pyth Hermes Mainnet Price Feed IDs
PYTH_FEEDS = {
    "ETH": "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "BTC": "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    "SOL": "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "POL": "0xffd11c5a1cfd42f80afb2df4d9c264c15f956d68153336374649f56509dc5720",
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
        for sym in ("ETH", "BTC", "SOL", "POL"):
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
    for sym in ("ETH", "BTC", "SOL", "POL"):
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
            if rsi <= 34:
                action = "BUY"
                confidence = 78
                reasons.append(f"RSI-14 is {rsi:.1f} (oversold dip)")
            elif rsi >= 68:
                action = "SELL"
                confidence = 76
                reasons.append(f"RSI-14 is {rsi:.1f} (overbought zone)")
            elif sma7 > sma24 * 1.005 and rsi < 64:
                action = "BUY"
                confidence = 68
                reasons.append(f"7h avg (${sma7:,.2f}) crossed above 24h avg (${sma24:,.2f})")
            elif sma7 < sma24 * 0.995 and rsi > 38:
                action = "SELL"
                confidence = 65
                reasons.append(f"7h avg (${sma7:,.2f}) slipped below 24h avg (${sma24:,.2f})")
            else:
                reasons.append(f"RSI-14 neutral at {rsi:.1f}; 7h avg (${sma7:,.2f}) near 24h avg (${sma24:,.2f})")

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

        return {"block_number": next_num, "block_hash": bhash, "nonce": nonce, "tx_hash": tx_hash}


def verify_chain_integrity():
    """Verify sequential block numbers, previous_hash links, and PoW prefixes across all Supabase blocks."""
    t0 = time.perf_counter()
    st, rows = supa_rest("blocks?select=block_number,block_hash,previous_hash,nonce,difficulty&order=block_number.asc&limit=5000")
    if st != 200 or not isinstance(rows, list):
        return {"ok": False, "error": f"Failed to load blocks: {rows}"}
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
    tx_count = max(100, min(50000, int(tx_count)))
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

        if parsed == "/api/agent/policy":
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

        if parsed == "/api/chain/stress_test":
            tx_count = int(payload.get("txCount") or 5000)
            anchor_block = bool(payload.get("anchorBlock", True))
            try:
                res = run_chain_stress_test(tx_count=tx_count, anchor_block=anchor_block)
                self._send_json(res)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        self._send_json({"ok": False, "error": "Unknown endpoint"}, 404)


if __name__ == "__main__":
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    port = int(os.environ.get("PORT", 8910))
    srv = ThreadingHTTPServer(("127.0.0.1", port), WalletHandler)
    print(f"AllwaysAlways AgentKit Wallet & Pyth Oracle running at http://127.0.0.1:{port}/")
    srv.serve_forever()
