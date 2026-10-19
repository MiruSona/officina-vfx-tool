using System;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Officina.Vfx
{
    // 정수(≥ 0)면 줄 번호, 글자 "random" 이면 아무 줄. 그 밖은 Bad 에 원문을 담는다. 쓰기는 안 한다.
    public class VfxRowConverter : JsonConverter<VfxRow>
    {
        public override bool CanWrite => false;

        public override void WriteJson(JsonWriter writer, VfxRow value, JsonSerializer serializer)
        {
            throw new NotSupportedException("VfxRow 는 읽기만 한다.");
        }

        public override VfxRow ReadJson(JsonReader reader, Type objectType, VfxRow existingValue, bool hasExistingValue, JsonSerializer serializer)
        {
            return Parse(JToken.Load(reader));
        }

        public static VfxRow Parse(JToken token)
        {
            if (token.Type == JTokenType.Null) { return null; }
            // 정수 JValue 의 속값은 long 이거나(long 밖이면) BigInteger 다. 꺼내 보지 않고 꼴로 갈라야
            // int · long 을 넘는 큰 수가 OverflowException · InvalidCastException 으로 터지지 않고 Bad 로 간다.
            if (token is JValue value && value.Value is long index && index >= 0 && index <= int.MaxValue)
            {
                return new VfxRow { Index = (int)index };
            }
            if (token.Type == JTokenType.String && token.Value<string>() == VfxRow.RandomWord)
            {
                return new VfxRow { IsRandom = true };
            }
            return new VfxRow { Bad = token.ToString(Formatting.None) };
        }
    }
}
