using Newtonsoft.Json;

namespace Officina.Vfx
{
    // rotationOverLifetime 모듈 칸. z 는 라디안/초 (Unity API 단위).
    public class VfxRotationOverLifetimeModule : VfxFields
    {
        [JsonProperty("z")] public VfxValue Z;
    }
}
