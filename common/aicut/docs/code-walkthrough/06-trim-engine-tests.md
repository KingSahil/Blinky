# 06 - Tests

This file explains the current test style.

The project uses small C++ test executables instead of a test framework. Each
test file has its own `main()` function, prints a clear failure message, and
returns `1` when a check fails.

## Test Files

```text
tests/TrimEngineTests.cpp
tests/CommandLineParserTests.cpp
tests/MusicMergeEngineTests.cpp
```

## Running Tests

After building the project, run:

```powershell
ctest --test-dir build -C Debug --output-on-failure
```

The `-C Debug` option is useful when CMake uses the Visual Studio generator.

## TrimEngineTests

`TrimEngineTests.cpp` checks that trimming rejects invalid inputs before FFmpeg
runs.

It covers:

- missing input file rejection
- invalid time range rejection
- output folder rejection
- helpful output-path error message

The tests create temporary files and folders when they need validation to reach
a specific branch.

## CommandLineParserTests

`CommandLineParserTests.cpp` checks command-line parsing without running
FFmpeg.

It covers:

- valid `trim` commands
- valid `add-song` commands
- default music volume
- missing required options
- unknown commands
- unknown options
- invalid music volume
- `--help`

This is important because the command format is the public interface that a
human or AI agent will call.

## MusicMergeEngineTests

`MusicMergeEngineTests.cpp` checks the background music engine.

It covers:

- missing video file rejection
- missing song file rejection
- output folder rejection
- generated FFmpeg command details

The command check verifies that the music engine:

- loops short songs
- applies music volume
- mixes original audio and music
- copies the video stream
- encodes output audio as AAC
- stops at the video duration

## What These Tests Do Not Cover Yet

The tests do not currently verify:

- successful processing of real video and audio files
- behavior when FFmpeg is missing
- behavior when FFmpeg returns a non-zero exit code
- videos with no original audio stream
- paths containing embedded double quotes

Those are useful future test areas as the app grows.
