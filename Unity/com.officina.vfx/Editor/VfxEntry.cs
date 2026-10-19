using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Debug = UnityEngine.Debug;

namespace Officina.Vfx.Editor
{
    // -batchmode -executeMethod Officina.Vfx.Editor.VfxEntry.Run -vfxJob <job.json> 의 정적 진입점 (설계 5-4).
    // result.json 은 job.json 옆에 쓴다. 종료 코드 : 0 ok · 1 issues · 2 error.
    public static class VfxEntry
    {
        private const string LogHead = "[VFXTOOL] ";
        private const string JobArg = "-vfxJob";

        public static void Run()
        {
            var result = new VfxResult();
            string resultPath = null;
            try
            {
                string jobPath = ReadArg(JobArg);
                if (string.IsNullOrEmpty(jobPath)) { throw new VfxBuildException($"인자 {JobArg} <job.json> 이 없다"); }
                jobPath = Path.GetFullPath(jobPath);
                if (!File.Exists(jobPath)) { throw new VfxBuildException($"job.json 이 없다 : {jobPath}"); }
                resultPath = Path.Combine(Path.GetDirectoryName(jobPath), "result.json");
                RunJob(jobPath, result);
            }
            catch (Exception e)
            {
                Debug.LogException(e);
                // 레시피 · job 이 틀린 것(VfxBuildException)과 툴 코드 버그를 rule 로 나눠 Python 쪽이 고칠 자리를 안다.
                string rule = e is VfxBuildException ? "entry.exception" : "entry.bug";
                result.Fail(rule, $"{e.GetType().Name}: {e.Message}");
            }

            int code = 2;
            try
            {
                if (resultPath != null) { result.Save(resultPath); }
                code = result.ExitCode();
            }
            catch (Exception e)
            {
                Debug.LogException(e);
            }
            Debug.Log(LogHead + $"status={result.Status} issues={result.Issues.Count} frames={result.Frames.Count} exit={code} result={resultPath}");
            EditorApplication.Exit(code);
        }

        // 빈 씬에서 조립 → (build) 프리팹 저장 → (render) 프레임 뽑기 → 루트 지우기.
        private static void RunJob(string jobPath, VfxResult result)
        {
            VfxJob job = VfxJob.Load(jobPath);
            if (string.IsNullOrEmpty(job.Recipe) || !File.Exists(job.Recipe))
            {
                throw new VfxBuildException($"job.recipe 파일이 없다 : {job.Recipe}");
            }
            if (!job.WantsPrefab && !job.WantsRender) { throw new VfxBuildException($"job.mode 를 모른다 : {job.Mode}"); }

            // 한 번만 읽는다. 해시와 파싱이 같은 바이트를 본다(두 번 읽으면 사이에 바뀔 수 있다).
            byte[] bytes = File.ReadAllBytes(job.Recipe);
            string json = new UTF8Encoding(false).GetString(bytes);
            if (json.Length > 0 && json[0] == '\uFEFF') { json = json.Substring(1); }
            result.Unity = Application.unityVersion;
            result.GraphicsDevice = SystemInfo.graphicsDeviceType.ToString();
            result.RecipeSha256 = Sha256(bytes);
            VfxRecipe recipe = VfxRecipe.Parse(json);
            Debug.Log(LogHead + $"job={jobPath} mode={job.Mode} recipe={recipe.Name} layers={recipe.Layers.Count}");

            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var watch = Stopwatch.StartNew();
            GameObject root = null;
            try
            {
                root = VfxBuilder.Build(recipe, job, result);
                if (job.WantsPrefab) { VfxBuilder.SavePrefab(root, recipe, json, job, result); }
                result.Seconds["build"] = Math.Round(watch.Elapsed.TotalSeconds, 3);

                if (job.WantsRender)
                {
                    watch.Restart();
                    VfxRenderer.Render(root, recipe, job, result);
                    result.Seconds["render"] = Math.Round(watch.Elapsed.TotalSeconds, 3);
                }
            }
            finally { VfxBuilder.Dispose(root); }
        }

        private static string ReadArg(string key)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == key) { return args[i + 1]; }
            }
            return null;
        }

        private static string Sha256(byte[] bytes)
        {
            using (var sha = SHA256.Create())
            {
                return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
            }
        }
    }
}
