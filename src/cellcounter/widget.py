"""napari dock widget + drag-and-drop auto-count (the headline UI).

Drop a ``.czi`` (or TIFF) onto the window → the DAPI channel is segmented automatically in a
worker thread and a big cell count appears, with an editable ``nuclei`` Labels layer overlaid.
The user then refines: adjust min/max area (µm²) and circularity (live, non-destructive),
fix the AI with napari's brush/erase (then Recount), change sensitivity, or export a CSV.

All Fiji preprocessing (blur/threshold/watershed) is intentionally absent — the AI replaces it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import batch, compare, measure, segment, session


class CounterWidget:
    """Wraps a napari viewer with the count UI. Use ``CounterWidget(viewer).container``.

    Implemented as a thin class so the magicgui ``Container`` (``.container``) can be docked,
    while the viewer wiring (drag-drop hook, worker, edits) lives in methods.
    """

    def __init__(self, viewer):
        from magicgui.widgets import (
            ComboBox,
            FloatSlider,
            FloatSpinBox,
            Label,
            PushButton,
        )

        self.viewer = viewer
        self._cells = None  # cached regionprops DataFrame for the current labels
        self._labels_layer = None
        self._image_layer = None
        self._busy = False

        models = segment.list_models()
        self.w_model = ComboBox(label="Model", choices=models, value=models[0])
        self.w_channel = ComboBox(label="Channel", choices=[("DAPI", 0)], value=0)
        self.w_pixel = FloatSpinBox(label="Pixel size (µm/px)", value=0.0, step=0.001, min=0.0)
        # Default 30 µm² (~6 µm nucleus) filters small noise/debris — validated against the
        # lab's ground-truth counts (overcount 26% → ~1%). Adjustable here per image.
        self.w_min_area = FloatSlider(label="Min area (µm²)", min=0.0, max=500.0, value=30.0)
        self.w_max_area = FloatSlider(label="Max area (µm²)", min=0.0, max=5000.0, value=0.0)
        self.w_circ = FloatSlider(label="Min circularity", min=0.0, max=1.0, value=0.0)
        self.w_sensitivity = FloatSlider(label="Sensitivity", min=0.0, max=1.0, value=0.5)
        self.w_recount = PushButton(text="Recount (after edits)")
        self.w_peek = PushButton(text="Show original (hide outlines)")
        self.w_export = PushButton(text="Export CSV")
        self.w_count = Label(label="Cells", value="—")
        self.w_status = Label(label="", value="Drop an image to begin.")

        # Colocalization (multi-channel): which channel is EdU / PDGFRa.
        self.w_edu_channel = ComboBox(label="EdU channel", choices=[("none", -1)], value=-1)
        self.w_pdgfra_channel = ComboBox(
            label="PDGFRa channel", choices=[("none", -1)], value=-1
        )
        self.w_coloc = PushButton(text="Colocalization")
        self.w_coloc_result = Label(label="Coloc", value="—")

        self.w_batch = PushButton(text="Batch folder…")
        self.w_save = PushButton(text="Save session")
        self.w_load = PushButton(text="Load session")

        from magicgui.widgets import Container

        self.container = Container(
            widgets=[
                self.w_count,
                self.w_status,
                self.w_model,
                self.w_channel,
                self.w_pixel,
                self.w_min_area,
                self.w_max_area,
                self.w_circ,
                self.w_sensitivity,
                self.w_recount,
                self.w_peek,
                self.w_export,
                self.w_edu_channel,
                self.w_pdgfra_channel,
                self.w_coloc,
                self.w_coloc_result,
                self.w_batch,
                self.w_save,
                self.w_load,
            ],
            labels=True,
        )

        # Live filters re-select rows from cached regionprops (cheap, no model re-run).
        for w in (self.w_min_area, self.w_max_area, self.w_circ):
            w.changed.connect(self._refilter)
        # Sensitivity and channel re-run the model.
        self.w_sensitivity.changed.connect(self._resegment)
        self.w_channel.changed.connect(self._on_channel_change)
        self.w_recount.clicked.connect(self._recount_from_labels)
        self.w_peek.clicked.connect(self._toggle_overlay)
        self.w_export.clicked.connect(self._export)
        self.w_coloc.clicked.connect(self._run_coloc)
        self.w_batch.clicked.connect(self._run_batch)
        self.w_save.clicked.connect(self._save_session)
        self.w_load.clicked.connect(self._load_session)

        # Auto-count whenever an Image layer is added (drag-drop or File→Open).
        viewer.layers.events.inserted.connect(self._on_layer_inserted)

        # Hold 'h' to peek at the original photo (hide the AI outlines while held).
        @viewer.bind_key("h", overwrite=True)
        def _peek_key(_v):
            if self._labels_layer is not None:
                self._labels_layer.visible = False
            yield  # released
            if self._labels_layer is not None:
                self._labels_layer.visible = True

    # --- segmentation flow --------------------------------------------------------------

    def _on_layer_inserted(self, event):
        from napari.layers import Image

        layer = event.value
        if not isinstance(layer, Image):
            return  # ignore our own Labels layer (prevents an infinite loop)
        if layer.metadata.get("cellcounter_result"):
            return
        if layer.metadata.get("cellcounter_skip"):
            return  # marker channel (EdU/PDGFRa) — shown for viewing, not counted
        self._image_layer = layer
        # Populate pixel size + channel choices from the reader's metadata.
        pixel_um = layer.metadata.get("pixel_um")
        if pixel_um:
            self.w_pixel.value = round(float(pixel_um), 4)
        names = layer.metadata.get("channel_names")
        if names:
            self.w_channel.choices = [(n, i) for i, n in enumerate(names)]
            self.w_channel.value = 0
            # Marker-role dropdowns: include a "none" option; default by matching the
            # channel name, falling back to the usual position (EdU last, PDGFRa middle).
            roles = [("none", -1)] + [(n, i) for i, n in enumerate(names)]
            self.w_edu_channel.choices = roles
            self.w_pdgfra_channel.choices = roles
            lower = [n.lower() for n in names]
            edu = next((i for i, n in enumerate(lower) if "edu" in n), len(names) - 1)
            pdgfra = next((i for i, n in enumerate(lower) if "pdgfra" in n), -1)
            self.w_edu_channel.value = edu
            self.w_pdgfra_channel.value = pdgfra
        self._resegment()

    def _current_channel_image(self) -> np.ndarray | None:
        """The 2D plane to segment: selected channel from stashed stack, else the layer data."""
        if self._image_layer is None:
            return None
        channels = self._image_layer.metadata.get("channels")
        idx = int(self.w_channel.value)
        if channels is not None and getattr(channels, "ndim", 2) == 3:
            return np.asarray(channels[idx])
        return np.asarray(self._image_layer.data)

    def _resegment(self, *_):
        img = self._current_channel_image()
        if img is None or self._busy:
            return
        from napari.qt.threading import thread_worker

        self._busy = True
        self.w_status.value = "Counting…"
        pixel_um = self.w_pixel.value or None
        model_name = self.w_model.value
        sensitivity = float(self.w_sensitivity.value)

        @thread_worker
        def _work():
            return segment.segment(img, model_name, sensitivity, pixel_um)

        worker = _work()
        worker.returned.connect(self._on_segmented)
        worker.errored.connect(self._on_error)
        worker.start()

    def _on_segmented(self, labels):
        self._busy = False
        if self._labels_layer is None or self._labels_layer not in self.viewer.layers:
            self._labels_layer = self.viewer.add_labels(
                labels, name="AI cells (DAPI)", metadata={"cellcounter_result": True}
            )
        else:
            self._labels_layer.data = labels
        self.w_status.value = "Edit with the brush, then Recount. Adjust sliders to filter."
        self._recount_from_labels()

    def _on_error(self, exc):
        self._busy = False
        self.w_status.value = f"Could not segment: {exc}"

    # --- counting / filtering -----------------------------------------------------------

    def _recount_from_labels(self, *_):
        """Recompute regionprops from the current (possibly hand-edited) Labels layer."""
        if self._labels_layer is None:
            return
        pixel_um = self.w_pixel.value or None
        self._cells = measure.regionprops_df(
            np.asarray(self._labels_layer.data), pixel_um
        )
        self._refilter()

    def _refilter(self, *_):
        """Update the count from cached regionprops using the current slider values."""
        if self._cells is None:
            return
        pixel_um = self.w_pixel.value or None
        kept = measure.apply_filters(
            self._cells,
            pixel_um,
            min_um2=float(self.w_min_area.value),
            max_um2=float(self.w_max_area.value) or None,
            min_circ=float(self.w_circ.value),
        )
        self.w_count.value = f"{len(kept):,} cells"

    def _on_channel_change(self, *_):
        if self._image_layer is not None and not self._busy:
            self._resegment()

    def _toggle_overlay(self, *_):
        """Show/hide the AI outline layer so the raw photo is visible underneath."""
        if self._labels_layer is None:
            return
        visible = not self._labels_layer.visible
        self._labels_layer.visible = visible
        self.w_peek.text = "Show outlines" if not visible else "Show original (hide outlines)"

    def _run_coloc(self, *_):
        """Compute % EdU+ (and % EdU+ within PDGFRa+) from current nuclei + marker channels."""
        if self._labels_layer is None or self._image_layer is None:
            self.w_coloc_result.value = "Count cells first."
            return
        channels = self._image_layer.metadata.get("channels")
        if channels is None or getattr(channels, "ndim", 2) != 3:
            self.w_coloc_result.value = "Need a multi-channel image."
            return
        edu_idx = int(self.w_edu_channel.value)
        if edu_idx < 0:
            self.w_coloc_result.value = "Pick the EdU channel."
            return
        pdgfra_idx = int(self.w_pdgfra_channel.value)
        pdgfra = np.asarray(channels[pdgfra_idx]) if pdgfra_idx >= 0 else None
        res = compare.colocalize(
            np.asarray(self._labels_layer.data),
            np.asarray(channels[edu_idx]),
            pdgfra,
            pixel_um=self.w_pixel.value or None,
        )
        txt = f"{res.pct_edu_pos:.1f}% EdU+ ({res.n_edu_pos}/{res.n_nuclei})"
        if res.pct_edu_in_pdgfra is not None:
            txt += f"; {res.pct_edu_in_pdgfra:.1f}% EdU+ in PDGFRa+ ({res.n_pdgfra_pos})"
        self.w_coloc_result.value = txt
        self._last_coloc = res

    # --- export -------------------------------------------------------------------------

    def _export(self, *_):
        if self._cells is None or self._labels_layer is None:
            self.w_status.value = "Nothing to export yet."
            return
        from qtpy.QtWidgets import QFileDialog

        pixel_um = self.w_pixel.value or None
        kept = measure.apply_filters(
            self._cells,
            pixel_um,
            min_um2=float(self.w_min_area.value),
            max_um2=float(self.w_max_area.value) or None,
            min_circ=float(self.w_circ.value),
        )
        src = (self._image_layer.metadata.get("source") if self._image_layer else None)
        default = str(Path(src).with_suffix(".cells.csv")) if src else "cells.csv"
        path, _ = QFileDialog.getSaveFileName(None, "Export per-cell CSV", default, "CSV (*.csv)")
        if not path:
            return
        summary = {
            "source": src,
            "channel": self.w_channel.value,
            "model": self.w_model.value,
            "pixel_um": pixel_um,
            "count": len(kept),
            "min_area_um2": float(self.w_min_area.value),
            "max_area_um2": float(self.w_max_area.value) or None,
            "min_circularity": float(self.w_circ.value),
            "sensitivity": float(self.w_sensitivity.value),
        }
        cells_path, summary_path = measure.export_csv(kept, summary, path)
        self.w_status.value = f"Wrote {cells_path.name} + {summary_path.name}"


    # --- batch + session ----------------------------------------------------------------

    def _run_batch(self, *_):
        from napari.qt.threading import thread_worker
        from qtpy.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(None, "Choose a folder of images")
        if not folder:
            return
        out, _ = QFileDialog.getSaveFileName(
            None, "Save combined CSV", str(Path(folder) / "cellcounter_batch.csv"), "CSV (*.csv)"
        )
        if not out:
            return
        edu = int(self.w_edu_channel.value)
        pdgfra = int(self.w_pdgfra_channel.value)
        kw = dict(
            model_name=self.w_model.value,
            sensitivity=float(self.w_sensitivity.value),
            pixel_um=self.w_pixel.value or None,
            min_um2=float(self.w_min_area.value),
            max_um2=float(self.w_max_area.value) or None,
            min_circ=float(self.w_circ.value),
            edu_channel=edu if edu >= 0 else None,
            pdgfra_channel=pdgfra if pdgfra >= 0 else None,
        )
        self.w_status.value = "Batch running…"

        @thread_worker
        def _work():
            return batch.batch_folder(folder, out, **kw)

        worker = _work()
        worker.returned.connect(
            lambda df: setattr(self.w_status, "value", f"Batch done: {len(df)} images → {Path(out).name}")
        )
        worker.errored.connect(lambda e: setattr(self.w_status, "value", f"Batch failed: {e}"))
        worker.start()

    def _save_session(self, *_):
        if self._labels_layer is None:
            self.w_status.value = "Nothing to save yet."
            return
        from qtpy.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(None, "Choose a folder to save the session")
        if not folder:
            return
        params = {
            "source": self._image_layer.metadata.get("source") if self._image_layer else None,
            "model": self.w_model.value,
            "channel": self.w_channel.value,
            "pixel_um": self.w_pixel.value or None,
            "min_area_um2": float(self.w_min_area.value),
            "max_area_um2": float(self.w_max_area.value) or None,
            "min_circularity": float(self.w_circ.value),
            "sensitivity": float(self.w_sensitivity.value),
        }
        session.save_session(folder, np.asarray(self._labels_layer.data), params)
        self.w_status.value = f"Session saved to {Path(folder).name}"

    def _load_session(self, *_):
        from qtpy.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(None, "Choose a saved session folder")
        if not folder:
            return
        labels, params = session.load_session(folder)
        if params.get("pixel_um"):
            self.w_pixel.value = round(float(params["pixel_um"]), 4)
        for key, w in [
            ("min_area_um2", self.w_min_area),
            ("max_area_um2", self.w_max_area),
            ("min_circularity", self.w_circ),
            ("sensitivity", self.w_sensitivity),
        ]:
            if params.get(key) is not None:
                w.value = float(params[key])
        self._labels_layer = self.viewer.add_labels(
            labels, name="AI cells (DAPI)", metadata={"cellcounter_result": True}
        )
        self._recount_from_labels()
        self.w_status.value = f"Loaded session from {Path(folder).name}"


def make_widget(napari_viewer):
    """npe2 widget factory: return the dockable container for the given viewer."""
    return CounterWidget(napari_viewer).container


def main() -> None:
    """Console entry point: launch napari with the cellcounter dock widget."""
    import napari

    viewer = napari.Viewer(title="cellcounter")
    widget = CounterWidget(viewer)
    viewer.window.add_dock_widget(widget.container, area="right", name="cellcounter")
    napari.run()
