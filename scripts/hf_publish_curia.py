#!/usr/bin/env python3
"""Publish Curia first-party Hub artifacts under the auspex-aerie HF user.

Requires HF_TOKEN (write). Does not commit tokens. Re-run is idempotent
(create_repo exist_ok + upload_folder). Syncs router labels from the canonical
in-repo path before upload so the Hub mirror cannot drift silently.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HF_DIR = ROOT / "hf"
# HF account for this lab is the *user* `auspex-aerie` (GitHub org is Auspex-Aerie).
ORG = os.environ.get("HF_NAMESPACE", "auspex-aerie")
CANONICAL_LABELS = ROOT / "backend" / "rag" / "router_training.json"
MIRROR_LABELS = HF_DIR / "curia-router-labels" / "data" / "router_training.json"


def _is_already_present(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        needle in text
        for needle in (
            "already",
            "exists",
            "duplicate",
            "409",
            "conflict",
        )
    )


def _sync_router_labels() -> None:
    if not CANONICAL_LABELS.is_file():
        raise FileNotFoundError(f"canonical labels missing: {CANONICAL_LABELS}")
    MIRROR_LABELS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CANONICAL_LABELS, MIRROR_LABELS)
    print(f"Synced router labels → {MIRROR_LABELS.relative_to(ROOT)}")


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

    try:
        from huggingface_hub import HfApi
        from huggingface_hub.errors import HfHubHTTPError
    except ImportError:
        print(
            "ERROR: huggingface_hub is required "
            "(declared in pyproject.toml; run `uv sync`)",
            file=sys.stderr,
        )
        return 2

    _sync_router_labels()

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
        # Empty collections still exist; they appear under the user's Collections
        # tab (https://huggingface.co/auspex-aerie/collections), not always on
        # the profile "Models" landing strip.
        collections_spec = [
            ("curia", "Curia — multi-model deliberation & code grounding"),
            ("netflow-anomaly", "Netflow anomaly detection (planned artifacts)"),
            ("domain-lexicon", "Malicious / suspicious domain lexical models (planned)"),
            ("brand-protection", "Brand spoof / lookalike protection (planned)"),
            ("text-compression", "Neural text compression (planned)"),
        ]
        slug_by_key: dict[str, str] = {}
        existing = list(api.list_collections(owner=ORG))
        by_title = {c.title: c for c in existing}

        for key, title in collections_spec:
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
            slug_by_key[key] = col.slug

        curia_slug = slug_by_key.get("curia")
        if not curia_slug:
            print("ERROR: Curia collection slug missing after create/list", file=sys.stderr)
            return 1
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
            except HfHubHTTPError as exc:
                if _is_already_present(exc):
                    print(f"  already in collection: {item_id}")
                    continue
                print(f"ERROR: add_collection_item {item_id}: {exc}", file=sys.stderr)
                return 1
            except Exception as exc:
                if _is_already_present(exc):
                    print(f"  already in collection: {item_id}")
                    continue
                print(f"ERROR: add_collection_item {item_id}: {exc}", file=sys.stderr)
                return 1

        print(
            f"Collections UI: https://huggingface.co/{ORG}/collections "
            "(empty shelves still list here; they are not hidden, just easy to miss)"
        )

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
