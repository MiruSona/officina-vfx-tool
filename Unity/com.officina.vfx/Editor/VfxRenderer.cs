using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.Rendering.Universal;

namespace Officina.Vfx.Editor
{
    // 조립된 이펙트를 프레임 PNG 로 뽑는다 (설계 5-2 · 실측 ①~④).
    // 정사영 카메라 · 후처리 끔 · 투명 배경 · 프레임마다 Simulate(t, restart) · 흑백 짝은 옵션.
    public static class VfxRenderer
    {
        private static readonly Color Transparent = new Color(0f, 0f, 0f, 0f);

        public static void Render(GameObject root, VfxRecipe recipe, VfxJob job, VfxResult result)
        {
            string project = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            string outDir = VfxOutDir.Resolve(job.OutDir, project);
            Directory.CreateDirectory(outDir);
            List<VfxJobFrame> frames = job.Frames;
            if (frames == null || frames.Count == 0)
            {
                frames = VfxFrameTimes.Compute(recipe);
                int required = VfxFrameTimes.RequiredCount(recipe);
                if (required > VfxFrameTimes.MaxFrames)
                {
                    result.Issue("render.frames_capped", null, $"프레임 {required} 장 중 {VfxFrameTimes.MaxFrames} 장만 뽑음");
                }
            }

            ParticleSystem[] systems = root.GetComponentsInChildren<ParticleSystem>();
            Vector2Int size = VfxFrameTimes.PixelSize(recipe);
            bool black = job.Backgrounds.Contains("black");
            bool white = job.Backgrounds.Contains("white");
            float previousStep = Time.fixedDeltaTime;
            Camera camera = null;
            GameObject light = null;
            try
            {
                // fixedTimeStep 판은 Time.fixedDeltaTime 걸음으로 돈다. 프로젝트 설정 대신 레시피 값을 쓴다.
                if (recipe.FixedDeltaTime > 0f) { Time.fixedDeltaTime = recipe.FixedDeltaTime; }
                result.FixedDeltaTime = Time.fixedDeltaTime;
                camera = CreateCamera(recipe);
                if (recipe.Light == "global") { light = CreateGlobalLight(); }
                using (var capture = new VfxCapture(size))
                {
                    foreach (VfxJobFrame frame in frames)
                    {
                        int particles = Simulate(systems, frame.T, recipe.FixedTimeStep);
                        string png = VfxFrameTimes.FileName(frame.I, "");
                        result.RenderApi = Shoot(capture, camera, Transparent, Path.Combine(outDir, png));
                        if (black) { Shoot(capture, camera, Color.black, Path.Combine(outDir, VfxFrameTimes.FileName(frame.I, "_k"))); }
                        if (white) { Shoot(capture, camera, Color.white, Path.Combine(outDir, VfxFrameTimes.FileName(frame.I, "_w"))); }
                        result.Frames.Add(new VfxFrameResult { I = frame.I, T = frame.T, Png = png, Particles = particles });
                    }
                }
                // t<=0 프레임이 하나도 없으면 「0초는 건너뛰었다」. 받은 frames 에 0초가 있으면 거짓이다.
                result.T0Skipped = !frames.Any(f => f.T <= 0f);
            }
            finally
            {
                Time.fixedDeltaTime = previousStep;
                if (camera != null) { Object.DestroyImmediate(camera.gameObject); }
                if (light != null) { Object.DestroyImmediate(light); }
            }
        }

        // 절대 시각 t 까지 처음부터 다시 돌린다. seed 는 Build 가 넣은 randomSeed 그대로라 같은 그림이 나온다(실측 ④).
        private static int Simulate(ParticleSystem[] systems, float t, bool fixedTimeStep)
        {
            int particles = 0;
            foreach (ParticleSystem ps in systems)
            {
                ps.Simulate(t, false, true, fixedTimeStep);
                particles += ps.particleCount;
            }
            return particles;
        }

        private static string Shoot(VfxCapture capture, Camera camera, Color background, string path)
        {
            camera.backgroundColor = background;
            return capture.Grab(camera, path);
        }

        // 원점에 텍셀 격자를 맞춘 정사영 카메라. 후처리 · MSAA 끔(후처리가 켜지면 알파가 죽는다, 실측 ③). HDR 은 안 건드린다.
        private static Camera CreateCamera(VfxRecipe recipe)
        {
            var go = new GameObject("VfxCaptureCamera");
            go.transform.position = new Vector3(0f, 0f, -10f);
            var camera = go.AddComponent<Camera>();
            camera.orthographic = true;
            camera.orthographicSize = VfxFrameTimes.OrthoSize(recipe);
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = Transparent;
            camera.allowMSAA = false;

            UniversalAdditionalCameraData data = camera.GetUniversalAdditionalCameraData();
            data.renderPostProcessing = false;
            data.antialiasing = AntialiasingMode.None;
            return camera;
        }

        // lit 층 판정용 흰 Global Light2D 하나 (실측 D). 모든 정렬 층을 비춘다.
        private static GameObject CreateGlobalLight()
        {
            var go = new GameObject("VfxGlobalLight");
            var light = go.AddComponent<Light2D>();
            light.lightType = Light2D.LightType.Global;
            light.color = Color.white;
            light.intensity = 1f;
            light.targetSortingLayers = SortingLayer.layers.Select(x => x.id).ToArray();
            return go;
        }
    }
}
