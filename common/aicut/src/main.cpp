#include "CommandLineParser.h"
#include "MusicMergeEngine.h"
#include "TrimEngine.h"
#include "MergeEngine.h"

#include <iostream>
#include <string>
#include <vector>

std::vector<std::string> collectArguments(int argc, char* argv[])
{
    std::vector<std::string> arguments;

    for (int index = 0; index < argc; ++index)
    {
        arguments.push_back(argv[index]);
    }

    return arguments;
}

int main(int argc, char* argv[])
{
    ParsedCommand command = parseCommandLine(collectArguments(argc, argv));

    if (command.type == CommandType::Help)
    {
        std::cout << getUsageText();
        return 0;
    }

    if (!command.isValid)
    {
        std::cout << "Error: " << command.errorMessage << "\n\n";
        std::cout << getUsageText();
        return 1;
    }

    if (command.type == CommandType::Trim)
    {
        TrimEngine engine;

        bool success = engine.trim(
            command.inputPath,
            command.outputPath,
            command.startSeconds,
            command.endSeconds
        );

        return success ? 0 : 1;
    }

    if (command.type == CommandType::AddSong)
    {
        MusicMergeEngine engine;

        bool success = engine.addBackgroundMusic(
            command.videoPath,
            command.songPath,
            command.outputPath,
            command.musicVolume
        );

        return success ? 0 : 1;
    }

    if (command.type == CommandType::Merge)
    {
        MergeEngine engine;

        bool success = engine.merge(
            command.inputPaths,
            command.outputPath
        );

        return success ? 0 : 1;
    }

    std::cout << "Error: unsupported command.\n\n";
    std::cout << getUsageText();
    return 1;
}
