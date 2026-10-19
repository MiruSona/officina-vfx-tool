using System.Collections.Generic;
using NUnit.Framework;
using Officina.Vfx.Editor;
using UnityEngine;

namespace Officina.Vfx.Tests
{
    // 임시 GameObject 에 조립해 모듈 값이 레시피대로 들어갔는지 본다. 에셋 저장은 안 한다.
    public class VfxBuilderTests
    {
        private const string Recipe = @"{
  ""version"": 1, ""name"": ""hit_sparks_a"", ""seed"": 1234, ""fixedTimeStep"": true, ""duration"": 0.5,
  ""ppu"": 32, ""sortingLayer"": ""Default"", ""bogusTop"": 1,
  ""layers"": [
    { ""name"": ""sparks"", ""material"": ""unlit"", ""blend"": ""alpha"", ""sortOrder"": 10, ""offset"": [0.5, 0.25],
      ""main"": { ""startLifetime"": { ""random"": [0.25, 0.45] }, ""startSize"": 0.03125,
                  ""startColor"": ""#FFE08A"", ""maxParticles"": 64, ""foo"": 3 },
      ""emission"": { ""rateOverTime"": 0, ""bursts"": [[0, 18], { ""t"": 0.1, ""n"": 4, ""cycles"": 2, ""interval"": 0.05 }] },
      ""shape"": { ""type"": ""Cone"", ""angle"": 35, ""radius"": 0.03125, ""rotation"": [-90, 0, 0] },
      ""colorOverLifetime"": { ""color"": { ""gradient"": { ""color"": [[0, ""#FFE08A""], [0.5, ""#F0A040""]], ""alpha"": [[0, 1], [0.8, 0]] } } },
      ""sizeOverLifetime"": { ""size"": { ""curve"": [[0, 2], [0.4, 1]], ""step"": true } },
      ""trails"": { ""enabled"": true } },
    { ""name"": ""drift"", ""blend"": ""additive"",
      ""velocityOverLifetime"": { ""x"": { ""curve"": [[0, 1], [1, 0]] }, ""space"": ""world"" },
      ""noise"": { ""strength"": 0.5, ""frequency"": 2, ""quality"": ""Ultra"" },
      ""textureSheet"": { ""tiles"": [4, 2], ""fps"": 12, ""startFrame"": { ""random"": [0, 4] }, ""cycles"": 1 } }
  ] }";

        private GameObject root;
        private VfxResult result;

        [SetUp]
        public void SetUp()
        {
            result = new VfxResult();
            var job = new VfxJob { Mode = VfxJob.ModeRender };
            root = VfxBuilder.Build(VfxRecipe.Parse(Recipe), job, result);
        }

        [TearDown]
        public void TearDown()
        {
            VfxBuilder.Dispose(root);
        }

        private ParticleSystem Layer(int index)
        {
            return root.transform.GetChild(index).GetComponent<ParticleSystem>();
        }

        private bool HasIssue(string rule, string layer, string detail)
        {
            return result.Issues.Exists(x => x.Rule == rule && x.Layer == layer && x.Detail.StartsWith(detail));
        }

        [Test]
        public void LayersBecomeChildrenWithSeed()
        {
            Assert.AreEqual("hit_sparks_a", root.name);
            Assert.AreEqual(2, root.transform.childCount);
            Assert.AreEqual("sparks", root.transform.GetChild(0).name);
            Assert.AreEqual(new Vector3(0.5f, 0.25f, 0f), root.transform.GetChild(0).localPosition);
            Assert.IsFalse(Layer(0).useAutoRandomSeed);
            Assert.AreEqual(1234u, Layer(0).randomSeed);
            Assert.AreEqual(1235u, Layer(1).randomSeed);
        }

        [Test]
        public void MainModule()
        {
            var main = Layer(0).main;
            Assert.AreEqual(0.5f, main.duration, 1e-4f);
            Assert.IsFalse(main.loop);
            Assert.AreEqual(ParticleSystemCurveMode.TwoConstants, main.startLifetime.mode);
            Assert.AreEqual(0.25f, main.startLifetime.constantMin, 1e-4f);
            Assert.AreEqual(0.03125f, main.startSize.constant, 1e-6f);
            Assert.AreEqual(64, main.maxParticles);
        }

        [Test]
        public void EmissionAndShape()
        {
            var ps = Layer(0);
            Assert.IsTrue(ps.emission.enabled);
            Assert.AreEqual(0f, ps.emission.rateOverTime.constant, 1e-6f);
            Assert.AreEqual(2, ps.emission.burstCount);
            Assert.AreEqual(18f, ps.emission.GetBurst(0).count.constant, 1e-6f);
            Assert.AreEqual(2, ps.emission.GetBurst(1).cycleCount);
            Assert.AreEqual(ParticleSystemShapeType.Cone, ps.shape.shapeType);
            Assert.AreEqual(35f, ps.shape.angle, 1e-4f);
            Assert.AreEqual(-90f, ps.shape.rotation.x, 1e-4f);
        }

        [Test]
        public void LifetimeModulesOnlyWhenWritten()
        {
            var sparks = Layer(0);
            Assert.IsTrue(sparks.colorOverLifetime.enabled);
            Assert.AreEqual(ParticleSystemGradientMode.Gradient, sparks.colorOverLifetime.color.mode);
            Assert.IsTrue(sparks.sizeOverLifetime.enabled);
            Assert.AreEqual(ParticleSystemCurveMode.Curve, sparks.sizeOverLifetime.size.mode);
            Assert.IsFalse(sparks.velocityOverLifetime.enabled);
            Assert.IsFalse(sparks.noise.enabled);
            Assert.IsFalse(sparks.textureSheetAnimation.enabled);
            Assert.IsFalse(Layer(1).emission.enabled);
            Assert.IsFalse(Layer(1).shape.enabled);
        }

        [Test]
        public void VelocityAxesShareMode()
        {
            var velocity = Layer(1).velocityOverLifetime;
            Assert.IsTrue(velocity.enabled);
            Assert.AreEqual(ParticleSystemCurveMode.Curve, velocity.x.mode);
            Assert.AreEqual(ParticleSystemCurveMode.Curve, velocity.y.mode);
            Assert.AreEqual(ParticleSystemCurveMode.Curve, velocity.z.mode);
            Assert.AreEqual(ParticleSystemSimulationSpace.World, velocity.space);
        }

        [Test]
        public void TextureSheetIsFpsGrid()
        {
            var sheet = Layer(1).textureSheetAnimation;
            Assert.IsTrue(sheet.enabled);
            Assert.AreEqual(4, sheet.numTilesX);
            Assert.AreEqual(2, sheet.numTilesY);
            Assert.AreEqual(ParticleSystemAnimationTimeMode.FPS, sheet.timeMode);
            Assert.AreEqual(12f, sheet.fps, 1e-4f);
            // 프레임 번호 [0, 4] 를 칸 8개 비율 [0, 0.5] 로 옮긴다.
            Assert.AreEqual(0.5f, sheet.startFrame.constantMax, 1e-4f);
        }

        [Test]
        public void RendererHasSnapStreams()
        {
            var renderer = Layer(0).GetComponent<ParticleSystemRenderer>();
            var streams = new List<ParticleSystemVertexStream>();
            renderer.GetActiveVertexStreams(streams);
            CollectionAssert.AreEqual(new[]
            {
                ParticleSystemVertexStream.Position,
                ParticleSystemVertexStream.Color,
                ParticleSystemVertexStream.UV,
                ParticleSystemVertexStream.Center,
            }, streams);
            Assert.AreEqual(ParticleSystemRenderMode.Billboard, renderer.renderMode);
            Assert.AreEqual(10, renderer.sortingOrder);
        }

        [Test]
        public void UnknownFieldsBecomeIssues()
        {
            Assert.IsTrue(HasIssue("build.unknown_field", "sparks", "main.foo"));
            Assert.IsTrue(HasIssue("build.unknown_field", "sparks", "trails"));
            Assert.IsTrue(HasIssue("build.unknown_field", null, "bogusTop"));
            Assert.IsTrue(HasIssue("build.bad_value", "drift", "noise.quality=Ultra"));
            Assert.AreEqual(VfxResult.StatusIssues, result.Status);
            Assert.AreEqual(1, result.ExitCode());
        }

        [Test]
        public void SaveRootMustStayInsideAssets()
        {
            Assert.AreEqual("Assets/Vfx/Generated", VfxAssets.NormalizeSaveRoot(null));
            Assert.AreEqual("Assets/Vfx/Out", VfxAssets.NormalizeSaveRoot("Assets\\Vfx\\Out\\"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.NormalizeSaveRoot("Assets/../Packages"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.NormalizeSaveRoot("C:/Temp/Vfx"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.NormalizeSaveRoot("Packages/com.officina.vfx"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.PrepareFolder("Assets/Vfx", "Bad/Name"));
        }
    }
}
