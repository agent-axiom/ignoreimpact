#!/usr/bin/env python3
"""Render captured IgnoreImpact terminal output at an illustrative 28-second pace.

Requires Pillow and ffmpeg (libx264), plus DejaVu Sans/Mono fonts. No CLI results
are generated here: all terminal text comes from record_demo.py's storyboard.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1600, 1080
PALETTE = {
    "bg": "#0b1220", "terminal": "#101c2e", "bar": "#17253a",
    "white": "#edf4ff", "muted": "#aebed5", "faint": "#7286a3",
    "cyan": "#67e8df", "orange": "#ffc087", "border": "#293b55",
}
# Scene, seconds, heading, subheading, focus, number of terminal lines shown.
# Text is post-capture presentation only. No actual execution timing is implied.
TIMELINE = [
    ("build", 0.6, "Build from source", "From a checkout · Go 1.24+", "", 1),
    ("build", 0.8, "Build from source", "From a checkout · Go 1.24+", "", 4),
    ("build", 3.6, "Build from source", "From a checkout · Go 1.24+", "", None),
    ("policies", 1.0, "One tree. Two ignore policies.", "Tiny bundled fixture · no dependencies installed", "", 2),
    ("policies", 4.0, "One tree. Two ignore policies.", "Before excludes node_modules; after excludes .env*", "", None),
    ("compare", 1.0, "See exactly what changed", "Both policies are evaluated against the same current tree", "", 2),
    ("compare", 2.0, "One file added. One file removed.", "The report shows bytes and the matching rule on each side", "summary", None),
    ("compare", 5.0, ".env* now excludes .env.example", "Removed from inclusion: the 11-byte sample environment file", "removed", None),
    ("compare", 5.0, "node_modules is no longer excluded", "Newly included: the 18-byte synthetic cache.bin fixture", "added", None),
    ("gate", 5.0, "CI can require review of added paths", "Exit 1 means the requested gate failed; exit 2 means an error", "", None),
]


def terminal_lines(scene):
    lines = []
    for command in scene["transcript"]:
        parts = command["command"].splitlines()
        lines.extend([("$ " if i == 0 else "  ") + part for i, part in enumerate(parts)])
        lines.extend(command["output"].splitlines())
        lines.append("")
    # Physical wrapping only; preserve every source character, indentation and
    # spacing. Output is ASCII, so columns equal character positions.
    wrapped = []
    for line in lines:
        if not line.isascii():
            raise ValueError("Non-ASCII terminal content needs width-aware wrapping")
        wrapped.extend(textwrap.wrap(line, width=92, expand_tabs=False, replace_whitespace=False,
                                     drop_whitespace=False) or [""])
    return wrapped


def font(directory, name, size):
    from PIL import ImageFont

    return ImageFont.truetype(str(directory / name), size)


def render_frame(scene, heading, subtitle, focus, maximum, fonts, progress):
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (WIDTH, HEIGHT), PALETTE["bg"])
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((48, 46, 59, 74), radius=5, fill=PALETTE["cyan"])
    draw.text((76, 46), "IGNOREIMPACT", font=fonts["label"], fill=PALETTE["cyan"])
    draw.text((1548, 48), "SAME TREE / TWO POLICIES", anchor="ra", font=fonts["small"], fill=PALETTE["muted"])
    draw.text((48, 92), heading, font=fonts["heading"], fill=PALETTE["white"])
    if draw.textbbox((48, 92), heading, font=fonts["heading"])[2] > 1552:
        raise ValueError("Heading overflow")
    draw.text((50, 158), subtitle, font=fonts["body"], fill=PALETTE["muted"])
    draw.rounded_rectangle((48, 218, 1552, 960), radius=18, fill=PALETTE["terminal"], outline=PALETTE["border"], width=2)
    draw.rounded_rectangle((49, 219, 1551, 266), radius=17, fill=PALETTE["bar"])
    draw.rectangle((49, 244, 1551, 266), fill=PALETTE["bar"])
    labels = {"build": "01  SOURCE BUILD", "policies": "02  POLICY INPUTS", "compare": "03  ACTUAL CLI OUTPUT", "gate": "04  REVIEW GATE"}
    draw.text((76, 228), labels[scene["id"]], font=fonts["small"], fill=PALETTE["muted"])
    cwd = "repository root" if scene["cwd"] == "." else scene["cwd"]
    draw.text((1524, 228), "cwd: " + cwd, anchor="ra", font=fonts["small"], fill=PALETTE["muted"])
    lines = terminal_lines(scene)
    if maximum is not None:
        lines = lines[:maximum]
    if len(lines) > 21:
        raise ValueError(f"Terminal overflow: {len(lines)} lines")
    y = 287
    zone = ""
    for line in lines:
        if line.startswith('- ".env.example"'):
            zone = "removed"
        elif line.startswith('+ "node_modules/cache.bin"'):
            zone = "added"
        elif not line or line.startswith("Bytes are"):
            zone = ""
        summary = line.startswith(("Included:", "Added:", "Removed:"))
        highlighted = (focus == zone and bool(zone)) or (focus == "summary" and summary)
        if highlighted:
            draw.rounded_rectangle((65, y - 1, 1534, y + 29), radius=4, fill="#233951")
            draw.rectangle((66, y - 1, 70, y + 29), fill=PALETTE["orange"] if zone == "removed" else PALETTE["cyan"])
        color = PALETTE["white"]
        if line.startswith("$") or (line.startswith("    --")):
            color = PALETTE["cyan"]
        elif line.startswith("-"):
            color = PALETTE["orange"]
        elif line.startswith("+"):
            color = PALETTE["cyan"]
        elif line.startswith(("Bytes are", "entries with", "Symlinks", "    before:", "    after:")):
            color = PALETTE["muted"]
        bbox = draw.textbbox((82, y), line, font=fonts["mono"])
        if bbox[2] > 1524 or bbox[3] > 950:
            raise ValueError(f"Terminal text overflow: {line!r}")
        draw.text((82, y), line, font=fonts["mono"], fill=color)
        y += 31
    draw.text((50, 987), "github.com/agent-axiom/ignoreimpact", font=fonts["footer"], fill=PALETTE["white"])
    draw.text((1550, 989), "Actual output · illustrative playback pace", anchor="ra", font=fonts["small"], fill=PALETTE["muted"])
    draw.rectangle((50, 1040, 1550, 1044), fill=PALETTE["border"])
    draw.rectangle((50, 1040, 50 + round(1500 * progress), 1044), fill=PALETTE["cyan"])
    return im


def render(directory, font_dir):
    storyboard = json.loads((directory / "storyboard.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    # Refuse stale/edited output rather than silently making an illustrative
    # terminal from arbitrary hand-edited text.
    for scene in storyboard["scenes"]:
        records = [c for c in manifest["commands"] if c["scene"] == scene["id"]]
        if len(records) != len(scene["transcript"]):
            raise ValueError("Scene command count differs from capture manifest")
        for record, command in zip(records, scene["transcript"]):
            data = (directory / record["pty_file"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != record["pty_sha256"]:
                raise ValueError("Captured PTY file changed")
            if command["output"] != data.decode("utf-8").replace("\r\n", "\n"):
                raise ValueError("Storyboard output differs from raw PTY capture")
            if record["cwd"] != scene["cwd"] or command["command"] != record["command"] or command["exit_code"] != record["exit_code"] or record["exit_code"] != scene.get("expected_exit", 0):
                raise ValueError("Storyboard command differs from capture manifest")
    # Integrity checks and unit tests do not require optional media packages.
    from PIL import Image

    fonts = {"mono": font(font_dir, "DejaVuSansMono.ttf", 26),
             "heading": font(font_dir, "DejaVuSans-Bold.ttf", 44),
             "label": font(font_dir, "DejaVuSans-Bold.ttf", 24),
             "body": font(font_dir, "DejaVuSans.ttf", 26),
             "footer": font(font_dir, "DejaVuSans.ttf", 24),
             "small": font(font_dir, "DejaVuSans.ttf", 20)}
    scenes = {scene["id"]: scene for scene in storyboard["scenes"]}
    frames, durations, concat, at = [], [], [], 0.0
    for index, (scene, seconds, heading, subtitle, focus, maximum) in enumerate(TIMELINE):
        frame = render_frame(scenes[scene], heading, subtitle, focus, maximum, fonts, (at + seconds) / 28)
        frame_name = f"frame-{index:02}.png"
        frame.save(directory / frame_name)
        frames.append(frame)
        durations.append(round(seconds * 1000))
        concat.extend([f"file '{frame_name}'", f"duration {seconds:.6f}"])
        at += seconds
    assert round(at, 3) == 28.0
    concat.append(f"file 'frame-{len(frames) - 1:02}.png'")
    (directory / "frames.ffconcat").write_text("\n".join(concat) + "\n")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", "frames.ffconcat", "-t", "28", "-vf", "fps=10", "-c:v", "libx264", "-preset", "slow",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", "ignoreimpact-demo.mp4"],
                   cwd=directory, check=True)
    # A shared palette prevents text-color shimmer between GIF frames. Keep full
    # resolution; it is already small because only ten frames change.
    swatches = Image.new("RGB", (WIDTH, HEIGHT * len(frames)))
    for index, frame in enumerate(frames):
        swatches.paste(frame, (0, index * HEIGHT))
    palette = swatches.quantize(colors=256)
    gifs = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    gifs[0].save(directory / "ignoreimpact-demo.gif", save_all=True, append_images=gifs[1:],
                 duration=durations, loop=0, optimize=True, disposal=2)
    shutil.copyfile(directory / "frame-08.png", directory / "poster.png")
    media = {"renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "storyboard_sha256": hashlib.sha256((directory / "storyboard.json").read_bytes()).hexdigest(),
             "duration_seconds": at, "width": WIDTH, "height": HEIGHT,
             "pacing": "Illustrative reading pace; not elapsed command/runtime performance",
             "source_commit": manifest["source_commit"],
             "files": {name: {"bytes": (directory / name).stat().st_size,
                              "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest()}
                       for name in ("ignoreimpact-demo.mp4", "ignoreimpact-demo.gif", "poster.png")},
             "scenes": [{"scene": item[0], "duration_seconds": item[1], "heading": item[2]} for item in TIMELINE]}
    (directory / "media.json").write_text(json.dumps(media, indent=2) + "\n")
    print(json.dumps(media, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "dist/demo")
    parser.add_argument("--font-dir", type=Path, default=Path("/usr/share/fonts/truetype/dejavu"))
    args = parser.parse_args()
    directory = args.input.resolve()
    if directory == ROOT or not directory.is_relative_to(ROOT):
        parser.error("Keep input/output inside this checkout")
    render(directory, args.font_dir)


if __name__ == "__main__":
    main()
