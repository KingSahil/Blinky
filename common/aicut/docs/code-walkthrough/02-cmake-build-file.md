# 02 - CMake Build File

This file explains `CMakeLists.txt`.

`CMakeLists.txt` tells CMake how to configure and build the project. It defines
the C++ version, the application executable, the test executables, include
folders, and the CTest registrations.

## File Location

```text
CMakeLists.txt
```

## Purpose

The build file answers these questions:

- What is the project called?
- Which programming language is used?
- Which C++ standard is required?
- Which source files belong to the main app?
- Which source files belong to each test executable?
- Where should the compiler look for header files?
- How should CTest run the tests?

## Minimum CMake Version

```cmake
cmake_minimum_required(VERSION 3.16)
```

This means the project expects CMake version `3.16` or newer.

## Project Declaration

```cmake
project(AIVideoEditor LANGUAGES CXX)
```

This names the project `AIVideoEditor` and says the project uses C++.

## C++ Standard Settings

```cmake
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
```

These lines require C++17. The project uses C++17 features such as
`std::filesystem`.

## Main Application Executable

```cmake
add_executable(AIVideoEditor
    src/main.cpp
    src/CommandLineParser.cpp
    src/MusicMergeEngine.cpp
    src/TrimEngine.cpp
)
```

This creates the main executable named `AIVideoEditor`.

It is built from:

- `src/main.cpp`, the program entry point.
- `src/CommandLineParser.cpp`, the command parser.
- `src/MusicMergeEngine.cpp`, the background music engine.
- `src/TrimEngine.cpp`, the trim engine.

## Include Directory For The Main App

```cmake
target_include_directories(AIVideoEditor PRIVATE
    include
)
```

This tells the compiler that header files can be found in the `include`
directory.

That is why source files can write:

```cpp
#include "TrimEngine.h"
```

instead of:

```cpp
#include "../include/TrimEngine.h"
```

## Enable Testing

```cmake
enable_testing()
```

This turns on CTest support for the project.

With the Visual Studio generator, tests can be run with:

```powershell
ctest --test-dir build -C Debug --output-on-failure
```

## Test Executables

The project builds three test executables:

```text
TrimEngineTests
CommandLineParserTests
MusicMergeEngineTests
```

Each test executable has its own `main()` function and links only the production
source file it needs.

For example:

```cmake
add_executable(CommandLineParserTests
    tests/CommandLineParserTests.cpp
    src/CommandLineParser.cpp
)
```

This keeps tests focused and avoids linking `src/main.cpp` into test programs.

## Registering Tests With CTest

Each test executable is registered with CTest:

```cmake
add_test(NAME CommandLineParserTests COMMAND CommandLineParserTests)
```

CTest can then run all tests together.

## Why There Are Multiple Executables

The project builds separate programs:

```text
AIVideoEditor             -> the real command-line app
TrimEngineTests           -> trim validation tests
CommandLineParserTests    -> command parser tests
MusicMergeEngineTests     -> background music tests
```

This keeps the real app and tests separate while allowing both to reuse the
same production source files.
