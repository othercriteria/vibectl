# vibectl

*A vibes‑first alternative to kubectl — because clusters deserve good vibes too.*

---

## ✨ Why vibectl?

Managing Kubernetes shouldn’t feel like editing an INI file through a periscope. *vibectl* wraps plain‑English intent, a dash of emoji, and an LLM planner around ordinary `kubectl`, giving you **memory‑aware, conversational control** of any cluster. Keep using every manifest, context, and kube‑config you already have – just add vibes.

---

## 🚀 Feature Highlights

| Category                    | What it does                                                                 |
| --------------------------- | ---------------------------------------------------------------------------- |
| **Conversational Commands** | `vibectl get vibe pods` → natural‑language queries for any verb.             |
| **LLM Planner**             | Structured JSON contracts ensure predictable plans that you confirm.         |
| **Memory System**           | Context persists between invocations (`vibectl memory ...`).                   |
| **Semi‑Autonomous Loops**   | `vibectl semiauto` iteratively proposes & executes safe changes.             |
| **Full Autonomy**           | `vibectl vibe` plans, confirms, executes, summarises, updates memory.        |
| **Rich TUI**                | Live *watch*, *logs ‑f*, *port‑forward* with pause/filter/save key‑bindings. |
| **Traffic Proxy**           | Optional middle‑proxy shows per‑session throughput & errors.                 |
| **Chaos / Demo Tooling**    | Drop‑in sandbox demos for CTFs, Kafka tuning, Chaos‑Monkey battles.          |
| **Intelligent Apply**       | `vibectl apply vibe` autocorrects or generates manifests before applying.    |

> **New in 0.8.x**  `vibectl diff` for live comparisons and the new intelligent apply workflow.

---

## 🛠 Installation

### Via pip (any OS)

```bash
pip install vibectl            # core CLI
pip install llm-anthropic      # Claude (default)
# or: pip install llm-openai   # OpenAI models
# or: pip install llm-ollama   # local Ollama models
```

### Via Nix flakes (NixOS & friends)

```bash
git clone https://github.com/othercriteria/vibectl.git
cd vibectl
flake develop        # drops you into a fully wired shell
```

---

## 🔑 Configure an LLM key

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # quickest
vibectl config set model claude-3.7-sonnet
```

More options?  See `docs/MODEL_KEYS.md`.

---

## ⏱ 60‑Second Tour

### 1 – Ask for a vibe check

```bash
❯ vibectl get vibe pods
🔄 Consulting claude-3.7-sonnet for a plan…
🔄 Running: kubectl get pods -n sandbox
✨ Vibe check:
🚀 3 nginx‑demo pods in deployment 🌟
```

### 2 – Persist a fact

```bash
vibectl memory set "We're working in 'sandbox' namespace."
```

### 3 – Iterate with *semiauto*

```bash
vibectl semiauto "set up a demo redis"
# …you confirm each command (`y / n / a / b / m / e`)
```

### 4 – One‑liner natural language

```bash
vibectl scale vibe "nginx‑demo down to 1 replica"
```

### 5 – Rich port‑forward session

```bash
vibectl port-forward vibe "nginx-demo-service to 8090"
# Keybindings:  P‑pause  W‑wrap  F‑filter  S‑save  E‑exit
```

### 6 – Live event watch

```bash
vibectl events -n sandbox --watch
```

---

## 📚 Command Cheatsheet

| Mode                                                | When to use                                 | Example                                        |
| --------------------------------------------------- | ------------------------------------------- | ---------------------------------------------- |
| *Just* pass‑through                                 | You want raw `kubectl`                      | `vibectl just get pods -A`                     |
| **get / describe / scale / delete / logs / events** | Familiar verbs, plus AI summary             | `vibectl get pods`           |
| **vibe**                                            | Full autonomous planner                     | `vibectl vibe "deploy redis with persistence"` |
| **semiauto**                                        | Step‑wise interactive planner               | `vibectl semiauto`                             |
| **auto**                                            | Non‑interactive loops (used by agents) | `vibectl auto "keep latency <50 ms"`    |

---

## 🧠 Memory Commands

```bash
vibectl memory show          # view
vibectl memory set "..."        # replace
vibectl memory set --edit    # $EDITOR
vibectl memory disable|enable
vibectl memory clear
```

The planner sees memory every turn, so write facts, goals, and preferences there.

---

## 🎮 Interactive UI Details

### Watch / Logs / Events

* Live table updates with elapsed time & line count
* `P` pause display `W` wrap `F` regex filter `S` save buffer `E` exit
* Upon exit vibectl prints a metrics table **plus** an LLM‑generated summary.

### Port‑Forward Enhancements

Configure a proxy port range once:

```bash
vibectl config set intermediate_port_range 10000-11000
```

Every `port-forward` thereafter shows bytes ⇅, connection duration, errors, and a colourful recap.

---

## ⚙️ Key Configuration Knobs (`vibectl config`)

| Key                      | Default             | Why you’d change it                              |
| ------------------------ | ------------------- | ------------------------------------------------ |
| `model`                  | `claude-3.7-sonnet` | Switch to `gpt-4o`, `ollama:llama3:latest`, etc. |
| `show_metrics`           | `false`             | View LLM tokens & latency.                       |
| `show_raw_output`        | `false`             | Always print raw kubectl output.                 |
| `theme`                  | `dark`              | `light` / `system` / custom.                     |
| `live_display_max_lines` |  `20`               | Default visible buffer for watch/logs.           |

Full schema in `docs/CONFIG.md`.

---

## 📦 Demo Environments

| Demo                 | What it shows                            | Path                                     |
| -------------------- | ---------------------------------------- | ---------------------------------------- |
| **Bootstrap**        | k3d + Ollama self‑contained playground   | `examples/k8s-sandbox/bootstrap/`        |
| **CTF Sandbox**      | vibectl autonomously solves staged flags | `examples/k8s-sandbox/ctf/`              |
| **Chaos Monkey**     | Red vs Blue vibectl agents battle        | `examples/k8s-sandbox/chaos-monkey/`     |
| **Kafka Throughput** | vibectl tunes Kafka via agent loop       | `examples/k8s-sandbox/kafka-throughput/` |

Each demo has its own `README.md` with step‑by‑step instructions.

---

## 🧪 Development & Testing

```bash
flake develop     # or: make install-dev
make check        # ruff + mypy + pytest
make test-fast    # quick subset
make bump-patch   # bump version with changelog guard
```

Pre‑commit hooks enforce Ruff lint/format; CI targets 100 % coverage (see `TESTING.md`).

---

## 🤝 Contributing

Pull requests welcome!  Start with an issue or draft PR so we can vibe‑check the idea.  All contributors agree to the [MIT License](LICENSE).

---

© 2025 Daniel Klein & the vibectl community.  Spread good vibes — even to your clusters.
