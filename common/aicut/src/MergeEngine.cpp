#include "MergeEngine.h"

#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <sstream>

bool MergeEngine::merge(
    const std::vector<std::string>& inputPaths,
    const std::string& outputPath
)
{
    if (inputPaths.size() < 2)
    {
        std::cout << "Failure: at least 2 input video files are required to merge.\n";
        return false;
    }

    if (!inputFilesExist(inputPaths))
    {
        std::cout << "Failure: one or more input files do not exist.\n";
        return false;
    }

    if (!outputPathLooksLikeFile(outputPath))
    {
        std::cout << "Failure: output path must include a file name, like output.mp4.\n";
        return false;
    }

    std::string command = buildCommand(inputPaths, outputPath);

    std::cout << "\nGenerated FFmpeg command:\n";
    std::cout << command << "\n\n";

    int exitCode = std::system(command.c_str());

    if (exitCode == 0)
    {
        std::cout << "Success: videos were merged successfully.\n";
        return true;
    }

    std::cout << "Failure: FFmpeg could not merge the videos.\n";
    return false;
}

std::string MergeEngine::buildCommand(
    const std::vector<std::string>& inputPaths,
    const std::string& outputPath
) const
{
    std::ostringstream command;

    command << "ffmpeg -y ";

    for (const auto& path : inputPaths)
    {
        command << "-i " << quotePath(path) << " ";
    }

    command << "-filter_complex \"";
    for (std::size_t i = 0; i < inputPaths.size(); ++i)
    {
        command << "[" << i << ":v:0]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v" << i << "];";
        command << "[" << i << ":a:0]aformat=sample_rates=44100:channel_layouts=stereo[a" << i << "];";
    }
    for (std::size_t i = 0; i < inputPaths.size(); ++i)
    {
        command << "[v" << i << "][a" << i << "]";
    }
    command << "concat=n=" << inputPaths.size() << ":v=1:a=1[v][a]\" ";
    command << "-map \"[v]\" -map \"[a]\" ";
    command << "-c:v libx264 -c:a aac ";
    command << quotePath(outputPath);

    return command.str();
}

bool MergeEngine::inputFilesExist(const std::vector<std::string>& inputPaths) const
{
    for (const auto& path : inputPaths)
    {
        if (!std::filesystem::exists(path))
        {
            return false;
        }
    }
    return true;
}

bool MergeEngine::outputPathLooksLikeFile(const std::string& outputPath) const
{
    std::filesystem::path path(outputPath);

    if (std::filesystem::is_directory(path))
    {
        return false;
    }

    return path.has_filename() && path.has_extension();
}

std::string MergeEngine::quotePath(const std::string& path) const
{
    return "\"" + path + "\"";
}
