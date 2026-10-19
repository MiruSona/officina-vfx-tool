using Newtonsoft.Json;

namespace Officina.Vfx.Editor
{
    // job.json frames 한 줄. 시각 t 는 Python 이 셈하고 C# 은 따른다 (설계 6-2).
    public class VfxJobFrame
    {
        [JsonProperty("i")] public int I;
        [JsonProperty("t")] public float T;
    }
}
