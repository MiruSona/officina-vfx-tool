using Newtonsoft.Json;

namespace Officina.Vfx
{
    // noise 모듈 칸. quality = Low · Medium · High.
    public class VfxNoiseModule : VfxFields
    {
        [JsonProperty("strength")] public VfxValue Strength;
        [JsonProperty("frequency")] public float? Frequency;
        [JsonProperty("scrollSpeed")] public VfxValue ScrollSpeed;
        [JsonProperty("octaves")] public int? Octaves;
        [JsonProperty("quality")] public string Quality;
    }
}
