using System.Collections.Generic;
using Newtonsoft.Json;

namespace Officina.Vfx
{
    // resolved.json 최상위 (설계 2-1). ppu · sortingLayer · snap 은 Python 이 프로필에서 옮겨 적는다.
    public class VfxRecipe : VfxFields
    {
        [JsonProperty("version")] public int Version;
        [JsonProperty("name")] public string Name;
        [JsonProperty("profile")] public string Profile;
        [JsonProperty("seed")] public int Seed;
        [JsonProperty("fixedTimeStep")] public bool FixedTimeStep = true;
        // fixedTimeStep 이 true 면 Simulate 가 Time.fixedDeltaTime 걸음으로 돈다. 프로젝트 설정이 달라도 같은 그림이 나오게 레시피 값으로 고정한다.
        [JsonProperty("fixedDeltaTime")] public float FixedDeltaTime = 0.02f;
        [JsonProperty("duration")] public float Duration = 1f;
        [JsonProperty("fps")] public int Fps = 12;
        [JsonProperty("loop")] public bool Loop;
        [JsonProperty("canvas")] public VfxCanvas Canvas = new VfxCanvas();
        [JsonProperty("bloom")] public bool Bloom;
        [JsonProperty("light")] public string Light = "none";
        [JsonProperty("ppu")] public int Ppu = 32;
        [JsonProperty("sortingLayer")] public string SortingLayer = "Default";
        [JsonProperty("snap")] public bool Snap = true;
        [JsonProperty("layers")] public List<VfxLayer> Layers = new List<VfxLayer>();

        public static VfxRecipe Parse(string json)
        {
            return JsonConvert.DeserializeObject<VfxRecipe>(json);
        }
    }
}
