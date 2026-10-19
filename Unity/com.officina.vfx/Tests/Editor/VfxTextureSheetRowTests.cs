using System.IO;
using NUnit.Framework;
using Officina.Vfx.Editor;
using UnityEngine;

namespace Officina.Vfx.Tests
{
    // textureSheet.row (소재 묶음 설계 5 · 8절 E1~E5). 줄 고르기 매핑 · 꼴 거절 · SingleRow 의 startFrame 칸 수를 본다.
    // E3 은 값만 보지 않고 입자를 실제로 돌려 BakeMesh 의 UV 로 「몇 번 칸이 그려졌나」를 잰다.
    public class VfxTextureSheetRowTests
    {
        private string tempPng;

        [TearDown]
        public void TearDown()
        {
            if (tempPng != null && File.Exists(tempPng)) { File.Delete(tempPng); }
            tempPng = null;
        }

        // 층 하나짜리 레시피. sheet 는 textureSheet 객체 JSON 글.
        private static string Recipe(string sheet, string texture = "px1")
        {
            return "{ \"version\": 1, \"name\": \"fx_row\", \"seed\": 7, \"duration\": 1, \"ppu\": 32, \"layers\": [ "
                + "{ \"name\": \"core\", \"texture\": " + Newtonsoft.Json.JsonConvert.ToString(texture) + ","
                + " \"main\": { \"startLifetime\": 1, \"startSpeed\": 0, \"startSize\": 1, \"maxParticles\": 4 },"
                + " \"emission\": { \"rateOverTime\": 0, \"bursts\": [[0, 1]] },"
                + " \"textureSheet\": " + sheet + " } ] }";
        }

        private static GameObject Build(string json, VfxResult result)
        {
            return VfxBuilder.Build(VfxRecipe.Parse(json), new VfxJob { Mode = VfxJob.ModeRender }, result);
        }

        private static ParticleSystem.TextureSheetAnimationModule Sheet(GameObject root)
        {
            return root.transform.GetChild(0).GetComponent<ParticleSystem>().textureSheetAnimation;
        }

        // E1
        [Test]
        public void IntegerRowIsSingleRowCustom()
        {
            var result = new VfxResult();
            GameObject root = Build(Recipe("{ \"tiles\": [4, 3], \"fps\": 12, \"row\": 2 }"), result);
            try
            {
                var sheet = Sheet(root);
                Assert.AreEqual(ParticleSystemAnimationType.SingleRow, sheet.animation);
                Assert.AreEqual(ParticleSystemAnimationRowMode.Custom, sheet.rowMode);
                Assert.AreEqual(2, sheet.rowIndex);
                Assert.AreEqual(0, result.Issues.Count);
            }
            finally { VfxBuilder.Dispose(root); }
        }

        // E2
        [Test]
        public void RandomRowIsSingleRowRandom()
        {
            var result = new VfxResult();
            GameObject root = Build(Recipe("{ \"tiles\": [4, 3], \"row\": \"random\" }"), result);
            try
            {
                var sheet = Sheet(root);
                Assert.AreEqual(ParticleSystemAnimationType.SingleRow, sheet.animation);
                Assert.AreEqual(ParticleSystemAnimationRowMode.Random, sheet.rowMode);
                Assert.AreEqual(0, result.Issues.Count);
            }
            finally { VfxBuilder.Dispose(root); }
        }

        // E3 (값) : SingleRow 면 startFrame 1 이 1 / numTilesX 로 들어간다.
        [Test]
        public void SingleRowStartFrameDividesByRowLength()
        {
            var result = new VfxResult();
            GameObject root = Build(Recipe("{ \"tiles\": [4, 2], \"row\": 1, \"startFrame\": 1 }"), result);
            try
            {
                Assert.AreEqual(0.25f, Sheet(root).startFrame.constant, 1e-6f);
            }
            finally { VfxBuilder.Dispose(root); }
        }

        // E3 (실측) : Unity 가 SingleRow 의 startFrame 비율을 한 줄 길이로 곱하는지 그린 칸으로 확인한다.
        // 4×2 시트 · 1번 줄 · startFrame 0.25 → 줄 길이(4)로 곱하면 floor(1)=1번 칸, 시트 전체(8)로 곱하면 floor(2)=2번 칸.
        // fps 를 아주 작게 해 시간이 흘러도 칸이 안 바뀌게 한다.
        [Test]
        public void SingleRowStartFrameMeasuredByBakedUv()
        {
            var go = new GameObject("row_probe");
            var cameraGo = new GameObject("row_probe_cam");
            var mesh = new Mesh();
            try
            {
                var ps = go.AddComponent<ParticleSystem>();
                ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
                var main = ps.main;
                main.duration = 1f;
                main.loop = false;
                main.startLifetime = 1f;
                main.startSpeed = 0f;
                main.startSize = 1f;
                var emission = ps.emission;
                emission.rateOverTime = 0f;
                emission.SetBursts(new[] { new ParticleSystem.Burst(0f, 1) });
                var shape = ps.shape;
                shape.enabled = false;
                var sheet = ps.textureSheetAnimation;
                sheet.enabled = true;
                sheet.mode = ParticleSystemAnimationMode.Grid;
                sheet.numTilesX = 4;
                sheet.numTilesY = 2;
                sheet.animation = ParticleSystemAnimationType.SingleRow;
                sheet.rowMode = ParticleSystemAnimationRowMode.Custom;
                sheet.rowIndex = 1;
                sheet.timeMode = ParticleSystemAnimationTimeMode.FPS;
                sheet.fps = 0.001f;
                sheet.startFrame = 0.25f;

                cameraGo.transform.position = new Vector3(0f, 0f, -10f);
                var camera = cameraGo.AddComponent<Camera>();
                ps.Simulate(0.05f, true, true);
                Assert.AreEqual(1, ps.particleCount, "입자가 하나 있어야 잴 수 있다");
                go.GetComponent<ParticleSystemRenderer>().BakeMesh(mesh, camera, ParticleSystemBakeMeshOptions.Default);

                Vector2 min = new Vector2(float.MaxValue, float.MaxValue);
                foreach (Vector2 uv in mesh.uv)
                {
                    min = Vector2.Min(min, uv);
                }
                int column = Mathf.RoundToInt(min.x * 4f);
                // UV 의 v 는 아래가 0 이고 Unity 시트의 줄 번호는 위가 0 이다.
                int rowFromTop = 2 - 1 - Mathf.RoundToInt(min.y * 2f);
                Assert.AreEqual(1, rowFromTop, "rowIndex 1 줄이 그려져야 한다");
                Assert.AreEqual(1, column, "startFrame 0.25 가 한 줄 길이(4)로 곱해지면 1번 칸이다");
            }
            finally
            {
                Object.DestroyImmediate(mesh);
                Object.DestroyImmediate(go);
                Object.DestroyImmediate(cameraGo);
            }
        }

        // E4 : row 없으면 지금처럼 시트 전체.
        [Test]
        public void NoRowStaysWholeSheet()
        {
            var result = new VfxResult();
            GameObject root = Build(Recipe("{ \"tiles\": [4, 2], \"startFrame\": 2 }"), result);
            try
            {
                var sheet = Sheet(root);
                Assert.AreEqual(ParticleSystemAnimationMode.Grid, sheet.mode);
                Assert.AreEqual(ParticleSystemAnimationType.WholeSheet, sheet.animation);
                Assert.AreEqual(0.25f, sheet.startFrame.constant, 1e-6f);
            }
            finally { VfxBuilder.Dispose(root); }
        }

        // E5 : 꼴이 틀린 row 는 build.bad_value, 시트 전체로 둔다.
        [TestCase("\"abc\"")]
        [TestCase("-1")]
        [TestCase("1.5")]
        [TestCase("99999999999")]
        [TestCase("99999999999999999999999")] // long 밖 — Newtonsoft 가 BigInteger 로 읽는다
        public void BadRowIsBadValue(string row)
        {
            var result = new VfxResult();
            GameObject root = Build(Recipe("{ \"tiles\": [4, 2], \"row\": " + row + " }"), result);
            try
            {
                Assert.IsTrue(result.Issues.Exists(x => x.Rule == "build.bad_value" && x.Layer == "core"
                    && x.Detail.StartsWith("textureSheet.row=")), row);
                Assert.AreEqual(ParticleSystemAnimationType.WholeSheet, Sheet(root).animation);
            }
            finally { VfxBuilder.Dispose(root); }
        }

        // 줄 수(tiles.y) 이상인 row 는 build.texture_sheet_row 로 거절한다.
        [Test]
        public void RowOutOfRangeIsRejected()
        {
            var result = new VfxResult();
            GameObject root = Build(Recipe("{ \"tiles\": [4, 2], \"row\": 2 }"), result);
            try
            {
                Assert.IsTrue(result.Issues.Exists(x => x.Rule == "build.texture_sheet_row" && x.Layer == "core"));
                Assert.AreEqual(ParticleSystemAnimationType.WholeSheet, Sheet(root).animation);
                Assert.AreEqual(1, result.ExitCode());
            }
            finally { VfxBuilder.Dispose(root); }
        }

        // Python 이 lib: 를 풀어 보낸 resolved.json 꼴 — 절대 PNG 경로 + tiles · fps · row. issue 없이 조립돼야 한다.
        [TestCase("2", ParticleSystemAnimationRowMode.Custom)]
        [TestCase("\"random\"", ParticleSystemAnimationRowMode.Random)]
        public void ResolvedLibRecipeBuildsClean(string row, ParticleSystemAnimationRowMode mode)
        {
            tempPng = Path.Combine(Path.GetTempPath(), "vfx_row_" + System.Guid.NewGuid().ToString("N") + ".png");
            var texture = new Texture2D(32, 24, TextureFormat.RGBA32, false);
            try { File.WriteAllBytes(tempPng, texture.EncodeToPNG()); }
            finally { Object.DestroyImmediate(texture); }

            var result = new VfxResult();
            GameObject root = Build(Recipe("{ \"tiles\": [4, 3], \"fps\": 12, \"row\": " + row + " }", tempPng), result);
            try
            {
                Assert.AreEqual(0, result.Issues.Count, string.Join(" | ", result.Issues.ConvertAll(x => x.Rule + ":" + x.Detail)));
                var sheet = Sheet(root);
                Assert.AreEqual(ParticleSystemAnimationType.SingleRow, sheet.animation);
                Assert.AreEqual(mode, sheet.rowMode);
                Assert.AreEqual(4, sheet.numTilesX);
                Assert.AreEqual(3, sheet.numTilesY);
                Material material = root.transform.GetChild(0).GetComponent<ParticleSystemRenderer>().sharedMaterial;
                Assert.AreEqual(32, material.GetTexture(VfxMaterialFactory.MainTex).width);
            }
            finally { VfxBuilder.Dispose(root); }
        }
    }
}
