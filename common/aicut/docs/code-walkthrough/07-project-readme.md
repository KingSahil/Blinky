# 07 - Project README

This file explains `README.md`.

The README is the user-facing guide for the project. It tells someone what the
app does, what tools they need, how to build it, how to run commands, how to
run tests, and what common errors mean.

## File Location

```text
README.md
```

## Purpose

The README is not part of the compiled application. It is documentation for
humans.

It is especially useful for someone who has just opened the project and wants
to know:

- what the app is
- what must be installed
- how the files are organized
- how to build the app
- which terminal commands are available
- how to run the tests
- what common errors mean

## Project Summary

The README describes the project as a beginner-friendly C++ command-line app
that edits videos by calling FFmpeg.

The C++ app does not directly decode, edit, or encode video frames. Instead, it
validates command options and uses FFmpeg to do the media work.

## Required Tools

The README lists three requirements:

- a C++17 compiler
- CMake 3.16 or newer
- FFmpeg

These match the project code and build file.

## Project Files Section

The README shows the main folders and the important parser, engine, and test
files.

The files in this `docs/code-walkthrough` folder expand those short
explanations into more detailed notes.

## Build Instructions

The README recommends:

```powershell
cmake -S . -B build
cmake --build build
```

The first command configures the project and creates the `build` directory.

The second command compiles the project.

With the Visual Studio generator, the main executable is usually:

```text
build\Debug\AIVideoEditor.exe
```

## Command Instructions

The README explains the available commands:

```powershell
AIVideoEditor trim --input <video> --output <video> --start <seconds> --end <seconds>
AIVideoEditor add-song --video <video> --song <audio> --output <video> [--music-volume <0.0-1.0>]
AIVideoEditor --help
```

This replaces the older prompt-based flow. The user now passes all values in
one terminal command.

That makes the app easier for an AI agent to control because there are no
interactive questions to answer.

## FFmpeg Explanations

The README explains that trim uses stream copying:

```text
-c copy
```

It also explains that add-song:

- keeps the original video audio
- mixes the selected song underneath it
- loops short songs
- stops at the video duration
- writes AAC audio

## Test Instructions

The README recommends:

```powershell
ctest --test-dir build -C Debug --output-on-failure
```

It also lists direct commands for each test executable.

## Common Problems Section

The README explains likely user errors:

- FFmpeg is not found.
- An input file does not exist.
- The output path does not include a file name.
- The trim end time is not greater than the start time.
- The music volume is outside `0.0` to `1.0`.

These match the validation behavior in the parser and engine classes.

## How This README Relates To The Code Walkthrough

Use `README.md` when you want to build, run, or understand the app at a high
level.

Use this numbered walkthrough folder when you want a deeper explanation of each
individual file.
