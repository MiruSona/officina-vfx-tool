using System.IO;
using Newtonsoft.Json;
using NUnit.Framework;
using Officina.Vfx.Editor;
using UnityEditor;
using UnityEngine;

namespace Officina.Vfx.Tests
{
    // 거절해야 할 입력(경로 · 이름 · 판 · 모르는 열쇠)을 거절하는지, 조용히 넘기던 값이 issue 로 남는지 본다.
    public class VfxSafetyTests
    {
        private static string RecipeJson(int version, string name, string layerName, string extraLayer = "", string top = "")
        {
            return "{ \"version\": " + version + ", \"name\": " + JsonConvert.ToString(name) + ", \"seed\": 1, \"duration\": 0.5, \"ppu\": 32" + top
                + ", \"layers\": [ { \"name\": " + JsonConvert.ToString(layerName) + extraLayer + " } ] }";
        }

        private static VfxResult BuildAndDispose(string json)
        {
            var result = new VfxResult();
            GameObject root = VfxBuilder.Build(VfxRecipe.Parse(json), new VfxJob { Mode = VfxJob.ModeRender }, result);
            VfxBuilder.Dispose(root);
            return result;
        }

        [Test]
        public void OutDirMustBeAbsoluteAndOutsideProject()
        {
            string project = Path.Combine(Path.GetTempPath(), "VfxProj");
            string sibling = Path.Combine(Path.GetTempPath(), "VfxProjBackup", "frames");
            Assert.AreEqual(Path.GetFullPath(sibling), VfxOutDir.Resolve(sibling, project));
            Assert.AreEqual(Path.GetFullPath(sibling), VfxOutDir.Resolve(sibling + Path.DirectorySeparatorChar, project));
            Assert.Throws<VfxBuildException>(() => VfxOutDir.Resolve("frames/out", project));
            Assert.Throws<VfxBuildException>(() => VfxOutDir.Resolve("", project));
            Assert.Throws<VfxBuildException>(() => VfxOutDir.Resolve(project, project));
            Assert.Throws<VfxBuildException>(() => VfxOutDir.Resolve(Path.Combine(project, "Assets", "f"), project));
            Assert.Throws<VfxBuildException>(() => VfxOutDir.Resolve(Path.Combine(project, "Library", "f"), project));
            Assert.Throws<VfxBuildException>(() => VfxOutDir.Resolve(Path.Combine(project, "x", "..", "Temp"), project));
        }

        [Test]
        public void LayerFileNameRule()
        {
            Assert.AreEqual("sparks_A-1.b", VfxAssets.SafeFileName("sparks_A-1.b"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName(".."));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName("a..b"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName("a/b"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName("a\b"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName("sparks\n"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName(""));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName(".hidden"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName("-dash"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName("core."));
            Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName(new string('a', 41)));
            Assert.AreEqual(new string('a', 40), VfxAssets.SafeFileName(new string('a', 40)));
            foreach (string reserved in new[] { "CON", "prn", "Aux", "nul", "COM1", "com9", "LPT1", "lpt9", "CON.x", "nul.a.b", "Com3.glow" })
            {
                Assert.Throws<VfxBuildException>(() => VfxAssets.SafeFileName(reserved), reserved);
            }
            Assert.AreEqual("COM10", VfxAssets.SafeFileName("COM10"));
            Assert.AreEqual("console", VfxAssets.SafeFileName("console"));
            Assert.AreEqual("x.CON", VfxAssets.SafeFileName("x.CON"));
            Assert.AreEqual("CONx.glow", VfxAssets.SafeFileName("CONx.glow"));
            Assert.AreEqual("_core", VfxAssets.SafeFileName("_core"));
        }

        [Test]
        public void RecipeNameRejectsTrailingNewline()
        {
            VfxAssets.CheckRecipeName("hit_sparks_a");
            Assert.Throws<VfxBuildException>(() => VfxAssets.CheckRecipeName("hit_sparks\n"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.CheckRecipeName("Hit"));
        }

        [Test]
        public void FolderWithoutSideFileIsNotOverwritten()
        {
            const string saveRoot = "Assets/VfxSafetyTestTmp";
            string folder = Path.GetFullPath(saveRoot + "/foreign_fx");
            Directory.CreateDirectory(folder);
            try
            {
                Assert.Throws<VfxBuildException>(() => VfxAssets.PrepareFolder(saveRoot, "foreign_fx"));
            }
            finally
            {
                Directory.Delete(Path.GetFullPath(saveRoot), true);
                string meta = Path.GetFullPath(saveRoot) + ".meta";
                if (File.Exists(meta)) { File.Delete(meta); }
                AssetDatabase.Refresh();
            }
        }

        [Test]
        public void BuildRejectsVersionAndBadLayerName()
        {
            Assert.Throws<VfxBuildException>(() => BuildAndDispose(RecipeJson(2, "fx_a", "core")));
            Assert.Throws<VfxBuildException>(() => BuildAndDispose(RecipeJson(1, "fx_a", "../core")));
            Assert.Throws<VfxBuildException>(() => BuildAndDispose(RecipeJson(1, "fx_a\n", "core")));
        }

        [Test]
        public void SilentFallbacksBecomeIssues()
        {
            VfxResult result = BuildAndDispose(RecipeJson(1, "fx_a", "core",
                ", \"colorOverLifetime\": { \"color\": \"#FFFFFF\" }", ", \"sortingLayer\": \"NoSuchLayer\", \"light\": \"spot\""));
            Assert.IsTrue(result.Issues.Exists(x => x.Rule == "build.bad_value" && x.Layer == "core" && x.Detail.Contains("colorOverLifetime")));
            Assert.IsTrue(result.Issues.Exists(x => x.Rule == "build.bad_value" && x.Detail.Contains("NoSuchLayer")));
            Assert.IsTrue(result.Issues.Exists(x => x.Rule == "build.bad_value" && x.Detail.StartsWith("light=spot")));
        }

        [TestCase("{\"random\": [0, 1], \"mult\": 2}")]
        [TestCase("{\"curve\": [[0, 1]], \"random\": [0, 1]}")]
        [TestCase("{\"curve\": [[0, 1]], \"mul\": 2}")]
        [TestCase("{\"random_curve\": [[[0, 1]], [[0, 2]]], \"steps\": true}")]
        public void ValueRejectsUnknownKeys(string json)
        {
            Assert.Throws<JsonSerializationException>(() => JsonConvert.DeserializeObject<VfxValue>(json));
        }

        [TestCase("{\"random\": [\"#FFFFFF\", \"#000000\"], \"mode\": \"fixed\"}")]
        [TestCase("{\"gradient\": {\"color\": [[0, \"#FFFFFF\"]]}, \"random\": [\"#FFFFFF\", \"#000000\"]}")]
        [TestCase("{\"gradient\": {\"color\": [[0, \"#FFFFFF\"]], \"alhpa\": [[0, 1]]}}")]
        [TestCase("{\"gradient\": {\"color\": [[0, \"#FFFFFF\"]]}, \"mdoe\": \"blend\"}")]
        [TestCase("{\"random_gradient\": [{\"color\": [[0, \"#FFFFFF\"]], \"x\": 1}, {\"color\": [[0, \"#000000\"]]}]}")]
        public void ColorRejectsUnknownKeys(string json)
        {
            Assert.Throws<JsonSerializationException>(() => JsonConvert.DeserializeObject<VfxColor>(json));
        }

        [Test]
        public void BurstRejectsUnknownKeys()
        {
            Assert.Throws<JsonSerializationException>(() => JsonConvert.DeserializeObject<VfxBurst>("{\"t\": 0, \"n\": 3, \"count\": 2}"));
            Assert.AreEqual(3f, JsonConvert.DeserializeObject<VfxBurst>("{\"t\": 0, \"n\": 3, \"cycles\": 1}").Count, 1e-6f);
        }

        [Test]
        public void FrameCountReportsUncapped()
        {
            VfxRecipe recipe = VfxRecipe.Parse("{ \"version\": 1, \"name\": \"long_fx\", \"duration\": 10, \"fps\": 12, \"loop\": true, \"layers\": [] }");
            Assert.AreEqual(120, VfxFrameTimes.RequiredCount(recipe));
            Assert.AreEqual(VfxFrameTimes.MaxFrames, VfxFrameTimes.Compute(recipe).Count);
        }
    }
}
