#ifndef TRIM_ENGINE_H
#define TRIM_ENGINE_H

#include <string>

class TrimEngine
{
public:
    bool trim(
        const std::string& inputPath,
        const std::string& outputPath,
        double startSeconds,
        double endSeconds
    );

private:
    bool inputFileExists(const std::string& inputPath) const;

    bool outputPathLooksLikeFile(const std::string& outputPath) const;

    bool isTimeRangeValid(double startSeconds, double endSeconds) const;

    std::string buildCommand(
        const std::string& inputPath,
        const std::string& outputPath,
        double startSeconds,
        double durationSeconds
    ) const;

    std::string quotePath(const std::string& path) const;
};

#endif
