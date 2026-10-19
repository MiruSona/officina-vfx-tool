using Newtonsoft.Json;
using NUnit.Framework;
using UnityEngine;

namespace Officina.Vfx.Tests
{
    // 색 값 넷 → MinMaxGradient 모드 · 키가 1:1 로 가는지 본다. hex 만 받는다.
    public class VfxColorTests
    {
        private static ParticleSystem.MinMaxGradient Gradient(string json)
        {
            return JsonConvert.DeserializeObject<VfxColor>(json).ToMinMaxGradient();
        }

        [Test]
        public void HexIsColor()
        {
            var g = Gradient("\"#FF0000\"");
            Assert.AreEqual(ParticleSystemGradientMode.Color, g.mode);
            Assert.AreEqual(1f, g.color.r, 1e-3f);
            Assert.AreEqual(0f, g.color.g, 1e-3f);
            Assert.AreEqual(1f, g.color.a, 1e-3f);
        }

        [Test]
        public void HexWithAlpha()
        {
            Assert.AreEqual(128f / 255f, Gradient("\"#FFE08A80\"").color.a, 1e-3f);
        }

        [Test]
        public void RandomIsTwoColors()
        {
            var g = Gradient("{\"random\": [\"#000000\", \"#FFFFFF\"]}");
            Assert.AreEqual(ParticleSystemGradientMode.TwoColors, g.mode);
            Assert.AreEqual(0f, g.colorMin.r, 1e-3f);
            Assert.AreEqual(1f, g.colorMax.r, 1e-3f);
        }

        [Test]
        public void GradientDefaultsToFixed()
        {
            var g = Gradient("{\"gradient\": {\"color\": [[0, \"#FF0000\"], [0.5, \"#0000FF\"]], \"alpha\": [[0, 1], [0.8, 0]]}}");
            Assert.AreEqual(ParticleSystemGradientMode.Gradient, g.mode);
            Assert.AreEqual(GradientMode.Fixed, g.gradient.mode);
            Assert.AreEqual(2, g.gradient.colorKeys.Length);
            Assert.AreEqual(2, g.gradient.alphaKeys.Length);
            // fixed 키 [t, v] 는 「t 부터 다음 키까지 v」 — 빨강은 0.5 까지, 알파 1 은 0.8 까지 간다.
            Assert.AreEqual(1f, g.gradient.Evaluate(0.3f).r, 1e-3f);
            Assert.AreEqual(1f, g.gradient.Evaluate(0.6f).b, 1e-3f);
            Assert.AreEqual(1f, g.gradient.Evaluate(0.5f).a, 1e-3f);
            Assert.AreEqual(0f, g.gradient.Evaluate(0.9f).a, 1e-3f);
        }

        [Test]
        public void GradientBlendMode()
        {
            var g = Gradient("{\"gradient\": {\"color\": [[0, \"#FF0000\"]]}, \"mode\": \"blend\"}");
            Assert.AreEqual(GradientMode.Blend, g.gradient.mode);
            // 알파 키를 안 주면 불투명 하나를 넣는다. Unity 는 키 하나를 0·1 두 끝으로 늘려 돌려주므로 개수 대신 값으로 본다.
            Assert.AreEqual(1f, g.gradient.Evaluate(0.5f).a, 1e-3f);
        }

        [Test]
        public void RandomGradientTakesBothForms()
        {
            string json = "{\"random_gradient\": ["
                + "{\"gradient\": {\"color\": [[0, \"#FF0000\"]]}},"
                + "{\"color\": [[0, \"#00FF00\"]], \"alpha\": [[0, 0.5]]}]}";
            var g = Gradient(json);
            Assert.AreEqual(ParticleSystemGradientMode.TwoGradients, g.mode);
            Assert.AreEqual(1f, g.gradientMin.colorKeys[0].color.r, 1e-3f);
            Assert.AreEqual(1f, g.gradientMax.colorKeys[0].color.g, 1e-3f);
            Assert.AreEqual(0.5f, g.gradientMax.alphaKeys[0].alpha, 1e-3f);
        }

        [Test]
        public void NonHexThrows()
        {
            Assert.Throws<JsonSerializationException>(() => Gradient("\"red\""));
            Assert.Throws<JsonSerializationException>(() => Gradient("\"#FFF\""));
            Assert.Throws<JsonSerializationException>(() => Gradient("\"p3\""));
            Assert.Throws<JsonSerializationException>(() => Gradient("{\"gradient\": {}, \"mode\": \"smooth\"}"));
        }
    }
}
