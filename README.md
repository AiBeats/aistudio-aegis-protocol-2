# ABV Sovereign Stack

Modular AI-powered security and system management platform. Bifurcated architecture with **public** consumer-facing modules and **private** tactical-grade defense layers.

## Architecture

```
                        ┌──────────────────────────────────────┐
                        │          ABV Sovereign Stack          │
                        └──────────────┬───────────────────────┘
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 │                     │                     │
        ┌────────▼────────┐   ┌────────▼────────┐   ┌───────▼────────┐
        │   PUBLIC LAYER  │   │  COMMON UTILS   │   │ PRIVATE LAYER  │
        │  (Consumer API) │   │  Config / Logs  │   │  (Tactical)    │
        └────────┬────────┘   │  Feature Flags  │   └───────┬────────┘
                 │            └─────────────────┘           │
    ┌────────────┼────────────┐              ┌──────────────┼──────────────┐
    │            │            │              │              │              │
┌───▼───┐  ┌────▼────┐  ┌────▼────┐   ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
│Fortress│  │Protocol │  │ Crystal │   │ Sentry  │   │Transport│   │  Mesh   │
│Thermal │  │   A3    │  │  Vault  │   │Bio/Mesh │   │GPS Teth.│   │Heartbeat│
│  SOS   │  │ NetFP   │  │AES-256  │   │Duress   │   │Travel   │   │  TOTP   │
└───┬───┘  └────┬────┘  └────┬────┘   └────┬────┘   └────┬────┘   └────┬────┘
    │            │            │              │              │              │
    └────────────┴────────────┴──────────────┴──────────────┴──────────────┘
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 │                     │                     │
        ┌────────▼────────┐   ┌────────▼────────┐   ┌───────▼────────┐
        │    Wear OS      │   │    ESP32 Fob    │   │  React Decoy   │
        │ SovereignPulse  │   │   Ghost Fob     │   │  BSOD/Update   │
        └─────────────────┘   └─────────────────┘   └────────────────┘
```

## Modules

### Fortress — Thermal Governor
Adaptive CPU/GPU thermal monitoring and throttling optimized for Ryzen and Nvidia AI workloads. Monitors system temperatures via `psutil` and applies intelligent throttle logic across four thermal zones (Nominal, Elevated, Throttle, Critical).

### Fortress — SOS Listener
HTTP/SMS relay listener for remote lock and wipe commands. All commands are verified using HMAC-SHA256 signatures with replay protection. Exposes a Flask-based endpoint for integration with external alerting systems.

### Protocol-A3 — Network Fingerprinting
Detects the current network environment by analyzing SSID, gateway MAC address, public IP geolocation, and VPN/mesh connectivity. Classifies environments as Home, Office, Transit, or Unknown to enable context-aware security policies.

### Crystal Vault — Encrypted Storage
AES-256-GCM encrypted file vault with custom `.cryst` container format. Features an encrypted File Allocation Table (FAT) for fast directory listing, mount/unmount semantics, and secure destruction capabilities.

### Common Utilities
Shared configuration management, structured logging, and environment-driven feature flags used across all modules.

## Installation

```bash
# Clone the repository
git clone https://github.com/AiBeats/ABV_Sovereign.git
cd ABV_Sovereign

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your actual values
```

## Usage

### Thermal Governor
```python
from src.public.fortress import ThermalGovernor

governor = ThermalGovernor()
actions = governor.evaluate()  # Single evaluation cycle
# governor.run()               # Continuous monitoring loop
```

### SOS Listener
```python
from src.public.fortress import SOSListener

listener = SOSListener()
app = listener.create_flask_app()
app.run(host="0.0.0.0", port=9000)
```

### Protocol-A3
```python
from src.public.protocol_a3 import ProtocolA3

proto = ProtocolA3()
fp = proto.fingerprint()
env = proto.classify(fp)
print(f"Environment: {env.value}")
```

### Crystal Vault
```python
from src.public.crystal import VaultClientAPI

api = VaultClientAPI("/path/to/vault.cryst")
api.create("my-passphrase")
api.add("secret.txt", b"classified content")
data = api.read("secret.txt")
api.close()
```

### Sanitize Build (Public Release)
```bash
python sanitize_build.py
# Outputs sanitized public build to public_dist/
```

## OpenClaw + MetaClaw Integration

The ABV Sovereign Stack is designed to integrate with the **OpenClaw** AI agent gateway and **MetaClaw** meta-coordination layer:

- **OpenClaw Gateway**: Routes commands between messaging platforms (Discord, Telegram, etc.) and the Sovereign Stack's SOS Listener and Protocol-A3 modules. Enables remote status queries, environment checks, and emergency commands through conversational AI interfaces.

- **MetaClaw Coordination**: Meta-layer that orchestrates multiple AI agents across the Sovereign Stack. Manages policy decisions (when to escalate, which modules to activate) based on combined signals from thermal monitoring, network fingerprinting, and vault status.

- **LOCAL-MIND Frontend**: Desktop AI OS that serves as the primary UI for local model interaction. Displays Sovereign Stack dashboards, vault management, and thermal status through a unified interface.

- **Project Crystal Core**: 5D optical storage simulation layer that extends the Crystal Vault with advanced storage paradigms for long-term archival of AI weights and digital media.

## Project Structure

```
ABV_Sovereign/
├── src/
│   ├── public/           # Consumer-facing modules
│   │   ├── fortress/     # Thermal governor + SOS listener
│   │   ├── protocol_a3/  # Network fingerprinting
│   │   ├── crystal/      # Encrypted file vault
│   │   └── common/       # Shared config, logging, flags
│   └── private/          # Tactical layer (not in public builds)
├── wearos/               # Wear OS heart rate + gait monitor
├── esp32/                # ESP32 BLE proximity fob firmware
├── react/                # Decoy screen components
├── tests/                # Unit tests
├── sanitize_build.py     # Strips private code for public release
├── requirements.txt
└── .env.example
```

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

---

Built by [Antonio (AiBeats)](https://github.com/AiBeats)
