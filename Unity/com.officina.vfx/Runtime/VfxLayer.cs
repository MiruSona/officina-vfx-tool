using Newtonsoft.Json;

namespace Officina.Vfx
{
    // resolved.json 의 층 하나 = 자식 ParticleSystem 하나. 템플릿은 Python 이 이미 펼쳤다.
    public class VfxLayer : VfxModuleSet
    {
        [JsonProperty("name")] public string Name;
        [JsonProperty("material")] public string Material = "unlit";
        [JsonProperty("blend")] public string Blend = "alpha";
        [JsonProperty("texture")] public string Texture = "px1";
        [JsonProperty("sortOrder")] public int SortOrder;
        [JsonProperty("space")] public string Space = "local";
        [JsonProperty("offset")] public float[] Offset;
    }
}
