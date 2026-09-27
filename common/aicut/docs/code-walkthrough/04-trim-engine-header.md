# 04 - Trim Engine Header

This file explains `include/TrimEngine.h`.

The header file declares the `TrimEngine` class. A declaration tells the rest
of the program what functions exist, what arguments they take, and what they
return.

## File Location

```text
include/TrimEngine.h
```

## Include Guard

```cpp
#ifndef TRIM_ENGINE_H
#define TRIM_ENGINE_H
```

and:

```cpp
#endif
```

These lines are an include guard.

They prevent the same header from being included multiple times in one
translation unit. Without include guards, the compiler could see duplicate
class declarations and report errors.

## Included Header

```cpp
#include <string>
```

The class uses `std::string`, so the header includes the standard string
library.

## Class Declaration

```cpp
class TrimEngine
{
public:
    ...

private:
    ...
};
```

`TrimEngine` groups all trim-related behavior into one class.

The class has:

- one public function that other files can call
- several private helper functions used internally

## Public Function

```cpp
bool trim(
    const std::string& inputPath,
    const std::string& outputPath,
    double startSeconds,
    double endSeconds
);
```

This is the main function exposed by the class.

It receives:

- `inputPath`: path to the video file that should be trimmed.
- `outputPath`: path where the new trimmed video should be written.
- `startSeconds`: trim start time.
- `endSeconds`: trim end time.

It returns:

- `true` when trimming succeeds.
- `false` when validation fails or FFmpeg fails.

The string parameters are passed as `const std::string&`.

That means:

- `const`: the function should not modify the string.
- `&`: the string is passed by reference, avoiding an unnecessary copy.

## Private Helper: inputFileExists

```cpp
bool inputFileExists(const std::string& inputPath) const;
```

This checks whether the input file exists on disk.

It is private because callers do not need to use it directly. They only need to
call `trim`.

The final `const` means the helper does not modify the `TrimEngine` object.

## Private Helper: outputPathLooksLikeFile

```cpp
bool outputPathLooksLikeFile(const std::string& outputPath) const;
```

This checks that the output path appears to include a file name and extension.

For example:

```text
C:\Videos\clip.mp4
```

looks like a file path.

But:

```text
C:\Videos
```

does not clearly include a file name.

## Private Helper: isTimeRangeValid

```cpp
bool isTimeRangeValid(double startSeconds, double endSeconds) const;
```

This validates the time range.

The current rule is simple:

```text
endSeconds must be greater than startSeconds
```

## Private Helper: buildCommand

```cpp
std::string buildCommand(
    const std::string& inputPath,
    const std::string& outputPath,
    double startSeconds,
    double durationSeconds
) const;
```

This creates the FFmpeg command string.

It receives a duration instead of an end time because the implementation
calculates:

```cpp
durationSeconds = endSeconds - startSeconds;
```

before building the command.

## Private Helper: quotePath

```cpp
std::string quotePath(const std::string& path) const;
```

This wraps a file path in double quotes.

That helps FFmpeg receive paths with spaces as one argument.

Example:

```text
C:\My Videos\input.mp4
```

becomes:

```text
"C:\My Videos\input.mp4"
```

## Why These Helpers Are Private

Only `trim` is part of the public interface.

The other functions are implementation details. Keeping them private makes the
class easier to use because outside code only has one main operation to call.

It also gives the implementation freedom to change its internal helpers later
without changing the public API.
