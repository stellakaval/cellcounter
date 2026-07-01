"""Image loading, channel detection, and pixel-size metadata.

Loads Zeiss ``.czi`` (the lab's real format) and standard TIFFs into a uniform
``ImageData`` (channels-first), and provides a napari reader so dropping a ``.czi`` onto
the window works — napari's builtin reader does not handle CZI.

For these samples **channel 0 is DAPI** (the nuclei to count); other channels are markers
(EdU-594, 488-PDGFRa). Z-stacks are max-projected. Pixel size comes from CZI metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Channel index holding the nuclei stain (DAPI) for these samples.
DAPI_CHANNEL = 0


@dataclass
class ImageData:
    """A loaded image, normalized to a predictable layout.

    Attributes:
        array: 2D ``(Y, X)`` if single-channel, else channels-first ``(C, Y, X)``.
        channel_axis: 0 when multi-channel, else None.
        channel_names: one name per channel (or None for single-channel).
        pixel_um: physical pixel size in microns/pixel, or None if unknown.
        markers: marker name → channel index, resolved by dye (e.g.
            ``{"DAPI": 3, "PDGFRa": 0, "EdU": 1, "ASPA": 2}``). DAPI channel order is
            NOT fixed across datasets, so always consult this rather than assuming index 0.
    """

    array: np.ndarray
    channel_axis: int | None
    channel_names: list[str] | None
    pixel_um: float | None
    markers: dict[str, int] | None = None

    @property
    def n_channels(self) -> int:
        return 1 if self.channel_axis is None else self.array.shape[self.channel_axis]

    def channel(self, index: int) -> np.ndarray:
        """Return a single 2D channel plane."""
        if self.channel_axis is None:
            return self.array
        return self.array[index]

    def marker_index(self, marker: str) -> int | None:
        """Channel index for a marker (case-insensitive), or None if not resolved."""
        if not self.markers:
            return None
        for name, idx in self.markers.items():
            if name.lower() == marker.lower():
                return idx
        return None

    def nuclei(self) -> np.ndarray:
        """Return the DAPI/nuclei plane (by dye if known, else channel 0)."""
        idx = self.marker_index("DAPI")
        if idx is None:
            idx = min(DAPI_CHANNEL, self.n_channels - 1)
        return self.channel(idx)


def count_scenes(path: str | Path) -> int:
    """Number of scenes in a CZI (1 for non-CZI or single-scene files)."""
    path = Path(path)
    if path.suffix.lower() != ".czi":
        return 1
    import czifile
    with czifile.CziFile(path) as czi:
        axes = list(czi.axes)
        if "S" not in axes:
            return 1
        return int(czi.shape[axes.index("S")])


def load_image(path: str | Path, scene_index: int = 0) -> ImageData:
    """Load a CZI or TIFF into channels-first ``ImageData``."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".czi":
        return _load_czi(path, scene_index=scene_index)
    return _load_tiff(path)


def _load_czi(path: Path, scene_index: int = 0) -> ImageData:
    """Read a Zeiss CZI: max-project Z, keep channels first, parse pixel size + names."""
    import czifile

    with czifile.CziFile(path) as czi:
        arr = np.asarray(czi.asarray())
        axes = list(czi.axes)  # e.g. "STCZYX0"
        meta = czi.metadata()

    # Max-project a Z-stack (good for nuclei counting).
    if "Z" in axes:
        zi = axes.index("Z")
        arr = arr.max(axis=zi)
        axes.pop(zi)
    # Collapse every non-spatial, non-channel axis.
    # Use scene_index for the S axis; take index 0 for all others (H, T, sample "0").
    for ax in list(axes):
        if ax not in ("Y", "X", "C"):
            i = axes.index(ax)
            idx = scene_index if ax == "S" else 0
            arr = arr[tuple(idx if j == i else slice(None) for j in range(arr.ndim))]
            axes.pop(i)

    # Move channel axis to front if present, else stay 2D.
    if "C" in axes:
        ci = axes.index("C")
        arr = np.moveaxis(arr, ci, 0)
        n_ch = arr.shape[0]
        channel_axis: int | None = 0
        markers = _czi_markers(meta, path.name, n_ch)
        channel_names = _channel_names(path, meta, n_ch, markers)
    else:
        channel_axis = None
        channel_names = None
        markers = None

    return ImageData(
        array=arr.astype(np.float32),
        channel_axis=channel_axis,
        channel_names=channel_names,
        pixel_um=_czi_pixel_um(meta),
        markers=markers,
    )


def _czi_pixel_um(meta: str) -> float | None:
    """Pixel size from CZI metadata ``<Distance Id="X">`` (stored in metres/pixel)."""
    m = re.search(r"<Distance Id=\"X\">\s*<Value>([0-9.eE+-]+)</Value>", meta)
    return float(m.group(1)) * 1e6 if m else None


# Marker names we recognise (lowercased token → canonical name).
_KNOWN_MARKERS = {"dapi": "DAPI", "pdgfra": "PDGFRa", "edu": "EdU", "aspa": "ASPA", "gfp": "GFP"}


def _canon_marker(token: str) -> str:
    return _KNOWN_MARKERS.get(token.lower(), token)


def _czi_markers(meta: str, filename: str, n_ch: int) -> dict[str, int]:
    """Map ``marker name → channel index`` using CZI dye/fluor + filename tokens.

    DAPI is detected directly (its fluor is literally ``DAPI``); other channels are matched by
    their fluorophore number (e.g. ``Alexa Fluor 647``) to the marker that names that number in
    the filename (e.g. ``PDGFRa647`` → 647 → PDGFRa). The channel order is NOT assumed.
    """
    # Channel index → fluor string, in channel order.
    fluor_by_idx: dict[int, str] = {}
    for m in re.finditer(r'<Channel Id="Channel:(\d+)"[^>]*>(.*?)</Channel>', meta, re.S):
        idx = int(m.group(1))
        body = m.group(2)
        f = re.search(r"<Fluor>([^<]+)</Fluor>", body) or re.search(
            r"<DyeName>([^<]+)</DyeName>", body
        )
        if f and idx not in fluor_by_idx:
            fluor_by_idx[idx] = f.group(1)

    # Filename tokens: marker + 3-digit fluorophore number (PDGFRa647, ASPA488, DAPI405, …).
    num_to_marker: dict[str, str] = {}
    for marker, num in re.findall(r"([A-Za-z][A-Za-z]*?)(\d{3})", filename):
        num_to_marker[num] = _canon_marker(marker)

    markers: dict[str, int] = {}
    for idx in range(n_ch):
        fl = fluor_by_idx.get(idx, "")
        if "dapi" in fl.lower():
            markers["DAPI"] = idx
            continue
        num = re.search(r"(\d{3})", fl)
        if num and num.group(1) in num_to_marker:
            markers[num_to_marker[num.group(1)]] = idx

    # Fallback: if DAPI wasn't found via fluor but the filename mentions it, and channel 0 is
    # free, assume DAPI=channel 0 (keeps single-DAPI-first datasets working).
    if "DAPI" not in markers and re.search(r"dapi", filename, re.I) and 0 not in markers.values():
        markers["DAPI"] = 0
    return markers


def _channel_names(
    path: Path, meta: str, n_ch: int, markers: dict[str, int] | None = None
) -> list[str]:
    """Plain-English channel names (e.g. DAPI / PDGFRa / EdU / ASPA).

    Prefer the dye-resolved ``markers`` (authoritative, order-independent). Fill any
    unresolved slot from the filename stain order, then metadata, then ``Ch{i}``.
    """
    names: list[str | None] = [None] * n_ch
    for name, idx in (markers or {}).items():
        if 0 <= idx < n_ch:
            names[idx] = name
    if all(n is not None for n in names):
        return [n for n in names]  # fully resolved by dye

    # Filename stains, in order of appearance (positional fallback for unresolved slots).
    stem = path.stem.lower()
    stains = [
        label
        for _, label in sorted(
            (m.start(), canon)
            for tok, canon in _KNOWN_MARKERS.items()
            for m in [re.search(tok, stem)]
            if m
        )
    ]
    meta_names: list[str] = []
    for nm in re.findall(r"<Channel[^>]*Name=\"([^\"]+)\"", meta):
        if nm not in meta_names:
            meta_names.append(nm)

    for i in range(n_ch):
        if names[i] is not None:
            continue
        if i < len(stains):
            names[i] = stains[i]
        elif i < len(meta_names):
            names[i] = meta_names[i]
        else:
            names[i] = "DAPI" if i == 0 else f"Ch{i}"
    return [n for n in names]


def _load_tiff(path: Path) -> ImageData:
    """Read a TIFF; detect a small channel axis and read OME/ImageJ pixel size if present."""
    import tifffile

    with tifffile.TiffFile(path) as tif:
        arr = np.asarray(tif.asarray())
        pixel_um = _tiff_pixel_um(tif)

    arr = arr.astype(np.float32)
    if arr.ndim == 2:
        return ImageData(arr, None, None, pixel_um)

    # Heuristic: the smallest axis <= 5 that isn't the last two (spatial) is channels.
    channel_axis = None
    for ax in range(arr.ndim - 2):
        if arr.shape[ax] <= 5:
            channel_axis = ax
            break
    if channel_axis is None:
        # Treat leading axes as stack; take first plane until 2D.
        while arr.ndim > 2:
            arr = arr[0]
        return ImageData(arr, None, None, pixel_um)

    arr = np.moveaxis(arr, channel_axis, 0)
    # Collapse any remaining non-spatial axes between channel and (Y, X).
    while arr.ndim > 3:
        arr = arr[:, 0]
    n_ch = arr.shape[0]
    names = [f"Ch{i}" if i else "DAPI" for i in range(n_ch)]
    return ImageData(arr, 0, names, pixel_um)


def _tiff_pixel_um(tif) -> float | None:
    """Pixel size (µm/px) from ImageJ or OME-TIFF metadata, if available."""
    ij = getattr(tif, "imagej_metadata", None)
    try:
        page = tif.pages[0]
        tags = page.tags
        if "XResolution" in tags:
            num, den = tags["XResolution"].value
            if num:
                res = den / num  # units per pixel
                unit = tags["ResolutionUnit"].value if "ResolutionUnit" in tags else None
                # ImageJ stores resolution in pixels per `unit`; res above is unit/pixel.
                if ij and ij.get("unit") in ("um", "micron", "microns", "µm"):
                    return float(res)
                return float(res)
    except Exception:
        pass
    return None


# --- napari reader (npe2 contract) ------------------------------------------------------

def napari_get_reader(path):
    """Return a napari reader for ``.czi`` files, else None (let napari handle others)."""
    p = path[0] if isinstance(path, list) else path
    if not str(p).lower().endswith(".czi"):
        return None
    return _czi_reader


# Colour each named channel so the markers are obvious at a glance.
_CHANNEL_COLORMAP = {
    "DAPI": "bop blue",
    "EdU": "red",
    "PDGFRa": "green",
    "ASPA": "magenta",
    "GFP": "green",
}


def _czi_reader(path):
    """napari reader: one named, coloured Image layer per channel.

    The DAPI (nuclei) layer is the "primary" one — it carries the full stack, channel names,
    and pixel size in ``metadata`` (so the widget can run colocalization without re-reading)
    and is the layer that triggers the auto-count. Marker layers (EdU, PDGFRa) are added so
    the user can toggle them on to see them, but are flagged to skip the auto-count and are
    hidden by default.
    """
    p = Path(path[0] if isinstance(path, list) else path)
    img = load_image(p)
    n = img.n_channels
    names = img.channel_names or (["DAPI"] if n == 1 else [f"Ch{i}" for i in range(n)])

    # The DAPI (nuclei) channel is the primary one — detected by dye, not assumed to be 0.
    dapi_idx = img.marker_index("DAPI")
    if dapi_idx is None:
        dapi_idx = min(DAPI_CHANNEL, n - 1)

    layers = []
    for i in range(n):
        plane = img.channel(i)
        name = names[i] if i < len(names) else f"Ch{i}"
        if i == dapi_idx:
            meta = {
                "cellcounter": True,
                "source": str(p),
                "pixel_um": img.pixel_um,
                "channels": img.array if n > 1 else None,
                "channel_names": names,
                "markers": img.markers,
            }
        else:
            meta = {"cellcounter": True, "cellcounter_skip": True}
        layers.append(
            (
                plane,
                {
                    "name": name,
                    "colormap": _CHANNEL_COLORMAP.get(name, "gray"),
                    "blending": "additive",
                    "visible": i == dapi_idx,  # show DAPI; markers off until toggled
                    "contrast_limits": _percentile_limits(plane),
                    "metadata": meta,
                },
                "image",
            )
        )
    return layers


def _percentile_limits(img: np.ndarray, low: float = 1.0, high: float = 99.5):
    """Robust contrast limits so dim DAPI is visible on add."""
    lo, hi = np.percentile(img, [low, high])
    if hi <= lo:
        hi = lo + 1
    return [float(lo), float(hi)]
