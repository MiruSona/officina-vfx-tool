using System.Collections.Generic;
using Newtonsoft.Json;

namespace Officina.Vfx
{
    // emission 모듈 칸. rateOverTime 을 안 적으면 0 으로 넣는다(Unity 기본 10 이 몰래 새지 않게).
    public class VfxEmissionModule : VfxFields
    {
        [JsonProperty("rateOverTime")] public VfxValue RateOverTime;
        [JsonProperty("bursts")] public List<VfxBurst> Bursts;
    }
}
