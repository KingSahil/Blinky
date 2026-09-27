cmake_minimum_required(VERSION 3.16)

project(AIVideoEditor LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(AIVideoEditor
    src/main.cpp
    src/CommandLineParser.cpp
    src/MusicMergeEngine.cpp
    src/TrimEngine.cpp
    src/MergeEngine.cpp
)

target_include_directories(AIVideoEditor PRIVATE
    include
)

enable_testing()

add_executable(TrimEngineTests
    tests/TrimEngineTests.cpp
    src/TrimEngine.cpp
)

target_include_directories(TrimEngineTests PRIVATE
    include
)

add_test(NAME TrimEngineTests COMMAND TrimEngineTests)

add_executable(CommandLineParserTests
    tests/CommandLineParserTests.cpp
    src/CommandLineParser.cpp
)

target_include_directories(CommandLineParserTests PRIVATE
    include
)

add_test(NAME CommandLineParserTests COMMAND CommandLineParserTests)

add_executable(MusicMergeEngineTests
    tests/MusicMergeEngineTests.cpp
    src/MusicMergeEngine.cpp
)

target_include_directories(MusicMergeEngineTests PRIVATE
    include
)

add_test(NAME MusicMergeEngineTests COMMAND MusicMergeEngineTests)

add_executable(MergeEngineTests
    tests/MergeEngineTests.cpp
    src/MergeEngine.cpp
)

target_include_directories(MergeEngineTests PRIVATE
    include
)

add_test(NAME MergeEngineTests COMMAND MergeEngineTests)
