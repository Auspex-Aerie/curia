# Hugging Face packages (Auspex)

Sources for first-party Hub artifacts under the **`auspex-aerie`** HF user
(GitHub org remains `Auspex-Aerie`).

## Published

| Local dir | Hub id | Type |
|-----------|--------|------|
| `curia-router-labels/` | [auspex-aerie/curia-router-labels](https://huggingface.co/datasets/auspex-aerie/curia-router-labels) | dataset |
| `curia-grounding-config/` | [auspex-aerie/curia-grounding-config](https://huggingface.co/auspex-aerie/curia-grounding-config) | model (recipe only) |

Curia collection:
https://huggingface.co/collections/auspex-aerie/curia-multi-model-deliberation-and-code-grounding-6a6997ae6e5e29ab06677987

## Republish

```bash
export HF_TOKEN=…   # write token; do not commit
uv run python scripts/hf_publish_curia.py
```

See [docs/hf_hub.md](../docs/hf_hub.md).
