#!/usr/bin/env bash
# Clone ProPainter and apply the patches needed for --method inpaint.
# Safe to re-run: it resets the clone to the pinned commit before patching.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PP="$DIR/ProPainter"
PIN="e870e79321c31b733e2031af5aa2fb1fe3ac7eec"

if [ ! -d "$PP/.git" ]; then
  echo "Cloning ProPainter..."
  git clone https://github.com/sczhou/ProPainter.git "$PP"
fi

echo "Pinning ProPainter to $PIN and applying patch..."
git -C "$PP" fetch --depth 1 origin "$PIN" 2>/dev/null || git -C "$PP" fetch origin
git -C "$PP" checkout -f "$PIN"
git -C "$PP" apply "$DIR/propainter.patch"

echo "Done. ProPainter is ready at $PP"
echo "Model weights (~500MB) download automatically on the first inpaint run."
