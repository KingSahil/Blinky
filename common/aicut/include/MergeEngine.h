#ifndef MERGE_ENGINE_H
#define MERGE_ENGINE_H

#include <string>
#include <vector>

class MergeEngine
{
public:
    bool merge(
        const std::vector<std::string>& inputPaths,
        const std::string& outputPath
    );

    std::string buildCommand(
        const std::vector<std::string>& inputPaths,
        const std::string& outputPath
    ) const;

private:
    bool inputFilesExist(const std::vector<std::string>& inputPaths) const;

    bool outputPathLooksLikeFile(const std::string& outputPath) const;

    std::string quotePath(const std::string& path) const;
};

#endif
