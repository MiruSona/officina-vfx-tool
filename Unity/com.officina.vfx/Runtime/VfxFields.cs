using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Officina.Vfx
{
    // 모델 클래스의 바탕. 모르는 칸을 버리지 않고 Extra 에 모아 조립기가 build.unknown_field 로 알린다.
    public abstract class VfxFields
    {
        [JsonExtensionData]
        public IDictionary<string, JToken> Extra = new Dictionary<string, JToken>();
    }
}
