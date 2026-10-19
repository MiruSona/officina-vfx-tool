using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace Officina.Vfx.Editor
{
    // 저장 자리 검사 · 텍스처 · 머티리얼 에셋 저장 (설계 5-5). 프리팹보다 먼저 불린다.
    public static class VfxAssets
    {
        // \z 는 문자열 끝만 받는다($ 는 끝 줄바꿈 앞도 받아 "abc" + 줄바꿈이 통과한다).
        private static readonly Regex RecipeName = new Regex(@"^[a-z0-9_]+\z");
        private static readonly Regex LayerFileName = new Regex(@"^[A-Za-z0-9_][A-Za-z0-9_.\-]*\z");
        private static readonly Regex WindowsReserved = new Regex(@"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\z", RegexOptions.IgnoreCase);
        public const int LayerNameMax = 40;

        // saveRoot 를 정규화해 Assets/ 안인지 본다. `..` · 절대 경로 · Assets 밖은 거절(종료 2).
        // 조각 끝 공백 · 점도 거절한다 — Windows 가 벗겨 내 AssetDatabase 경로와 디스크 경로가 어긋난다.
        // 그래서 앞뒤 공백을 Trim 으로 조용히 벗기지 않는다(마지막 조각 끝 공백도 거절). 파일 이름에 못 쓰는 글자도 거절.
        public static string NormalizeSaveRoot(string saveRoot)
        {
            string root = VfxJob.DefaultSaveRoot;
            if (!string.IsNullOrWhiteSpace(saveRoot)) { root = saveRoot.Replace('\\', '/').TrimEnd('/'); }
            // Unity Mono 의 IsPathRooted 는 잘못된 글자(< 등)에 ArgumentException 을 던진다(실측 2026-10-15) — 먼저 거른다.
            if (root.IndexOfAny(Path.GetInvalidPathChars()) >= 0)
            {
                throw new VfxBuildException($"saveRoot 에 경로에 못 쓰는 글자가 있다 : {saveRoot}");
            }
            if (Path.IsPathRooted(root) || root.Contains(":"))
            {
                throw new VfxBuildException($"saveRoot 는 프로젝트 상대 경로여야 한다 : {saveRoot}");
            }

            string[] segments = root.Split('/');
            if (segments[0] != "Assets")
            {
                throw new VfxBuildException($"saveRoot 는 Assets/ 안이어야 한다 : {saveRoot}");
            }
            foreach (string segment in segments)
            {
                if (segment.Length == 0 || segment == "." || segment == "..")
                {
                    throw new VfxBuildException($"saveRoot 에 빈 칸 · . · .. 이 있다 : {saveRoot}");
                }
                if (segment != segment.TrimEnd(' ', '.'))
                {
                    throw new VfxBuildException($"saveRoot 조각 끝에 공백 · 점이 있다 : {saveRoot}");
                }
                if (segment.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
                {
                    throw new VfxBuildException($"saveRoot 에 파일 이름에 못 쓰는 글자가 있다 : {saveRoot}");
                }
            }
            return root;
        }

        // <saveRoot>/<name> 폴더를 만든다. 이미 있는데 <name>.recipe.json 옆 파일이 없으면 사람이 만든 폴더라 덮지 않는다.
        public static string PrepareFolder(string saveRoot, string name)
        {
            CheckRecipeName(name);
            string folder = CheckedAssetPath(NormalizeSaveRoot(saveRoot) + "/" + name);
            string sideFile = Path.GetFullPath(folder + "/" + name + ".recipe.json");
            if (Directory.Exists(Path.GetFullPath(folder)) && !File.Exists(sideFile))
            {
                throw new VfxBuildException($"{folder} 에 {name}.recipe.json 이 없다 — 툴이 만든 폴더가 아니라 덮지 않는다");
            }

            string current = "Assets";
            string[] segments = folder.Split('/');
            for (int i = 1; i < segments.Length; i++)
            {
                string next = current + "/" + segments[i];
                if (!AssetDatabase.IsValidFolder(next)) { AssetDatabase.CreateFolder(current, segments[i]); }
                current = next;
            }
            return folder;
        }

        // 에셋을 쓰는 모든 경로(폴더 · png · mat · prefab · recipe.json)가 지나는 한 길목. 통과한 경로를 그대로 돌려준다.
        // Assets 아래 조각 · 쓸 파일 중 링크(정션 · 심볼릭 링크)가 있으면 거절한다(종료 2).
        // 문자열 검사만으로는 링크를 지나 Assets 밖에 쓴다. Assets 자신은 프로젝트 구성이라 보지 않는다.
        public static string CheckedAssetPath(string assetPath)
        {
            string[] segments = assetPath.Split('/');
            string current = segments[0];
            for (int i = 1; i < segments.Length; i++)
            {
                current += "/" + segments[i];
                if (IsLink(FullPathOrReject(current)))
                {
                    throw new VfxBuildException($"저장 자리에 링크(정션 · 심볼릭 링크)가 있다 : {current}");
                }
            }
            return assetPath;
        }

        // 잘못된 글자 · 너무 긴 경로로 GetFullPath 가 터지면 종료 2 로 바꾼다(그대로 두면 처리 안 된 예외).
        private static string FullPathOrReject(string assetPath)
        {
            try
            {
                return Path.GetFullPath(assetPath);
            }
            catch (System.Exception error) when (error is System.ArgumentException || error is System.NotSupportedException
                || error is PathTooLongException)
            {
                throw new VfxBuildException($"저장 자리 경로가 잘못됐다 : {assetPath} — {error.Message}");
            }
        }

        // Exists 로 거르지 않는다 — 끊긴 링크는 Directory.Exists · File.Exists 가 둘 다 false 라 그냥 지나간다.
        // GetAttributes 는 링크를 따라가지 않아 끊긴 링크도 ReparsePoint 를 돌려준다. 정말 없는 자리만 링크 아님.
        // 그 밖의 읽기 실패(권한 등)는 링크인지 모르니 거절 쪽으로 닫는다.
        private static bool IsLink(string fullPath)
        {
            try
            {
                return (File.GetAttributes(fullPath) & FileAttributes.ReparsePoint) != 0;
            }
            catch (FileNotFoundException) { return false; }
            catch (DirectoryNotFoundException) { return false; }
            catch (System.Exception error) when (error is IOException || error is System.UnauthorizedAccessException
                || error is System.ArgumentException || error is System.NotSupportedException)
            {
                throw new VfxBuildException($"저장 자리를 확인할 수 없다 : {fullPath} — {error.Message}");
            }
        }

        public static void WriteRecipeSideFile(string folder, string name, string recipeJson)
        {
            string path = CheckedAssetPath(folder + "/" + name + ".recipe.json");
            File.WriteAllText(Path.GetFullPath(path), recipeJson.Replace("\r\n", "\n"), new UTF8Encoding(false));
            AssetDatabase.ImportAsset(path);
        }

        // 원본을 <folder>/<층>.png 로 복사하고 도트용 가져오기 설정(Point · 압축 없음 · mipmap 끔 · sRGB)을 건다.
        public static Texture2D SaveTexture(string folder, string layerName, string sourceFile)
        {
            string path = CheckedAssetPath(folder + "/" + SafeFileName(layerName) + ".png");
            File.Copy(sourceFile, Path.GetFullPath(path), true);
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);

            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null) { throw new VfxBuildException($"텍스처 가져오기 실패 : {path}"); }
            importer.textureType = TextureImporterType.Default;
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.mipmapEnabled = false;
            importer.sRGBTexture = true;
            importer.alphaIsTransparency = true;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.npotScale = TextureImporterNPOTScale.None;
            importer.SaveAndReimport();
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }

        // 메모리 머티리얼을 <folder>/<층>.mat 로 남긴다. 이미 있으면 GUID 를 지키려고 속성만 덮는다.
        public static Material SaveMaterial(string folder, string layerName, Material source, Texture2D texture)
        {
            string path = CheckedAssetPath(folder + "/" + SafeFileName(layerName) + ".mat");
            var material = new Material(source) { name = layerName };
            if (texture != null) { material.SetTexture(VfxMaterialFactory.MainTex, texture); }

            var existing = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (existing == null)
            {
                AssetDatabase.CreateAsset(material, path);
                return material;
            }
            existing.shader = material.shader;
            existing.CopyPropertiesFromMaterial(material);
            EditorUtility.SetDirty(existing);
            UnityEngine.Object.DestroyImmediate(material);
            return existing;
        }

        public static void CheckRecipeName(string name)
        {
            if (name == null || !RecipeName.IsMatch(name))
            {
                throw new VfxBuildException($"레시피 name 은 [a-z0-9_]+ 여야 한다 : {name}");
            }
        }

        // 층 이름은 파일 이름(<층>.png · <층>.mat)이 된다. Python check 와 같은 규칙 :
        // ^[A-Za-z0-9_][A-Za-z0-9_.\-]*\z · 「..」 금지 · 끝이 「.」 금지 · 40자 이하 ·
        // 첫 점 앞 조각이 Windows 예약 이름(CON · PRN · AUX · NUL · COM1-9 · LPT1-9)이면 금지 — Windows 는 CON.x.png 도 장치로 본다.
        public static string SafeFileName(string layerName)
        {
            bool bad = layerName == null
                || layerName.Length > LayerNameMax
                || !LayerFileName.IsMatch(layerName)
                || layerName.Contains("..")
                || layerName.EndsWith(".")
                || WindowsReserved.IsMatch(layerName.Split('.')[0]);
            if (bad) { throw new VfxBuildException($"층 이름을 파일 이름으로 못 쓴다 : {layerName}"); }
            return layerName;
        }
    }
}
