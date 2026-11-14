/**
 * AtAA CROW Chain Cloud SDK
 * Drop into any web game (MandalOz 3D, A-Stack'd, Echo-Scout AI) on allwaysalways.net
 * Connects 24/7 to the live Supabase Edge Function node (no local PC required).
 */
(function (global) {
  const DEFAULT_CLOUD_URL = "https://urfhlxdlanncpfqtdkvb.supabase.co/functions/v1/crow-chain";

  class CrowChainClient {
    constructor(baseUrl = DEFAULT_CLOUD_URL) {
      this.baseUrl = baseUrl.replace(/\/+$/, "");
    }

    async _req(path, method = "GET", body = null) {
      const opts = { method, headers: { "Content-Type": "application/json" } };
      if (body !== null) opts.body = JSON.stringify(body);
      const res = await fetch(`${this.baseUrl}${path}`, opts);
      return await res.json();
    }

    async getState() {
      return await this._req("/state", "GET");
    }

    async verifyChain() {
      return await this._req("/verify", "GET");
    }

    async getTokenomics() {
      return await this._req("/tokenomics", "GET");
    }

    async createWallet(label = "Game Player", address = "") {
      return await this._req("/wallets/create", "POST", { label, address });
    }

    async claimFaucet(address, crowAmount = 250, usdCents = 5000) {
      return await this._req("/wallets/faucet", "POST", { address, crowAmount, usdCents });
    }

    async reward(address, crowAmount, gameName = "MandalOz 3D", reason = "Quest Victory") {
      return await this._req("/game/reward", "POST", { address, crowAmount, gameName, reason });
    }

    async spend(address, crowAmount, gameName = "MandalOz 3D", reason = "In-Game Purchase") {
      return await this._req("/game/spend", "POST", { address, crowAmount, gameName, reason });
    }

    async runStressTest(txCount = 5000, anchorBlock = true) {
      return await this._req("/stress_test", "POST", { txCount, anchorBlock });
    }
  }

  global.CrowChain = new CrowChainClient();
  global.CrowChainClient = CrowChainClient;
  global.NovaSDK = global.CrowChain;
  global.CrowCoin = global.CrowChain;
})(typeof window !== "undefined" ? window : globalThis);
