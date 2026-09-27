# AI Video Editor

A beginner-friendly C++ command-line app that edits videos by calling FFmpeg.
The app uses separate terminal commands so it can be controlled by a person or
by an AI agent.

The current app can:

- trim a video
- add background music to a video

## What You Will Need

Install these before you build the project:

- A C++ compiler that supports C++17
- CMake 3.16 or newer
- FFmpeg

On Windows, you can use Visual Studio Build Tools, Visual Studio Community, or
another C++ compiler that works with CMake.
  aicut trim --input "sample\input\dance.mp4" --output "sample\output\dance-trimmed.mp4" --start 10 --end 25

Check that FFmpeg is installed by running:

```powershell
ffmpeg -version
```

If PowerShell says the command is not found, install FFmpeg and add it to your
ffmpeg -y -ss 10 -i "sample\input\dance.mp4" -t 15 -c copy "sample\output\dance-trimmed.mp4"
system `PATH`.

## Project Files

```text
  aicut add-song --video "sample\output\dance-trimmed.mp4" --song "sample\input\edm.mp3" --output "sample\output\dance-with-music.mp4"
AIVideoEditor/
|-- CMakeLists.txt
|-- README.md
|-- aicut.cmd
|-- include/
|   |-- CommandLineParser.h
  aicut add-song --video "sample\output\dance-trimmed.mp4" --song "sample\input\edm.mp3" --output "sample\output\dance-with-music.mp4" --music-volume 0.35
|   |-- MusicMergeEngine.h
|   `-- TrimEngine.h
|-- src/
|   |-- CommandLineParser.cpp
|   |-- MusicMergeEngine.cpp
|   |-- TrimEngine.cpp
sample\output\clip.mp4
|   `-- main.cpp
|-- tests/
|   |-- CommandLineParserTests.cpp
|   |-- MusicMergeEngineTests.cpp
|   `-- TrimEngineTests.cpp
`-- docs/
sample\output
    `-- code-walkthrough/
```

What each important file does:

- `src/main.cpp` starts the app and sends commands to the right engine.
- `CommandLineParser` parses commands like `trim` and `add-song`.
- `TrimEngine` validates trim settings and runs FFmpeg for trimming.
- `MusicMergeEngine` validates video/music paths and runs FFmpeg to mix audio.
- `tests/` contains small test programs for the parser and engines.

## Build The App

Open PowerShell in this project folder, then run:

```powershell
cmake -S . -B build
cmake --build build
```

With the Visual Studio generator, the executable is usually here:

```text
build\Debug\AIVideoEditor.exe
```

With a single-config generator, it may be here instead:

```text
build\AIVideoEditor.exe
```

## Short Command

From the project folder, you can use the included wrapper:

```powershell
.\aicut --help
```

This runs the built app from `build\Debug\AIVideoEditor.exe` when it exists,
or `build\AIVideoEditor.exe` for single-config builds.

## Show Help

```powershell
.\aicut --help
```

Help output:

```text
Usage:
  AIVideoEditor trim --input <video> --output <video> --start <seconds> --end <seconds>
  AIVideoEditor add-song --video <video> --song <audio> --output <video> [--music-volume <0.0-1.0>]
  AIVideoEditor merge --inputs <video1,video2,...> --output <video>
  AIVideoEditor --help
```

## Trim A Video

```powershell
.\aicut trim --input "sample\input\dance.mp4" --output "sample\output\dance-trimmed.mp4" --start 10 --end 25
```

This creates a new video clip from second `10` to second `25`.

## Add Background Music

```powershell
.\aicut add-song --video "sample\input\dance.mp4" --song "sample\input\edm.mp3" --output "sample\output\dance-with-music.mp4" --music-volume 0.35
```

## Merge / Concatenate Videos

```powershell
.\aicut merge --inputs "sample\output\clip1.mp4,sample\output\clip2.mp4" --output "sample\output\merged.mp4"
```

## Blinky Desktop UI & Model Context Protocol (MCP) Integration

AiCut can be controlled using **Blinky** as an AI voice/desktop user interface.

- **MCP Server**: `aicut_mcp.py` implements standard JSON-RPC 2.0 stdio Model Context Protocol.
- **Windows File Explorer Context**: When you have File Explorer open, you can ask Blinky:
  - *"Trim this video from 10 to 25 seconds"* (automatically detects selected video in Explorer)
  - *"Add song edm.mp3 to this video with 30% volume"*
  - *"Merge these selected clips"*
  - *"Inspect media info"*
- **MCP Config**: Use `mcp_config.json` to register AiCut with any MCP client.

## Run The Tests

```powershell
.\build\CommandLineParserTests.exe
.\build\TrimEngineTests.exe
.\build\MusicMergeEngineTests.exe
.\build\MergeEngineTests.exe
```

## Common Problems

### FFmpeg is not found

Run:

```powershell
ffmpeg -version
```

If that fails, FFmpeg is either not installed or not available in your `PATH`.

### Input file does not exist

Check that the video or song path is correct. On Windows, you can drag a file
into PowerShell to paste its full path.

### Output path must include a file name

Use a full file path for the output, not just a folder.

Good:

```text
sample\output\clip.mp4
```

Not enough:

```text
sample\output
```

### End time must be greater than start time

The trim command needs an end time that comes after the start time.

Good:

```text
--start 10 --end 25
```

Not valid:

```text
--start 25 --end 10
```

### Music volume must be between 0.0 and 1.0

Good:

```text
--music-volume 0.25
```

Not valid:

```text
--music-volume 1.5
```

## Beginner Notes

If you are new to this project, start with the detailed walkthrough docs:

```text
docs/code-walkthrough/01-reading-order.md
```

The walkthrough files explain the build file, app entry point, trim engine, and
tests. They are intentionally written for someone learning the project from
scratch.

## Current Scope

This project currently focuses on a simple command-driven workflow:

1. Parse a terminal command.
2. Validate paths, options, and time ranges.
3. Build an FFmpeg command.
4. Run FFmpeg.
5. Exit with `0` on success or `1` on failure.

Future versions could add more commands, previews, multiple clips, or
AI-assisted editing workflows.
