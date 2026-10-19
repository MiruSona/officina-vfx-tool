using Newtonsoft.Json;

namespace Officina.Vfx
{
    // colorOverLifetime 모듈 칸.
    public class VfxColorOverLifetimeModule : VfxFields
    {
        [JsonProperty("color")] public VfxColor Color;
    }
}
