using Newtonsoft.Json;

namespace Officina.Vfx
{
    // 층이 가진 모듈 열 개. null 인 모듈은 레시피에 안 적은 것이라 끈다.
    public abstract class VfxModuleSet : VfxFields
    {
        [JsonProperty("main")] public VfxMainModule Main;
        [JsonProperty("emission")] public VfxEmissionModule Emission;
        [JsonProperty("shape")] public VfxShapeModule Shape;
        [JsonProperty("velocityOverLifetime")] public VfxVelocityOverLifetimeModule VelocityOverLifetime;
        [JsonProperty("colorOverLifetime")] public VfxColorOverLifetimeModule ColorOverLifetime;
        [JsonProperty("sizeOverLifetime")] public VfxSizeOverLifetimeModule SizeOverLifetime;
        [JsonProperty("rotationOverLifetime")] public VfxRotationOverLifetimeModule RotationOverLifetime;
        [JsonProperty("noise")] public VfxNoiseModule Noise;
        [JsonProperty("textureSheet")] public VfxTextureSheetModule TextureSheet;
        [JsonProperty("renderer")] public VfxRendererModule Renderer;
    }
}
