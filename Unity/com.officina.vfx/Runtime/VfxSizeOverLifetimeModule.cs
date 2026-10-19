using Newtonsoft.Json;

namespace Officina.Vfx
{
    // sizeOverLifetime 모듈 칸. 배수 곡선 하나(축 나누기 없음).
    public class VfxSizeOverLifetimeModule : VfxFields
    {
        [JsonProperty("size")] public VfxValue Size;
    }
}
