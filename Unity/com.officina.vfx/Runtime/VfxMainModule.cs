using Newtonsoft.Json;

namespace Officina.Vfx
{
    // main 모듈 칸 (설계 2-3). 값은 이미 Unity 단위다. startRotation 은 라디안.
    public class VfxMainModule : VfxFields
    {
        [JsonProperty("startDelay")] public VfxValue StartDelay;
        [JsonProperty("startLifetime")] public VfxValue StartLifetime;
        [JsonProperty("startSpeed")] public VfxValue StartSpeed;
        [JsonProperty("startSize")] public VfxValue StartSize;
        [JsonProperty("startColor")] public VfxColor StartColor;
        [JsonProperty("gravityModifier")] public VfxValue GravityModifier;
        [JsonProperty("maxParticles")] public int? MaxParticles;
        [JsonProperty("startRotation")] public VfxValue StartRotation;
    }
}
