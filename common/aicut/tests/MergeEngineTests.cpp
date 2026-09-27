#include "MergeEngine.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>

bool expect(bool condition, const std::string& message)
{
    if (!condition)
    {
        std::cout << "Test failed: " << message << "\n";
        return false;
    }

    return true;
}

int main()
{
    MergeEngine engine;

    // Test missing input files
    bool missingFilesResult = engine.merge(
        {"non-existent-1.mp4", "non-existent-2.mp4"},
        "output.mp4"
    );

    if (!expect(!missingFilesResult, "merge should reject missing input files")) return 1;

    // Test less than 2 inputs
    bool singleInputResult = engine.merge(
        {"input1.mp4"},
        "output.mp4"
    );

    if (!expect(!singleInputResult, "merge should reject less than 2 input files")) return 1;

    // Create temporary dummy files
    const std::string temp1 = "temp-video-1.mp4";
    const std::string temp2 = "temp-video-2.mp4";

    std::ofstream f1(temp1); f1 << "video data 1\n"; f1.close();
    std::ofstream f2(temp2); f2 << "video data 2\n"; f2.close();

    // Test folder as output
    std::filesystem::create_directory("temporary-output-folder");

    std::ostringstream capturedOutput;
    std::streambuf* originalOutput = std::cout.rdbuf(capturedOutput.rdbuf());

    bool dirOutputResult = engine.merge(
        {temp1, temp2},
        "temporary-output-folder"
    );

    std::cout.rdbuf(originalOutput);

    std::filesystem::remove(temp1);
    std::filesystem::remove(temp2);
    std::filesystem::remove("temporary-output-folder");

    if (!expect(!dirOutputResult, "merge should reject folder output")) return 1;
    if (!expect(capturedOutput.str().find("output path must include a file name") != std::string::npos, "folder output should be explained")) return 1;

    // Test command building
    std::string command = engine.buildCommand(
        {"clip1.mp4", "clip2.mp4"},
        "final.mp4"
    );

    if (!expect(command.find("concat=n=2:v=1:a=1") != std::string::npos, "command should use concat filter with 2 inputs")) return 1;
    if (!expect(command.find("scale=1280:720") != std::string::npos, "command should scale and letterbox/pillarbox inputs")) return 1;
    if (!expect(command.find("aformat=sample_rates=44100") != std::string::npos, "command should normalize audio format and channels")) return 1;
    if (!expect(command.find("-c:v libx264") != std::string::npos, "command should specify video codec")) return 1;
    if (!expect(command.find("-c:a aac") != std::string::npos, "command should specify audio codec")) return 1;

    std::cout << "All MergeEngine tests passed.\n";
    return 0;
}
