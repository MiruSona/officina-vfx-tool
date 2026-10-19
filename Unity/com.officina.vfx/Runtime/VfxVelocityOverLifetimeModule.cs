using Newtonsoft.Json;

namespace Officina.Vfx
{
    // velocityOverLifetime 모듈 칸. space = local · world.
    public class VfxVelocityOverLifetimeModule : VfxFields
    {
        [JsonProperty("x")] public VfxValue X;
        [JsonProperty("y")] public VfxValue Y;
        [JsonProperty("radial")] public VfxValue Radial;
        [JsonProperty("orbitalZ")] public VfxValue OrbitalZ;
        [JsonProperty("space")] public string Space;
    }
}
