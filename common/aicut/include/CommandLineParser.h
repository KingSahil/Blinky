#ifndef COMMAND_LINE_PARSER_H
#define COMMAND_LINE_PARSER_H

#include <string>
#include <vector>

enum class CommandType
{
    Invalid,
    Help,
    Trim,
    AddSong,
    Merge
};

struct ParsedCommand
{
    CommandType type = CommandType::Invalid;
    bool isValid = false;
    std::string errorMessage;

    std::string inputPath;
    std::vector<std::string> inputPaths;
    std::string videoPath;
    std::string songPath;
    std::string outputPath;
    double startSeconds = 0.0;
    double endSeconds = 0.0;
    double musicVolume = 0.25;
};

ParsedCommand parseCommandLine(const std::vector<std::string>& arguments);

std::string getUsageText();

#endif
