#include "TrimEngine.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>

int main()
{
    TrimEngine engine;

    bool missingFileResult = engine.trim(
        "this-file-should-not-exist.mp4",
        "output.mp4",
        1.0,
        2.0
    );

    if (missingFileResult)
    {
        std::cout << "Test failed: trim should reject a missing input file.\n";
        return 1;
    }

    const std::string temporaryInputPath = "temporary-test-input.mp4";

    std::ofstream temporaryFile(temporaryInputPath);
    temporaryFile << "This is only a test file.\n";
    temporaryFile.close();

    bool invalidTimeResult = engine.trim(
        temporaryInputPath,
        "output.mp4",
        5.0,
        2.0
    );

    std::filesystem::remove(temporaryInputPath);

    if (invalidTimeResult)
    {
        std::cout << "Test failed: trim should reject end time <= start time.\n";
        return 1;
    }

    std::filesystem::create_directory("temporary-output-folder");

    std::ofstream secondTemporaryFile(temporaryInputPath);
    secondTemporaryFile << "This is only a test file.\n";
    secondTemporaryFile.close();

    std::ostringstream capturedOutput;
    std::streambuf* originalOutput = std::cout.rdbuf(capturedOutput.rdbuf());

    bool directoryOutputResult = engine.trim(
        temporaryInputPath,
        "temporary-output-folder",
        1.0,
        2.0
    );

    std::cout.rdbuf(originalOutput);

    std::filesystem::remove(temporaryInputPath);
    std::filesystem::remove("temporary-output-folder");

    if (directoryOutputResult)
    {
        std::cout << "Test failed: trim should reject a folder as the output path.\n";
        return 1;
    }

    if (capturedOutput.str().find("output path must include a file name") == std::string::npos)
    {
        std::cout << "Test failed: trim should explain that output needs a file name.\n";
        return 1;
    }

    std::cout << "All TrimEngine tests passed.\n";
    return 0;
}
