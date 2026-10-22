using System.IO;
using NUnit.Framework;
using Officina.Vfx.Editor;
using UnityEngine;

namespace Officina.Vfx.Tests
{
    // 묶어 굽기는 한 Unity 안에서 판을 이어 굽는다. 앞 판 상태가 다음 판으로 새지 않는지 본다 (묶어굽기설계 6-3 · R1).
    public class VfxRepeatRenderTests
    {
        private const string Recipe = @"{
  ""version"": 1, ""name"": ""repeat_fx"", ""seed"": 7, ""fixedTimeStep"": true, ""fixedDeltaTime"": 0.0125,
  ""duration"": 0.25, ""fps"": 12, ""ppu"": 32,
  ""layers"": [ { ""name"": ""dots"", ""blend"": ""additive"",
    ""main"": { ""startLifetime"": 0.2, ""startSpeed"": 2, ""startSize"": 0.0625, ""maxParticles"": 32 },
    ""emission"": { ""rateOverTime"": 0, ""bursts"": [[0, 12]] } } ] }";

        private string dir;
        private float savedStep;

        [SetUp]
        public void SetUp()
        {
            dir = Path.Combine(Path.GetTempPath(), "VfxRepeatRenderTests_" + Path.GetRandomFileName());
            savedStep = Time.fixedDeltaTime;
        }

        [TearDown]
        public void TearDown()
        {
            Time.fixedDeltaTime = savedStep;
            if (Directory.Exists(dir)) { Directory.Delete(dir, true); }
        }

        private VfxResult BuildAndRender(string outDir)
        {
            var result = new VfxResult();
            var job = new VfxJob { Mode = VfxJob.ModeRender, OutDir = outDir };
            job.Backgrounds.Add("transparent");
            VfxRecipe recipe = VfxRecipe.Parse(Recipe);
            GameObject root = null;
            try
            {
                root = VfxBuilder.Build(recipe, job, result);
                VfxRenderer.Render(root, recipe, job, result);
            }
            finally { VfxBuilder.Dispose(root); }
            return result;
        }

        [Test]
        public void SecondRunMatchesFirst()
        {
            string first = Path.Combine(dir, "a");
            string second = Path.Combine(dir, "b");
            VfxResult a = BuildAndRender(first);
            // Unity 가 fixedDeltaTime 을 넣을 때 끝자리를 깎아 넣어 정확히 같지는 않다(실측 1e-8 쯤).
            Assert.AreEqual(savedStep, Time.fixedDeltaTime, 1e-6f, "Render 가 fixedDeltaTime 을 되돌려야 한다");
            VfxResult b = BuildAndRender(second);

            Assert.Greater(a.Frames.Count, 0);
            Assert.AreEqual(a.Frames.Count, b.Frames.Count);
            Assert.AreEqual(0.0125f, a.FixedDeltaTime, 1e-6f);
            Assert.AreEqual(a.FixedDeltaTime, b.FixedDeltaTime);
            Assert.AreEqual(savedStep, Time.fixedDeltaTime, 1e-6f);
            for (int i = 0; i < a.Frames.Count; i++)
            {
                Assert.AreEqual(a.Frames[i].Particles, b.Frames[i].Particles, $"프레임 {i} 입자 수");
                byte[] pa = File.ReadAllBytes(Path.Combine(first, a.Frames[i].Png));
                byte[] pb = File.ReadAllBytes(Path.Combine(second, b.Frames[i].Png));
                CollectionAssert.AreEqual(pa, pb, $"프레임 {i} PNG 바이트");
            }
        }
    }
}
