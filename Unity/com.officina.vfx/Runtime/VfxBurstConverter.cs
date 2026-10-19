using System;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Officina.Vfx
{
    // 배열이면 [t, n], 객체면 {t, n, cycles, interval}. 쓰기는 안 한다.
    public class VfxBurstConverter : JsonConverter<VfxBurst>
    {
        public override bool CanWrite => false;

        public override void WriteJson(JsonWriter writer, VfxBurst value, JsonSerializer serializer)
        {
            throw new NotSupportedException("VfxBurst 는 읽기만 한다.");
        }

        public override VfxBurst ReadJson(JsonReader reader, Type objectType, VfxBurst existingValue, bool hasExistingValue, JsonSerializer serializer)
        {
            JToken token = JToken.Load(reader);
            if (token.Type == JTokenType.Array && ((JArray)token).Count == 2)
            {
                return new VfxBurst { Time = token[0].Value<float>(), Count = token[1].Value<float>() };
            }
            if (token.Type != JTokenType.Object)
            {
                throw new JsonSerializationException($"burst 는 [t, n] 이나 객체여야 한다 : {token}");
            }

            var obj = (JObject)token;
            VfxJsonKeys.Only(obj, "burst", "t", "n", "cycles", "interval");
            var burst = new VfxBurst
            {
                Time = RequireFloat(obj, "t"),
                Count = RequireFloat(obj, "n"),
            };
            if (obj.TryGetValue("cycles", out JToken cycles)) { burst.Cycles = cycles.Value<int>(); }
            if (obj.TryGetValue("interval", out JToken interval)) { burst.Interval = interval.Value<float>(); }
            return burst;
        }

        private static float RequireFloat(JObject obj, string key)
        {
            if (!obj.TryGetValue(key, out JToken value))
            {
                throw new JsonSerializationException($"burst 에 {key} 칸이 없다 : {obj}");
            }
            return value.Value<float>();
        }
    }
}
