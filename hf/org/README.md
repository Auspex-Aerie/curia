---
title: Auspex Aerie
emoji: 🦅
colorFrom: yellow
colorTo: green
sdk: static
pinned: false
---

# Auspex Aerie

Models and datasets from **Auspex Labs** under the **[Auspex-Aerie](https://huggingface.co/auspex-aerie)** org (same name as [GitHub](https://github.com/Auspex-Aerie)).

We publish more than one product line:

| Collection | Focus |
|------------|--------|
| **curia** | Multi-model deliberation grounded in code ([GitHub](https://github.com/Auspex-Aerie/curia)) |
| **netflow-anomaly** | Netflow / traffic anomaly scoring *(artifacts landing over time)* |
| **domain-lexicon** | Lexical malicious-domain prediction *(planned)* |
| **brand-protection** | Spoof / lookalike detection *(planned)* |
| **text-compression** | Neural text compression *(planned)* |

## Curia (first public artifacts)

- Dataset: [`curia-router-labels`](https://huggingface.co/datasets/auspex-aerie/curia-router-labels)
- Recipe card: [`curia-grounding-config`](https://huggingface.co/auspex-aerie/curia-grounding-config)

We **cite** upstream Hub models (ColBERT, Jina, MiniLM) rather than re-host multi-GB third-party weights.

## Naming

`Auspex-Aerie/<product>-<role>[-vN]` — knobs live in cards/`config.json`, not in the id. Details: [hf_hub.md in Curia](https://github.com/Auspex-Aerie/curia/blob/main/docs/hf_hub.md).
