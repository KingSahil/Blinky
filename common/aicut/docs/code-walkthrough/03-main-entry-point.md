# 03 - Main Entry Point

This file explains `src/main.cpp`.

`src/main.cpp` is where the command-line application starts. It parses the
terminal arguments, chooses the requested command, calls the matching engine,
and returns an exit code.

## File Location

```text
src/main.cpp
```

## Included Headers

```cpp
#include "CommandLineParser.h"
#include "MusicMergeEngine.h"
#include "TrimEngine.h"

#include <iostream>
#include <string>
#include <vector>
```

The project headers provide the parser and editing engines.

The standard headers are used for:

- `<iostream>`: printing help and error messages.
- `<string>`: storing paths and command values.
- `<vector>`: collecting `argv` into an easier-to-use container.

## collectArguments

```cpp
std::vector<std::string> collectArguments(int argc, char* argv[])
```

The operating system gives `main` arguments as `argc` and `argv`.

This helper copies those values into a `std::vector<std::string>` so
`CommandLineParser` can work with normal C++ strings.

## main

```cpp
int main(int argc, char* argv[])
```

This is the starting point of the app.

## Parsing The Command

```cpp
ParsedCommand command = parseCommandLine(collectArguments(argc, argv));
```

This turns terminal input into a structured command.

For example:

```powershell
AIVideoEditor trim --input input.mp4 --output clip.mp4 --start 10 --end 25
```

becomes a `ParsedCommand` with:

- command type: `Trim`
- input path: `input.mp4`
- output path: `clip.mp4`
- start seconds: `10`
- end seconds: `25`

## Help Command

```cpp
if (command.type == CommandType::Help)
{
    std::cout << getUsageText();
    return 0;
}
```

If the user asks for help, the app prints usage text and exits successfully.

## Invalid Commands

```cpp
if (!command.isValid)
{
    std::cout << "Error: " << command.errorMessage << "\n\n";
    std::cout << getUsageText();
    return 1;
}
```

Invalid commands print a clear error, show usage help, and exit with `1`.

This is important for AI control because a calling agent can tell whether a
command succeeded by checking the exit code.

## Trim Command

```cpp
if (command.type == CommandType::Trim)
{
    TrimEngine engine;
    bool success = engine.trim(...);
    return success ? 0 : 1;
}
```

The trim command creates a `TrimEngine` and passes it the parsed values.

`TrimEngine` handles validation, FFmpeg command creation, and command
execution.

## Add-Song Command

```cpp
if (command.type == CommandType::AddSong)
{
    MusicMergeEngine engine;
    bool success = engine.addBackgroundMusic(...);
    return success ? 0 : 1;
}
```

The add-song command creates a `MusicMergeEngine` and passes it the parsed
video path, song path, output path, and music volume.

`MusicMergeEngine` handles validation, FFmpeg command creation, and command
execution.

## Responsibility Of This File

`src/main.cpp` should stay focused on command dispatch:

- collect arguments
- parse the command
- print help or errors
- call the correct engine
- return the final process status

It does not build FFmpeg commands directly. That job belongs to the engine
classes.
