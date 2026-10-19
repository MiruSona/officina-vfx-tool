using System.Diagnostics;
using System.IO;
using NUnit.Framework;
using Officina.Vfx.Editor;
using UnityEditor;
using UnityEngine;

namespace Officina.Vfx.Tests
{
    // 저장 자리 경로 감옥(조각 끝 공백 · 점, Assets 안 링크)과 텍스처 원본을 한 번만 고르는지 본다.
    public class VfxPathJailTests
    {
        private const string TempRoot = "Assets/VfxPathJailTestTmp";

        [Test]
        public void SaveRootRejectsTrailingSpace()
        {
            Assert.Throws<VfxBuildException>(() => VfxAssets.NormalizeSaveRoot("Assets/Vfx /Out"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.PrepareFolder("Assets/Vfx /Out", "fx_a"));
        }

        [Test]
        public void SaveRootRejectsTrailingDot()
        {
            Assert.Throws<VfxBuildException>(() => VfxAssets.NormalizeSaveRoot("Assets/Vfx./Out"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.NormalizeSaveRoot("Assets/Vfx/Out."));
        }

        // 마지막 조각 끝 · 맨 앞 공백도 Trim 으로 벗기지 않고 거절한다.
        [Test]
        public void SaveRootRejectsLastSegmentSpace()
        {
            Assert.Throws<VfxBuildException>(() => VfxAssets.NormalizeSaveRoot("Assets/Vfx/Out "));
            Assert.Throws<VfxBuildException>(() => VfxAssets.NormalizeSaveRoot(" Assets/Vfx/Out"));
        }

        // 파일 이름에 못 쓰는 글자는 ArgumentException 으로 터지지 않고 종료 2(VfxBuildException)로 거절한다.
        [Test]
        public void SaveRootRejectsInvalidChars()
        {
            Assert.Throws<VfxBuildException>(() => VfxAssets.NormalizeSaveRoot("Assets/a<b"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.PrepareFolder("Assets/a<b", "fx_a"));
            Assert.Throws<VfxBuildException>(() => VfxAssets.CheckedAssetPath("Assets/a<b/c.png"));
        }

        // Assets 안 정션이 Assets 밖 폴더를 가리키면 PrepareFolder 가 폴더를 만들기 전에 거절한다.
        [Test]
        public void SaveRootThroughJunctionIsRejected()
        {
            if (Application.platform != RuntimePlatform.WindowsEditor) { Assert.Ignore("정션 시험은 Windows 만"); }
            string holder = Path.GetFullPath(TempRoot);
            string link = Path.Combine(holder, "linked");
            string outside = Path.Combine(Path.GetTempPath(), "VfxPathJailOutside_" + System.Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(holder);
            Directory.CreateDirectory(outside);
            try
            {
                RunCmd($"mklink /J \"{link}\" \"{outside}\"");
                Assert.IsTrue(Directory.Exists(link), "정션을 못 만들었다");
                var error = Assert.Throws<VfxBuildException>(() => VfxAssets.PrepareFolder(TempRoot + "/linked", "fx_a"));
                StringAssert.Contains("링크", error.Message);
                Assert.AreEqual(0, Directory.GetFileSystemEntries(outside).Length, "링크 너머에 무언가 생겼다");
            }
            finally
            {
                // 정션은 rmdir 로 링크만 지운다(재귀 삭제는 대상 폴더 안까지 지울 수 있다).
                if (Directory.Exists(link)) { RunCmd($"rmdir \"{link}\""); }
                Directory.Delete(holder, true);
                Directory.Delete(outside, true);
                string meta = holder + ".meta";
                if (File.Exists(meta)) { File.Delete(meta); }
                AssetDatabase.Refresh();
            }
        }

        // 폴더는 멀쩡해도 쓸 파일(core.mat) 자리가 링크면 SaveMaterial 이 거절한다 — 길목이 mat 에도 걸린다.
        // 파일 심볼릭 링크는 관리자 권한이 들어 정션(디렉터리 링크)으로 같은 ReparsePoint 를 만든다.
        [Test]
        public void MaterialPathThroughLinkIsRejected()
        {
            if (Application.platform != RuntimePlatform.WindowsEditor) { Assert.Ignore("정션 시험은 Windows 만"); }
            string holder = Path.GetFullPath(TempRoot);
            string link = Path.Combine(holder, "core.mat");
            string outside = Path.Combine(Path.GetTempPath(), "VfxPathJailOutside_" + System.Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(holder);
            Directory.CreateDirectory(outside);
            var source = new Material(Shader.Find("Sprites/Default"));
            try
            {
                RunCmd($"mklink /J \"{link}\" \"{outside}\"");
                Assert.IsTrue(Directory.Exists(link), "정션을 못 만들었다");
                var error = Assert.Throws<VfxBuildException>(() => VfxAssets.SaveMaterial(TempRoot, "core", source, null));
                StringAssert.Contains("링크", error.Message);
                Assert.AreEqual(0, Directory.GetFileSystemEntries(outside).Length, "링크 너머에 무언가 생겼다");
            }
            finally
            {
                Object.DestroyImmediate(source);
                Cleanup(holder, link);
                Directory.Delete(outside, true);
            }
        }

        // 끊긴 정션(대상 폴더가 지워짐)도 링크로 보고 거절한다. .NET 은 끊긴 링크에 Exists 가 false 지만
        // Unity Mono 는 true 를 돌려준다(실측 2026-10-15) — 런타임과 상관없이 길목이 Exists 를 안 거친다.
        [Test]
        public void BrokenJunctionIsRejected()
        {
            if (Application.platform != RuntimePlatform.WindowsEditor) { Assert.Ignore("정션 시험은 Windows 만"); }
            string holder = Path.GetFullPath(TempRoot);
            string link = Path.Combine(holder, "linked");
            string outside = Path.Combine(Path.GetTempPath(), "VfxPathJailOutside_" + System.Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(holder);
            Directory.CreateDirectory(outside);
            try
            {
                RunCmd($"mklink /J \"{link}\" \"{outside}\"");
                Directory.Delete(outside, true);
                Assert.IsFalse(Directory.Exists(outside), "정션 대상이 안 지워졌다");
                var error = Assert.Throws<VfxBuildException>(() => VfxAssets.PrepareFolder(TempRoot + "/linked", "fx_a"));
                StringAssert.Contains("링크", error.Message);
                Assert.IsFalse(Directory.Exists(outside), "끊긴 링크 너머에 폴더가 다시 생겼다");
            }
            finally
            {
                Cleanup(holder, link);
                if (Directory.Exists(outside)) { Directory.Delete(outside, true); }
            }
        }

        // 상대 경로 텍스처는 issue 한 번 · px1 에셋으로 바뀌고, build 가 복사할 원본도 그 px1 이다.
        [Test]
        public void RelativeTextureFallsBackOnceToPx1()
        {
            string json = "{ \"version\": 1, \"name\": \"fx_a\", \"seed\": 1, \"duration\": 0.5, \"ppu\": 32"
                + ", \"layers\": [ { \"name\": \"core\", \"texture\": \"Textures/px1.png\" } ] }";
            VfxRecipe recipe = VfxRecipe.Parse(json);
            var result = new VfxResult();
            GameObject root = VfxBuilder.Build(recipe, new VfxJob { Mode = VfxJob.ModeRender }, result);
            try
            {
                Assert.AreEqual(1, result.Issues.FindAll(x => x.Rule == "build.texture_missing").Count);
                Material material = root.transform.GetChild(0).GetComponent<ParticleSystemRenderer>().sharedMaterial;
                Texture texture = material.GetTexture(VfxMaterialFactory.MainTex);
                Assert.IsTrue(AssetDatabase.Contains(texture));
                string source = VfxMaterialFactory.TextureSourceFile(recipe.Layers[0], texture);
                StringAssert.EndsWith("px1.png", source.Replace('\\', '/'));
                Assert.IsTrue(File.Exists(source));
            }
            finally
            {
                VfxBuilder.Dispose(root);
            }
        }

        // 드라이브 상대(\…)는 실제 있는 파일을 가리켜도 CWD 드라이브 따라 달라지므로 받지 않고 px1 로 바꾼다.
        [Test]
        public void DriveRelativeTextureFallsBackToPx1()
        {
            Assert.IsTrue(VfxMaterialTable.TryGetTexturePath("px1", out string builtIn));
            string full = VfxMaterialFactory.PhysicalPath(builtIn);
            if (full.Length < 3 || full[1] != ':') { Assert.Ignore("드라이브 문자 경로가 아니다"); }
            var layer = new VfxLayer { Name = "core", Texture = full.Substring(2) };
            Assert.IsTrue(File.Exists(layer.Texture), "같은 드라이브 기준으로 파일이 있어야 옛 코드와 갈린다");
            var result = new VfxResult();
            Texture texture = VfxMaterialFactory.LoadTexture(layer, result);
            Assert.AreEqual(1, result.Issues.FindAll(x => x.Rule == "build.texture_missing").Count);
            StringAssert.EndsWith("px1.png", AssetDatabase.GetAssetPath(texture));
        }

        // 정션은 Exists 와 상관없이 rmdir 로 링크만 지운다(끊긴 정션은 Exists 가 false · 재귀 삭제는 대상 안까지 지울 수 있다).
        private static void Cleanup(string holder, string link)
        {
            RunCmd($"rmdir \"{link}\"");
            if (Directory.Exists(holder)) { Directory.Delete(holder, true); }
            string meta = holder + ".meta";
            if (File.Exists(meta)) { File.Delete(meta); }
            AssetDatabase.Refresh();
        }

        private static void RunCmd(string arguments)
        {
            var info = new ProcessStartInfo("cmd.exe", "/c " + arguments) { CreateNoWindow = true, UseShellExecute = false };
            using (Process process = Process.Start(info))
            {
                process.WaitForExit();
            }
        }
    }
}
