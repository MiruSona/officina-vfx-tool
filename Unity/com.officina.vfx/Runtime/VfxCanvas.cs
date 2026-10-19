using Newtonsoft.Json;

namespace Officina.Vfx
{
    // 판정 화면 크기. texels = [w, h], scale = 텍셀당 픽셀.
    public class VfxCanvas : VfxFields
    {
        [JsonProperty("texels")] public int[] Texels = { 64, 64 };
        [JsonProperty("scale")] public int Scale = 4;
    }
}
