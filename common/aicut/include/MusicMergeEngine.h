#ifndef MUSIC_MERGE_ENGINE_H
#define MUSIC_MERGE_ENGINE_H

#include <string>

class MusicMergeEngine
{
public:
    bool addBackgroundMusic(
        const std::string& videoPath,
        const std::string& songPath,
        const std::string& outputPath,
        double musicVolume = 0.25
    );

    std::string buildCommand(
        const std::string& videoPath,
        const std::string& songPath,
        const std::string& outputPath,
        double musicVolume
    ) const;

private:
    bool inputFileExists(const std::string& inputPath) const;

    bool outputPathLooksLikeFile(const std::string& outputPath) const;

    bool isMusicVolumeValid(double musicVolume) const;

    std::string quotePath(const std::string& path) const;
};

#endif
