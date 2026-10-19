using System;
using UnityEditor;
using UnityEngine;

namespace Officina.Vfx.Editor
{
    // resolved.json → 루트 GameObject + 층마다 자식 ParticleSystem. 판단 없이 그대로 옮기는 바보 조립기 (설계 1-2).
    // Build 는 에셋을 안 쓰고(render 모드), SavePrefab 이 텍스처 · 머티리얼 → 프리팹 → 옆 파일 순으로 남긴다(build 모드).
    public static class VfxBuilder
    {
        public const int SupportedVersion = 1;

        // job 은 지금 안 쓰지만 V9 진입점과 꼴을 맞춰 둔다(모드별 조립 차이가 생기면 여기서 본다).
        public static GameObject Build(VfxRecipe recipe, VfxJob job, VfxResult result)
        {
            if (recipe == null) { throw new ArgumentNullException(nameof(recipe)); }
            if (result == null) { throw new ArgumentNullException(nameof(result)); }
            CheckRecipe(recipe, result);

            result.Seed = recipe.Seed;
            result.FixedTimeStep = recipe.FixedTimeStep;
            result.FixedDeltaTime = recipe.FixedDeltaTime;
            VfxModules.ReportExtra(result, null, "", recipe.Extra);
            if (recipe.Canvas != null) { VfxModules.ReportExtra(result, null, "canvas.", recipe.Canvas.Extra); }

            var root = new GameObject(recipe.Name);
            for (int i = 0; i < recipe.Layers.Count; i++)
            {
                BuildLayer(root.transform, recipe, recipe.Layers[i], i, result);
            }
            return root;
        }

        // 프리팹 저장. 저장 자리를 거절하면 VfxBuildException(종료 2). 돌려주는 값은 프리팹 에셋 경로.
        // 옆 파일은 프리팹이 저장된 뒤에 쓴다 — 중간에 실패한 폴더를 「툴이 끝까지 만든 폴더」로 보이지 않게.
        public static string SavePrefab(GameObject root, VfxRecipe recipe, string recipeJson, VfxJob job, VfxResult result)
        {
            string folder = VfxAssets.PrepareFolder(job.SaveRoot, recipe.Name);

            for (int i = 0; i < recipe.Layers.Count; i++)
            {
                VfxLayer layer = recipe.Layers[i];
                var renderer = root.transform.GetChild(i).GetComponent<ParticleSystemRenderer>();
                Material memory = renderer.sharedMaterial;
                if (memory == null) { continue; }
                // 원본 경로는 Build(LoadTexture) 가 고른 텍스처에서 얻는다. 다시 셈하면 issue 가 겹친다.
                Texture memoryTexture = null;
                if (memory.HasProperty(VfxMaterialFactory.MainTex)) { memoryTexture = memory.GetTexture(VfxMaterialFactory.MainTex); }
                string source = VfxMaterialFactory.TextureSourceFile(layer, memoryTexture);
                Texture2D texture = null;
                if (source != null) { texture = VfxAssets.SaveTexture(folder, layer.Name, source); }
                renderer.sharedMaterial = VfxAssets.SaveMaterial(folder, layer.Name, memory, texture);
                DisposeMemoryMaterial(memory);
            }
            AssetDatabase.SaveAssets();

            string prefabPath = VfxAssets.CheckedAssetPath(folder + "/" + recipe.Name + ".prefab");
            PrefabUtility.SaveAsPrefabAsset(root, prefabPath, out bool saved);
            if (!saved) { throw new VfxBuildException($"프리팹 저장 실패 : {prefabPath}"); }
            VfxAssets.WriteRecipeSideFile(folder, recipe.Name, recipeJson);
            result.Prefab = prefabPath;
            return prefabPath;
        }

        // 조립이 메모리에 만든 머티리얼 · 텍스처(에셋이 아닌 것)와 루트를 지운다. 배치 판이 길어져도 새지 않게.
        public static void Dispose(GameObject root)
        {
            if (root == null) { return; }
            foreach (ParticleSystemRenderer renderer in root.GetComponentsInChildren<ParticleSystemRenderer>())
            {
                DisposeMemoryMaterial(renderer.sharedMaterial);
            }
            UnityEngine.Object.DestroyImmediate(root);
        }

        private static void DisposeMemoryMaterial(Material material)
        {
            if (material == null || AssetDatabase.Contains(material)) { return; }
            Texture texture = null;
            if (material.HasProperty(VfxMaterialFactory.MainTex)) { texture = material.GetTexture(VfxMaterialFactory.MainTex); }
            if (texture != null && !AssetDatabase.Contains(texture)) { UnityEngine.Object.DestroyImmediate(texture); }
            UnityEngine.Object.DestroyImmediate(material);
        }

        // 판 · 이름 · 층 이름 · light 를 조립 전에 본다. 판 · 이름은 종료 2, light 는 issue.
        // 층 이름 검사는 render 모드에서도 한다(파일 이름이 될 수 있는 이름만 받는다).
        private static void CheckRecipe(VfxRecipe recipe, VfxResult result)
        {
            if (recipe.Version != SupportedVersion)
            {
                throw new VfxBuildException($"레시피 version 은 {SupportedVersion} 이어야 한다 : {recipe.Version}");
            }
            VfxAssets.CheckRecipeName(recipe.Name);
            foreach (VfxLayer layer in recipe.Layers) { VfxAssets.SafeFileName(layer.Name); }
            if (recipe.Light != "none" && recipe.Light != "global")
            {
                result.Issue("build.bad_value", null, $"light={recipe.Light} — none 으로 둠");
            }
        }

        // seed 는 멈춘 상태에서 넣는다. randomSeed = seed + 층 번호(0부터).
        private static void BuildLayer(Transform parent, VfxRecipe recipe, VfxLayer layer, int index, VfxResult result)
        {
            var go = new GameObject(layer.Name);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = ToOffset(layer.Offset);

            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            ps.useAutoRandomSeed = false;
            ps.randomSeed = unchecked((uint)(recipe.Seed + index));

            VfxModules.ReportExtra(result, layer.Name, "", layer.Extra);
            VfxModules.ApplyMain(ps, recipe, layer, result);
            VfxModules.ApplyEmission(ps, layer, result);
            VfxModules.ApplyShape(ps, layer, result);
            VfxLifetimeModules.ApplyVelocity(ps, layer, result);
            VfxLifetimeModules.ApplyColor(ps, layer, result);
            VfxLifetimeModules.ApplySize(ps, layer, result);
            VfxLifetimeModules.ApplyRotation(ps, layer, result);
            VfxLifetimeModules.ApplyNoise(ps, layer, result);
            VfxLifetimeModules.ApplyTextureSheet(ps, layer, result);

            Texture2D texture = VfxMaterialFactory.LoadTexture(layer, result);
            Material material = VfxMaterialFactory.CreateMaterial(recipe, layer, texture, result);
            VfxModules.ApplyRenderer(ps, recipe, layer, material, result);
        }

        private static Vector3 ToOffset(float[] offset)
        {
            if (offset == null || offset.Length < 2) { return Vector3.zero; }
            return new Vector3(offset[0], offset[1], 0f);
        }
    }
}
