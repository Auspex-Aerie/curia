#!/usr/bin/env python3
"""Publish Curia first-party Hub artifacts under Auspex-Aerie.

Requires HF_TOKEN (write). Does not commit tokens. Re-run is idempotent
(create_repo exist_ok + upload_folder).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HF_DIR = ROOT / "hf"
ORG = "auspex-aerie"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--token",
        default=os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"),
        help="Write token (or set HF_TOKEN)",
    )
    parser.add_argument("--skip-collections", action="store_true")
    args = parser.parse_args()
    if not args.token:
        print("ERROR: pass --token or set HF_TOKEN", file=sys.stderr)
        return 2

    from huggingface_hub import HfApi

    api = HfApi(token=args.token)
    who = api.whoami()
    print(f"Authenticated as: {who.get('name') or who.get('fullname')}")

    # --- dataset: curia-router-labels ---
    ds_id = f"{ORG}/curia-router-labels"
    print(f"Creating dataset {ds_id} …")
    api.create_repo(ds_id, repo_type="dataset", exist_ok=True, private=False)
    api.upload_folder(
        folder_path=str(HF_DIR / "curia-router-labels"),
        repo_id=ds_id,
        repo_type="dataset",
        commit_message="Publish Curia router labels (public mirror of in-repo training JSON)",
    )
    print(f"  → https://huggingface.co/datasets/{ds_id}")

    # --- model: curia-grounding-config ---
    model_id = f"{ORG}/curia-grounding-config"
    print(f"Creating model {model_id} …")
    api.create_repo(model_id, repo_type="model", exist_ok=True, private=False)
    api.upload_folder(
        folder_path=str(HF_DIR / "curia-grounding-config"),
        repo_id=model_id,
        repo_type="model",
        commit_message="Publish Curia grounding stack recipe (config only; not runtime-loaded yet)",
    )
    print(f"  → https://huggingface.co/{model_id}")

    if not args.skip_collections:
        print("Ensuring product collections …")
        # Collection titles for the multi-product shelf
        collections_spec = [
            ("curia", "Curia — multi-model deliberation & code grounding"),
            ("netflow-anomaly", "Netflow anomaly detection (planned artifacts)"),
            ("domain-lexicon", "Malicious / suspicious domain lexical models (planned)"),
            ("brand-protection", "Brand spoof / lookalike protection (planned)"),
            ("text-compression", "Neural text compression (planned)"),
        ]
        slug_to_id: dict[str, str] = {}
        existing = list(api.list_collections(owner=ORG))
        by_title = {c.title: c for c in existing}

        for slug, title in collections_spec:
            if title in by_title:
                col = by_title[title]
                print(f"  collection exists: {col.slug}")
            else:
                col = api.create_collection(
                    title=title,
                    namespace=ORG,
                    description=title,
                )
                print(f"  created collection: {col.slug}")
            slug_to_id[slug] = col.slug

        curia_slug = slug_to_id.get("curia")
        if curia_slug:
            for item_id, item_type, note in (
                (ds_id, "dataset", "Router intent labels"),
                (model_id, "model", "Grounding stack recipe"),
            ):
                try:
                    api.add_collection_item(
                        curia_slug,
                        item_id=item_id,
                        item_type=item_type,
                        note=note,
                    )
                    print(f"  added {item_type} {item_id} → curia collection")
                except Exception as exc:
                    print(f"  add_collection_item {item_id}: {exc}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
