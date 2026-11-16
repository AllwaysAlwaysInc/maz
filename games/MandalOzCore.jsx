import { useState, useEffect } from "react";

/**
 * MandalOzCore — Connected to CROW Chain via window.CrowChain (public/crow_sdk.js).
 * All currency, market sales, and auction listings use CROW instead of legacy Echo/local coins.
 */
export default function MandalozCore({ walletAddress = "" }) {
  const [playerTier, setPlayerTier] = useState(1);
  const [mandalaCollection, setMandalaCollection] = useState([]);
  const [fusionShards, setFusionShards] = useState(20);
  const [marketPrices, setMarketPrices] = useState({});
  const [activeEvents, setActiveEvents] = useState([]);
  const [chainStatus, setChainStatus] = useState("Connected to CROW Chain");
  const [playerStats, setPlayerStats] = useState({
    level: 1,
    experience: 0,
    crow: 1000,
    fusionPower: 100
  });
  const [currentView, setCurrentView] = useState("collection");
  const [selectedMandala, setSelectedMandala] = useState(null);

  const TIER_REQUIREMENTS = {
    1: { name: "Novice", exp: 0, fusionPower: 100, color: "#9ca3af" },
    2: { name: "Apprentice", exp: 1000, fusionPower: 500, color: "#60a5fa" },
    3: { name: "Adept", exp: 5000, fusionPower: 2000, color: "#a78bfa" },
    4: { name: "Master", exp: 20000, fusionPower: 8000, color: "#f59e0b" },
    5: { name: "Grandmaster", exp: 100000, fusionPower: 32000, color: "#ef4444" },
    6: { name: "Archon", exp: 500000, fusionPower: 128000, color: "#10b981" },
    7: { name: "Aetheris", exp: 2500000, fusionPower: 512000, color: "#fbbf24" }
  };

  const RARITY_LEVELS = {
    common: { chance: 50, color: "#9ca3af", multiplier: 1 },
    uncommon: { chance: 30, color: "#60a5fa", multiplier: 1.5 },
    rare: { chance: 15, color: "#a78bfa", multiplier: 2 },
    epic: { chance: 4, color: "#f59e0b", multiplier: 3 },
    legendary: { chance: 1, color: "#ef4444", multiplier: 5 }
  };

  useEffect(() => {
    setMandalaCollection([
      { id: 1, name: "Circle of Beginnings", tier: 1, rarity: "common", pattern: "circular", elements: ["earth"], fusionPower: 60, marketValue: 100 },
      { id: 2, name: "Triangle of Balance", tier: 1, rarity: "common", pattern: "triangular", elements: ["water"], fusionPower: 75, marketValue: 100 },
      { id: 3, name: "Square of Stability", tier: 1, rarity: "uncommon", pattern: "square", elements: ["earth", "fire"], fusionPower: 110, marketValue: 150 },
      { id: 4, name: "Pentacle of Elements", tier: 2, rarity: "rare", pattern: "pentagonal", elements: ["fire", "water", "earth", "air", "spirit"], fusionPower: 180, marketValue: 200 }
    ]);
  }, []);

  const generateMandala = async () => {
    if (playerStats.crow < 100) {
      setChainStatus("Not enough CROW! Need 100 CROW to mint a Mandala.");
      return;
    }
    const roll = Math.random() * 100;
    let rarity = "common";
    let cumulative = 0;
    for (const [rarityName, rarityData] of Object.entries(RARITY_LEVELS)) {
      cumulative += rarityData.chance;
      if (roll < cumulative) {
        rarity = rarityName;
        break;
      }
    }
    const patterns = ["circular", "triangular", "square", "pentagonal", "hexagonal", "octagonal"];
    const elements = ["fire", "water", "earth", "air", "spirit", "light", "shadow"];
    const el = elements[Math.floor(Math.random() * elements.length)];
    const pat = patterns[Math.floor(Math.random() * patterns.length)];

    const newMandala = {
      id: Date.now(),
      name: `${el.charAt(0).toUpperCase() + el.slice(1)} ${pat.charAt(0).toUpperCase() + pat.slice(1)}`,
      tier: Math.min(playerTier, 3),
      rarity,
      pattern: pat,
      elements: [el],
      fusionPower: Math.floor(Math.random() * 100) + 50,
      marketValue: Math.round(100 * RARITY_LEVELS[rarity].multiplier)
    };

    if (window.CrowChain && walletAddress) {
      const res = await window.CrowChain.spend(walletAddress, 100, "MandalOz 3D", `Mint ${newMandala.name}`);
      if (!res?.ok) {
        setChainStatus(res?.error || "CROW Chain mint failed.");
        return;
      }
      setChainStatus(`Minted ${newMandala.name} on CROW Chain • Block #${res.block?.block_number}`);
    }

    setMandalaCollection(prev => [...prev, newMandala]);
    setPlayerStats(prev => ({ ...prev, crow: prev.crow - 100 }));
  };

  const fuseMandalas = async (mandala1, mandala2) => {
    if (fusionShards < 10) {
      setChainStatus("Need 10 Fusion Shards to fuse Mandalas.");
      return;
    }
    const fusedMandala = {
      id: Date.now(),
      name: `Fused ${mandala1.name} + ${mandala2.name}`,
      tier: Math.max(mandala1.tier, mandala2.tier) + 1,
      rarity:
        mandala1.rarity === "legendary" || mandala2.rarity === "legendary" ? "legendary" :
        mandala1.rarity === "epic" || mandala2.rarity === "epic" ? "epic" :
        mandala1.rarity === "rare" || mandala2.rarity === "rare" ? "rare" : "uncommon",
      pattern: mandala1.pattern,
      elements: [...new Set([...mandala1.elements, ...mandala2.elements])],
      fusionPower: (mandala1.fusionPower || 50) + (mandala2.fusionPower || 50) + 100,
      marketValue: Math.round(((mandala1.marketValue || 100) + (mandala2.marketValue || 100)) * 1.5),
      isFusion: true,
      parents: [mandala1.id, mandala2.id]
    };

    if (window.CrowChain && walletAddress) {
      const res = await window.CrowChain.reward(walletAddress, 25, "MandalOz 3D", `Fusion Bonus: ${fusedMandala.name}`);
      if (res?.ok) {
        setChainStatus(`Fused on CROW Chain (+25 CROW bonus) • Block #${res.block?.block_number}`);
      }
    }

    setMandalaCollection(prev => prev.filter(m => m.id !== mandala1.id && m.id !== mandala2.id).concat(fusedMandala));
    setFusionShards(prev => prev - 10);
    setPlayerStats(prev => ({
      ...prev,
      experience: prev.experience + 500,
      fusionPower: prev.fusionPower + fusedMandala.fusionPower
    }));
    setSelectedMandala(null);
  };

  const sellOnCrowChain = async (mandala) => {
    const price = marketPrices[mandala.id] || mandala.marketValue || 100;
    if (window.CrowChain && walletAddress) {
      const res = await window.CrowChain.reward(walletAddress, price, "MandalOz 3D", `Sold ${mandala.name}`);
      if (!res?.ok) {
        setChainStatus(res?.error || "CROW sale failed.");
        return;
      }
      setChainStatus(`Sold ${mandala.name} for ${price} CROW • Block #${res.block?.block_number}`);
    } else {
      setChainStatus(`Sold ${mandala.name} for ${price} CROW (local preview).`);
    }
    setMandalaCollection(prev => prev.filter(m => m.id !== mandala.id));
    setPlayerStats(prev => ({ ...prev, crow: prev.crow + price }));
  };

  const listOnCrowAuction = async (mandala) => {
    const minBid = marketPrices[mandala.id] || mandala.marketValue || 15;
    if (!window.CrowChain || !walletAddress) {
      setChainStatus("Connect a CROW wallet to list on the live CROW Chain Auction House.");
      return;
    }
    const res = await window.CrowChain.listAuction(walletAddress, mandala.name, minBid, `Tier ${mandala.tier} • ${mandala.rarity}`);
    if (res?.ok) {
      setMandalaCollection(prev => prev.filter(m => m.id !== mandala.id));
      setChainStatus(`Listed "${mandala.name}" on CROW Chain Auction House • Block #${res.block?.block_number}`);
    } else {
      setChainStatus(res?.error || "Failed to list auction on CROW Chain.");
    }
  };

  const generateEvent = () => {
    const ev = {
      id: Date.now(),
      name: "Aetheris Surge",
      description: "Bonus CROW rewards for fusing and listing Mandalas on CROW Chain.",
      startTime: Date.now(),
      duration: 120
    };
    setActiveEvents([ev]);
  };

  return (
    <div className="mandaloz-core">
      <div className="header-bar">
        <h3>🗡️ MandalOz 3D — Powered by CROW Chain</h3>
        <div className="chain-status">{chainStatus}</div>
        <div className="stats-bar">
          <span>Balance: {playerStats.crow} CROW</span>
          <span>Fusion Shards: {fusionShards}</span>
          <span>XP: {playerStats.experience} / {TIER_REQUIREMENTS[Math.min(playerTier + 1, 7)].exp}</span>
        </div>
      </div>

      <div className="nav-tabs">
        <button onClick={() => setCurrentView("collection")}>Collection</button>
        <button onClick={() => setCurrentView("fusion")}>Fusion</button>
        <button onClick={() => setCurrentView("market")}>Market &amp; Auctions</button>
        <button onClick={() => setCurrentView("events")}>Events</button>
        <button onClick={() => setCurrentView("realms")}>MandalOz Realms</button>
      </div>

      {currentView === "collection" && (
        <div className="collection-view">
          <button onClick={generateMandala}>✨ Mint Mandala (100 CROW)</button>
          <div className="mandala-grid">
            {mandalaCollection.map(m => (
              <div key={m.id} className="mandala-card" onClick={() => setSelectedMandala(m)}>
                <h5>{m.name}</h5>
                <p>Tier {m.tier} • {m.rarity}</p>
                <p>Value: {m.marketValue} CROW</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {currentView === "fusion" && (
        <div className="fusion-view">
          <h4>⚗️ Mandala Fusion</h4>
          <p>Cost: 10 Fusion Shards (+25 CROW Chain Bonus)</p>
          {selectedMandala && (
            <button
              onClick={() => {
                const second = mandalaCollection.find(m => m.id !== selectedMandala.id);
                if (second) fuseMandalas(selectedMandala, second);
              }}
              disabled={fusionShards < 10}
            >
              ⚗️ Fuse Selected Mandalas
            </button>
          )}
        </div>
      )}

      {currentView === "market" && (
        <div className="market-view">
          <h4>🏪 CROW Chain Market &amp; Auction House</h4>
          <div className="market-grid">
            {mandalaCollection.map(mandala => {
              const currentPrice = marketPrices[mandala.id] || mandala.marketValue;
              return (
                <div key={mandala.id} className="market-item">
                  <h5>{mandala.name}</h5>
                  <div className="price-display">
                    <span className="current-price">{currentPrice} CROW</span>
                  </div>
                  <div className="market-actions">
                    <button className="sell-btn" onClick={() => sellOnCrowChain(mandala)}>Sell for CROW</button>
                    <button className="auction-btn" onClick={() => listOnCrowAuction(mandala)}>List on CROW Auction</button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {currentView === "events" && (
        <div className="events-view">
          <h4>🎉 Limited-Time Events</h4>
          {activeEvents.map(event => (
            <div key={event.id} className="event-card">
              <h5>{event.name}</h5>
              <p>{event.description}</p>
            </div>
          ))}
          {activeEvents.length === 0 && (
            <button onClick={generateEvent}>🎲 Start Event</button>
          )}
        </div>
      )}

      {currentView === "realms" && (
        <div className="meta-view">
          <h4>🌐 MandalOz Realms (CROW Chain)</h4>
          <div className="land-plot"><h5>Plot #001 — Elemental Plains</h5></div>
          <div className="land-plot"><h5>Plot #002 — Crystal Mountains</h5></div>
        </div>
      )}
    </div>
  );
}
