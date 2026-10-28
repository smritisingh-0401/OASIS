# Sharing a test version by link

How to run OASIS with the real model on one computer and give testers a link to it (decision 2026-10-28). The host computer runs everything; testers only need a browser.

> **Made-up messages only.** The link reaches anyone who has it. The crisis wording awaits clinician review, and testing with people's real feelings needs ethics approval first (open items 4 and 5 in [memory.md](memory.md)). Demo mode shows a banner saying so on every page.

## What demo mode changes

Set `OASIS_DEMO=1` and OASIS:
- keeps every conversation in memory only, never on disk, even if a page asks to save;
- shows the demo data notice ([content/privacy/disclosure_demo.yaml](../src/oasis/content/privacy/disclosure_demo.yaml)), which says messages travel to this computer through Cloudflare and are written by a language model, and offers only "Start without saving";
- shows a "Test version. Use made-up messages only" banner on every page.

Two limits apply in every mode and matter most on a link: a request body over 16 KB is refused even without a `Content-Length`, and at most 1000 unsaved conversations are held at once (`OASIS_MAX_EPHEMERAL_SESSIONS`); beyond that a new visitor gets "busy".

## What the host computer needs

| | |
|---|---|
| Memory | 8 GB or more; 32 GB keeps the 4 GB model in memory with room to spare |
| Software | Git, [uv](https://docs.astral.sh/uv/), llama.cpp, cloudflared |
| Network | An internet connection; no router or firewall change (the tunnel connects out) |
| Uptime | The link works only while this computer is on, awake and running the three programs below |

## 1. Install (once)

Windows (PowerShell); on macOS use `brew install llama.cpp cloudflared` instead of the two winget lines.

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```powershell
winget install ggml.llamacpp
```

```powershell
winget install --id Cloudflare.cloudflared
```

Open a new terminal, then:

```powershell
git clone https://github.com/smritisingh-0401/OASIS.git
```

```powershell
cd OASIS
```

```powershell
uv sync
```

Create `.env` in the `OASIS` folder with:

```
OASIS_DEMO=1
OASIS_LLM_BACKEND=llama_server
OASIS_STORAGE_BACKEND=memory
```

## 2. Start (each session), in three terminals

**Terminal 1, the model.** The first start downloads it (2.7 GB):

```powershell
llama-server -hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj --jinja -c 4096 -np 1 -ngl 0 --host 127.0.0.1 --port 8080
```

`-ngl 0` keeps the model on the CPU. With a graphics card that has 4 GB or more of its own memory, leave it out to use the card.

**Terminal 2, OASIS**, from the `OASIS` folder:

```powershell
uv run uvicorn oasis.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

**Terminal 3, the link:**

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

It prints a link like `https://some-random-words.trycloudflare.com`. Open it yourself first: you should see the banner and "Before you start: test version". Then share it.

## 3. While testers use it

- Replies come one at a time. With two waiting, a third person gets "busy" and can send again.
- Keep the computer awake (Windows: Settings, System, Power, set sleep to Never while testing).
- The link changes every time `cloudflared` restarts. A link that stays the same needs a free Cloudflare account and a domain you own (a named tunnel).
- To stop, press Ctrl+C in all three terminals. Every conversation is gone once OASIS stops.

## What testers see and what is kept

Testers type into the page; the messages go through Cloudflare's network to this computer. Nothing is written to disk. OASIS's logs hold timings and decisions, never words, and the terminal running OASIS shows the same. Anyone with access to this computer while it runs controls it, which is why the notice asks for made-up messages.
