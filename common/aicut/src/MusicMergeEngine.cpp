#include "MusicMergeEngine.h"

#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <sstream>

bool MusicMergeEngine::addBackgroundMusic(
    const std::string& videoPath,
    const std::string& songPath,
    const std::string& outputPath,
    double musicVolume
)
{
    if (!inputFileExists(videoPath))
    {
        std::cout << "Failure: video file does not exist.\n";
        return false;
    }

    if (!inputFileExists(songPath))
    {
        std::cout << "Failure: song file does not exist.\n";
        return false;
    }

    if (!outputPathLooksLikeFile(outputPath))
    {
        std::cout << "Failure: output path must include a file name, like output.mp4.\n";
        return false;
    }

    if (!isMusicVolumeValid(musicVolume))
    {
        std::cout << "Failure: music volume must be from 0.0 to 1.0.\n";
        return false;
    }

    std::string command = buildCommand(
        videoPath,
        songPath,
        outputPath,
        musicVolume
    );

    std::cout << "\nGenerated FFmpeg command:\n";
    std::cout << command << "\n\n";

    int exitCode = std::system(command.c_str());

    if (exitCode == 0)
    {
        std::cout << "Success: background music was added to the video.\n";
        return true;
    }

    std::cout << "Failure: FFmpeg could not add background music.\n";
    return false;
}

std::string MusicMergeEngine::buildCommand(
    const std::string& videoPath,
    const std::string& songPath,
    const std::string& outputPath,
    double musicVolume
) const
{
    std::ostringstream command;

    command << "ffmpeg -y ";
    command << "-i " << quotePath(videoPath) << " ";
    command << "-stream_loop -1 ";
    command << "-i " << quotePath(songPath) << " ";
    command << "-filter_complex ";
    command << quotePath(
        "[1:a]volume=" + std::to_string(musicVolume) +
        "[music];[0:a][music]amix=inputs=2:duration=longest:dropout_transition=2[a]"
    ) << " ";
    command << "-map 0:v:0 ";
    command << "-map " << quotePath("[a]") << " ";
    command << "-c:v copy ";
    command << "-c:a aac ";
    command << "-shortest ";
    command << quotePath(outputPath);

    return command.str();
}

bool MusicMergeEngine::inputFileExists(const std::string& inputPath) const
{
    return std::filesystem::exists(inputPath);
}

bool MusicMergeEngine::outputPathLooksLikeFile(const std::string& outputPath) const
{
    std::filesystem::path path(outputPath);

    if (std::filesystem::is_directory(path))
    {
        return false;
    }

    return path.has_filename() && path.has_extension();
}

bool MusicMergeEngine::isMusicVolumeValid(double musicVolume) const
{
    return musicVolume >= 0.0 && musicVolume <= 1.0;
}

std::string MusicMergeEngine::quotePath(const std::string& path) const
{
    return "\"" + path + "\"";
}
