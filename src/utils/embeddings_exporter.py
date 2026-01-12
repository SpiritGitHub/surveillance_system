from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

import numpy as np


def _sanitize_filename(name: str) -> str:
    # Windows-safe (avoid ':'), and avoid path traversal
    name = name.replace(":", "_")
    name = name.replace("/", "_")
    name = name.replace("\\", "_")
    name = name.replace("..", "__")
    return name


def export_embeddings_from_trajectories(
    trajectories_dir: str | Path = "data/trajectories",
    out_dir: str | Path = "data/embeddings",
    run_id: str | None = None,
    *,
    class_filter: str | None = "person",
    mode: str = "mean",
    max_embeddings_per_track: int = 5,
) -> dict[str, Any]:
    """Export ReID embeddings from trajectories into `data/embeddings/`.

    Why this exists:
    - Embeddings are persisted in `data/trajectories/*.json`.
    - Some exam/test workflows expect a dedicated embeddings folder.

    What is exported:
    - One `.npy` file per track that contains embeddings.
    - By default only `person` tracks (because the pipeline only computes ReID for persons).
    - The exported vector is either the mean of the first N embeddings, or the first embedding.

    Output structure:
    - `data/embeddings/<VIDEO_ID>/<TRACK_ID>__gid_<GLOBAL_ID>.npy`
    - `data/embeddings/embeddings_index_<RUN_ID>.csv`
    """

    trajectories_dir = Path(trajectories_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if run_id is None:
        run_id = time.strftime("%Y%m%d_%H%M%S")

    index_csv = out_dir / f"embeddings_index_{run_id}.csv"

    headers = [
        "run_id",
        "video_id",
        "track_id",
        "class_name",
        "global_id",
        "n_embeddings",
        "embedding_mode",
        "embedding_file",
    ]

    tracks_exported = 0
    files_written = 0

    with open(index_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()

        for jf in trajectories_dir.glob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue

            video_id = str(data.get("video_id") or jf.stem)
            video_dir = out_dir / _sanitize_filename(video_id)
            video_dir.mkdir(parents=True, exist_ok=True)

            for trk in data.get("trajectories", []) or []:
                class_name = trk.get("class_name")
                if class_name is None:
                    class_name = "person"  # backward-compatible

                if class_filter is not None and class_name != class_filter:
                    continue

                embeddings = trk.get("embeddings") or []
                if not embeddings:
                    continue

                track_id = str(trk.get("track_id") or "")
                if not track_id:
                    continue

                global_id = trk.get("global_id")
                try:
                    global_id_int = int(global_id) if global_id is not None else None
                except Exception:
                    global_id_int = None

                # Use the first N embeddings for stability/size
                emb_take = embeddings[: max(1, int(max_embeddings_per_track))]
                try:
                    arr = np.asarray(emb_take, dtype=np.float32)
                except Exception:
                    continue

                if arr.ndim != 2 or arr.shape[0] < 1:
                    continue

                if mode == "first":
                    emb = arr[0]
                else:
                    # default: mean
                    emb = arr.mean(axis=0)

                safe_track = _sanitize_filename(track_id)
                suffix = f"__gid_{global_id_int}" if global_id_int is not None else ""
                out_path = video_dir / f"{safe_track}{suffix}.npy"

                try:
                    np.save(out_path, emb)
                except Exception:
                    continue

                w.writerow(
                    {
                        "run_id": run_id,
                        "video_id": video_id,
                        "track_id": track_id,
                        "class_name": class_name,
                        "global_id": "" if global_id_int is None else str(global_id_int),
                        "n_embeddings": int(arr.shape[0]),
                        "embedding_mode": mode,
                        "embedding_file": str(out_path).replace("\\", "/"),
                    }
                )

                tracks_exported += 1
                files_written += 1

    return {
        "out_dir": str(out_dir).replace("\\", "/"),
        "index_csv": str(index_csv).replace("\\", "/"),
        "tracks_exported": tracks_exported,
        "files_written": files_written,
        "class_filter": class_filter,
        "mode": mode,
        "max_embeddings_per_track": max_embeddings_per_track,
    }
