#include "TrimEngine.h"

#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <sstream>

bool TrimEngine::trim(
    const std::string& inputPath,
    const std::string& outputPath,
    double startSeconds,
    double endSeconds
)
{
    if (!isTimeRangeValid(startSeconds, endSeconds))
    {
        std::cout << "Failure: invalid time range (start=" << startSeconds << ", end=" << endSeconds << "). Times must be non-negative and end > start.\n";
        return false;
    }

    if (!inputFileExists(inputPath))
    {
        std::cout << "Failure: input file does not exist.\n";
        return false;
    }

    if (!outputPathLooksLikeFile(outputPath))
    {
        std::cout << "Failure: output path must include a file name, like output.mp4.\n";
        return false;
    }

    double durationSeconds = endSeconds - startSeconds;

    std::string command = buildCommand(
        inputPath,
        outputPath,
        startSeconds,
        durationSeconds
    );

    std::cout << "\nGenerated FFmpeg command:\n";
    std::cout << command << "\n\n";

    int exitCode = std::system(command.c_str());

    if (exitCode == 0)
    {
        std::cout << "Success: video was trimmed without re-encoding.\n";
        return true;
    }

    std::cout << "Failure: FFmpeg could not trim the video.\n";
    return false;
}

bool TrimEngine::inputFileExists(const std::string& inputPath) const
{
    return std::filesystem::exists(inputPath);
}

bool TrimEngine::outputPathLooksLikeFile(const std::string& outputPath) const
{
    std::filesystem::path path(outputPath);

    if (std::filesystem::is_directory(path))
    {
        return false;
    }

    return path.has_filename() && path.has_extension();
}

bool TrimEngine::isTimeRangeValid(double startSeconds, double endSeconds) const
{
    return startSeconds >= 0 && endSeconds > startSeconds;
}

std::string TrimEngine::buildCommand(
    const std::string& inputPath,
    const std::string& outputPath,
    double startSeconds,
    double durationSeconds
) const
{
    std::ostringstream command;

    command << "ffmpeg -y ";
    command << "-ss " << startSeconds << " ";
    command << "-i " << quotePath(inputPath) << " ";
    command << "-t " << durationSeconds << " ";
    command << "-c copy ";
    command << quotePath(outputPath);

    return command.str();
}

std::string TrimEngine::quotePath(const std::string& path) const
{
    return "\"" + path + "\"";
}
