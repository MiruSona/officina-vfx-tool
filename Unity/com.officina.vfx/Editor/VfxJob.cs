using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;

namespace Officina.Vfx.Editor
{
    // job.json 모델 (설계 5-4). mode = build · render · both.
    public class VfxJob
    {
        public const string ModeBuild = "build";
        public const string ModeRender = "render";
        public const string ModeBoth = "both";
        public const string DefaultSaveRoot = "Assets/Vfx/Generated";

        [JsonProperty("recipe")] public string Recipe;
        [JsonProperty("mode")] public string Mode = ModeBoth;
        [JsonProperty("saveRoot")] public string SaveRoot = DefaultSaveRoot;
        [JsonProperty("outDir")] public string OutDir;
        [JsonProperty("frames")] public List<VfxJobFrame> Frames = new List<VfxJobFrame>();
        [JsonProperty("backgrounds")] public List<string> Backgrounds = new List<string>();

        public bool WantsPrefab => Mode == ModeBuild || Mode == ModeBoth;
        public bool WantsRender => Mode == ModeRender || Mode == ModeBoth;

        public static VfxJob Load(string path)
        {
            // job 은 Python 이 만드는 계약 파일이라 모르는 칸은 오타로 보고 거절한다.
            var settings = new JsonSerializerSettings { MissingMemberHandling = MissingMemberHandling.Error };
            var job = JsonConvert.DeserializeObject<VfxJob>(File.ReadAllText(path), settings);
            if (job == null) { throw new JsonSerializationException($"job.json 이 비었다 : {path}"); }
            if (job.Frames == null) { job.Frames = new List<VfxJobFrame>(); }
            if (job.Backgrounds == null) { job.Backgrounds = new List<string>(); }
            if (job.Backgrounds.Count == 0) { job.Backgrounds.Add("transparent"); }
            return job;
        }
    }
}
