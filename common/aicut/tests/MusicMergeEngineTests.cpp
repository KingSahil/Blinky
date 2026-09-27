#include "MusicMergeEngine.h"

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
    MusicMergeEngine engine;

    bool missingVideoResult = engine.addBackgroundMusic(
        "this-video-should-not-exist.mp4",
        "song.mp3",
        "output.mp4",
        0.25
    );

    if (!expect(!missingVideoResult, "addBackgroundMusic should reject a missing video file")) return 1;

    const std::string temporaryVideoPath = "temporary-test-video.mp4";
    const std::string temporarySongPath = "temporary-test-song.mp3";

    std::ofstream temporaryVideoFile(temporaryVideoPath);
    temporaryVideoFile << "This is only a test video file.\n";
    temporaryVideoFile.close();

    bool missingSongResult = engine.addBackgroundMusic(
        temporaryVideoPath,
        "this-song-should-not-exist.mp3",
        "output.mp4",
        0.25
    );

    std::filesystem::remove(temporaryVideoPath);

    if (!expect(!missingSongResult, "addBackgroundMusic should reject a missing song file")) return 1;

    std::filesystem::create_directory("temporary-output-folder");

    std::ofstream secondTemporaryVideoFile(temporaryVideoPath);
    secondTemporaryVideoFile << "This is only a test video file.\n";
    secondTemporaryVideoFile.close();

    std::ofstream temporarySongFile(temporarySongPath);
    temporarySongFile << "This is only a test song file.\n";
    temporarySongFile.close();

    std::ostringstream capturedOutput;
    std::streambuf* originalOutput = std::cout.rdbuf(capturedOutput.rdbuf());

    bool directoryOutputResult = engine.addBackgroundMusic(
        temporaryVideoPath,
        temporarySongPath,
        "temporary-output-folder",
        0.25
    );

    std::cout.rdbuf(originalOutput);

    std::filesystem::remove(temporaryVideoPath);
    std::filesystem::remove(temporarySongPath);
    std::filesystem::remove("temporary-output-folder");

    if (!expect(!directoryOutputResult, "addBackgroundMusic should reject a folder as the output path")) return 1;
    if (!expect(capturedOutput.str().find("output path must include a file name") != std::string::npos, "folder output should be explained")) return 1;

    std::string command = engine.buildCommand(
        "input.mp4",
        "song.mp3",
        "final.mp4",
        0.25
    );

    if (!expect(command.find("-stream_loop -1") != std::string::npos, "command should loop short songs")) return 1;
    if (!expect(command.find("volume=0.25") != std::string::npos, "command should set music volume")) return 1;
    if (!expect(command.find("amix=inputs=2") != std::string::npos, "command should mix original audio and song")) return 1;
    if (!expect(command.find("-c:v copy") != std::string::npos, "command should copy video stream")) return 1;
    if (!expect(command.find("-c:a aac") != std::string::npos, "command should encode output audio as AAC")) return 1;
    if (!expect(command.find("-shortest") != std::string::npos, "command should stop at video duration")) return 1;

    std::cout << "All MusicMergeEngine tests passed.\n";
    return 0;
}
