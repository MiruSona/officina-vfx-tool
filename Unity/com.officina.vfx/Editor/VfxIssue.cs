using Newtonsoft.Json;

namespace Officina.Vfx.Editor
{
    // result.json issues 한 줄. 조립은 됐지만 못 옮긴 칸 같은 것.
    public class VfxIssue
    {
        [JsonProperty("rule")] public string Rule;
        [JsonProperty("layer")] public string Layer;
        [JsonProperty("detail")] public string Detail;
    }
}
