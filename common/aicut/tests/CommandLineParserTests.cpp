#include "CommandLineParser.h"

#include <iostream>
#include <vector>

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
    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "trim",
            "--input",
            "input.mp4",
            "--output",
            "clip.mp4",
            "--start",
            "10",
            "--end",
            "25"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(command.isValid, "trim command should parse successfully")) return 1;
        if (!expect(command.type == CommandType::Trim, "trim command should have trim type")) return 1;
        if (!expect(command.inputPath == "input.mp4", "trim command should keep input path")) return 1;
        if (!expect(command.outputPath == "clip.mp4", "trim command should keep output path")) return 1;
        if (!expect(command.startSeconds == 10.0, "trim command should parse start seconds")) return 1;
        if (!expect(command.endSeconds == 25.0, "trim command should parse end seconds")) return 1;
    }

    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "add-song",
            "--video",
            "clip.mp4",
            "--song",
            "song.mp3",
            "--output",
            "final.mp4",
            "--music-volume",
            "0.35"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(command.isValid, "add-song command should parse successfully")) return 1;
        if (!expect(command.type == CommandType::AddSong, "add-song command should have add-song type")) return 1;
        if (!expect(command.videoPath == "clip.mp4", "add-song command should keep video path")) return 1;
        if (!expect(command.songPath == "song.mp3", "add-song command should keep song path")) return 1;
        if (!expect(command.outputPath == "final.mp4", "add-song command should keep output path")) return 1;
        if (!expect(command.musicVolume == 0.35, "add-song command should parse music volume")) return 1;
    }

    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "add-song",
            "--video",
            "clip.mp4",
            "--song",
            "song.mp3",
            "--output",
            "final.mp4"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(command.isValid, "add-song command should default music volume")) return 1;
        if (!expect(command.musicVolume == 0.25, "default music volume should be 0.25")) return 1;
    }

    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "trim",
            "--input",
            "input.mp4",
            "--output",
            "clip.mp4",
            "--start",
            "10"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(!command.isValid, "trim command should reject missing --end")) return 1;
        if (!expect(command.errorMessage.find("--end") != std::string::npos, "missing --end should be explained")) return 1;
    }

    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "resize",
            "--input",
            "input.mp4"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(!command.isValid, "unknown command should fail")) return 1;
        if (!expect(command.errorMessage.find("Unknown command") != std::string::npos, "unknown command should be explained")) return 1;
    }

    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "trim",
            "--input",
            "input.mp4",
            "--output",
            "clip.mp4",
            "--start",
            "10",
            "--end",
            "25",
            "--surprise",
            "value"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(!command.isValid, "unknown trim option should fail")) return 1;
        if (!expect(command.errorMessage.find("--surprise") != std::string::npos, "unknown option should be named")) return 1;
    }

    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "add-song",
            "--video",
            "clip.mp4",
            "--song",
            "song.mp3",
            "--output",
            "final.mp4",
            "--music-volume",
            "1.5"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(!command.isValid, "music volume above 1.0 should fail")) return 1;
        if (!expect(command.errorMessage.find("--music-volume") != std::string::npos, "invalid volume should be explained")) return 1;
    }

    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "--help"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(command.isValid, "--help should parse successfully")) return 1;
        if (!expect(command.type == CommandType::Help, "--help should have help type")) return 1;
    }

    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "merge",
            "--inputs",
            "clip1.mp4,clip2.mp4,clip3.mp4",
            "--output",
            "merged.mp4"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(command.isValid, "merge command with --inputs should parse successfully")) return 1;
        if (!expect(command.type == CommandType::Merge, "merge command should have merge type")) return 1;
        if (!expect(command.inputPaths.size() == 3, "merge command should parse 3 inputs")) return 1;
        if (!expect(command.inputPaths[0] == "clip1.mp4", "merge command first input")) return 1;
        if (!expect(command.outputPath == "merged.mp4", "merge command output path")) return 1;
    }

    {
        std::vector<std::string> arguments = {
            "AIVideoEditor",
            "merge",
            "--input1",
            "clip1.mp4",
            "--input2",
            "clip2.mp4",
            "--output",
            "merged.mp4"
        };

        ParsedCommand command = parseCommandLine(arguments);

        if (!expect(command.isValid, "merge command with --input1/2 should parse successfully")) return 1;
        if (!expect(command.type == CommandType::Merge, "merge command should have merge type")) return 1;
        if (!expect(command.inputPaths.size() == 2, "merge command should parse 2 inputs")) return 1;
    }

    std::cout << "All CommandLineParser tests passed.\n";
    return 0;
}
