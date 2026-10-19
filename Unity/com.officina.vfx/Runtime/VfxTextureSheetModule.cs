using Newtonsoft.Json;

namespace Officina.Vfx
{
    // textureSheet 모듈 칸. Time Mode = FPS 고정, Frame Blending 은 정점 스트림을 안 넣어 꺼 둔다.
    // row 를 안 적으면 시트 전체(Whole Sheet), 적으면 한 줄만(Single Row) 돈다.
    public class VfxTextureSheetModule : VfxFields
    {
        [JsonProperty("tiles")] public int[] Tiles;
        [JsonProperty("fps")] public float? Fps;
        [JsonProperty("startFrame")] public VfxValue StartFrame;
        [JsonProperty("cycles")] public int? Cycles;
        [JsonProperty("row")] public VfxRow Row;
    }
}
