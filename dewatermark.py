#!/usr/bin/env python3
"""
dewatermark — remove a visible watermark/logo overlay from a video.

Designed for the Veo / Gemini sparkle logo that sits in a corner of the frame,
but works for any small rectangular overlay.

By default the watermark box is detected automatically: a logo overlay is the
region that is temporally stable (it doesn't change while the scene moves) yet
spatially structured (it has edges, unlike a plain static background), tucked
into a corner. You can override detection with --corner or an explicit --box.

Two removal strategies:
  delogo (default) — ffmpeg's delogo filter interpolates over the box from
                     surrounding pixels. Keeps full frame; soft on busy areas.
  crop           — crops the band away then scales back to the original size.
                   Cleanest result, but loses a sliver of the picture.

Note: this removes the *visible* overlay only. AI-generated videos may also
carry an invisible provenance watermark (e.g. SynthID) that is not touched.
Use on videos you have the right to edit.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(path):
    out = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json", str(path),
    ])
    if out.returncode != 0:
        sys.exit(f"ffprobe failed:\n{out.stderr}")
    info = json.loads(out.stdout)
    s = info["streams"][0]
    dur = float(info.get("format", {}).get("duration", 0) or 0)
    return int(s["width"]), int(s["height"]), dur


def sample_gray_frames(path, W, H, dur, max_frames=48, max_w=480):
    """Return (frames, dw, dh): a stack of grayscale frames as uint8 [N,dh,dw]."""
    dw = min(W, max_w)
    dh = max(2, round(H * dw / W))
    dw -= dw % 2
    dh -= dh % 2
    fps = 3.0 if dur <= 0 else min(3.0, max(0.5, max_frames / dur))
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", f"fps={fps},scale={dw}:{dh},format=gray",
         "-f", "rawvideo", "pipe:1"],
        capture_output=True)
    if r.returncode != 0:
        sys.exit(f"frame sampling failed:\n{r.stderr.decode(errors='ignore')}")
    buf = np.frombuffer(r.stdout, dtype=np.uint8)
    n = buf.size // (dw * dh)
    if n < 2:
        sys.exit("could not sample enough frames to detect a watermark.")
    frames = buf[: n * dw * dh].reshape(n, dh, dw)
    return frames, dw, dh


def neighbor_count(mask):
    """3x3 neighbour count of a boolean mask (for cheap denoising)."""
    p = np.pad(mask.astype(np.int16), 1)
    s = np.zeros_like(mask, dtype=np.int16)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            s += p[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return s


def detect_box(frames, dw, dh, W, H):
    """Detect the watermark box. Returns (x,y,w,h) in full-res px and a score.

    Signal: edge *persistence*. A logo's edges sit in the same pixels in almost
    every frame; moving-scene edges do not, and smooth background has no edges.
    Edges are thresholded per frame (relative to that frame) so a low-contrast
    light-on-light watermark is still picked up.
    """
    f = frames.astype(np.float32)
    n = f.shape[0]
    gx = np.abs(np.diff(f, axis=2, prepend=f[:, :, :1]))
    gy = np.abs(np.diff(f, axis=1, prepend=f[:, :1, :]))
    grad = gx + gy                                   # [N, h, w]

    thr = np.percentile(grad.reshape(n, -1), 93, axis=1)[:, None, None]
    edges = grad > np.maximum(thr, 4.0)
    edge_freq = edges.mean(axis=0)                   # [h, w] in 0..1

    cand = edge_freq > 0.80                          # edge present in >=80% of frames
    cand &= neighbor_count(cand) >= 3               # drop isolated speckle
    grad = edge_freq                                 # use persistence as the weight

    # restrict to the four corners (outer band of the frame)
    cw, ch = round(dw * 0.34), round(dh * 0.24)
    weight = grad * cand
    regions = {
        "tl": (slice(0, ch), slice(0, cw)),
        "tr": (slice(0, ch), slice(dw - cw, dw)),
        "bl": (slice(dh - ch, dh), slice(0, cw)),
        "br": (slice(dh - ch, dh), slice(dw - cw, dw)),
    }
    best, best_score = None, 0.0
    for name, (ys, xs) in regions.items():
        score = float(weight[ys, xs].sum())
        if score > best_score:
            best, best_score = name, score
    if best is None:
        return None, 0.0

    ys, xs = regions[best]
    sub = cand[ys, xs]
    yy, xx = np.where(sub)
    if yy.size < 4:
        return None, 0.0
    # robust bbox (trim outliers), then offset back into the full frame
    x0, x1 = np.percentile(xx, 2), np.percentile(xx, 98)
    y0, y1 = np.percentile(yy, 2), np.percentile(yy, 98)
    x0 += xs.start; x1 += xs.start; y0 += ys.start; y1 += ys.start

    scale = W / dw
    pad_x = (x1 - x0) * 0.30 + 4
    pad_y = (y1 - y0) * 0.30 + 4
    fx = max(0, round((x0 - pad_x) * scale))
    fy = max(0, round((y0 - pad_y) * scale))
    fw = min(W - fx, round((x1 - x0 + 2 * pad_x) * scale))
    fh = min(H - fy, round((y1 - y0 + 2 * pad_y) * scale))
    # confidence: mean edge-persistence inside the detected blob, on a 0-10 scale
    conf = float(weight[ys, xs][sub].mean()) * 10.0
    return (fx, fy, fw, fh), conf


def resolve_corner_preset(corner, size, margin, W, H):
    bw = round(W * size)
    bh = min(bw, round(H * 0.30))
    m = round(min(W, H) * margin)
    corners = {
        "br": (W - bw - m, H - bh - m), "bl": (m, H - bh - m),
        "tr": (W - bw - m, m),          "tl": (m, m),
    }
    x, y = corners[corner]
    return max(0, x), max(0, y), bw, bh


def crop_window(box, W, H, ctx=256):
    """A square window around the watermark box, clamped to the frame (mult of 8).

    The watermark is tiny; inpainting only this window keeps memory low and
    speed high while still giving the model plenty of surrounding context.
    """
    x, y, w, h = box
    size = min(max(ctx, max(w, h) * 4), W, H)
    size -= size % 8
    cx = int(round(x + w / 2 - size / 2))
    cy = int(round(y + h / 2 - size / 2))
    cx = max(0, min(cx, W - size))
    cy = max(0, min(cy, H - size))
    return cx, cy, size


def run_inpaint(src, out, box, W, H, propainter_dir, dilation, device, ctx):
    """Remove the watermark with ProPainter flow-based video inpainting.

    Crops a window around the watermark, inpaints only that window (ProPainter
    borrows real pixels from neighbouring frames where the spot isn't occluded),
    then composites the window back over the original and re-attaches audio.

    Runs on CPU by default: ProPainter's RAFT step deadlocks on Apple MPS, and
    a small crop window keeps it within RAM (no swap) so CPU stays fast.
    """
    x, y, w, h = box
    pp = Path(propainter_dir)
    if not (pp / "inference_propainter.py").exists():
        sys.exit(f"ProPainter not found at {pp}. Clone it there first.")

    cx, cy, size = crop_window(box, W, H, ctx)
    print(f"inpaint window {size}x{size} at ({cx},{cy})  device={device}")

    work = src.parent / "_dewatermark_tmp"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    crop_vid = work / "crop.mp4"
    mask = work / "mask.png"

    # crop the watermark window out of the source
    r = run(["ffmpeg", "-y", "-i", str(src), "-vf", f"crop={size}:{size}:{cx}:{cy}",
             "-c:v", "libx264", "-qp", "0", "-an", str(crop_vid)])
    if r.returncode != 0:
        sys.exit(f"crop failed:\n{r.stderr}")
    # mask in window-local coordinates
    mx, my = x - cx, y - cy
    r = run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={size}x{size}",
             "-vf", f"drawbox=x={mx}:y={my}:w={w}:h={h}:color=white:t=fill",
             "-frames:v", "1", str(mask)])
    if r.returncode != 0:
        sys.exit(f"mask creation failed:\n{r.stderr}")

    results = work / "results"
    env = dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK="1")
    if device == "cpu":
        env["PROPAINTER_FORCE_CPU"] = "1"
    # memory-bounded settings so a 16GB machine doesn't swap during CPU inference
    cmd = [sys.executable, "inference_propainter.py",
           "-i", str(crop_vid.resolve()), "-m", str(mask.resolve()),
           "-o", str(results.resolve()), "--mask_dilation", str(dilation),
           "--raft_iter", "8", "--subvideo_length", "50", "--neighbor_length", "6"]
    print(f"running ProPainter inpainting ({device})...")
    if subprocess.run(cmd, cwd=str(pp), env=env).returncode != 0:
        sys.exit("ProPainter inference failed.")

    produced = results / crop_vid.stem / "inpaint_out.mp4"
    if not produced.exists():
        sys.exit(f"expected output not found: {produced}")

    # composite the inpainted window back over the original; keep original audio
    r = run(["ffmpeg", "-y", "-i", str(src), "-i", str(produced),
             "-filter_complex", f"[0:v][1:v]overlay={cx}:{cy}:format=auto[v]",
             "-map", "[v]", "-map", "0:a:0?",
             "-c:v", "libx264", "-crf", "18", "-preset", "medium",
             "-c:a", "copy", str(out)])
    if r.returncode != 0:
        sys.exit(f"composite failed:\n{r.stderr}")
    shutil.rmtree(work, ignore_errors=True)
    print(f"done -> {out}")


def build_filter(method, x, y, w, h, W, H):
    if method == "delogo":
        x = max(1, x); y = max(1, y)
        w = min(w, W - x - 1); h = min(h, H - y - 1)
        return f"delogo=x={x}:y={y}:w={w}:h={h}"
    if y > H - (y + h):                       # logo nearer the bottom
        return f"crop={W}:{y}:0:0,scale={W}:{H}"
    cut = y + h                               # logo nearer the top
    return f"crop={W}:{H - cut}:0:{cut},scale={W}:{H}"


def main():
    p = argparse.ArgumentParser(description="Remove a visible watermark from a video.")
    p.add_argument("input", help="input video path")
    p.add_argument("-o", "--output", help="output path (default: <name>_clean.mp4)")
    p.add_argument("--method", choices=["inpaint", "delogo", "crop"], default="inpaint",
                   help="inpaint=AI flow-based (best), delogo=interpolate, crop=cut band")
    p.add_argument("--propainter", default=str(SCRIPT_DIR / "ProPainter"),
                   help="path to the ProPainter repo (for --method inpaint)")
    p.add_argument("--dilation", type=int, default=8,
                   help="mask dilation in px for inpaint (default 8)")
    p.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu",
                   help="inpaint compute device (default cpu; use cuda for NVIDIA GPU)")
    p.add_argument("--ctx", type=int, default=256,
                   help="inpaint window size in px; bigger=more context, more RAM (default 256)")
    p.add_argument("--corner", choices=["br", "bl", "tr", "tl"],
                   help="force the logo corner (skips auto-detection)")
    p.add_argument("--box", help="explicit box 'x,y,w,h' in px (skips auto-detection)")
    p.add_argument("--size", type=float, default=0.16,
                   help="preset box width fraction, used with --corner (default 0.16)")
    p.add_argument("--margin", type=float, default=0.02,
                   help="preset inset fraction, used with --corner (default 0.02)")
    p.add_argument("--preview", action="store_true",
                   help="write one frame with the box drawn, then exit")
    p.add_argument("--crf", type=int, default=18, help="x264 quality, lower=better (default 18)")
    args = p.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH.")
    src = Path(args.input)
    if not src.exists():
        sys.exit(f"no such file: {src}")

    W, H, dur = probe(src)

    if args.box:
        x, y, w, h = (int(v) for v in args.box.split(","))
        print(f"video {W}x{H}  box x={x} y={y} w={w} h={h}  (manual)")
    elif args.corner:
        x, y, w, h = resolve_corner_preset(args.corner, args.size, args.margin, W, H)
        print(f"video {W}x{H}  box x={x} y={y} w={w} h={h}  (preset {args.corner})")
    else:
        frames, dw, dh = sample_gray_frames(src, W, H, dur)
        box, conf = detect_box(frames, dw, dh, W, H)
        if box is None:
            sys.exit("could not auto-detect a watermark. Try --corner br or --box x,y,w,h.")
        x, y, w, h = box
        print(f"video {W}x{H}  detected box x={x} y={y} w={w} h={h}  "
              f"(confidence {conf:.1f}, {frames.shape[0]} frames)")
        if conf < 4:
            print("  ! low confidence — double-check with --preview before processing.")

    if args.preview:
        out = src.with_name(src.stem + "_preview.png")
        vf = f"drawbox=x={x}:y={y}:w={w}:h={h}:color=red@1.0:t=4"
        r = run(["ffmpeg", "-y", "-i", str(src), "-vf", vf, "-frames:v", "1", str(out)])
        if r.returncode != 0:
            sys.exit(r.stderr)
        print(f"preview -> {out}")
        return

    out = Path(args.output) if args.output else src.with_name(src.stem + "_clean.mp4")

    if args.method == "inpaint":
        run_inpaint(src, out, (x, y, w, h), W, H, args.propainter,
                    args.dilation, args.device, args.ctx)
        return

    vf = build_filter(args.method, x, y, w, h, W, H)
    cmd = ["ffmpeg", "-y", "-i", str(src), "-vf", vf,
           "-c:v", "libx264", "-crf", str(args.crf), "-preset", "medium",
           "-c:a", "copy", str(out)]
    print("running:", " ".join(cmd))
    if subprocess.run(cmd).returncode != 0:
        sys.exit("ffmpeg failed.")
    print(f"done -> {out}")


if __name__ == "__main__":
    main()
