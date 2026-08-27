# 01 - Reading Order

This folder explains the project one file at a time. The files are numbered so
a beginner can follow the program from the build setup, to the command-line
entry point, to the editing engines and tests.

## Recommended Order

1. `01-reading-order.md`
   - Start here to understand how the documentation is organized.

2. `02-cmake-build-file.md`
   - Explains `CMakeLists.txt`, which defines how the application and test
     executables are built.

3. `03-main-entry-point.md`
   - Explains `src/main.cpp`, where the command-line app starts and dispatches
     commands.

4. `04-trim-engine-header.md`
   - Explains `include/TrimEngine.h`, which declares the trim engine.

5. `05-trim-engine-implementation.md`
   - Explains `src/TrimEngine.cpp`, where trim validation, FFmpeg command
     creation, and command execution happen.

6. `06-trim-engine-tests.md`
   - Explains the current test style and the validation cases covered by the
     test executables.

7. `07-project-readme.md`
   - Explains `README.md`, the user-facing project guide.

## Project Shape

```text
AIVideoEditor/
|-- CMakeLists.txt
|-- README.md
|-- include/
|   |-- CommandLineParser.h
|   |-- MusicMergeEngine.h
|   `-- TrimEngine.h
|-- src/
|   |-- CommandLineParser.cpp
|   |-- MusicMergeEngine.cpp
|   |-- TrimEngine.cpp
|   `-- main.cpp
|-- tests/
|   |-- CommandLineParserTests.cpp
|   |-- MusicMergeEngineTests.cpp
|   `-- TrimEngineTests.cpp
`-- docs/
    `-- code-walkthrough/
```

## High-Level Program Flow

The current app is a small command-line video editor with separate commands.

```text
User runs a command
    |
    v
src/main.cpp parses command-line arguments
    |
    v
Command is sent to TrimEngine or MusicMergeEngine
    |
    v
The engine validates inputs
    |
    v
The engine builds an FFmpeg command
    |
    v
std::system runs FFmpeg
    |
    v
App exits with 0 on success, 1 on failure
```

## Main Ideas To Watch For

- `src/main.cpp` is responsible for dispatching commands.
- `CommandLineParser` turns terminal arguments into a structured command.
- `TrimEngine` is responsible for trimming.
- `MusicMergeEngine` is responsible for adding background music.
- `CMakeLists.txt` builds the app and all test executables.
- FFmpeg does the real media work; this C++ program prepares and launches the
  FFmpeg commands.
