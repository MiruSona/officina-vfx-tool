using Newtonsoft.Json;
using NUnit.Framework;
using UnityEngine;

namespace Officina.Vfx.Tests
{
    // 다형 값 넷 → MinMaxCurve 모드 · 값이 1:1 로 가는지 본다.
    public class VfxValueTests
    {
        private static ParticleSystem.MinMaxCurve Curve(string json)
        {
            return JsonConvert.DeserializeObject<VfxValue>(json).ToMinMaxCurve();
        }

        [Test]
        public void NumberIsConstant()
        {
            var curve = Curve("0.3");
            Assert.AreEqual(ParticleSystemCurveMode.Constant, curve.mode);
            Assert.AreEqual(0.3f, curve.constant, 1e-6f);
        }

        [Test]
        public void IntegerIsConstant()
        {
            Assert.AreEqual(2f, Curve("2").constant, 1e-6f);
        }

        [Test]
        public void RandomIsTwoConstants()
        {
            var curve = Curve("{\"random\": [0.2, 0.5]}");
            Assert.AreEqual(ParticleSystemCurveMode.TwoConstants, curve.mode);
            Assert.AreEqual(0.2f, curve.constantMin, 1e-6f);
            Assert.AreEqual(0.5f, curve.constantMax, 1e-6f);
        }

        [Test]
        public void StepCurveHasInfiniteTangents()
        {
            var curve = Curve("{\"curve\": [[0, 2], [0.4, 1]], \"mult\": 3, \"step\": true}");
            Assert.AreEqual(ParticleSystemCurveMode.Curve, curve.mode);
            Assert.AreEqual(3f, curve.curveMultiplier, 1e-6f);
            Assert.AreEqual(2, curve.curve.length);
            Assert.IsTrue(float.IsInfinity(curve.curve.keys[0].outTangent));
            Assert.AreEqual(2f, curve.curve.Evaluate(0.3f), 1e-4f);
        }

        [Test]
        public void SmoothCurveHasFiniteTangents()
        {
            var curve = Curve("{\"curve\": [[0, 1], [0.5, 2], [1, 0]]}");
            Assert.AreEqual(1f, curve.curveMultiplier, 1e-6f);
            Assert.AreEqual(3, curve.curve.length);
            Assert.IsFalse(float.IsInfinity(curve.curve.keys[1].outTangent));
        }

        [Test]
        public void RandomCurveIsTwoCurves()
        {
            var curve = Curve("{\"random_curve\": [[[0, 1], [1, 0]], [[0, 2], [1, 0]]]}");
            Assert.AreEqual(ParticleSystemCurveMode.TwoCurves, curve.mode);
            Assert.AreEqual(1f, curve.curveMin.Evaluate(0f), 1e-4f);
            Assert.AreEqual(2f, curve.curveMax.Evaluate(0f), 1e-4f);
        }

        [Test]
        public void ZeroLikeKeepsMode()
        {
            var value = JsonConvert.DeserializeObject<VfxValue>("{\"curve\": [[0, 1], [1, 0]]}");
            var zero = value.ToZeroLike();
            Assert.AreEqual(ParticleSystemCurveMode.Curve, zero.mode);
            Assert.AreEqual(0f, zero.Evaluate(0.5f), 1e-6f);
        }

        [Test]
        public void UnknownShapeThrows()
        {
            Assert.Throws<JsonSerializationException>(() => Curve("{\"from\": 2, \"to\": 0}"));
            Assert.Throws<JsonSerializationException>(() => Curve("[1, 2]"));
            Assert.Throws<JsonSerializationException>(() => Curve("{\"random\": [1]}"));
        }
    }
}
