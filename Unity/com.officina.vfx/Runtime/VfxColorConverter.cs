using System;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Officina.Vfx
{
    // 글자면 hex, 객체면 열쇠(random · gradient · random_gradient)로 꼴을 가른다. 팔레트 p<n> 풀이는 Python 몫이라 hex 만 받는다.
    public class VfxColorConverter : JsonConverter<VfxColor>
    {
        public override bool CanWrite => false;

        public override void WriteJson(JsonWriter writer, VfxColor value, JsonSerializer serializer)
        {
            throw new NotSupportedException("VfxColor 는 읽기만 한다.");
        }

        public override VfxColor ReadJson(JsonReader reader, Type objectType, VfxColor existingValue, bool hasExistingValue, JsonSerializer serializer)
        {
            return Parse(JToken.Load(reader));
        }

        public static VfxColor Parse(JToken token)
        {
            if (token.Type == JTokenType.Null) { return null; }
            if (token.Type == JTokenType.String)
            {
                return new VfxColor { Mode = VfxColorMode.Color, Color = ParseHex(token.Value<string>()) };
            }
            if (token.Type != JTokenType.Object)
            {
                throw new JsonSerializationException($"색 값은 hex 글자나 객체여야 한다 : {token}");
            }

            var obj = (JObject)token;
            string shape = VfxJsonKeys.OneShape(obj, "색 값", "random", "gradient", "random_gradient");
            if (shape == "random")
            {
                VfxJsonKeys.Only(obj, "색 값 random", "random");
                var pair = RequirePair(obj["random"], "random");
                return new VfxColor
                {
                    Mode = VfxColorMode.TwoColors,
                    Color = ParseHex(pair[0].Value<string>()),
                    ColorMax = ParseHex(pair[1].Value<string>()),
                };
            }
            if (shape == "gradient")
            {
                return new VfxColor { Mode = VfxColorMode.Gradient, Gradient = ParseGradientEntry(obj, ReadMode(obj)) };
            }
            VfxJsonKeys.Only(obj, "색 값 random_gradient", "random_gradient", "mode");
            var gradients = RequirePair(obj["random_gradient"], "random_gradient");
            string mode = ReadMode(obj);
            return new VfxColor
            {
                Mode = VfxColorMode.TwoGradients,
                Gradient = ParseGradientEntry(gradients[0], mode),
                GradientMax = ParseGradientEntry(gradients[1], mode),
            };
        }

        // "#RRGGBB" · "#RRGGBBAA" 만 받는다. ColorUtility 가 받는 색 이름 · #RGB 는 거절한다.
        public static Color ParseHex(string hex)
        {
            bool shapeOk = hex != null && hex.StartsWith("#") && (hex.Length == 7 || hex.Length == 9);
            if (!shapeOk || !ColorUtility.TryParseHtmlString(hex, out Color color))
            {
                throw new JsonSerializationException($"hex 색이 아니다 : {hex}");
            }
            return color;
        }

        private static string ReadMode(JObject obj)
        {
            if (obj.TryGetValue("mode", out JToken mode)) { return mode.Value<string>(); }
            return "fixed";
        }

        // random_gradient 의 한 쪽은 {gradient, mode} 꼴이어도 되고 {color, alpha} 꼴이어도 된다.
        private static VfxGradient ParseGradientEntry(JToken token, string mode)
        {
            if (token.Type != JTokenType.Object)
            {
                throw new JsonSerializationException($"그러데이션은 객체여야 한다 : {token}");
            }
            var obj = (JObject)token;
            if (obj.TryGetValue("gradient", out JToken inner))
            {
                VfxJsonKeys.Only(obj, "그러데이션", "gradient", "mode");
                return ParseGradient(inner, ReadModeOr(obj, mode));
            }
            return ParseGradient(obj, mode);
        }

        private static string ReadModeOr(JObject obj, string fallback)
        {
            if (obj.TryGetValue("mode", out JToken mode)) { return mode.Value<string>(); }
            return fallback;
        }

        private static VfxGradient ParseGradient(JToken token, string mode)
        {
            if (token.Type != JTokenType.Object)
            {
                throw new JsonSerializationException($"gradient 는 객체여야 한다 : {token}");
            }
            var gradient = new VfxGradient { Mode = ParseGradientMode(mode) };
            var obj = (JObject)token;
            VfxJsonKeys.Only(obj, "gradient", "color", "alpha");
            if (obj.TryGetValue("color", out JToken colors))
            {
                foreach (JToken key in colors)
                {
                    var pair = RequirePair(key, "색 키");
                    gradient.ColorKeys.Add(new GradientColorKey(ParseHex(pair[1].Value<string>()), pair[0].Value<float>()));
                }
            }
            if (obj.TryGetValue("alpha", out JToken alphas))
            {
                foreach (JToken key in alphas)
                {
                    var pair = RequirePair(key, "알파 키");
                    gradient.AlphaKeys.Add(new GradientAlphaKey(pair[1].Value<float>(), pair[0].Value<float>()));
                }
            }
            return gradient;
        }

        private static GradientMode ParseGradientMode(string mode)
        {
            if (mode == "fixed") { return GradientMode.Fixed; }
            if (mode == "blend") { return GradientMode.Blend; }
            throw new JsonSerializationException($"그러데이션 mode 는 fixed · blend 만 : {mode}");
        }

        private static JArray RequirePair(JToken token, string what)
        {
            if (token.Type != JTokenType.Array || ((JArray)token).Count != 2)
            {
                throw new JsonSerializationException($"{what} 는 두 칸 배열이어야 한다 : {token}");
            }
            return (JArray)token;
        }
    }
}
