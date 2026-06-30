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
    """

    array: np.ndarray
    channel_axis: int | None
    channel_names: list[str] | None
    pixel_um: float | None

    @property
    def n_channels(self) -> int:
        return 1 if self.channel_axis is None else self.array.shape[self.channel_axis]

    def channel(self, index: int) -> np.ndarray:
        """Return a single 2D channel plane."""
        if self.channel_axis is None:
            return self.array
        return self.array[index]

    def nuclei(self) -> np.ndarray:
        """Return the DAPI/nuclei plane (channel 0), or the image if single-channel."""
        return self.channel(min(DAPI_CHANNEL, self.n_channels - 1))


def load_image(path: str | Path) -> ImageData:
    """Load a CZI or TIFF into channels-first ``ImageData``."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".czi":
        return _load_czi(path)
    return _load_tiff(path)


def _load_czi(path: Path) -> ImageData:
    """Read a Zeiss CZI: max-project Z, keep channels first, parse pixel size + names."""
    import czifile

    with czifile.CziFile(path) as czi:
        arr = np.asarray(czi.asarray())
        axes = list(czi.axes)  # e.g. "HTCZYX0"
        meta = czi.metadata()

    # Max-project a Z-stack (good for nuclei counting).
    if "Z" in axes:
        zi = axes.index("Z")
        arr = arr.max(axis=zi)
        axes.pop(zi)
    # Collapse every non-spatial, non-channel axis by taking index 0 (H, T, sample "0").
    for ax in list(axes):
        if ax not in ("Y", "X", "C"):
            i = axes.index(ax)
            arr = arr[tuple(0 if j == i else slice(None) for j in range(arr.ndim))]
            axes.pop(i)

    # Move channel axis to front if present, else stay 2D.
    if "C" in axes:
        ci = axes.index("C")
        arr = np.moveaxis(arr, ci, 0)
        n_ch = arr.shape[0]
        channel_axis: int | None = 0
        channel_names = _czi_channel_names(meta, n_ch)
    else:
        channel_axis = None
        channel_names = None

    return ImageData(
        array=arr.astype(np.float32),
        channel_axis=channel_axis,
        channel_names=channel_names,
        pixel_um=_czi_pixel_um(meta),
    )


def _czi_pixel_um(meta: str) -> float | None:
    """Pixel size from CZI metadata ``<Distance Id="X">`` (stored in metres/pixel)."""
    m = re.search(r"<Distance Id=\"X\">\s*<Value>([0-9.eE+-]+)</Value>", meta)
    return float(m.group(1)) * 1e6 if m else None


def _czi_channel_names(meta: str, n_ch: int) -> list[str]:
    """Best-effort channel names from metadata; fall back to Ch0..ChN (Ch0 = DAPI)."""
    names = re.findall(r"<Channel[^>]*Name=\"([^\"]+)\"", meta)
    # De-dupe preserving order; metadata can list per-track duplicates.
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    if len(seen) >= n_ch:
        return seen[:n_ch]
    return [f"Ch{i}" if i else "DAPI" for i in range(n_ch)]


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


def _czi_reader(path):
    """napari reader: add the DAPI plane as one Image layer; stash full stack in metadata.

    Returns one ``(data, add_kwargs, 'image')`` tuple. The full multi-channel array, channel
    names, and pixel size ride along in ``metadata`` so the widget can switch channels and run
    colocalization without re-reading the file.
    """
    p = Path(path[0] if isinstance(path, list) else path)
    img = load_image(p)
    nuclei = img.nuclei()
    meta = {
        "cellcounter": True,
        "source": str(p),
        "pixel_um": img.pixel_um,
        "channels": img.array,
        "channel_names": img.channel_names,
    }
    add_kwargs = {
        "name": (img.channel_names[DAPI_CHANNEL] if img.channel_names else p.stem),
        "metadata": meta,
        "contrast_limits": _percentile_limits(nuclei),
    }
    return [(nuclei, add_kwargs, "image")]


def _percentile_limits(img: np.ndarray, low: float = 1.0, high: float = 99.5):
    """Robust contrast limits so dim DAPI is visible on add."""
    lo, hi = np.percentile(img, [low, high])
    if hi <= lo:
        hi = lo + 1
    return [float(lo), float(hi)]
