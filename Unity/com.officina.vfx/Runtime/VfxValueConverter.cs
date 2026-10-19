using System;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Officina.Vfx
{
    // 숫자면 상수, 객체면 열쇠(random · curve · random_curve)로 꼴을 가른다. 쓰기는 안 한다.
    public class VfxValueConverter : JsonConverter<VfxValue>
    {
        public override bool CanWrite => false;

        public override void WriteJson(JsonWriter writer, VfxValue value, JsonSerializer serializer)
        {
            throw new NotSupportedException("VfxValue 는 읽기만 한다.");
        }

        public override VfxValue ReadJson(JsonReader reader, Type objectType, VfxValue existingValue, bool hasExistingValue, JsonSerializer serializer)
        {
            JToken token = JToken.Load(reader);
            return Parse(token);
        }

        public static VfxValue Parse(JToken token)
        {
            if (token.Type == JTokenType.Null) { return null; }
            if (token.Type == JTokenType.Integer || token.Type == JTokenType.Float)
            {
                return VfxValue.Of(token.Value<float>());
            }
            if (token.Type != JTokenType.Object)
            {
                throw new JsonSerializationException($"다형 값은 숫자나 객체여야 한다 : {token}");
            }

            var obj = (JObject)token;
            string shape = VfxJsonKeys.OneShape(obj, "다형 값", "random", "curve", "random_curve");
            if (shape == "random")
            {
                VfxJsonKeys.Only(obj, "다형 값 random", "random");
                return ParseRandom(obj["random"]);
            }
            VfxJsonKeys.Only(obj, "다형 값 " + shape, shape, "mult", "step");
            if (shape == "curve") { return ParseCurve(obj, obj["curve"]); }
            return ParseRandomCurve(obj, obj["random_curve"]);
        }

        private static VfxValue ParseRandom(JToken random)
        {
            var pair = RequireArray(random, 2, "random");
            return new VfxValue
            {
                Mode = VfxValueMode.TwoConstants,
                Min = pair[0].Value<float>(),
                Max = pair[1].Value<float>(),
            };
        }

        private static VfxValue ParseCurve(JObject obj, JToken curve)
        {
            var value = new VfxValue { Mode = VfxValueMode.Curve, Keys = ParseKeys(curve) };
            ReadMultAndStep(obj, value);
            return value;
        }

        private static VfxValue ParseRandomCurve(JObject obj, JToken randomCurve)
        {
            var pair = RequireArray(randomCurve, 2, "random_curve");
            var value = new VfxValue
            {
                Mode = VfxValueMode.TwoCurves,
                Keys = ParseKeys(pair[0]),
                MaxKeys = ParseKeys(pair[1]),
            };
            ReadMultAndStep(obj, value);
            return value;
        }

        private static void ReadMultAndStep(JObject obj, VfxValue value)
        {
            if (obj.TryGetValue("mult", out JToken mult)) { value.Mult = mult.Value<float>(); }
            if (obj.TryGetValue("step", out JToken step)) { value.Step = step.Value<bool>(); }
        }

        // [[t, v], ...] 를 읽는다. 키 수 · 오름차순 검사는 Python check 몫이다.
        private static List<Vector2> ParseKeys(JToken token)
        {
            var keys = new List<Vector2>();
            foreach (JToken key in RequireArray(token, -1, "curve"))
            {
                var pair = RequireArray(key, 2, "curve 키");
                keys.Add(new Vector2(pair[0].Value<float>(), pair[1].Value<float>()));
            }
            return keys;
        }

        private static JArray RequireArray(JToken token, int count, string what)
        {
            if (token.Type != JTokenType.Array)
            {
                throw new JsonSerializationException($"{what} 는 배열이어야 한다 : {token}");
            }
            var array = (JArray)token;
            if (count >= 0 && array.Count != count)
            {
                throw new JsonSerializationException($"{what} 는 {count}개여야 한다 : {token}");
            }
            return array;
        }
    }
}
