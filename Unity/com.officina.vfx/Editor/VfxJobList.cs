using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;

namespace Officina.Vfx.Editor
{
    // 묶어 굽기 목록 jobs.json = {"jobs":[job.json 절대 경로…]} (묶어굽기설계 2-2).
    // 틀리면 VfxBuildException · 모르는 칸은 JsonSerializationException. 어느 쪽이든 어느 판도 안 굽는다.
    public class VfxJobList
    {
        public const int MaxJobs = 48;

        [JsonProperty("jobs")] public List<string> Jobs;

        public static VfxJobList Load(string path)
        {
            // job.json 과 같은 엄격함 — Python 이 만드는 계약 파일이라 모르는 칸은 오타다.
            var settings = new JsonSerializerSettings { MissingMemberHandling = MissingMemberHandling.Error };
            var list = JsonConvert.DeserializeObject<VfxJobList>(File.ReadAllText(path), settings);
            if (list == null || list.Jobs == null) { throw new VfxBuildException($"jobs.json 에 jobs 칸이 없다 : {path}"); }
            if (list.Jobs.Count < 1 || list.Jobs.Count > MaxJobs)
            {
                throw new VfxBuildException($"jobs 는 1~{MaxJobs} 개여야 한다 : {list.Jobs.Count}");
            }

            // 판 결과는 job.json 옆 result.json 이라, 같은 폴더가 두 번 나오면 결과를 서로 덮는다.
            var folders = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (string job in list.Jobs)
            {
                if (string.IsNullOrWhiteSpace(job)) { throw new VfxBuildException("jobs 에 빈 경로가 있다"); }
                if (!Path.IsPathFullyQualified(job)) { throw new VfxBuildException($"jobs 원소는 절대 경로여야 한다 : {job}"); }
                string folder = Path.GetDirectoryName(Path.GetFullPath(job));
                if (!folders.Add(folder)) { throw new VfxBuildException($"jobs 에 같은 판 폴더가 두 번 있다 : {job}"); }
            }
            return list;
        }
    }
}
