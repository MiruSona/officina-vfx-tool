using Newtonsoft.Json;

namespace Officina.Vfx.Editor
{
    // result.json frames 한 줄. png 는 outDir 안의 파일 이름.
    public class VfxFrameResult
    {
        [JsonProperty("i")] public int I;
        [JsonProperty("t")] public float T;
        [JsonProperty("png")] public string Png;
        [JsonProperty("particles")] public int Particles;
    }
}
