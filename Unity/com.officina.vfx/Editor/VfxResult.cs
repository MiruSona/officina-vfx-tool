using System.Collections.Generic;
using System.IO;
using System.Text;
using Newtonsoft.Json;

namespace Officina.Vfx.Editor
{
    // result.json 모델 (설계 5-4). 종료 코드 : ok 0 · issues 1 · error 2.
    public class VfxResult
    {
        public const string StatusOk = "ok";
        public const string StatusIssues = "issues";
        public const string StatusError = "error";

        [JsonProperty("status")] public string Status = StatusOk;
        [JsonProperty("unity")] public string Unity;
        [JsonProperty("recipeSha256")] public string RecipeSha256;
        [JsonProperty("seed")] public int Seed;
        [JsonProperty("fixedTimeStep")] public bool FixedTimeStep;
        [JsonProperty("fixedDeltaTime")] public float FixedDeltaTime;
        [JsonProperty("renderApi")] public string RenderApi;
        [JsonProperty("graphicsDevice")] public string GraphicsDevice;
        [JsonProperty("prefab")] public string Prefab;
        [JsonProperty("t0_skipped")] public bool T0Skipped = true;
        [JsonProperty("frames")] public List<VfxFrameResult> Frames = new List<VfxFrameResult>();
        [JsonProperty("issues")] public List<VfxIssue> Issues = new List<VfxIssue>();
        [JsonProperty("seconds")] public Dictionary<string, double> Seconds = new Dictionary<string, double>();

        // 못 옮긴 칸 하나를 적는다. error 판은 error 로 남긴다.
        public void Issue(string rule, string layer, string detail)
        {
            Issues.Add(new VfxIssue { Rule = rule, Layer = layer, Detail = detail });
            if (Status != StatusError) { Status = StatusIssues; }
        }

        // 판 전체를 못 쓰게 된 일(예외 · job 못 읽음 · 렌더 실패).
        public void Fail(string rule, string detail)
        {
            Issues.Add(new VfxIssue { Rule = rule, Detail = detail });
            Status = StatusError;
        }

        public int ExitCode()
        {
            if (Status == StatusError) { return 2; }
            if (Status == StatusIssues) { return 1; }
            return 0;
        }

        // UTF-8(BOM 없음) · 줄 끝 LF · 빈 칸(null)은 뺀다.
        public void Save(string path)
        {
            var settings = new JsonSerializerSettings { NullValueHandling = NullValueHandling.Ignore };
            string json = JsonConvert.SerializeObject(this, Formatting.Indented, settings).Replace("\r\n", "\n");
            File.WriteAllText(path, json + "\n", new UTF8Encoding(false));
        }
    }
}
