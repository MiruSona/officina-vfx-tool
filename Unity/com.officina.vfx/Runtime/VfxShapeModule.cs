using Newtonsoft.Json;

namespace Officina.Vfx
{
    // shape 모듈 칸. type = Circle · Cone · Box · Edge · Sphere. 각도는 도, 벡터는 상수 [x, y(, z)].
    public class VfxShapeModule : VfxFields
    {
        [JsonProperty("type")] public string Type;
        [JsonProperty("radius")] public float? Radius;
        [JsonProperty("angle")] public float? Angle;
        [JsonProperty("arc")] public float? Arc;
        [JsonProperty("box")] public float[] Box;
        [JsonProperty("position")] public float[] Position;
        [JsonProperty("rotation")] public float[] Rotation;
        [JsonProperty("radiusThickness")] public float? RadiusThickness;
    }
}
