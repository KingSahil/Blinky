# 05 - Trim Engine Implementation

This file explains `src/TrimEngine.cpp`.

This is the core implementation file. It validates user input, builds an
FFmpeg command, runs that command, and reports whether the trim succeeded.

## File Location

```text
src/TrimEngine.cpp
```

## Included Headers

```cpp
#include "TrimEngine.h"

#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <sstream>
```

`TrimEngine.h` provides the class declaration.

The standard headers are used for:

- `<cstdlib>`: `std::system`
- `<filesystem>`: checking files and directories
- `<iostream>`: printing messages
- `<sstream>`: building the command string

## trim

```cpp
bool TrimEngine::trim(
    const std::string& inputPath,
    const std::string& outputPath,
    double startSeconds,
    double endSeconds
)
```

This is the main function in the trim engine.

It controls the full trim workflow:

```text
validate time range
validate input file
validate output path
calculate duration
build FFmpeg command
print command
run command
return success or failure
```

## Step 1: Validate Time Range

```cpp
if (!isTimeRangeValid(startSeconds, endSeconds))
{
    std::cout << "Failure: end time must be greater than start time.\n";
    return false;
}
```

The app rejects the request if the end time is not after the start time.

Examples:

```text
start = 10, end = 25    valid
start = 25, end = 10    invalid
start = 10, end = 10    invalid
```

This check happens before checking files because it is fast and independent of
the file system.

## Step 2: Validate Input File

```cpp
if (!inputFileExists(inputPath))
{
    std::cout << "Failure: input file does not exist.\n";
    return false;
}
```

If the input path does not exist, there is no video for FFmpeg to read.

The function returns `false` immediately instead of trying to run FFmpeg.

## Step 3: Validate Output Path

```cpp
if (!outputPathLooksLikeFile(outputPath))
{
    std::cout << "Failure: output path must include a file name, like output.mp4.\n";
    return false;
}
```

The app expects the output path to include a file name and extension.

Good:

```text
C:\Videos\clip.mp4
```

Not enough:

```text
C:\Videos
```

This avoids passing an unclear output target to FFmpeg.

## Step 4: Calculate Duration

```cpp
double durationSeconds = endSeconds - startSeconds;
```

The user enters a start time and an end time.

FFmpeg receives a start time and an output length.

So the code converts:

```text
start = 10
end = 25
```

into:

```text
start = 10
duration = 15
```

## Step 5: Build The FFmpeg Command

```cpp
std::string command = buildCommand(
    inputPath,
    outputPath,
    startSeconds,
    durationSeconds
);
```

The command-building details are kept in `buildCommand` so `trim` can stay
readable.

## Step 6: Print The Command

```cpp
std::cout << "\nGenerated FFmpeg command:\n";
std::cout << command << "\n\n";
```

This helps the user see exactly what command the program is about to run.

It is also useful while debugging.

## Step 7: Run FFmpeg

```cpp
int exitCode = std::system(command.c_str());
```

`std::system` asks the operating system shell to run the generated command.

`command` is a `std::string`, but `std::system` expects a C-style string, so
the code calls:

```cpp
command.c_str()
```

The returned `exitCode` tells whether the command succeeded.

## Step 8: Report Result

```cpp
if (exitCode == 0)
{
    std::cout << "Success: video was trimmed without re-encoding.\n";
    return true;
}

std::cout << "Failure: FFmpeg could not trim the video.\n";
return false;
```

An exit code of `0` normally means success.

Any other exit code is treated as failure.

## inputFileExists

```cpp
bool TrimEngine::inputFileExists(const std::string& inputPath) const
{
    return std::filesystem::exists(inputPath);
}
```

This checks whether the path exists.

One detail: this only checks that something exists at the path. It does not
currently check whether the path is specifically a regular file or whether it
is a valid video.

## outputPathLooksLikeFile

```cpp
bool TrimEngine::outputPathLooksLikeFile(const std::string& outputPath) const
{
    std::filesystem::path path(outputPath);

    if (std::filesystem::is_directory(path))
    {
        return false;
    }

    return path.has_filename() && path.has_extension();
}
```

This converts the output string into a `std::filesystem::path`.

Then it rejects the path if it is an existing directory.

Finally, it checks:

- `path.has_filename()`
- `path.has_extension()`

That means the output path should include something like:

```text
clip.mp4
```

The function does not guarantee the extension is a real video extension. It
only checks that some extension exists.

## isTimeRangeValid

```cpp
bool TrimEngine::isTimeRangeValid(double startSeconds, double endSeconds) const
{
    return endSeconds > startSeconds;
}
```

This enforces the minimum time rule.

The function currently allows negative start times if the end time is greater.
For example, `start = -5` and `end = 10` would pass this check. A future
version could add a rule that both values must be non-negative.

## buildCommand

```cpp
std::string TrimEngine::buildCommand(
    const std::string& inputPath,
    const std::string& outputPath,
    double startSeconds,
    double durationSeconds
) const
```

This builds the command sent to FFmpeg.

The command is assembled with `std::ostringstream`:

```cpp
std::ostringstream command;
```

That lets the code append strings and numbers cleanly.

## Command Pieces

```cpp
command << "ffmpeg -y ";
```

Starts FFmpeg and allows overwriting the output file.

```cpp
command << "-ss " << startSeconds << " ";
```

Seeks to the trim start time.

```cpp
command << "-i " << quotePath(inputPath) << " ";
```

Sets the input file. The path is quoted so spaces in the path work.

```cpp
command << "-t " << durationSeconds << " ";
```

Sets how many seconds of output to keep after the seek point.

```cpp
command << "-c copy ";
```

Copies the original audio/video streams without re-encoding.

This is why the app describes itself as lossless and fast.

```cpp
command << quotePath(outputPath);
```

Adds the output file path.

## Example Command

For:

```text
inputPath = C:\Videos\original.mp4
outputPath = C:\Videos\short.mp4
startSeconds = 10
durationSeconds = 15
```

the command becomes:

```powershell
ffmpeg -y -ss 10 -i "C:\Videos\original.mp4" -t 15 -c copy "C:\Videos\short.mp4"
```

## quotePath

```cpp
std::string TrimEngine::quotePath(const std::string& path) const
{
    return "\"" + path + "\"";
}
```

This wraps a path in double quotes.

Example:

```text
C:\My Videos\input.mp4
```

becomes:

```text
"C:\My Videos\input.mp4"
```

## Important Limitations

This implementation is intentionally simple.

Current limitations include:

- It uses `std::system`, which runs through the shell.
- It does not escape double quotes inside paths.
- It checks whether the input path exists, but not whether it is a valid video.
- It checks that the output path has an extension, but not whether the extension
  is a video format.
- It depends on `ffmpeg` being installed and available in the system `PATH`.
- Stream-copy trimming with `-c copy` may cut most accurately near keyframes,
  depending on the input video.

These are reasonable tradeoffs for a small Phase 1 command-line prototype.
