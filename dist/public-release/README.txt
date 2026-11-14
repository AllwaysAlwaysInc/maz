AllwaysAlways Inc. — AgentKit Wallet, CROW Chain & Cloud SDK (Public Client Package)
================================================================================

What's Inside (Zero-Secrets Client Bundle):
- index.html      : Standalone 24/7 Cloud Wallet, Oracle, Kit Copilot & Watchdog UI
- crow_sdk.js     : Drop-in browser SDK (CrowChain, NovaSDK, CrowCoin)
- app_icon.png    : App icon
- favicon.ico     : Browser favicon

Security Notes:
- Contains ZERO server secrets, service role keys, or private keys.
- Connects over HTTPS to the Supabase Cloud Edge Function (`crow-chain`)
  protected by AtAA Watchdog (30 writes / 60s rate limit) & SentryGuard caps.
- Designed to be hosted on https://allwaysalways.net or downloaded as a ZIP.

Quick Start:
- Open `index.html` in any modern browser, OR upload this folder to your
  `allwaysalways.net` static hosting / downloads directory.
