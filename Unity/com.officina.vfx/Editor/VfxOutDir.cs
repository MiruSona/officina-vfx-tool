using System;
using System.IO;

namespace Officina.Vfx.Editor
{
    // render 프레임을 쓸 자리 판정. 순수 함수라 EditMode 시험으로 바로 본다.
    // 절대 경로만 받고, Unity 프로젝트 폴더 안(Assets · Library · Packages 모두)은 거절한다(설계 5-5).
    public static class VfxOutDir
    {
        // 맞으면 정규화한 절대 경로, 틀리면 VfxBuildException.
        public static string Resolve(string outDir, string projectRoot)
        {
            if (string.IsNullOrWhiteSpace(outDir)) { throw new VfxBuildException("job.outDir 이 비었다"); }
            if (!Path.IsPathRooted(outDir)) { throw new VfxBuildException($"job.outDir 은 절대 경로여야 한다 : {outDir}"); }
            string full = Trim(Path.GetFullPath(outDir));
            string project = Trim(Path.GetFullPath(projectRoot));
            // 「프로젝트 + 구분자」로 앞을 맞춰 본다. 그냥 앞 글자만 보면 옆 폴더(…/ProjectBackup)까지 걸린다.
            if (string.Equals(full, project, StringComparison.OrdinalIgnoreCase)
                || full.StartsWith(project + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            {
                throw new VfxBuildException($"outDir 이 Unity 프로젝트 안이다 : {full} (프로젝트 {project} 밖에 둔다)");
            }
            return full;
        }

        private static string Trim(string path)
        {
            string root = Path.GetPathRoot(path);
            path = path.Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar);
            return path.Length > root.Length ? path.TrimEnd(Path.DirectorySeparatorChar) : path;
        }
    }
}
