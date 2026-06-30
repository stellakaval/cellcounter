"""The per-image pipeline run by the background worker.

load_image -> segment (StarDist) -> regionprops + contours -> persist artifacts ->
update the DB row (status, counts, dimensions). Calling this directly is synchronous, so
tests use it as ``process_image(image_id)`` without depending on worker-thread timing.

We deliberately call ``io``/``segment``/``measure`` directly rather than
``batch.process_image`` because we need the label image + per-object table + contours
persisted (so filters and the overlay work later without re-segmenting).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import tifffile
from sqlmodel import Session

from cellcounter import io, measure, segment

from .. import config
from ..db import get_engine
from ..models import Image, Project
from . import rendering


def _artifacts(project_id: int, image_id: int) -> dict:
    d = config.image_dir(project_id, image_id)
    return {
        "labels": d / "labels.tif",
        "detections": d / "detections.parquet",
        "contours": d / "contours.json",
        "render_dapi": d / "render_dapi.png",
        "meta": d / "meta.json",
    }


def process_image(image_id: int) -> None:
    """Run the full pipeline for one image and persist results. Errors are recorded."""
    with Session(get_engine()) as session:
        image = session.get(Image, image_id)
        if image is None:
            return
        project = session.get(Project, image.project_id)
        image.status = "processing"
        session.add(image)
        session.commit()
        session.refresh(image)

        try:
            data = io.load_image(image.source_path)
            nuclei = data.nuclei()
            pixel_um = data.pixel_um
            dapi_idx = data.marker_index("DAPI")
            if dapi_idx is None:
                dapi_idx = 0

            labels = segment.segment(
                nuclei, project.model_name, project.sensitivity, pixel_um
            )

            props = measure.regionprops_df(labels, pixel_um)
            contours = measure.contours_df(labels)

            paths = _artifacts(image.project_id, image_id)
            tifffile.imwrite(paths["labels"], labels.astype(np.int32))
            props.to_parquet(paths["detections"], index=False)
            paths["contours"].write_text(
                json.dumps({int(r.label): r.polygon for r in contours.itertuples()})
            )
            rendering.render_png(nuclei, paths["render_dapi"])
            h, w = nuclei.shape[:2]
            paths["meta"].write_text(
                json.dumps(
                    {
                        "pixel_um": pixel_um,
                        "channel_names": data.channel_names,
                        "markers": data.markers,
                        "width": int(w),
                        "height": int(h),
                        "n_channels": data.n_channels,
                        "dapi_channel": int(dapi_idx),
                    },
                    default=str,
                )
            )

            filtered = measure.apply_filters(
                props, pixel_um, project.min_um2, project.max_um2, project.min_circ
            )

            image.width = int(w)
            image.height = int(h)
            image.pixel_um = pixel_um
            image.n_channels = data.n_channels
            image.channel_names = json.dumps(data.channel_names)
            image.dapi_channel = int(dapi_idx)
            image.raw_count = int(len(props))
            image.filtered_count = int(len(filtered))
            image.status = "done"
            image.error = None
            image.processed_at = datetime.now(timezone.utc)
        except Exception as e:  # record and move on; worker keeps running
            image.status = "error"
            image.error = str(e)

        session.add(image)
        session.commit()


# Tests read better with an explicit synchronous name.
process_image_now = process_image
