using System.IO;
using UnityEditor;
using UnityEngine;

namespace Officina.Vfx.Editor
{
    // 층 하나의 텍스처 · 머티리얼을 메모리에 만든다. 에셋으로 남기는 건 VfxAssets 몫(build 모드만).
    public static class VfxMaterialFactory
    {
        public const string MainTex = "_MainTex";
        public const string Ppu = "_PPU";
        public const string Snap = "_Snap";
        private const string FallbackTexture = "px1";

        // 파일 텍스처(px1 · px2 밖)의 원본 경로. LoadTexture 한 곳에서만 부른다 — 두 번 부르면 issue 가 겹친다.
        // 절대 경로이고 파일이 있어야 받는다. 상대 경로는 CWD 따라 아무 파일이나 잡히므로 받지 않는다.
        // IsPathRooted 는 드라이브 상대(\foo.png · C:foo.png)도 참이라 IsPathFullyQualified 로 본다.
        // 못 받으면 build.texture_missing 을 남기고 null(부르는 쪽이 px1 로 바꾼다).
        private static string ResolveTextureFile(VfxLayer layer, VfxResult result)
        {
            // 잘못된 글자는 Mono 의 Path 함수가 ArgumentException 으로 터지므로 먼저 거른다.
            if (!string.IsNullOrEmpty(layer.Texture) && layer.Texture.IndexOfAny(Path.GetInvalidPathChars()) < 0
                && Path.IsPathFullyQualified(layer.Texture) && File.Exists(layer.Texture))
            {
                return layer.Texture;
            }
            result.Issue("build.texture_missing", layer.Name, $"texture={layer.Texture} — 절대 경로 파일이 아니라 px1 로 바꿈");
            return null;
        }

        // Packages/<이름>/… 가상 경로 → 디스크 경로. file: 패키지(프로젝트 밖)든 PackageCache 든 Unity 가 풀어 준다
        // (실측 2026-10-15 : Path.GetFullPath · FileUtil.GetPhysicalPath 둘 다 같은 실제 경로). 뜻이 드러나는 쪽을 쓴다.
        public static string PhysicalPath(string assetPath)
        {
            return Path.GetFullPath(FileUtil.GetPhysicalPath(assetPath));
        }

        public static Texture2D LoadTexture(VfxLayer layer, VfxResult result)
        {
            if (VfxMaterialTable.TryGetTexturePath(layer.Texture, out string builtIn))
            {
                var asset = AssetDatabase.LoadAssetAtPath<Texture2D>(builtIn);
                if (asset == null) { result.Issue("build.texture_missing", layer.Name, builtIn); }
                return asset;
            }

            string file = ResolveTextureFile(layer, result);
            if (file == null) { return LoadFallback(); }
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false) { name = layer.Name };
            if (!texture.LoadImage(File.ReadAllBytes(file)))
            {
                // PNG 가 아니거나 깨진 파일. 조용히 2×2 빈 텍스처로 그리지 않고 알린 뒤 px1 로 바꾼다.
                Object.DestroyImmediate(texture);
                result.Issue("build.texture_bad", layer.Name, $"texture={file} 를 그림으로 못 읽음 — px1 로 바꿈");
                return LoadFallback();
            }
            texture.filterMode = FilterMode.Point;
            texture.wrapMode = TextureWrapMode.Clamp;
            return texture;
        }

        // 메모리 텍스처는 layer.Texture 파일에서만 나온다(px1 대체는 패키지 에셋). build 가 복사할 원본을 여기서 정한다 —
        // 원본 경로를 다시 셈하지 않아 issue 가 겹치지 않고, 깨진 파일 대신 실제로 쓴 px1 이 복사된다.
        public static string TextureSourceFile(VfxLayer layer, Texture texture)
        {
            if (texture == null) { return null; }
            if (AssetDatabase.Contains(texture)) { return PhysicalPath(AssetDatabase.GetAssetPath(texture)); }
            return layer.Texture;
        }

        private static Texture2D LoadFallback()
        {
            VfxMaterialTable.TryGetTexturePath(FallbackTexture, out string fallback);
            return AssetDatabase.LoadAssetAtPath<Texture2D>(fallback);
        }

        // 이름표 머티리얼을 복사해 _MainTex · _PPU · _Snap 을 넣는다. lit/additive 같은 없는 이름표는 issue.
        public static Material CreateMaterial(VfxRecipe recipe, VfxLayer layer, Texture texture, VfxResult result)
        {
            if (!VfxMaterialTable.TryGetMaterialPath(layer.Material, layer.Blend, out string path))
            {
                result.Issue("build.material", layer.Name, $"없는 이름표 {layer.Material}/{layer.Blend}");
                return null;
            }
            var source = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (source == null)
            {
                result.Issue("build.material_missing", layer.Name, path);
                return null;
            }

            var material = new Material(source) { name = layer.Name };
            if (texture != null) { material.SetTexture(MainTex, texture); }
            material.SetFloat(Ppu, recipe.Ppu);
            float snap = 0f;
            if (recipe.Snap) { snap = 1f; }
            material.SetFloat(Snap, snap);
            return material;
        }
    }
}
