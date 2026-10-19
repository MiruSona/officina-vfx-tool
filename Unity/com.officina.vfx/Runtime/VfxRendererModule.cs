using Newtonsoft.Json;

namespace Officina.Vfx
{
    // renderer 모듈 칸. renderMode 는 Billboard 만. 머티리얼 · 정렬 · 정점 스트림은 층 칸과 코드가 정한다.
    public class VfxRendererModule : VfxFields
    {
        [JsonProperty("renderMode")] public string RenderMode;
    }
}
